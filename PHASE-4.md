# Phase 4 — Operator release

**Status:** Shipped as a local operator node. Not a public currency release.

## What shipped

- `mesht_cli.py` — keygen, enroll, transfer, freeze, reconcile.
- `.github/workflows/python.yml` — installs `pynacl` and runs `test_milestone.py` and `test_phases.py` on `main` and pull requests.
- Python remains the only authoritative ledger. Rust PR #1 is still a draft reference.

## How to run

```bash
pip install -r requirements.txt
python3 test_milestone.py
python3 test_phases.py
python3 mesht_cli.py --db mesht.db reconcile
```

## Out the door means

A co-op operator can run one SQLite node, enroll members, accept signed transfers, freeze an account, export a checkpoint, and reject a rewritten journal. It does not mean hardware, internet-facing service, cash-out, or production custody of value.

## Still deferred

- Meshtastic radio integration.
- Rust replacement of this node.
- Issuance.
- Legal sign-off of the bylaws against this ledger.
