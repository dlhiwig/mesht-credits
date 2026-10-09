# Phase 2 transport threat model

Scope: the local mesh envelope in `mesh.py`. Not a radio threat model.

| Threat | Control | Residual |
|---|---|---|
| Forged transfer | Envelope and transaction both require Ed25519 signatures | Stolen sender key |
| Replay of a mesh packet | `msg_id` accepted once; ledger sequence rejects a second apply | Operator must keep the seen set for the node lifetime |
| Dropped packet | Sender retries the same envelope; ledger sequence makes retry safe | Retry storm if drop rate stays high |
| Reorder | Same-sender sequence must arrive in order; retry covers a dropped earlier sequence | No delay bound |
| Duplicate delivery | Second `msg_id` returns duplicate and does not move balances | None in the simulator |
| Fake receipt | Receipt is signed by the operator key and covers `msg_id` plus `tx_hash` | Operator key is a trusted role |

Out of scope: radio jamming, node impersonation at the LoRa layer, Meshtastic channel keys.
