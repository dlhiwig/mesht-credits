"""
First milestone test: two members, 100 authenticated transactions,
including duplicates, limit violations, interrupted-write simulation,
and recovery. Zero accounting discrepancies.
"""

import os
import tempfile
import unittest

from ledger import Ledger, make_keypair, sign_tx


class MilestoneTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db = os.path.join(self.tmpdir, "ledger.db")
        self.ledger = Ledger(self.db)

        self.sk_a, pk_a = make_keypair()
        self.sk_b, pk_b = make_keypair()
        self.ledger.enroll("member-001", pk_a, credit_limit=10_000)
        self.ledger.enroll("member-002", pk_b, credit_limit=10_000)

    def tearDown(self):
        self.ledger.close()

    def test_100_transactions_and_edge_cases(self):
        # 100 alternating transfers
        for i in range(100):
            sender, sk, recip = (
                ("member-001", self.sk_a, "member-002")
                if i % 2 == 0
                else ("member-002", self.sk_b, "member-001")
            )
            seq = self.ledger.next_sequence(sender)
            tx = sign_tx(sk, sender, recip, amount=10, sequence=seq)
            result = self.ledger.submit(tx)
            self.assertIn("tx_hash", result)

        self.assertEqual(self.ledger.system_sum(), 0)
        self.assertTrue(self.ledger.verify_chain())

        # duplicate submission must be rejected
        seq_a = self.ledger.next_sequence("member-001")
        tx = sign_tx(self.sk_a, "member-001", "member-002", amount=5, sequence=seq_a)
        self.ledger.submit(tx)
        with self.assertRaises(ValueError):
            self.ledger.submit(tx)  # same tx_id + sequence

        # insufficient credit
        # drain member-001 beyond limit
        bal = self.ledger.get_balance("member-001")
        limit = self.ledger.get_credit_limit("member-001")
        over = bal + limit + 1
        seq = self.ledger.next_sequence("member-001")
        bad = sign_tx(self.sk_a, "member-001", "member-002", amount=over, sequence=seq)
        with self.assertRaises(ValueError):
            self.ledger.submit(bad)

        # recovery: close and reopen the same file
        self.ledger.close()
        recovered = Ledger(self.db)
        self.assertEqual(recovered.system_sum(), 0)
        self.assertTrue(recovered.verify_chain())
        recovered.close()

    def test_interrupted_write_simulation(self):
        """
        Simulate a partial write by injecting a raw row without updating balances,
        then confirm verify_chain detects the inconsistency.
        """
        seq = self.ledger.next_sequence("member-001")
        tx = sign_tx(self.sk_a, "member-001", "member-002", amount=25, sequence=seq)
        self.ledger.submit(tx)
        self.assertTrue(self.ledger.verify_chain())

        # corrupt: manually insert an orphan row that doesn't update balances
        from ledger import canonical_payload, compute_tx_hash
        fake = sign_tx(self.sk_b, "member-002", "member-001", amount=999, sequence=999)
        prev = self.ledger._last_hash()
        fake_hash = compute_tx_hash(fake, prev)
        self.ledger._conn.execute(
            """INSERT INTO transactions
               (tx_id, sender, recipient, amount, currency, sequence, timestamp,
                signature, prev_hash, tx_hash, applied_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fake["tx_id"], fake["sender"], fake["recipient"], fake["amount"],
                fake["currency"], fake["sequence"], fake["timestamp"],
                fake["signature"], prev, fake_hash, "2026-01-01T00:00:00Z",
            ),
        )
        self.ledger._conn.commit()
        self.assertFalse(self.ledger.verify_chain())


if __name__ == "__main__":
    unittest.main(verbosity=2)
