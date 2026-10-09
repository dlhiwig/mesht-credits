"""Local mesh envelope, signed receipts, and lossy delivery. No radios."""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass, field

from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey, VerifyKey

from ledger import Ledger


def canonical_envelope(env: dict) -> bytes:
    body = {
        "version": env["version"],
        "msg_id": env["msg_id"],
        "sender": env["sender"],
        "kind": env["kind"],
        "payload": env["payload"],
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def seal(sk: SigningKey, sender: str, kind: str, payload: dict) -> dict:
    env = {
        "version": 1,
        "msg_id": str(uuid.uuid4()),
        "sender": sender,
        "kind": kind,
        "payload": payload,
    }
    env["signature"] = Base64Encoder.encode(sk.sign(canonical_envelope(env)).signature).decode("ascii")
    return env


def open_envelope(env: dict, public_key_b64: str) -> dict:
    vk = VerifyKey(public_key_b64, encoder=Base64Encoder)
    vk.verify(canonical_envelope(env), Base64Encoder.decode(env["signature"]))
    return env


def sign_receipt(sk: SigningKey, msg_id: str, tx_hash: str, status: str) -> dict:
    body = {"version": 1, "msg_id": msg_id, "tx_hash": tx_hash, "status": status}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    body["signature"] = Base64Encoder.encode(sk.sign(raw).signature).decode("ascii")
    return body


def verify_receipt(receipt: dict, public_key_b64: str) -> bool:
    body = {k: receipt[k] for k in ("version", "msg_id", "tx_hash", "status")}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    vk = VerifyKey(public_key_b64, encoder=Base64Encoder)
    vk.verify(raw, Base64Encoder.decode(receipt["signature"]))
    return True


@dataclass
class LocalMesh:
    """In-process delivery with drop, duplicate, reorder, and retry."""

    ledger: Ledger
    keys: dict[str, str]
    operator_key: SigningKey | None = None
    drop_rate: float = 0.0
    dup_rate: float = 0.0
    rng: random.Random = field(default_factory=random.Random)
    seen: set[str] = field(default_factory=set)
    applied: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    receipts: list[dict] = field(default_factory=list)

    def deliver(self, env: dict) -> str:
        open_envelope(env, self.keys[env["sender"]])
        if env["msg_id"] in self.seen:
            return "duplicate"
        if self.rng.random() < self.drop_rate:
            self.dropped.append(env["msg_id"])
            return "dropped"
        self.seen.add(env["msg_id"])
        if env["kind"] != "transfer":
            raise ValueError(f"unsupported kind {env['kind']}")
        result = self.ledger.submit(env["payload"])
        self.applied.append(env["msg_id"])
        if self.operator_key is not None:
            self.receipts.append(sign_receipt(self.operator_key, env["msg_id"], result["tx_hash"], "applied"))
        if self.rng.random() < self.dup_rate:
            return self.deliver(env)
        return "applied"

    def deliver_with_retry(self, env: dict, attempts: int = 5) -> str:
        last = "dropped"
        for _ in range(attempts):
            last = self.deliver(env)
            if last in ("applied", "duplicate"):
                return last
        return last

    def deliver_many(self, envelopes: list[dict], reorder: bool = False, retry: bool = False) -> list[str]:
        batch = list(envelopes)
        if reorder:
            self.rng.shuffle(batch)
        if retry:
            return [self.deliver_with_retry(env) for env in batch]
        return [self.deliver(env) for env in batch]
