# Phase 1 Report (draft)

**Repository:** [dlhiwig/mesht-credits](https://github.com/dlhiwig/mesht-credits)  
**Date:** 2026-10-09  
**`main` at drafting:** `ff4c34e`  
**Plan:** [PHASE-1-PLAN.md](PHASE-1-PLAN.md)  
**Baseline:** [PHASE-ZERO.md](PHASE-ZERO.md)  
**Status:** Draft. Phase 1 has not been implemented. This report records the risk judgment and the planned close-out. It is not a completion report.

## Bottom line

The simulation milestone is met on two cores. The integrity milestone is not met on either. Phase 1 exists to close that gap on one core.

Recommendation in the plan: Python on `main` remains authoritative. Draft PR #2 is the governance source to reconcile. Draft PR #1 stays a Rust reference and is not merged beside Python.

## Risk determination

Each open gap was scored by what a 20–50 member co-op would actually lose: a wrong balance, an unprovable limit, or two histories that cannot be reconciled. Detection after the fact is not the same as prevention.

### 1. Dual ledger — high

PR #1 (Rust) and PR #2 (Python governance) are both open drafts. `main` already has the Python transfer core. If both land, signature bytes, sequence rules, or hash inputs can drift. The co-op then has two “authoritative” files and no rule for which one wins.

Risk if ignored: a transfer accepted on one node and rejected on the other, with no common replay.  
Phase 1 control: one core. The unused PR is explicitly non-authoritative.

### 2. Freeze race — high

PR #2 checks a freeze flag, then applies a transfer. Those are not yet one atomic decision under two writers. A member can be frozen in the journal and still debit.

Risk if ignored: a freeze does not mean what the co-op thinks it means. Disputes become arguments about timing.  
Phase 1 control: one SQLite transaction, plus a two-connection test that must fail closed.

### 3. Governance cache vs journal — high

Limits and freezes can sit in mutable tables. The signed journal is not yet a complete rebuild source. After a restore, a bug, or a hand edit, the table can disagree with the events members signed.

Risk if ignored: a member is held to a limit they did not accept, or a freeze is lifted with no event.  
Phase 1 control: replay the journal and require an exact match before the node serves transfers.

### 4. No external checkpoint — high

The hash chain lives in the same database as the rows it chains. Replacing the file replaces the chain. Signatures still show who authorized each surviving transaction; they do not show that transactions were removed.

Risk if ignored: silent history edits are visible only if someone kept an older copy, and today nothing asks them to.  
Phase 1 control: export a checkpoint a second machine can retain and verify. This detects replacement. It does not by itself stop the operator from holding the only node.

### 5. Append-only not enforced — high

Application code appends. The database user can still update or delete. A bug or a local script can rewrite a row and leave balances looking consistent if the cache is updated too.

Risk if ignored: the “append-only ledger” claim is false under the same credentials that run the node.  
Phase 1 control: database-level rejection of journal updates and deletes, with tests that attempt both.

### 6. Power-loss coverage — medium

The current interrupted-write test inserts a bad row and expects `verify_chain()` to fail. That shows detection of an inconsistent file. It does not show that a crash during `COMMIT` reopens without a split between log and balances.

Risk if ignored: a power cut on the ledger node produces a file that looks openable and is wrong.  
Phase 1 control: interrupt a commit, reopen, and require clean rollback or a refused ledger. Severity is medium because SQLite WAL plus a full transaction already reduces this, but it is not proven here.

### 7. No CI on `main` — medium

Rust CI on PR #1 is green. Python tests were run locally and are not gated. The next push to `main` can break the milestone with no signal.

Risk if ignored: regressions land in the branch the plan calls canonical.  
Phase 1 control: Actions on the Python suite.

## What this draft does not claim

- No Phase 1 code has been merged for these controls.
- Freeze atomicity, journal rebuild, checkpoints, append-only triggers, and crash injection are still open.
- Meshtastic is still deferred.
- The node remains a trusted operator plus retained checkpoints, not a distributed ledger.

## Phase 1 exit, restated

Phase 1 can be reported complete only when `main` has one Python ledger, journal replay, atomic freeze, rejected journal mutation, an external checkpoint, passing crash and concurrency tests, and green CI. This draft marks the start of that work, not the end.
