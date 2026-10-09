"""
mesht-credits ledger core

Single-authoritative-node mutual-credit ledger.
Integer units, Ed25519 signatures, append-only SQLite log,
per-member sequence numbers, atomic commits, recovery.

Not for real value. Experimental.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey, VerifyKey


SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    member_id TEXT PRIMARY KEY,
    public_key TEXT NOT NULL UNIQUE,
    credit_limit INTEGER NOT NULL DEFAULT 0,   -- max negative (as positive integer)
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    tx_id TEXT PRIMARY KEY,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'BIC',
    sequence INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    signature TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    tx_hash TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL,
    UNIQUE(sender, sequence)
);

CREATE TABLE IF NOT EXISTS balances (
    member_id TEXT PRIMARY KEY REFERENCES members(member_id),
    balance INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tx_sender_seq ON transactions(sender, sequence);

CREATE TABLE IF NOT EXISTS member_state (
    member_id TEXT PRIMARY KEY REFERENCES members(member_id),
    frozen INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS governance_events (
    event_id TEXT PRIMARY KEY,
    admin_id TEXT NOT NULL,
    action TEXT NOT NULL,
    member_id TEXT NOT NULL,
    value TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    signature TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS disputes (
    dispute_id TEXT PRIMARY KEY,
    tx_id TEXT NOT NULL,
    opener TEXT NOT NULL,
    note TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    signature TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS transactions_no_update
BEFORE UPDATE ON transactions
BEGIN
    SELECT RAISE(ABORT, 'transactions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS transactions_no_delete
BEFORE DELETE ON transactions
BEGIN
    SELECT RAISE(ABORT, 'transactions are append-only');
END;

CREATE TRIGGER IF NOT EXISTS governance_no_update
BEFORE UPDATE ON governance_events
BEGIN
    SELECT RAISE(ABORT, 'governance journal is append-only');
END;

CREATE TRIGGER IF NOT EXISTS governance_no_delete
BEFORE DELETE ON governance_events
BEGIN
    SELECT RAISE(ABORT, 'governance journal is append-only');
END;
"""


def canonical_payload(tx: dict) -> bytes:
    """Deterministic encoding of all fields except signature."""
    fields = {
        "version": tx["version"],
        "tx_id": tx["tx_id"],
        "sender": tx["sender"],
        "recipient": tx["recipient"],
        "amount": tx["amount"],
        "currency": tx["currency"],
        "sequence": tx["sequence"],
        "timestamp": tx["timestamp"],
    }
    return json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_tx_hash(tx: dict, prev_hash: str) -> str:
    data = canonical_payload(tx) + prev_hash.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


@dataclass
class Ledger:
    db_path: str = ":memory:"
    _conn: sqlite3.Connection = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- membership ---

    def enroll(self, member_id: str, public_key_b64: str, credit_limit: int = 0) -> None:
        if credit_limit < 0:
            raise ValueError("credit_limit must be >= 0")
        now = datetime.now(timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                "INSERT INTO members(member_id, public_key, credit_limit, created_at) VALUES (?,?,?,?)",
                (member_id, public_key_b64, credit_limit, now),
            )
            self._conn.execute(
                "INSERT INTO balances(member_id, balance) VALUES (?,0)",
                (member_id,),
            )
            self._conn.execute(
                "INSERT INTO member_state(member_id, frozen) VALUES (?,0)",
                (member_id,),
            )

    def set_credit_limit(self, member_id: str, credit_limit: int) -> None:
        if credit_limit < 0:
            raise ValueError("credit_limit must be >= 0")
        with self._conn:
            cur = self._conn.execute(
                "UPDATE members SET credit_limit = ? WHERE member_id = ?",
                (credit_limit, member_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"unknown member {member_id}")

    def get_balance(self, member_id: str) -> int:
        row = self._conn.execute(
            "SELECT balance FROM balances WHERE member_id = ?", (member_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown member {member_id}")
        return int(row["balance"])

    def get_credit_limit(self, member_id: str) -> int:
        row = self._conn.execute(
            "SELECT credit_limit FROM members WHERE member_id = ?", (member_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown member {member_id}")
        return int(row["credit_limit"])

    def next_sequence(self, member_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS n FROM transactions WHERE sender = ?",
            (member_id,),
        ).fetchone()
        return int(row["n"])

    def _last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT tx_hash FROM transactions ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        return row["tx_hash"] if row else "0" * 64

    # --- transactions ---

    def submit(self, tx: dict) -> dict:
        """
        Verify and apply a signed transaction atomically.
        Returns the stored record on success.
        Raises ValueError on any rejection (duplicate, bad sig, insufficient credit, etc.).
        """
        required = {
            "version", "tx_id", "sender", "recipient", "amount",
            "currency", "sequence", "timestamp", "signature",
        }
        missing = required - tx.keys()
        if missing:
            raise ValueError(f"missing fields: {sorted(missing)}")

        if tx["version"] != 1:
            raise ValueError("unsupported version")
        if not isinstance(tx["amount"], int) or tx["amount"] <= 0:
            raise ValueError("amount must be positive integer")
        if tx["sender"] == tx["recipient"]:
            raise ValueError("self-transfer not allowed")

        # membership
        sender_row = self._conn.execute(
            "SELECT public_key, credit_limit FROM members WHERE member_id = ?",
            (tx["sender"],),
        ).fetchone()
        if sender_row is None:
            raise ValueError(f"unknown sender {tx['sender']}")
        recip_row = self._conn.execute(
            "SELECT 1 FROM members WHERE member_id = ?", (tx["recipient"],)
        ).fetchone()
        if recip_row is None:
            raise ValueError(f"unknown recipient {tx['recipient']}")

        # signature
        try:
            vk = VerifyKey(sender_row["public_key"], encoder=Base64Encoder)
            raw_sig = Base64Encoder.decode(tx["signature"])
            vk.verify(canonical_payload(tx), raw_sig)
        except Exception as e:
            raise ValueError(f"invalid signature: {e}") from e

        # sequence / replay
        expected = self.next_sequence(tx["sender"])
        if tx["sequence"] != expected:
            raise ValueError(f"bad sequence: expected {expected}, got {tx['sequence']}")

        # duplicate tx_id
        if self._conn.execute("SELECT 1 FROM transactions WHERE tx_id = ?", (tx["tx_id"],)).fetchone():
            raise ValueError("duplicate tx_id")

        frozen = self._conn.execute(
            "SELECT frozen FROM member_state WHERE member_id = ?", (tx["sender"],)
        ).fetchone()
        if frozen and int(frozen["frozen"]) == 1:
            raise ValueError(f"sender frozen: {tx['sender']}")

        # credit limit (sender may go negative up to credit_limit)
        sender_bal = self.get_balance(tx["sender"])
        new_sender_bal = sender_bal - tx["amount"]
        if new_sender_bal < -sender_row["credit_limit"]:
            raise ValueError(
                f"insufficient credit: balance {sender_bal}, limit {sender_row['credit_limit']}, amount {tx['amount']}"
            )

        # hash chain
        prev = self._last_hash()
        tx_hash = compute_tx_hash(tx, prev)
        now = datetime.now(timezone.utc).isoformat()

        try:
            with self._conn:
                self._conn.execute(
                    """INSERT INTO transactions
                       (tx_id, sender, recipient, amount, currency, sequence, timestamp,
                        signature, prev_hash, tx_hash, applied_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        tx["tx_id"], tx["sender"], tx["recipient"], tx["amount"],
                        tx["currency"], tx["sequence"], tx["timestamp"],
                        tx["signature"], prev, tx_hash, now,
                    ),
                )
                self._conn.execute(
                    "UPDATE balances SET balance = balance - ? WHERE member_id = ?",
                    (tx["amount"], tx["sender"]),
                )
                self._conn.execute(
                    "UPDATE balances SET balance = balance + ? WHERE member_id = ?",
                    (tx["amount"], tx["recipient"]),
                )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"constraint violation: {e}") from e

        return {
            "tx_id": tx["tx_id"],
            "tx_hash": tx_hash,
            "prev_hash": prev,
            "sender_balance": self.get_balance(tx["sender"]),
            "recipient_balance": self.get_balance(tx["recipient"]),
        }

    # --- integrity ---

    def verify_chain(self) -> bool:
        """Recompute hash chain and confirm balances match the log."""
        rows = self._conn.execute(
            "SELECT * FROM transactions ORDER BY rowid"
        ).fetchall()
        prev = "0" * 64
        derived: dict[str, int] = {}
        for r in rows:
            tx = {
                "version": 1,
                "tx_id": r["tx_id"],
                "sender": r["sender"],
                "recipient": r["recipient"],
                "amount": r["amount"],
                "currency": r["currency"],
                "sequence": r["sequence"],
                "timestamp": r["timestamp"],
            }
            expected = compute_tx_hash(tx, prev)
            if expected != r["tx_hash"] or r["prev_hash"] != prev:
                return False
            prev = r["tx_hash"]
            derived[r["sender"]] = derived.get(r["sender"], 0) - r["amount"]
            derived[r["recipient"]] = derived.get(r["recipient"], 0) + r["amount"]

        # all members should have derived == stored (default 0 if no txs)
        members = self._conn.execute("SELECT member_id FROM members").fetchall()
        for m in members:
            mid = m["member_id"]
            stored = self.get_balance(mid)
            if derived.get(mid, 0) != stored:
                return False
        # zero-sum
        total = sum(self.get_balance(m["member_id"]) for m in members)
        return total == 0

    def system_sum(self) -> int:
        row = self._conn.execute("SELECT COALESCE(SUM(balance), 0) AS s FROM balances").fetchone()
        return int(row["s"])



    def _gov_hash(self, event: dict, prev: str) -> str:
        body = {k: event[k] for k in ("event_id", "admin_id", "action", "member_id", "value", "sequence", "timestamp")}
        data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode() + prev.encode()
        return hashlib.sha256(data).hexdigest()

    def apply_governance(self, event: dict, admin_public_key_b64: str) -> dict:
        required = {"event_id", "admin_id", "action", "member_id", "value", "sequence", "timestamp", "signature"}
        missing = required - event.keys()
        if missing:
            raise ValueError(f"missing fields: {sorted(missing)}")
        if event["action"] not in ("limit", "freeze", "unfreeze"):
            raise ValueError("unsupported governance action")
        body = {k: event[k] for k in ("event_id", "admin_id", "action", "member_id", "value", "sequence", "timestamp")}
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        try:
            vk = VerifyKey(admin_public_key_b64, encoder=Base64Encoder)
            vk.verify(raw, Base64Encoder.decode(event["signature"]))
        except Exception as e:
            raise ValueError(f"invalid governance signature: {e}") from e
        expected = self._conn.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 AS n FROM governance_events WHERE admin_id = ?",
            (event["admin_id"],),
        ).fetchone()["n"]
        if int(event["sequence"]) != int(expected):
            raise ValueError(f"bad governance sequence: expected {expected}")
        member = self._conn.execute(
            "SELECT 1 FROM members WHERE member_id = ?", (event["member_id"],)
        ).fetchone()
        if member is None:
            raise ValueError(f"unknown member {event['member_id']}")
        prev = self._conn.execute(
            "SELECT event_hash FROM governance_events ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        prev_hash = prev["event_hash"] if prev else "0" * 64
        event_hash = self._gov_hash(event, prev_hash)
        with self._conn:
            self._conn.execute(
                """INSERT INTO governance_events
                   (event_id, admin_id, action, member_id, value, sequence, timestamp, signature, prev_hash, event_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    event["event_id"], event["admin_id"], event["action"], event["member_id"],
                    event["value"], event["sequence"], event["timestamp"], event["signature"],
                    prev_hash, event_hash,
                ),
            )
            if event["action"] == "limit":
                limit = int(event["value"])
                if limit < 0:
                    raise ValueError("limit must be >= 0")
                self._conn.execute(
                    "UPDATE members SET credit_limit = ? WHERE member_id = ?",
                    (limit, event["member_id"]),
                )
            else:
                flag = 1 if event["action"] == "freeze" else 0
                self._conn.execute(
                    "UPDATE member_state SET frozen = ? WHERE member_id = ?",
                    (flag, event["member_id"]),
                )
        return {"event_id": event["event_id"], "event_hash": event_hash}

    def open_dispute(self, dispute: dict, opener_public_key_b64: str) -> None:
        body = {k: dispute[k] for k in ("dispute_id", "tx_id", "opener", "note", "timestamp")}
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        vk = VerifyKey(opener_public_key_b64, encoder=Base64Encoder)
        vk.verify(raw, Base64Encoder.decode(dispute["signature"]))
        tx = self._conn.execute("SELECT 1 FROM transactions WHERE tx_id = ?", (dispute["tx_id"],)).fetchone()
        if tx is None:
            raise ValueError("unknown tx_id")
        with self._conn:
            self._conn.execute(
                "INSERT INTO disputes(dispute_id, tx_id, opener, note, timestamp, signature) VALUES (?,?,?,?,?,?)",
                (dispute["dispute_id"], dispute["tx_id"], dispute["opener"], dispute["note"], dispute["timestamp"], dispute["signature"]),
            )

    def replay_governance(self) -> dict:
        limits = {}
        frozen = {}
        prev = "0" * 64
        for row in self._conn.execute("SELECT * FROM governance_events ORDER BY rowid"):
            event = {k: row[k] for k in ("event_id", "admin_id", "action", "member_id", "value", "sequence", "timestamp")}
            if self._gov_hash(event, prev) != row["event_hash"] or row["prev_hash"] != prev:
                raise ValueError("governance chain mismatch")
            prev = row["event_hash"]
            if row["action"] == "limit":
                limits[row["member_id"]] = int(row["value"])
            elif row["action"] == "freeze":
                frozen[row["member_id"]] = 1
            elif row["action"] == "unfreeze":
                frozen[row["member_id"]] = 0
        return {"limits": limits, "frozen": frozen}

    def verify_governance_cache(self) -> bool:
        derived = self.replay_governance()
        for row in self._conn.execute("SELECT member_id, credit_limit FROM members"):
            if row["member_id"] in derived["limits"] and int(row["credit_limit"]) != derived["limits"][row["member_id"]]:
                return False
        for row in self._conn.execute("SELECT member_id, frozen FROM member_state"):
            expected = derived["frozen"].get(row["member_id"], 0)
            if int(row["frozen"]) != expected:
                return False
        return True

    def export_checkpoint(self) -> dict:
        members = []
        for row in self._conn.execute(
            """SELECT m.member_id, m.credit_limit, b.balance, s.frozen
               FROM members m
               JOIN balances b ON b.member_id = m.member_id
               JOIN member_state s ON s.member_id = m.member_id
               ORDER BY m.member_id"""
        ):
            members.append({
                "member_id": row["member_id"],
                "credit_limit": int(row["credit_limit"]),
                "balance": int(row["balance"]),
                "frozen": int(row["frozen"]),
            })
        tip = self._last_hash()
        count = int(self._conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"])
        body = {"tip": tip, "tx_count": count, "system_sum": self.system_sum(), "members": members}
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        body["checkpoint_hash"] = hashlib.sha256(canonical).hexdigest()
        return body

    def reconcile(self) -> dict:
        return {
            "system_sum": self.system_sum(),
            "chain_ok": self.verify_chain(),
            "governance_ok": self.verify_governance_cache(),
            "checkpoint": self.export_checkpoint(),
            "disputes": int(self._conn.execute("SELECT COUNT(*) AS n FROM disputes").fetchone()["n"]),
        }


def sign_governance(sk: SigningKey, admin_id: str, action: str, member_id: str, value: str, sequence: int) -> dict:
    event = {
        "event_id": str(uuid.uuid4()),
        "admin_id": admin_id,
        "action": action,
        "member_id": member_id,
        "value": value,
        "sequence": sequence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    raw = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    event["signature"] = Base64Encoder.encode(sk.sign(raw).signature).decode("ascii")
    return event


def make_keypair() -> tuple[SigningKey, str]:
    sk = SigningKey.generate()
    pk_b64 = sk.verify_key.encode(encoder=Base64Encoder).decode("ascii")
    return sk, pk_b64


def sign_tx(sk: SigningKey, sender: str, recipient: str, amount: int, sequence: int,
            currency: str = "BIC") -> dict:
    tx = {
        "version": 1,
        "tx_id": str(uuid.uuid4()),
        "sender": sender,
        "recipient": recipient,
        "amount": amount,
        "currency": currency,
        "sequence": sequence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # Sign raw payload; store base64 signature
    raw_sig = sk.sign(canonical_payload(tx)).signature
    tx["signature"] = Base64Encoder.encode(raw_sig).decode("ascii")
    return tx
