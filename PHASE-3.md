# Phase 3 report

**Date:** 2026-10-09
**Status:** Software port only. Hardware gates stay open.

## Done

- Bill of materials written in `HARDWARE-BOM.md`. No parts purchased.
- `radio_port.py` uses the same signed envelope as the Phase 2 mesh simulator. It is a stand-in for a serial radio, not a radio.
- Power-cut drill closes the node and reopens the database. Chain and zero-sum hold in `test_phase34.py`.

## Not done

- No offline LoRa transfer.
- No power-loss on a physical device.
- No field reliability numbers. The drop rate in the simulator is configured, not measured.
