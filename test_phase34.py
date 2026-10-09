"""Phase 3 and 4 software drills. No radios, no live members."""

import os
import tempfile
import unittest

from ledger import Ledger, make_keypair, sign_tx
from nacl.encoding import Base64Encoder
from nacl.signing import SigningKey

from radio_port import RadioPort


def dispute(sk, opener, tx_id, note):
    body = {
        "dispute_id": "dsp-" + tx_id[:8],
        "tx_id": tx_id,
        "opener": opener,
        "note": note,
        "timestamp": "2026-10-09T19:00:00Z",
    }
    import json
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    body["signature"] = Base64Encoder.encode(sk.sign(raw).signature).decode()
    return body


class Phase34(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "pilot.db")
        self.ledger = Ledger(self.db)
        self.keys = {}
        self.pks = {}
        for i in range(1, 6):
            sk, pk = make_keypair()
            mid = f"member-{i:03d}"
            self.keys[mid] = sk
            self.pks[mid] = pk
            self.ledger.enroll(mid, pk, credit_limit=500)

    def tearDown(self):
        if self.ledger:
            try:
                self.ledger.close()
            except Exception:
                pass

    def test_onboarding_and_pilot_dry_run(self):
        pairs = [("member-001", "member-002"), ("member-002", "member-003"), ("member-003", "member-001")]
        seq = {m: 1 for m in self.keys}
        for sender, recip in pairs:
            tx = sign_tx(self.keys[sender], sender, recip, 25, seq[sender])
            seq[sender] += 1
            self.ledger.submit(tx)
        report = self.ledger.reconcile()
        self.assertEqual(report["system_sum"], 0)
        self.assertTrue(report["chain_ok"])

    def test_dispute_does_not_rewrite(self):
        tx = sign_tx(self.keys["member-001"], "member-001", "member-002", 10, 1)
        applied = self.ledger.submit(tx)
        before = self.ledger.get_balance("member-001")
        self.ledger.open_dispute(
            dispute(self.keys["member-001"], "member-001", applied["tx_id"], "tabletop dispute"),
            self.pks["member-001"],
        )
        self.assertEqual(self.ledger.get_balance("member-001"), before)
        self.assertEqual(self.ledger.reconcile()["disputes"], 1)

    def test_radio_port_drop_and_power_cut(self):
        op = SigningKey.generate()
        port = RadioPort(self.ledger, self.pks, op, drop_rate=0.7)
        tx = sign_tx(self.keys["member-004"], "member-004", "member-005", 15, 1)
        status = port.send(self.keys["member-004"], "member-004", tx, attempts=15)
        self.assertIn(status, ("applied", "duplicate"))
        port.power_cut()
        self.ledger = None
        reopened = Ledger(self.db)
        self.assertEqual(reopened.system_sum(), 0)
        self.assertTrue(reopened.verify_chain())
        reopened.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
