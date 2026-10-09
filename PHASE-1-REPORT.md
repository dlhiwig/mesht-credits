# Phase 1 Report

**Date:** 2026-10-09
**Status:** Complete for the Python node. Not a hardware or legal release.

Python on `main` is the only authoritative ledger. Rust PR #1 remains a draft reference.

## Evidence

| Exit criterion | Result |
|---|---|
| Canonical ledger documented | README names Python |
| Governance replay matches cache | `test_phases.py` |
| Freeze checked inside the transfer transaction | `test_phase12.py` second connection |
| Journal mutation rejected | `test_phases.py` append-only trigger |
| External checkpoint verifies and rejects tamper | `test_phase12.py` |
| Uncommitted write does not survive reopen | `test_phase12.py` |
| CI runs milestone, phase, and phase12 tests | `.github/workflows/python.yml` |

## Residual

Disk-level power loss during `fsync` is not injected. The crash test rolls back an uncommitted transaction and reopens the file. A replaced database file is still only caught if a second copy of the checkpoint is retained.
