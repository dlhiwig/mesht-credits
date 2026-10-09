"""Radio-port simulator. Same envelopes as mesh.py. No LoRa device."""

from __future__ import annotations

from nacl.signing import SigningKey

from ledger import Ledger
from mesh import LocalMesh, seal


class RadioPort:
    """Stand-in for a Meshtastic serial port. Drops packets, then retries."""

    def __init__(self, ledger: Ledger, keys: dict[str, str], operator: SigningKey, drop_rate: float = 0.5):
        self.mesh = LocalMesh(ledger, keys, operator_key=operator, drop_rate=drop_rate)
        self.powered = True

    def power_cut(self) -> None:
        self.powered = False
        self.mesh.ledger.close()

    def send(self, sk: SigningKey, sender: str, payload: dict, attempts: int = 8) -> str:
        if not self.powered:
            raise RuntimeError("radio port is powered off")
        env = seal(sk, sender, "transfer", payload)
        return self.mesh.deliver_with_retry(env, attempts=attempts)
