# Phase 1 Plan

**Repository:** [dlhiwig/mesht-credits](https://github.com/dlhiwig/mesht-credits)  
**Date:** 2026-10-09  
**Depends on:** [PHASE-ZERO.md](PHASE-ZERO.md)  
**Status:** Planned. Not started in code.

Phase 1 closes the integrity gaps that block a single authoritative ledger. It does not add Meshtastic, hardware, issuance, or a second node.

## Canonical choice

Keep the Python ledger on `main` as the Phase 1 core. Port the signed governance work from draft PR #2 onto that core, then add checkpoints and fault tests there.

Why this path:

- Python is already on `main` and already passed the 100-transfer milestone.
- Governance exists only on the Python branch.
- Rust on PR #1 is a useful reference and has CI, but it has no governance journal. Rewriting governance in Rust before the integrity tests exist delays the gate Phase Zero already set.

PR #1 stays a draft. It is not merged as a second core. A later phase can port the proven Python protocol to Rust if a single-binary node is wanted. Protocol compatibility is required before that port replaces Python.

## Open integrity gaps and risks

| Gap | What can go wrong | Severity | Phase 1 response |
|---|---|---|---|
| Two ledger cores | Python and Rust diverge on signature encoding, sequence rules, or balance derivation. A later merge cannot replay the same history. Operators do not know which node is authoritative. | High | One core on `main`. The other PR stays draft and is marked non-authoritative. |
| Freeze not concurrency-safe | A freeze and a transfer interleave. A frozen member still spends. The journal says frozen; the balance says otherwise. | High | Freeze flag and transfer debit commit in one SQLite transaction. Concurrent writers are tested. |
| Governance state not rebuildable | Limits or freezes live only in mutable tables. An admin process, bug, or restored backup can disagree with the signed journal. Members cannot prove which limit applied. | High | Journal is the source. Mutable tables are a cache. A rebuild function replays signed events and must match. |
| No external checkpoint | A hash chain inside the same database cannot detect a rewritten database. Whoever holds the file can replace history and the tip together. | High | Export tip hash, member set, limits, freezes, balances, and transaction count. A second process verifies the export against a retained copy. |
| Append-only not enforced | The writer can `UPDATE` or `DELETE` transactions. Signatures do not stop a local rewrite. | High | Reject updates and deletes on the transaction and governance journals at the database layer. Tests attempt both and expect failure. Verification still recomputes the chain. |
| Power-loss test is synthetic | Inserting a bad row proves detection, not recovery. A crash during commit can leave a torn write or a balance cache ahead of the log. | Medium | Kill or interrupt a commit, reopen, and require either a full commit or a clean rollback. `verify_chain()` and system sum must hold. |
| No CI on `main` | A passing local run is not repeatable. The next commit can break the milestone unnoticed. | Medium | GitHub Actions runs the Python suite on `main` and on pull requests. |

Secondary risks, accepted for Phase 1:

- Single operator still controls the node. Checkpoints detect change; they do not remove that trust.
- SQLite on one disk can still be lost. Checkpoints are not backups of the full log.
- Ed25519 keys can be stolen. Phase 1 does not add key rotation.

## Work packages

1. **Reconcile PR #2 onto a Phase 1 branch from current `main`.** Do not merge PR #1. Comment on both PRs that Python is canonical for this phase.
2. **Journal-first governance.** Enroll, limit, freeze, and unfreeze are signed events. Rebuild member set, limits, and freezes from the journal. Fail if the cache differs.
3. **Atomic freeze.** `submit()` reads the freeze flag inside the same transaction as the debit. Add a two-connection test.
4. **Append-only guards.** Triggers or equivalent reject mutation of journal rows. Test the rejection.
5. **Checkpoint export and verify.** Stable JSON or canonical bytes. Hash the export. A verifier with only the checkpoint file and the database reports match or mismatch.
6. **Crash test.** Interrupt a commit and reopen. Zero discrepancies, or a detected and refused ledger.
7. **CI.** `python3 -m unittest` for milestone, governance, concurrency, checkpoint, and crash tests.
8. **Docs.** Update README with one sentence: Python is the Phase 1 ledger; Meshtastic is not in this phase. Update Phase Zero status only after the exit criteria pass.

## Tests required before exit

- Existing 100-transfer milestone still passes.
- Duplicate `tx_id` and bad sequence still fail.
- Frozen sender cannot transfer; unfreeze allows the next sequence.
- Concurrent freeze and transfer cannot both succeed for the same debit.
- Rebuild-from-journal equals stored members, limits, freezes, and balances.
- `UPDATE` and `DELETE` on journal tables fail.
- Checkpoint verifier accepts a fresh export and rejects a tampered balance or tip.
- Interrupted commit reopens clean.
- System sum remains 0.

## Out of scope

- Meshtastic, LoRa hardware, packet-loss simulator.
- Rust replacement of the Python core.
- Issuance, disputes, Credit Commons nesting, cash-out.
- Multi-node consensus.
- Legal rewrite of the bylaws.

## Exit criteria

Phase 1 is done when all of these are true on `main`:

- Python is documented as the only authoritative ledger.
- Governance replay matches the cache.
- Freeze is atomic with transfer.
- Journal mutation is rejected.
- An external checkpoint verifies.
- Crash and concurrency tests pass.
- CI is green.

Until then this document is the plan, not evidence that the gaps are closed.
