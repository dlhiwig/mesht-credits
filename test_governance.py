import base64
import tempfile
import unittest
from pathlib import Path
from governance import GovernedLedger, sign_event
from ledger import make_keypair, sign_tx

class GovernanceTests(unittest.TestCase):
    def test_signed_controls_and_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "ledger.sqlite")
            db = GovernedLedger(path)
            admin_sk, admin_pk = make_keypair()
            alice_sk, alice_pk = make_keypair()
            bob_sk, bob_pk = make_keypair()
            db.bootstrap_admin("board", admin_pk)
            for member, pk in [("alice", alice_pk), ("bob", bob_pk)]:
                db.admin_apply(sign_event(admin_sk, "board", "enroll", member, f"{pk},100"))
            tx = sign_tx(alice_sk, "alice", "bob", 10, 1)
            db.submit(tx)
            freeze = sign_event(admin_sk, "board", "freeze", "alice", "")
            db.admin_apply(freeze)
            with self.assertRaises(ValueError):
                db.admin_apply(freeze)
            with self.assertRaises(ValueError):
                db.submit(sign_tx(alice_sk, "alice", "bob", 1, 2))
            with self.assertRaises(ValueError):
                db.admin_apply(sign_event(admin_sk, "board", "limit", "alice", "5"))
            db.admin_apply(sign_event(admin_sk, "board", "unfreeze", "alice", ""))
            db.admin_apply(sign_event(admin_sk, "board", "limit", "alice", "50"))
            forged, _ = make_keypair()
            with self.assertRaises(ValueError):
                db.admin_apply(sign_event(forged, "board", "freeze", "alice", ""))
            self.assertEqual(db.system_sum(), 0)
            self.assertTrue(db.verify_chain())
            self.assertTrue(db.verify_governance())
            db.close()
            recovered = GovernedLedger(path)
            self.assertTrue(recovered.verify_chain())
            self.assertTrue(recovered.verify_governance())
            recovered.close()

if __name__ == "__main__":
    unittest.main()
