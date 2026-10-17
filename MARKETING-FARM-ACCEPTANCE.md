# Marketing Farm — acceptance record

Updated 17 October 2026. **The full marketing product is not accepted for unattended use.** Local preparation and supervised draft saves now have evidence on Instagram, TikTok, X and YouTube. Automatic publishing and messaging remain disabled.

## Current candidate

- Native output: `output/codex-farm-video-20261017`, DLL SHA-256 `61764a45cf1ad1adced31cca087ff36412842af12f8d638104d800b0f48fee1e`.
- Candidate launcher: `Open Marketing Farm Candidate.ps1`; backend on loopback 9915, simulation mode, separate settings and hover tracking off.
- **161 Python tests**, no skips; **478 native headless checks**; Release build has zero warnings/errors. Python tests use only registered mock listeners; headless checks create no desktop window.
- All 14 upload formats execute with simulated transport and clean up ownership. Those tests do not establish real app completion.
- Installed console/release, shortcuts, kernel and receivers were not changed. This pass used observed C24C phone API input, never PC control. C241 received no input. The operator physically dismissed YouTube's optional local-network prompt using Don't Allow. Candidate controls were tested headlessly; the live saves were supervised through the existing release API.

## Usable scope and remaining gates

| Feature | Evidence / usable scope | Required before broader use |
|---|---|---|
| C24C profile | Validated local edits and persistence; canonical target matching | Other phones need binding and explicit scope |
| Content creation | Decodable template JPEGs/MP4, manifests, checksums, preserved earlier assets | External AI generation is not configured; editorial review remains necessary |
| Carousel editor | 2–10 slides, complete caption, ordering, import, preview, revision conflicts, crash recovery and export | Interactive usability check on the new native build |
| Native media transfer | Start/status/stop, private-address selection, immutable revision, expiry, duplicate-request recovery, backend restart, port conflicts and competing backends tested | New controls tested headlessly and through real loopback HTTP; actual native-window-to-phone run remains open |
| Video preparation | Saved H.264 720×1280 copies; full-frame fitting, source preservation, duration checks, audio decoding, immutable captions, lost-response recovery and saved-copy selection | Generated C24C videos only; 64 MiB and 45-second candidate limits. Source audio tested offline; silent MP4 used on the phone |
| Instagram draft | **Supervised C24C tests passed:** earlier three-slide carousel with exact multiline caption; this pass a real MP4 Reel saved, reopened and played with the exact test label | Repeatable app-state recognition, correct account verification, interruptions and unattended recovery |
| Jobs and Stop | Durable IDs, no replay, single-operation execution, cancellation, heartbeat timeout and recovery tested | Marketing-specific live console/backend handover remains unverified |
| Schedule | Preview, phase-one warmup planning, cooldown boundary, UTC daily budget and paused-account hold tested | No recurring live execution service is accepted; needs review queue, actual timing and restart acceptance |
| Warmup | Simulated sequencing, phase rules, cancellation and cleanup | Approved account activity and observed app outcomes; no claim of improving platform standing |
| Analytics | Submitted post observations require identity, account, timezone-qualified timestamps and mature/recent evidence; low-view review can pause but never auto-resume | Automatic observation provider and validation against real account data |
| Keyword replies / DMs | Missing observations refuse; no invented keyword matches or messages | Observations, recipient verification, approved messaging scope and live acceptance |
| Pins and cross-account actions | Simulation only | Separate authorization and observed outcomes; no acceptance claim |
| Automatic creation + deployment | Combined path runs in simulation | Every live stage must pass before this can be enabled |
| Instagram Reel/Post/Story | Reel and carousel draft saves observed; automated flows remain simulation only | Other post/story modes and unattended state validation |
| TikTok video/photo/story/text | Three-photo draft and transferred MP4 draft saved and reopened with exact test labels; MP4 playback verified and suggested sound removed | Text/story modes, repeated recovery checks and unattended state validation |
| X post/video/thread | Image and transferred MP4 drafts saved and reopened with exact labels; video played after tapping its initially blank preview | Threads, repeated recovery checks and unattended state validation |
| YouTube Short/video/community | Photo-derived Short and transferred MP4 Short saved and reopened with exact titles; MP4 playback and 3.0-second trim view verified | Long video/community modes, unattended permission handling and state validation |
| Publishing | Disabled under current instructions | Explicit publishing test scope, observed published item, duplicate prevention and failure recovery |

## Acceptance rules

1. Local work must preserve source media, full captions, order and recoverable edits; reject invalid inputs without partial hidden success.
2. Phone completion requires observed account, content and persisted state. An HTTP download or HID `code: 0` is insufficient.
3. A simulated action must stay labelled simulated. A media transfer is real delivery even when input jobs use simulation; the UI states this explicitly.
4. Unknown outcomes require inspection/status recovery. Never automatically repeat publication, messaging, transfer start, or phone input.
5. Stop, expiry, stale-session isolation and ownership cleanup must remain available during failures. A different backend cannot take over an existing media session.
6. A draft-only test never crosses Share/Publish/Send. Only C24C is authorized for live work; C241 and the installed release remain unchanged.
7. Counts need context: lifetime view totals are not 24-hour views; low views do not prove a platform restriction. Improved counts never clear a pause automatically.

## Fixes found during the video pass

- MP4 delivery now supports Safari byte-range requests. Counts are labelled potentially partial requests, never app-save confirmation.
- An expiry boundary could reset a valid client's connection before returning a refusal. Expired content remains unavailable; the server now allows a short, bounded refusal response.
- Failed preparation before storage, a busy backend, a lost response after storage and an HTTP 500 after storage retain the request identity until the saved result is checked. Recovery does not create a duplicate video.
- Selecting a saved video now shows its saved caption and destination. Editing the preparation invalidates transfer of the old copy. Unknown outcomes block selecting another copy.
- Transfer instructions reflect the observed Safari Downloads → Files preview → Save Video route. They warn about suggested sounds and unresponsive permission dialogs without claiming those are automated.

## Earlier transfer/acceptance audit fixes

- Transfer sessions initially kept SQLite file handles open. Transactions now close their connections; cleanup and restart tests pass.
- An early-phase account could remain held forever instead of receiving a warmup plan. Its schedule now plans warmup while preserving the no-upload phase rule.
- A schedule evaluated for a supplied date used the machine's current UTC day for its upload cap. Both now use the requested UTC day.
- Raw view counts could overwrite `views_24h` and clear a previous pause. Counts without identity/age evidence now preserve existing data. Structured observations retain their source records and only latch a pause.
- A competing control server could initialize data before discovering a port conflict. Startup now reserves an exclusive loopback listener first.
- Transfer requests have a total connection budget and bounded stop cleanup; a stalled client cannot keep the link alive indefinitely.

Three new analytics/scheduler cases fail against the preserved `f770b34` engine and pass against this source. Earlier failed/restricted test logs are retained separately from the final passing results.

## Remaining work

The operator authorized any already signed-in C24C accounts for **draft-only** checks; those supervised saves are complete for the tested formats above. Publishing and messaging remain outside scope. Full marketing acceptance still requires observed app/account recognition, safe handling of changed screens, media selection and caption verification, repeated interruption/recovery cases, recurring execution and real observations. The remaining format paths are not accepted merely because similar drafts worked. No live automatic route was enabled.

Latest report, logs and exact observed step references: `analysis/farm-platform-drafts-20261017/README.md`. Its private screenshots, account evidence, test package and exact candidate are archived outside Git with checksums. Earlier reports remain in `analysis/farm-native-transfer-20261017/` and `analysis/farm-phone-transfer-20261017/`. A supervised save, a native headless check and an unattended workflow are separate acceptance claims.
