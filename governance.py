"""Signed, hash-chained administrative events for the Python ledger prototype.

Bootstrap requires a trusted local operator to register the administrator key.
Administrative events are signed by that key; the private key is never stored in SQLite.
"""
import base64
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from ledger import Ledger

SCHEMA = """
CREATE TABLE IF NOT EXISTS governance_admins (
    admin_id TEXT PRIMARY KEY, public_key TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS governance_events (
    ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    admin_id TEXT NOT NULL,
    action TEXT NOT NULL,
    member_id TEXT NOT NULL,
    value TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    signature TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS member_freezes (
    member_id TEXT PRIMARY KEY,
    frozen INTEGER NOT NULL CHECK(frozen IN (0,1))
);
"""

def payload(event):
    return json.dumps({k: event[k] for k in
        ("event_id", "admin_id", "action", "member_id", "value", "timestamp")},
        sort_keys=True, separators=(",", ":")).encode()

def sign_event(sk, admin_id, action, member_id, value):
    event = dict(event_id=str(uuid.uuid4()), admin_id=admin_id, action=action,
                 member_id=member_id, value=str(value),
                 timestamp=datetime.now(timezone.utc).isoformat())
    event["signature"] = base64.b64encode(sk.sign(payload(event)).signature).decode()
    return event

class GovernedLedger(Ledger):
    def __post_init__(self):
        super().__post_init__()
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def bootstrap_admin(self, admin_id, public_key_b64):
        """One-time local bootstrap. Protect database filesystem permissions."""
        if self._conn.execute("SELECT COUNT(*) FROM governance_admins").fetchone()[0]:
            raise ValueError("admin already bootstrapped")
        VerifyKey(base64.b64decode(public_key_b64, validate=True))
        with self._conn:
            self._conn.execute("INSERT INTO governance_admins VALUES (?,?)",
                               (admin_id, public_key_b64))

    def admin_apply(self, event):
        if event["action"] not in ("enroll", "limit", "freeze", "unfreeze"):
            raise ValueError("unknown governance action")
        admin = self._conn.execute("SELECT public_key FROM governance_admins WHERE admin_id=?",
                                   (event["admin_id"],)).fetchone()
        if admin is None:
            raise ValueError("unauthorized administrator")
        try:
            VerifyKey(base64.b64decode(admin["public_key"])).verify(
                payload(event), base64.b64decode(event["signature"], validate=True))
        except (ValueError, BadSignatureError) as exc:
            raise ValueError("invalid admin signature") from exc
        member = event["member_id"]
        value = event["value"]
        action = event["action"]
        if not member:
            raise ValueError("empty member")
        if action == "enroll":
            # value: base64-public-key,credit-limit
            pk, limit_text = value.split(",", 1)
            VerifyKey(base64.b64decode(pk, validate=True))
            limit = int(limit_text)
            if limit < 0:
                raise ValueError("negative credit limit")
        elif action == "limit":
            limit = int(value)
            if limit < 0 or self.get_balance(member) < -limit:
                raise ValueError("limit below outstanding obligation")
        else:
            if value != "":
                raise ValueError("freeze/unfreeze value must be empty")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            if self._conn.execute("SELECT 1 FROM governance_events WHERE event_id=?",
                                  (event["event_id"],)).fetchone():
                raise ValueError("duplicate governance event")
            prev = self._conn.execute(
                "SELECT event_hash FROM governance_events ORDER BY ordinal DESC LIMIT 1"
            ).fetchone()
            prev_hash = prev[0] if prev else "0" * 64
            digest = hashlib.sha256(prev_hash.encode() + payload(event) +
                                    event["signature"].encode()).hexdigest()
            if action == "enroll":
                self._conn.execute("INSERT INTO members(member_id,public_key,credit_limit,created_at) VALUES (?,?,?,?)",
                                   (member, pk, limit, event["timestamp"]))
                self._conn.execute("INSERT INTO balances(member_id,balance) VALUES (?,0)", (member,))
                self._conn.execute("INSERT INTO member_freezes VALUES (?,0)", (member,))
            elif action == "limit":
                cursor = self._conn.execute("UPDATE members SET credit_limit=? WHERE member_id=?",
                                            (limit, member))
                if not cursor.rowcount:
                    raise ValueError("unknown member")
            else:
                if not self._conn.execute("SELECT 1 FROM members WHERE member_id=?", (member,)).fetchone():
                    raise ValueError("unknown member")
                self._conn.execute("INSERT INTO member_freezes VALUES (?,?) ON CONFLICT(member_id) DO UPDATE SET frozen=excluded.frozen",
                                   (member, 1 if action == "freeze" else 0))
            self._conn.execute("""INSERT INTO governance_events
                (event_id,admin_id,action,member_id,value,timestamp,signature,prev_hash,event_hash)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (event["event_id"], event["admin_id"], action, member, value,
                 event["timestamp"], event["signature"], prev_hash, digest))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return digest

    def submit(self, tx):
        # Preflight only: this does not protect against concurrent database writers.
        row = self._conn.execute("SELECT frozen FROM member_freezes WHERE member_id=?",
                                 (tx["sender"],)).fetchone()
        if row is not None and row[0]:
            raise ValueError("sender frozen")
        return super().submit(tx)

    def verify_governance(self):
        prev = "0" * 64
        rows = self._conn.execute("SELECT * FROM governance_events ORDER BY ordinal").fetchall()
        for row in rows:
            event = dict(row)
            admin = self._conn.execute("SELECT public_key FROM governance_admins WHERE admin_id=?",
                                       (event["admin_id"],)).fetchone()
            if admin is None or event["prev_hash"] != prev:
                return False
            try:
                VerifyKey(base64.b64decode(admin[0])).verify(
                    payload(event), base64.b64decode(event["signature"]))
            except (ValueError, BadSignatureError):
                return False
            digest = hashlib.sha256(prev.encode() + payload(event) +
                                    event["signature"].encode()).hexdigest()
            if digest != event["event_hash"]:
                return False
            prev = digest
        return True
