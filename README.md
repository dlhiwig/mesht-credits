# mesht-credits

**Meshtastic transport + auditable mutual-credit ledger for a small closed-loop cooperative.**

Offline-first community credits for 20–50 members. Not a cryptocurrency, not a bank, not a cash-out token. A zero-sum accounting system that records who provided value and who received it, carried over LoRa mesh when internet and grid power are unavailable.

Primary inspiration: Roni Bandini’s [Meshtbank](https://github.com/ronibandini/Meshtbank) (MIT, 2025). This project keeps the Meshtastic + low-power hardware idea and replaces the central balance-file model with integer mutual-credit accounting, signed append-only transactions, and explicit co-op governance.

## Why this name

`mesht-credits` is short, searchable, and precise: Meshtastic provides the communications layer; the credits are a separate, auditable mutual-credit ledger. Alternatives considered (`meshbank-coop`, `meshtastic-credits`) are longer or closer to Bandini’s exact project name. The hyphenated form stays distinct while remaining immediately understandable.

## Architecture (three layers)

| Layer | Responsibility | Initial implementation |
|-------|----------------|------------------------|
| **Mesh transport** | Delivery, retries, offline reach | Meshtastic (private channel, DMs) |
| **Ledger core** | Integer accounting, sequence numbers, signatures, replay protection, atomic commits | Single authoritative node, SQLite (or equivalent durable store) |
| **Co-op governance** | Enrollment, credit limits, issuance rules, disputes, reconciliation | Member records + admin/core-crew procedures |

**Initial release keeps a single authoritative ledger node.** Distributed synchronization adds failure modes that are unnecessary for a 20–50-member co-op. USB or mesh snapshots can be added later for backup and read-only replicas.

### Architectural correction from Meshtbank

Meshtbank stores a float balance per node ID in LittleFS (`/!nodeid.txt`) plus a plain-text history. That is sufficient for a proof of concept but fragile for mutual credit:

- Use **integer units** (no floats).
- Use **digitally signed transactions** (Ed25519).
- Use an **append-only ledger** with sequence numbers and replay protection.
- Derive balances from the verified transaction log; do not treat a balance file as the source of truth.
- Enforce limits atomically inside a transaction before accepting a transfer.

An append-only log is not automatically tamper-proof. Signatures prove authorization. Hash chaining, durable storage, and independently retained checkpoints detect unauthorized rewriting of history.

## Mutual credit model

Mutual credit (LETS, Sardex-style circuits, WIR-like closed systems, Credit Commons accounting) creates units at the moment of exchange rather than requiring prepaid tokens.

Core rules for this project:

1. **Zero-sum.** Every transfer debits one member and credits another by the same integer amount. Sum of all member balances is always zero (apart from any explicitly designated system/issuance account if used).
2. **Credit limits replace prepaid backing.** A member may go negative up to a configured limit. The limit is permission to incur an obligation to the co-op, not free money.
3. **Closed loop.** Credits are not redeemable for USD, crypto, or external value. They circulate only among enrolled members.
4. **Governance sets limits and resolves disputes.** The ledger enforces the numbers; the co-op decides membership, limit changes, freezes, and how to handle unpaid obligations.
5. **Issuance is optional and explicit.** Pure mutual credit needs no minting. If the co-op wants to recognize contributions outside bilateral exchange (e.g., propane run, firewood), that is a separate, signed issuance transaction from a designated account, still kept inside the zero-sum or carefully documented non-zero-sum rule.

Relevant precedents (for design, not code reuse):

- LETS / mutual credit: zero-sum accounts, credit limits, community trust.
- Sardex: closed-loop business mutual credit with turnover-based limits; non-convertible.
- Credit Commons protocol: nested mutual-credit ledgers; useful for future federation, overkill for v1.
- Meshtbank: practical Meshtastic transport and hardware reference.

## Minimal transaction schema

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

The signature covers a deterministic encoding of all fields except the signature itself (canonical JSON or CBOR with fixed field order). The ledger verifies the signature, checks the sequence against the sender’s last accepted sequence, enforces integer amount > 0, checks the resulting balances against limits, and commits atomically. Duplicate `tx_id` or sequence is rejected.

Identity is a stable member ID bound to an Ed25519 public key, not solely a Meshtastic node ID (node IDs can change). The node ID remains the routing address for mesh delivery.

## Implementation order

1. Repository renamed to `mesht-credits` (done).
2. Rewrite this README and related design docs.
3. Implement and test the ledger core in isolation (no radios).
4. Integrate Meshtastic transport once the ledger is correct.
5. Physical LoRa hardware last.

### First milestone

Two simulated members complete 100 authenticated transactions, including:

- duplicate submissions,
- insufficient funds / limit violations,
- interrupted writes,
- ledger recovery from durable storage.

Zero accounting discrepancies. Only then move to real Meshtastic nodes.

## Hardware reference (later phase)

Bandini’s proven stack remains a good starting point for the bank node:

- Seeed XIAO nRF52840 + SX1262 (Meshtastic radio)
- DFRobot FireBeetle 2 ESP32-C6 (or equivalent capable of SQLite / durable storage)
- Optional small TFT, LiPo + solar

User nodes can be any Meshtastic-compatible device. The ledger does not run on every radio.

## Status

Design and documentation. No ledger implementation yet. Prior documents in this repository (TECH-BIBLE.md, MVP-PLAN.md, etc.) describe the Beaver Island co-op framing and earlier Meshtbank-oriented notes; this README is the current architectural baseline.

## License

To be determined. Meshtbank is MIT; any derivative work should preserve appropriate notices.

---

*Credits are obligations inside a closed co-op, not money. The mesh keeps the ledger reachable when everything else is down.*
