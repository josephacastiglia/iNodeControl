# Carousel inspection under one lease — 18 October 2026

Status: **offline implementation and mock acceptance passed; live movement disabled.** No PC control, phone input, publishing, messaging, service restart or installed-release change occurred. A read-only request to the existing rack API was refused because nothing answered on port 9913. This does not establish phone, receiver or lease state.

## What changed

The previous review expected one ownership generation but collected only unowned snapshots. A sequence of separately acquired/released actions could not supply a consistent set. The new internal owned-capture guard authenticates its private token before and after each frame. It checks C24C's generation, settled input and receiver/stream identity. It does not mistake another controller's `owned` status for ownership. Ordinary observation requests remain read-only and cannot submit an ownership proof.

`farm_carousel_inspection.py` implements a bounded workflow beginning at the **first full-size slide of an already-open Instagram carousel editor**. It requires a saved source revision, the supported 500×1080 frame, exact recognized editor layout, paired recent frame metadata, matching image and page-dot count/index. It acquires one 30-second lease and authenticates/renews it as it proceeds. Each next slide uses only a fixed horizontal swipe inside the image area. No arbitrary coordinates, taps, text, Save, Share, Back or account-selection command is accepted.

Every action is journalled before transport. Lost responses, acquisition ambiguity, interruption, cancellation, paused input, stale/repeated frames, wrong media and ownership/stream changes terminate the run. There is no retry, automatic Resume or takeover. Cleanup uses only this run's token and records confirmed versus unconfirmed release. An unknown acquisition outcome cannot be force-released without a token. The 90-second budget stops admission of further work, rather than promising an in-flight request or cleanup can be forcibly interrupted at that instant.

The exact source ZIP and capture records/images are retained in `carousel-inspections.db`, independent of observation-history pruning. Results recover by ID without another command. Incomplete records after restart require review. Tokens and raw transport exception text are not persisted in inspection evidence. The underlying kernel client's existing in-memory audit behaviour is unchanged.

Owned captures can participate in evidence review without being labelled unowned/idle. Mixed run IDs, unauthenticated ownership, changed generations and all prior account-history limitations still block. The verifier still reports `savedDraftVerified=false`, `accountContinuityProven=false`, and `automaticInputAllowed=false`.

## API contract

All inspection routes are loopback/local-origin only, under the existing single-operation boundary:

- `POST /api/farm/carousel-inspections`: JSON `id`, `draft_id`, `revision`, `device_id` (`C24C`), `platform` (`instagram`) and expected `account`. No paths, commands, coordinates or caller verdicts.
- `GET /api/farm/carousel-inspections/{id}`: saved status or incomplete-outcome review hold. Recover here after an HTTP timeout; do not create a new ID to retry unknown work.
- `GET /api/farm/carousel-inspections/{id}/frames/{observationId}`: retained checksum-verified image.
- `POST /api/farm/carousel-inspections/{id}/cancel` with `{}`: request cancellation without waiting for the operation lock. An absent/completed run returns `cancellationRequested=false` and sends nothing. Cancellation cannot undo an in-flight movement.

Health reports `carouselInspectionVersion=1` and `carouselInspectionLiveMovement=false`. Simulation transport can exercise the workflow against appropriate frames; the standard blank mock does not pretend a carousel matched. Live transport can do the read-only preflight, but **cannot acquire or move**, even with valid metadata. No switch or request field bypasses this hold. There is no native inspection button yet.

## Validation

- **259 Python tests passed**, no skips, in 77.616 seconds. The 25 additions cover owned inspection, real adapter request serialization, HTTP result recovery and cancellation, evidence retention, no replay, ownership and account-history failure paths. HTTP tests connect only to registered ephemeral mock ports; a network guard rejects other destinations.
- **505 native headless checks passed** with all commands using mock transport. The first restricted run failed at the diagnostic-file replacement test with a sandbox `UnauthorizedAccessException`; the failure log is preserved. Rerunning with temporary-file access passed. No desktop window was controlled.
- Release build: zero warnings, zero errors. Native UI source is unchanged by this pass; it is rebuilt alongside the updated backend.
- Candidate: `output/codex-farm-inspection-20261018`.
- DLL SHA-256: `fbcf242f901e75b4f539704e8b69ddf6acdcea6e1343d309c9edb61af446199f`.
- Backend source SHA-256: `e221e3ce26ef529ac1cf5a6893fa7d17a79e704bf6e6a3461f6787bff7bf20b0` (15 source files).
- Separate launcher validated with `-ValidateOnly`; simulation backend on 9915 and isolated settings. Validation started no process.

## Next acceptance work

Validate screenshot-paired metadata on the candidate kernel in an authorized C24C window, then rehearse the bounded slide inspection before enabling live movement. Extending the run to bracket account identity and observe draft save/reopen transitions remains separate work. The old installed kernel lacks paired metadata; this pass did not replace it. Publishing, messaging and other phones remain out of scope.

Private logs, candidate binaries and exact source copies are preserved outside Git in `iMouseXP-2.0-evidence-archive/20261018-farm-inspection`, with checksums and a commit record. No screenshot or account data from a phone was collected this pass.
