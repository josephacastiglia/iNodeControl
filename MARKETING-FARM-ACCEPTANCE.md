# Marketing Farm — acceptance record

Updated 17 October 2026. **The full marketing product is not accepted for unattended use.** The tested candidate supports local preparation and supervised Instagram draft work. Automatic publishing and messaging remain disabled.

## Current candidate

- Native output: `output/codex-farm-transfer-20261017`, DLL SHA-256 `81dd034a5910edd95b0fec8bc92a6f1e6df5236def7569c7def0b1274472a591`.
- Candidate launcher: `Open Marketing Farm Candidate.ps1`; backend on loopback 9915, simulation mode, separate settings and hover tracking off.
- **149 Python tests**, no skips; **459 native headless checks**; Release build has zero warnings/errors. Engine and server self-checks also pass under a network guard.
- All 14 upload formats execute with simulated transport and clean up ownership. Those tests do not establish real app completion.
- Installed console/release, shortcuts, kernel and receivers were not changed. No desktop control or phone input occurred in this follow-up. The earlier C24C draft test remains its own live evidence.

## Usable scope and remaining gates

| Feature | Evidence / usable scope | Required before broader use |
|---|---|---|
| C24C profile | Validated local edits and persistence; canonical target matching | Other phones need binding and explicit scope |
| Content creation | Decodable template JPEGs/MP4, manifests, checksums, preserved earlier assets | External AI generation is not configured; editorial review remains necessary |
| Carousel editor | 2–10 slides, complete caption, ordering, import, preview, revision conflicts, crash recovery and export | Interactive usability check on the new native build |
| Native media transfer | Start/status/stop, private-address selection, immutable revision, expiry, duplicate-request recovery, backend restart, port conflicts and competing backends tested | New controls tested headlessly and through real loopback HTTP; actual native-window-to-phone run remains open |
| Instagram draft | **One supervised C24C test passed:** three slides, exact caption, Save draft, reopen and inspect; nothing published | Repeatable app-state recognition, correct account verification, interruptions and unattended recovery |
| Jobs and Stop | Durable IDs, no replay, single-operation execution, cancellation, heartbeat timeout and recovery tested | Marketing-specific live console/backend handover remains unverified |
| Schedule | Preview, phase-one warmup planning, cooldown boundary, UTC daily budget and paused-account hold tested | No recurring live execution service is accepted; needs review queue, actual timing and restart acceptance |
| Warmup | Simulated sequencing, phase rules, cancellation and cleanup | Approved account activity and observed app outcomes; no claim of improving platform standing |
| Analytics | Submitted post observations require identity, account, timezone-qualified timestamps and mature/recent evidence; low-view review can pause but never auto-resume | Automatic observation provider and validation against real account data |
| Keyword replies / DMs | Missing observations refuse; no invented keyword matches or messages | Observations, recipient verification, approved messaging scope and live acceptance |
| Pins and cross-account actions | Simulation only | Separate authorization and observed outcomes; no acceptance claim |
| Automatic creation + deployment | Combined path runs in simulation | Every live stage must pass before this can be enabled |
| Instagram Reel/Post/Story | Simulation only | Designated account, correct media/editor behavior, draft/reopen where supported |
| TikTok video/photo/story/text | Simulation only | Designated test account and draft-only live checks first |
| X post/video/thread | Simulation only | Designated test account and supported draft behavior |
| YouTube Short/video/community | Simulation only | Designated test account, app-specific draft capabilities and observed outcomes |
| Publishing | Disabled under current instructions | Explicit publishing test scope, observed published item, duplicate prevention and failure recovery |

## Acceptance rules

1. Local work must preserve source media, full captions, order and recoverable edits; reject invalid inputs without partial hidden success.
2. Phone completion requires observed account, content and persisted state. An HTTP download or HID `code: 0` is insufficient.
3. A simulated action must stay labelled simulated. A media transfer is real delivery even when input jobs use simulation; the UI states this explicitly.
4. Unknown outcomes require inspection/status recovery. Never automatically repeat publication, messaging, transfer start, or phone input.
5. Stop, expiry, stale-session isolation and ownership cleanup must remain available during failures. A different backend cannot take over an existing media session.
6. A draft-only test never crosses Share/Publish/Send. Only C24C is authorized for live work; C241 and the installed release remain unchanged.
7. Counts need context: lifetime view totals are not 24-hour views; low views do not prove a platform restriction. Improved counts never clear a pause automatically.

## Fixes found during this pass

- Transfer sessions initially kept SQLite file handles open. Transactions now close their connections; cleanup and restart tests pass.
- An early-phase account could remain held forever instead of receiving a warmup plan. Its schedule now plans warmup while preserving the no-upload phase rule.
- A schedule evaluated for a supplied date used the machine's current UTC day for its upload cap. Both now use the requested UTC day.
- Raw view counts could overwrite `views_24h` and clear a previous pause. Counts without identity/age evidence now preserve existing data. Structured observations retain their source records and only latch a pause.
- A competing control server could initialize data before discovering a port conflict. Startup now reserves an exclusive loopback listener first.
- Transfer requests have a total connection budget and bounded stop cleanup; a stalled client cannot keep the link alive indefinitely.

Three new analytics/scheduler cases fail against the preserved `f770b34` engine and pass against this source. Earlier failed/restricted test logs are retained separately from the final passing results.

## Next dependency

The operator was asked which C24C accounts may be used for TikTok, X and YouTube **draft-only** checks. No additional accounts are assumed approved. Publishing and messaging need a separate scope and remain disabled. An account designation alone does not make the existing coordinate-based automation safe to enable: screen/account verification must be implemented and tested first.

Detailed logs, headless renders, source and build inventory: `analysis/farm-native-transfer-20261017/`. The preceding live draft evidence is in `analysis/farm-phone-transfer-20261017/README.md` and its separate archive. No new live success is inferred from the offline results.
