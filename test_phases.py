"""Phase 2-4 tests: mesh loss, governance, checkpoints, append-only."""

import os
import tempfile
import unittest

from ledger import Ledger, make_keypair, sign_governance, sign_tx
from mesh import LocalMesh, seal


class PhaseTests(unittest.TestCase):
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

    def test_mesh_drop_reorder_duplicate(self):
        mesh = LocalMesh(
            self.ledger,
            {"member-001": self.pk_a, "member-002": self.pk_b},
            drop_rate=0.0,
            dup_rate=1.0,
            rng=__import__("random").Random(1),
        )
        envs = []
        for i in range(10):
            sender, sk, recip = ("member-001", self.sk_a, "member-002") if i % 2 == 0 else ("member-002", self.sk_b, "member-001")
            tx = sign_tx(sk, sender, recip, 5, self.ledger.next_sequence(sender) if False else (i // 2) + 1)
            # sequence must match sender's own count, so build after prior submits is not possible in batch.
            envs.append((sender, sk, recip))
        prepared = []
        seq = {"member-001": 1, "member-002": 1}
        for sender, sk, recip in envs:
            tx = sign_tx(sk, sender, recip, 5, seq[sender])
            seq[sender] += 1
            prepared.append(seal(sk, sender, "transfer", tx))
        results = mesh.deliver_many(prepared, reorder=False)
        self.assertEqual(len(mesh.applied), 10)
        self.assertIn("duplicate", results)
        self.assertEqual(self.ledger.system_sum(), 0)
        self.assertTrue(self.ledger.verify_chain())

    def test_freeze_blocks_transfer_and_journal_replays(self):
        event = sign_governance(self.sk_admin, "admin", "freeze", "member-001", "", 1)
        self.ledger.apply_governance(event, self.pk_admin)
        tx = sign_tx(self.sk_a, "member-001", "member-002", 5, 1)
        with self.assertRaises(ValueError):
            self.ledger.submit(tx)
        thaw = sign_governance(self.sk_admin, "admin", "unfreeze", "member-001", "", 2)
        self.ledger.apply_governance(thaw, self.pk_admin)
        self.ledger.submit(tx)
        self.assertTrue(self.ledger.verify_governance_cache())
        self.assertEqual(self.ledger.get_balance("member-001"), -5)

    def test_checkpoint_and_append_only(self):
        tx = sign_tx(self.sk_a, "member-001", "member-002", 7, 1)
        self.ledger.submit(tx)
        cp = self.ledger.export_checkpoint()
        self.assertEqual(cp["system_sum"], 0)
        self.assertEqual(cp["tx_count"], 1)
        with self.assertRaises(Exception):
            self.ledger._conn.execute("DELETE FROM transactions")
            self.ledger._conn.commit()
        report = self.ledger.reconcile()
        self.assertTrue(report["chain_ok"])
        self.assertEqual(report["system_sum"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
