"""Phase Two transport regression tests: reordering, retries and identity binding."""
import random
import tempfile
import unittest
from pathlib import Path

from ledger import Ledger, make_keypair, sign_tx
from mesh import LocalMesh, seal


class TransportHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(str(Path(self.temp.name) / "test.db"))
        self.a_sk, self.a_pk = make_keypair()
        self.b_sk, self.b_pk = make_keypair()
        self.ledger.enroll("a", self.a_pk, 100)
        self.ledger.enroll("b", self.b_pk, 100)
        self.mesh = LocalMesh(self.ledger, {"a": self.a_pk, "b": self.b_pk},
                              rng=random.Random(3))

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def test_out_of_order_can_retry_same_envelope(self):
        first = seal(self.a_sk, "a", "transfer", sign_tx(self.a_sk, "a", "b", 7, 1))
        second = seal(self.a_sk, "a", "transfer", sign_tx(self.a_sk, "a", "b", 9, 2))
        with self.assertRaises(ValueError):
            self.mesh.deliver(second)
        self.assertNotIn(second["msg_id"], self.mesh.seen)
        self.assertEqual(self.mesh.deliver(first), "applied")
        self.assertEqual(self.mesh.deliver(second), "applied")
        self.assertEqual(self.mesh.deliver(second), "duplicate")
        self.assertEqual(self.ledger.get_balance("a"), -16)
        self.assertTrue(self.ledger.verify_chain())

    def test_reject_sender_mismatch_without_spend(self):
        tx = sign_tx(self.a_sk, "a", "b", 5, 1)
        env = seal(self.b_sk, "b", "transfer", tx)
        with self.assertRaisesRegex(ValueError, "sender mismatch"):
            self.mesh.deliver(env)
        self.assertEqual(self.ledger.system_sum(), 0)
        self.assertEqual(len(self.mesh.applied), 0)

    def test_drop_then_retry_same_envelope(self):
        env = seal(self.a_sk, "a", "transfer", sign_tx(self.a_sk, "a", "b", 3, 1))
        self.mesh.drop_rate = 1.0
        self.assertEqual(self.mesh.deliver(env), "dropped")
        self.mesh.drop_rate = 0.0
        self.assertEqual(self.mesh.deliver(env), "applied")
        self.assertEqual(self.mesh.deliver(env), "duplicate")
        self.assertEqual(self.ledger.get_balance("a"), -3)

    def test_reject_unknown_envelope_version(self):
        env = seal(self.a_sk, "a", "transfer", sign_tx(self.a_sk, "a", "b", 1, 1))
        env["version"] = 99
        with self.assertRaisesRegex(ValueError, "unsupported envelope version"):
            self.mesh.deliver(env)


if __name__ == "__main__":
    unittest.main()
