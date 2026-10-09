# M1 ledger core

Run `cargo test --all-targets` from the repository root. No radio hardware is needed.

The SQLite transaction journal is authoritative; balances are derived using signed integer sums. The database uses WAL, synchronous FULL, immediate write transactions, sender sequence numbers, unique transaction IDs, and Ed25519 signatures over a versioned length-prefixed binary message.

`Ledger::enroll` is a bootstrap-only administrative method. M1 does not authenticate enrollment or credit-limit changes. Do not expose it to untrusted callers.

`Ledger::verify` checks the signature and hash chain and zero-sum accounting. It cannot detect deletion of a valid tail without an externally retained signed checkpoint, or historical key changes. These are required before real deployment. The simulation verifies 100 successful transfers, duplicates, rejected invalid transfers, and reopen/recovery. Actual power-loss fault injection and concurrency stress remain pending.

This is prototype code, not an audited financial system. Do not use for real-world value until independent review and governance/legal checks.
