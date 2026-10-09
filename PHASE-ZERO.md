# Phase Zero Report

**Repository:** [dlhiwig/mesht-credits](https://github.com/dlhiwig/mesht-credits)  
**Report date:** 2026-10-09  
**`main` tip:** `c93cb0e` — Python ledger core and rewritten README  
**Status:** Design settled. Two ledger cores exist. Neither draft is merged. Not production-ready.

Phase Zero is the work before radios, hardware, or live members: name the system, fix the accounting model, prove a single authoritative ledger can accept authenticated transfers without discrepancies, and record what is still open.

## Decision

`mesht-credits` is a closed-loop mutual-credit ledger for a 20–50 member cooperative. Meshtastic is the transport. The ledger is a separate, auditable accounting system. Credits are not convertible to USD, crypto, or external value.

The first release keeps one authoritative ledger node. Distributed sync is out of scope until the single-node core is boring.

## Architecture

| Layer | Responsibility | Phase Zero status |
|---|---|---|
| Mesh transport | Delivery, retries, offline reach | Specified only. No Meshtastic integration. |
| Ledger core | Integer units, Ed25519 signatures, sequence numbers, replay protection, atomic commits, hash chain | Implemented twice: Python on `main`, Rust on draft PR #1. |
| Co-op governance | Enrollment, limits, freezes, disputes, reconciliation | Partial Python prototype on draft PR #2. Issuance deferred. |

### Accounting rules

1. Transfers are zero-sum: one member is debited and another is credited by the same positive integer.
2. Credit limits replace prepaid balances. A negative balance is an obligation to the co-op, bounded by the member’s limit.
3. The loop is closed. No cash-out.
4. Governance sets membership and limits. The ledger enforces numbers; it does not invent policy.
5. Issuance, if ever used, is an explicit signed event from a designated account. Pure bilateral mutual credit needs none.

### Minimal transaction

```json
{
  "version": 1,
  "tx_id": "uuid",
  "sender": "member-001",
  "recipient": "member-002",
  "amount": 500,
  "currency": "BIC",
  "sequence": 42,
  "timestamp": "2026-10-09T16:00:00Z",
  "signature": "base64-ed25519-signature"
}
```

The signature covers a deterministic encoding of every field except itself. The ledger verifies the signature, checks the sender sequence, rejects duplicates, enforces the credit limit, and commits atomically. An append-only log is not tamper-proof by itself. Signatures authorize. Hash chaining, durable commits, and independently retained checkpoints detect history changes.

Identity is a stable member ID bound to an Ed25519 public key. A Meshtastic node ID is a routing address and can change.

## Precedents used

| System | What was taken | What was rejected |
|---|---|---|
| Meshtbank (Roni Bandini) | Meshtastic + low-power hardware idea; practical offline transport | Float balances, plaintext PIN, per-user balance files as source of truth |
| LETS / Michael Linton | Zero-sum accounts, credit created at the moment of exchange, no interest, closed loop | Unlimited overdraft as a v1 default |
| Sardex | Closed-loop B2B mutual credit, turnover-based limits, non-convertible unit, balances expected to return toward zero | Central operator discretion without a signed journal |
| WIR Bank | Longevity of a closed complementary currency | Not a pure mutual-credit model; issuance is bank lending |
| Credit Commons | Nested mutual-credit ledgers for later federation | Overkill for one 20–50 member node |
| BerkShares | Comparison only, already in repo docs | Convertible local currency; different instrument |

## What is in the repository

### On `main`

- README rewritten for the three-layer design, transaction schema, and implementation order.
- Python ledger: `ledger.py`, `requirements.txt`, `test_milestone.py`.
- Integer balances, Ed25519, SQLite, per-sender sequences, hash-chained append-only log, atomic limit checks, `verify_chain()`, zero-sum check.
- Older co-op documents retained: bylaws draft, membership agreement, legal brief, BerkShares note, tech bible, MVP plan.

Local verification of the Python milestone on `main` / PR #2 base: 100 alternating transfers, duplicate rejection, insufficient credit, recovery from the same database file, and a simulated partial write that fails integrity check. All passed.

### Draft PR #1 — Rust ledger

- Branch: `feat/m1-ledger-core`
- URL: https://github.com/dlhiwig/mesht-credits/pull/1
- Rust SQLite ledger, Ed25519, hash chain, 100-transfer harness, GitHub Actions.
- CI is green after rustfmt. Local `cargo test` passed (`hundred_transfers_and_recovery`, `rollback_on_constraint_failure`).
- No governance layer. Not merged.

### Draft PR #2 — Python governance and CLI

- Branch: `feat/m2-python-governance-cli`
- URL: https://github.com/dlhiwig/mesht-credits/pull/2
- Signed admin events for enroll, credit-limit change, freeze, and unfreeze.
- Local CLI for enrollment, limits, freeze/unfreeze, transfers, balances, history, and verification.
- Issuance omitted on purpose.
- Local tests passed: governance suite and the original milestone suite.
- Not merged. No CI on this branch.

## Milestone against the original bar

The first milestone was two simulated members completing 100 authenticated transactions, including duplicates, insufficient funds, interrupted writes, and recovery, with zero accounting discrepancies.

| Check | Python (`main`) | Rust (PR #1) |
|---|---|---|
| 100 authenticated transfers | Passed | Passed |
| Duplicate rejection | Passed | Passed |
| Insufficient credit | Passed | Covered by constraint/rollback test |
| Recovery after reopen | Passed | Passed |
| Interrupted / inconsistent write detected | Simulated bad row fails `verify_chain()` | Rollback on constraint failure passed |
| CI | None on `main` | Green |

Both cores meet the simulation bar. Neither has power-loss injection or an external checkpoint.

## Open integrity gaps

These block any claim of production readiness:

1. **One ledger.** Python is on `main` and has governance. Rust has CI and a cleaner node shape, but no governance. Merging both as peer cores will split every later fix.
2. **Freeze concurrency.** Freeze is checked, but not yet proven safe under concurrent writers.
3. **Journal rebuild.** Administrative state cannot yet be fully reconstructed from the signed governance journal alone.
4. **External checkpoints.** No export of tip hash, member set, limits, freezes, and balances for a second machine to retain.
5. **Append-only protection.** A process that can write SQLite can rewrite history. Triggers, a separate writer role, or an external hash anchor are still missing.
6. **Power-loss fault injection.** The current interrupted-write test inserts a bad row. It does not kill the process mid-commit.

## Need to do

1. Choose the canonical ledger: keep Python and port governance forward, or port governance onto Rust and retire the Python core.
2. Close the five integrity gaps above on the chosen core.
3. Add CI for the chosen core on `main`.
4. Merge only after that choice and a green run. Leave the other PR closed or marked superseded.
5. Keep Meshtastic and hardware behind the ledger. Do not start radios until checkpoint and recovery tests pass.

## Could do

Still without hardware:

- Reconciliation report: system sum is 0, limits and freezes listed, last checkpoint hash shown.
- Dispute records that reference a `tx_id` and never rewrite history.
- A mesh message schema that calls the same `submit()` path, tested with two local processes and dropped or reordered packets.
- One CLI: enroll, transfer, freeze, verify, export checkpoint.
- A one-paragraph README note naming the canonical implementation.

## Explicitly deferred

- Physical LoRa (XIAO nRF52840 + SX1262, FireBeetle, or equivalent).
- Meshtastic channel integration.
- Credit Commons nesting.
- Cash-out, USD peg enforcement, or BerkShares-style convertibility.
- Multi-node consensus.

## Extra, later

- A packet-loss simulator before any hardware buy.
- Legal review of the Michigan cooperative drafts against the actual model: closed-loop, non-convertible, zero-sum. BerkShares stays a comparison.
- Member disclosure rules inside the co-op (balances and limits visible to members), not published publicly.
- Issuance only if the co-op needs to recognize non-bilateral contributions, and only as a signed event.

## Phase Zero exit criteria

Phase Zero is done when all of these are true:

- One canonical ledger is on `main`.
- Governance events are signed and replayable from the journal.
- Checkpoint export exists and a second process can verify it.
- Power-loss and concurrency tests exist and pass.
- CI is green.
- README states that Meshtastic is next, not current.

Until then, Phase Zero is **open**. The simulation milestone is met. The integrity and single-implementation work is not.
