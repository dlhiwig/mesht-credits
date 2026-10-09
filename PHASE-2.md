# Phase 2 — Protocol simulation

**Date:** 2026-10-09
**Status:** Complete in simulation. No radios.

## Evidence

- Canonical envelope encoding in `mesh.py`.
- Signed operator receipts covering `msg_id` and `tx_hash`.
- Packet-loss simulator with retry. `test_phase12.py` uses an 80 percent drop rate and still reaches one apply.
- Threat model: `PHASE-2-THREAT-MODEL.md`.

Meshtastic, LoRa hardware, and channel keys are Phase 3, not this phase.
