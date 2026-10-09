# Phase 3 — Governance and integrity

**Status:** Implemented on the Python ledger on `main`.

This phase closes the Phase 1 integrity gate on the canonical Python core.

## What shipped

- Signed governance events for limit, freeze, and unfreeze, with admin sequence numbers and a hash chain.
- Freeze is checked before a transfer is applied. A frozen sender cannot spend. Unfreeze allows the next sequence.
- `verify_governance_cache()` replays the journal and compares limits and freezes to the tables.
- Append-only triggers reject `UPDATE` and `DELETE` on `transactions` and `governance_events`.
- `export_checkpoint()` returns tip hash, transaction count, system sum, member limits, balances, and freezes, plus a checkpoint hash.
- `reconcile()` reports chain, governance cache, checkpoint, and dispute count.
- Disputes reference a `tx_id` and do not rewrite history.

## Tests

- Freeze then unfreeze, then a transfer: `test_freeze_blocks_transfer_and_journal_replays`
- Checkpoint plus rejected delete: `test_checkpoint_and_append_only`
- Existing 100-transfer milestone still passes.

## Residual risk

Triggers stop ordinary SQL mutation. They do not stop someone replacing the database file. The checkpoint is the detection tool for that, and only if a second copy is retained. Crash-during-commit injection is still the weaker test from Phase Zero; SQLite transactions cover the normal commit path.
