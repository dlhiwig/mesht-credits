# Phase 3 hardware bill of materials

Status: specified, not purchased, not tested on air.

The ledger node is a computer running the Python core. Radios are transport only.

| Role | Part | Notes |
|---|---|---|
| Ledger node | Any machine that can run Python 3 and SQLite | Single authoritative node for v1 |
| Member radio | Seeed XIAO nRF52840 plus Semtech SX1262 | Meshtastic-compatible LoRa node |
| Alternate radio | DFRobot FireBeetle ESP32-C6 | Second Meshtastic target, not required for the first pair |
| Power | USB battery or 5 V supply with a switch | Needed for the power-cut drill |
| Antenna | 915 MHz for US ISM, matched to the radio | Do not mix regions |

No unit has been bought or flashed for this phase. G21 and G22 stay open until a pair is on the bench.
