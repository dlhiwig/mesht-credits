# Radio reliability note

This is not a field report.

`test_phase34.py` runs the radio-port simulator at a 70 percent configured drop rate and retries until one transfer applies. That shows the ledger accepts a delayed retry once. It does not measure range, packet error rate, or duty cycle on LoRa.

A field report needs two flashed nodes, a known distance, and a count of sent versus received envelopes. That test has not been run.
