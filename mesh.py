"""Local mesh envelope and lossy delivery simulator. No radios."""

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


@dataclass
class LocalMesh:
    """In-process delivery with drop, duplicate, and reorder. Ledger accepts once."""

    ledger: Ledger
    keys: dict[str, str]
    drop_rate: float = 0.0
    dup_rate: float = 0.0
    rng: random.Random = field(default_factory=random.Random)
    seen: set[str] = field(default_factory=set)
    applied: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)

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
        self.ledger.submit(env["payload"])
        self.applied.append(env["msg_id"])
        if self.rng.random() < self.dup_rate:
            return self.deliver(env)
        return "applied"

    def deliver_many(self, envelopes: list[dict], reorder: bool = False) -> list[str]:
        batch = list(envelopes)
        if reorder:
            self.rng.shuffle(batch)
        return [self.deliver(env) for env in batch]
