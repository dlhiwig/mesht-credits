# Phase 2 — Local mesh transport

**Status:** Implemented on `main`. No radios.

Phase 2 is a signed envelope and an in-process delivery simulator. Meshtastic is still a later transport, not this phase.

## What shipped

- `mesh.py` seals a transfer in a versioned envelope signed by the sender.
- `LocalMesh` verifies the envelope, drops or duplicates by configured rate, and submits the payload once.
- Duplicate `msg_id` does not apply twice.
- Sequence rules still reject a sender's transfer until the previous sequence exists. Reorder is safe only after retry.

## Test

`test_phases.py::test_mesh_drop_reorder_duplicate` — 10 transfers, forced duplicates, zero system sum, chain verifies.

## Not in this phase

Physical LoRa, Meshtastic channels, store-and-forward across devices.
