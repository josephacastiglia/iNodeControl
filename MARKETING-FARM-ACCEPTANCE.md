# Marketing Farm — acceptance record

Updated 18 October 2026. **The full marketing product is not accepted for unattended use.** Local preparation and supervised draft saves have evidence on Instagram, TikTok, X and YouTube. Automatic publishing and messaging remain disabled.

## Current candidate

- Native output: `output/codex-farm-preparation-20261018`, code commit `6b395eec620a`, DLL SHA-256 `49cab77c792b532b17b51283654ac9a2621ce1ae0d7058d8f45c8c05951ffd1b`.
- Candidate launcher: `Open Marketing Farm Candidate.ps1`; backend on loopback 9915, simulation mode, separate settings and hover tracking off.
- Previous native preparation build: **318 Python tests**, no skips; **532 native headless checks**. Clean Release build. Two real local scheduled renders and four older-batch video preparation/decoding paths passed. Actual process cancellation/crash checks and three negative controls passed. The newer C24C live pass and backend regression results are recorded below; native marketing code was not rebuilt this pass.
- All 14 upload formats execute with simulated transport and clean up ownership. Those tests do not establish real app completion.
- The latest live pass used a separate C24C-only kernel on 9916, built from `9fa7a85` (DLL `c72fa4e0…a873`). Paired freshness and one supervised existing-carousel save/reopen passed, including all slides, exact visible caption and account boundaries. It required API-driven diagnostic steps and agent image review; this is not an unattended adapter pass. All 25 protected installed files matched afterward; the initial stopped rack state was restored. No desktop control, publishing, messaging or C241 input. A complete interactive native-window-to-phone run remains open.
- Earlier live-pass validation: **330 Python regressions**, no skips, and **290 kernel self-tests**; clean isolated-kernel build. Backend hash `10d81465…236c91`; launcher ValidateOnly passed. The earlier 532 native checks apply to the unchanged native binary, not a new live desktop run.
- Latest offline validation: **353 Python tests pass**, no skips; launcher ValidateOnly passed with backend hash `234b585d…c11625`. The changes recognize the observed autoplay picker and corroborate ambiguous editor OCR; an exact same-frame Next crop is required before the model's details action when whole-frame OCR is incomplete. The rehearsal includes the post-save picker and protected-control stability checks. Eight retained OCR failures resolved, 36 older outcomes preserved, and four disabled-guard controls failed as intended. [Evidence and limitations](analysis/farm-layout-stability-20261018/README.md). This does not enable or accept a live action adapter.

## Usable scope and remaining gates

| Feature | Evidence / usable scope | Required before broader use |
|---|---|---|
| C24C profile | Validated local edits and persistence; canonical target matching | Other phones need binding and explicit scope |
| Content creation | Decodable template JPEGs/MP4, manifests, checksums, preserved earlier assets | External AI generation is not configured; editorial review remains necessary |
| Carousel editor | 2–10 slides, complete caption, ordering, import, preview, revision conflicts, crash recovery and export | Interactive usability check on the new native build |
| Native media transfer | Start/status/stop, private-address selection, immutable revision, expiry, duplicate-request recovery, backend restart, port conflicts and competing backends tested | New controls tested headlessly and through real loopback HTTP; actual native-window-to-phone run remains open |
| Video preparation | Saved H.264 720×1280 copies; full-frame fitting, source preservation, duration checks, audio decoding, immutable captions, lost-response recovery and saved-copy selection | Generated C24C videos only; 64 MiB and 45-second candidate limits. Source audio tested offline; silent MP4 used on the phone |
| Instagram draft | **Supervised C24C tests passed:** earlier three-slide carousel with exact multiline caption; this pass a real MP4 Reel saved, reopened and played with the exact test label | Repeatable app-state recognition, correct account verification, interruptions and unattended recovery |
| Jobs and Stop | Durable cancellation before admission, cooperative cancellation across processes, exclusive worker ownership, no replay after actual process crash, recovered completion and late-monitor race tested; uncertain server responses retain the native job bookmark | Marketing-specific live console/backend handover remains unverified. Cancellation cannot forcibly interrupt an in-progress codec |
| Screen/account review | Read-only C24C capture, local English OCR, caption-editor/carousel/photo/video patterns, exact text comparisons, saved frames and no replay. 39 saved-frame regression outcomes match, including one intentional unknown | Frames informed the rules; independent app-version/device validation remains open. Sparse libraries and ambiguous handles stay unresolved. No app/account authenticity or saved-draft proof |
| Carousel evidence comparison | Unique library-cover matching, full-size slides and page-dot count/order, exact visible caption, immutable source/screens. Latest supervised C24C pass observed Save, a moved cover, all three reopened slides, caption and account-before/after with paired frame ages | Per-step leases, capture gaps and unknown OCR prevent a complete continuous-history/product verification pass. Wider layouts and the actual action adapter still need acceptance. No input enabled by review |
| Carousel inspection run | Backend/API mock acceptance: one authenticated lease, fresh recognition before swipes, source-bound records, slide order/count, cancellation, no uncertain replay and scoped cleanup. Real C24C candidate frames now validated through separate supervised diagnostic steps | Product live movement remains disabled. The real phone run needed image review where OCR was unknown; it did not run the product adapter. No native start control or continuous observation claim |
| Save/reopen recovery rehearsal | Synthetic model covers save, autoplay picker, library, every slide/caption and account boundaries; cancellation, lost replies, crash after Save and no replay tested. Protected controls must agree across fresh frames; incomplete Next requires exact same-image crop OCR. One earlier supervised real C24C save/reopen was observed | The synthetic rehearsal still has no accepted live action adapter. The autoplay/OCR fixes have retained-frame and offline-model evidence only. Fresh phone validation, real interruption/recovery and repeatability remain open |
| Frame freshness | Paired session/sequence/delivery/age checked on the real C24C candidate stream. Old quiet frames and a slow OCR capture refused; move-only challenges produced new frames; a retained frame expired after 1.7 seconds without recapture. Offline backend-restart/native expiry checks remain | Receiver-delivery time is not iOS capture time. Static pages can be quiet without being frozen. Installed kernel still lacks paired metadata. No installed release change or automatic input enablement |
| Recurring local preparation | Each run retains its generation/manifest and editable carousel; native history opens that carousel or its original video/caption. Two actual background runs, batch preservation, failure holds, pause and restart tests pass | Latest 30 runs in the schedule window; older data retained. No days-long soak or unattended phone execution. Requires explicit configuration and a running backend; never transfers, publishes or messages |
| Schedule | Preview, phase-one warmup planning, cooldown boundary, UTC daily budget and paused-account hold tested | No recurring live execution service is accepted; needs a verified live review queue, actual timing and restart acceptance |
| Warmup | Simulated sequencing, phase rules, cancellation and cleanup | Approved account activity and observed app outcomes; no claim of improving platform standing |
| Analytics | Submitted post observations require identity, account, timezone-qualified timestamps and mature/recent evidence; low-view review pauses recurring preparation and never auto-resumes it | Automatic metric provider and validation against real account data. Screen counts remain unavailable as metrics without post identity/context |
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

Latest live report: `analysis/farm-live-verification-20261018/README.md`. Local preparation checks: `analysis/farm-preparation-continuity-20261018/README.md`. Earlier frame work is in `analysis/farm-recognition-20261017/README.md`; scheduling in `analysis/farm-observations-20261017/README.md`; earlier supervised draft steps in `analysis/farm-platform-drafts-20261017/README.md`. Private frames, OCR, records and exact candidates are archived outside Git with checksums. A supervised save, a native headless check, a read-only observation and an unattended workflow are separate acceptance claims.
