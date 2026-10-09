"""Phase 1 integrity and Phase 2 transport tests."""

import os
import tempfile
import threading
import unittest

from ledger import Ledger, make_keypair, sign_governance, sign_tx
from mesh import LocalMesh, seal, verify_receipt
from nacl.signing import SigningKey


class Phase12(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "ledger.db")
        self.ledger = Ledger(self.db)
        self.sk_a, self.pk_a = make_keypair()
        self.sk_b, self.pk_b = make_keypair()
        self.sk_admin, self.pk_admin = make_keypair()
        self.ledger.enroll("member-001", self.pk_a, credit_limit=1000)
        self.ledger.enroll("member-002", self.pk_b, credit_limit=1000)

    def tearDown(self):
        self.ledger.close()

    def test_checkpoint_rejects_tamper(self):
        self.ledger.submit(sign_tx(self.sk_a, "member-001", "member-002", 9, 1))
        cp = self.ledger.export_checkpoint()
        self.assertTrue(self.ledger.verify_checkpoint(cp))
        tampered = dict(cp)
        tampered["members"] = [dict(m) for m in cp["members"]]
        tampered["members"][0]["balance"] = 999
        self.assertFalse(self.ledger.verify_checkpoint(tampered))

    def test_uncommitted_write_does_not_stick(self):
        self.ledger._conn.execute("BEGIN")
        self.ledger._conn.execute(
            "UPDATE balances SET balance = 50 WHERE member_id = ?", ("member-001",)
        )
        self.ledger.close()
        reopened = Ledger(self.db)
        self.assertEqual(reopened.get_balance("member-001"), 0)
        self.assertTrue(reopened.verify_chain())
        reopened.close()

    def test_freeze_blocks_other_connection(self):
        event = sign_governance(self.sk_admin, "admin", "freeze", "member-001", "", 1)
        self.ledger.apply_governance(event, self.pk_admin)
        other = Ledger(self.db)
        with self.assertRaises(ValueError):
            other.submit(sign_tx(self.sk_a, "member-001", "member-002", 4, 1))
        other.close()
        self.assertEqual(self.ledger.system_sum(), 0)

    def test_packet_loss_retry_and_receipt(self):
        op = SigningKey.generate()
        mesh = LocalMesh(
            self.ledger,
            {"member-001": self.pk_a, "member-002": self.pk_b},
            operator_key=op,
            drop_rate=0.8,
            rng=__import__("random").Random(3),
        )
        tx = sign_tx(self.sk_a, "member-001", "member-002", 6, 1)
        env = seal(self.sk_a, "member-001", "transfer", tx)
        status = mesh.deliver_with_retry(env, attempts=20)
        self.assertIn(status, ("applied", "duplicate"))
        self.assertEqual(self.ledger.system_sum(), 0)
        self.assertTrue(mesh.receipts)
        from nacl.encoding import Base64Encoder
        pk = Base64Encoder.encode(op.verify_key.encode()).decode()
        self.assertTrue(verify_receipt(mesh.receipts[0], pk))


if __name__ == "__main__":
    unittest.main(verbosity=2)
