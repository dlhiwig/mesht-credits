# Echo AI Integration Sketch → Code

**Date:** 2026-10-29  
**Status:** Draft artifacts only. Implementation next.

## Architecture reminder

Echo is a fourth layer above co-op governance.

- Reads the ledger exclusively through **read-only checkpoint exports**.
- Takes actions only by producing payloads that become **signed governance events** submitted by an authorized party.
- The authoritative ledger node is separate. If the AI box dies, payments continue.
- Mesh transport is an additional delivery channel for Echo’s outbound messages (med-reminders, notices).

## Planned Ollama tools

Each tool wraps existing Python ledger / mesh APIs:

| Tool                  | Purpose                                      | Ledger interaction      |
|-----------------------|----------------------------------------------|-------------------------|
| get_balance           | Current balance + limit + frozen flag        | Read checkpoint         |
| get_member_history    | Recent txs for a member                      | Read checkpoint / log   |
| list_freezes          | Currently frozen members                     | Read governance state   |
| submit_issuance       | Draft issuance proposal                      | Produce unsigned payload|
| broadcast_mesh_text   | Queue mesh message                           | Mesh only (no ledger)   |
| query_weather         | Local weather (Beaver Island)                | External / local cache  |

## Onboarding hook

Med-reminder use case (EFMP-informed) builds trust before any transaction activity.

## Next steps (move from sketch to code)

1. Implement thin Python wrappers around `Ledger.export_checkpoint()`, `get_balance()`, history queries, and mesh send.
2. Register the tools with Ollama (or equivalent local agent runtime).
3. Wire checkpoint export as a periodic read-only feed.
4. Keep signing keys off the AI box.
5. Test: AI down → transfers still succeed on the ledger node.

Artifacts in this commit:

- `docs/echo/echo_tools.json` — Ollama-compatible tool schema
- `docs/echo/SAMPLE-SYSTEM-PROMPT.md` — starter system prompt
