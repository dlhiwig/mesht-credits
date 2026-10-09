"""Operator security and checkpoint CLI regression tests."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class OperatorTests(unittest.TestCase):
    def test_keygen_does_not_print_secret_and_is_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "member.key"
            cmd = [sys.executable, str(ROOT / "mesht_cli.py"), "keygen", "--out", str(key)]
            result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["private_key_file"], str(key))
            self.assertNotIn("private_key_b64", result.stdout)
            self.assertEqual(len(key.read_bytes()), 32)
            if os.name == "posix":
                self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            again = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(len(key.read_bytes()), 32)

    def test_checkpoint_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            db = str(Path(directory) / "ledger.db")
            cp = Path(directory) / "checkpoint.json"
            result = subprocess.run(
                [sys.executable, str(ROOT / "mesht_cli.py"), "--db", db,
                 "checkpoint", "--out", str(cp)],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            body = json.loads(cp.read_text())
            self.assertEqual(body["system_sum"], 0)
            self.assertIn("checkpoint_hash", body)
            self.assertEqual(json.loads(result.stdout)["checkpoint_hash"],
                             body["checkpoint_hash"])


if __name__ == "__main__":
    unittest.main()
