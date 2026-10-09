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
