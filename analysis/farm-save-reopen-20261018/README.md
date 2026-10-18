# Offline draft save/reopen and interruption recovery — 18 October 2026

## Scope

This candidate adds an accessible offline check to the native Instagram carousel editor. It uses the selected saved revision's real image bytes and caption in a deterministic app model. It exercises the existing recognition, media comparison, frame freshness, ownership guard, SQLite journal and evidence retention. No phone, rack API or desktop control is used. No publishing, messaging, release modification or deployment occurred.

**This is not an automatic Instagram saver.** The model uses semantic transitions, generated screens and explicitly synthetic OCR annotations. It has no tap coordinates, live transport, account login, Photos import or publishing path. The prepared editor is seeded. All results keep `savedDraftVerified`, `accountContinuityProven` and `automaticInputAllowed` false. Live acceptance remains open.

## Operator workflow

Open the separate Marketing Farm Candidate, choose Instagram carousel drafts, save a 2–10-slide revision and select **Offline recovery checks…**. Choose normal save/reopen or a named failure scenario. The app shows the result, actions, cleanup and retained simulated screens. **Check saved result** retrieves the same request after a lost response; a running or missing result does not silently enable a replacement attempt. Saved history works after reopening the window/backend. Stop remains available while a request is pending.

The supported caption comparison is deliberately limited to fully visible lines in the recorded details layout. Long or truncated captions hold for review instead of reporting an exact match.

## Implemented sequence and recovery

1. Verify the simulated account before entering a seeded prepared carousel.
2. Check every full-size slide, count/order and visible caption.
3. Check the complete recorded Save draft sheet (warning, Discard, Save draft and Cancel at their expected positions). A permission dialog takes precedence.
4. Persist the exact decision frame and an `outcome_unknown` action before dispatch; recheck freshness and authenticated ownership before the semantic action.
5. Require a unique matching cover in the library, reopen, compare every slide and caption again, and check the final account.
6. Release only this run's ownership. Unconfirmed cleanup cannot be a passing result.

Lost Save/reopen replies trigger at most one read-only observation. A matching library/editor image can narrow the uncertainty but cannot certify a new save or authorize another action. These runs stop for review; there is no automatic Save, reopen, Resume, account switch or dialog-dismissal retry. A new offline rehearsal uses a new isolated model, not a resumed phone transaction.

Stop before admission is recorded durably and survives a delayed request or backend restart. A real child-process test exits just after the simulated Save but before its acknowledgement is recorded. Reopening its database retains the unknown action and unconfirmed cleanup; retrying its ID constructs no model and repeats no action. A replacement owner is never released by an old token.

## API and boundaries

All routes are loopback/origin guarded:

- `POST /api/farm/draft-rehearsals`: exactly `id`, `draft_id`, `revision`, `scenario`; simulation backend only.
- `GET /api/farm/draft-rehearsals?draft_id=…`: retained history (latest 30 for the draft).
- `GET /api/farm/draft-rehearsals/{id}`: status; no dispatch.
- `GET /api/farm/draft-rehearsals/{id}/frames/{observationId}`: checksum-validated retained image.
- `POST /api/farm/draft-rehearsals/{id}/cancel` with `{}`: persistent stop intent; bypasses the operation lock.

Scenarios: normal, lost save reply, lost reopen reply, permission prompt, changed account, stale save frame, wrong reopened slide, wrong caption and duplicate matching library covers. A matching output is labelled **Simulation passed**; deliberate failures must stop at their intended check, not merely fail somewhere else.

Existing carousel inspection now exposes its atomic evidence-retention helper for reuse. The rehearsal uses a separate synthetic-observation database, so generated frames never enter the live observation library. Source ZIP and immutable observation/image manifests are retained with the run and survive capture pruning. Existing live inspection remains disabled.

## Evidence and limitations

- The real Windows OCR bridge recognized the archived C24C Save draft sheet from 17 October. That is a development fixture, not an independent accuracy sample or current live check. Its source SHA-256 is recorded in `saved-prompt-check.json`.
- An offline exercise uses the archived three-slide carousel package and original multiline test caption. Each expected interruption must be reached explicitly. The first real-clock exercise encountered a freshness hold before the account-change scenario; that remains recorded and does not count as testing the account change. The confirmed exercise is separate.
- Synthetic OCR annotations exercise workflow logic. They do not test camera quality, iOS app identity, real account continuity, current UI geometry or app persistence.
- The known installed release lacks the paired freshness metadata required by unattended input. This pass changes no installed kernel or receivers. A phone connection alone does not remove that prerequisite.
- Full live media transfer/import/navigation, current screen verification, app restart persistence and unattended recovery still need a validated live adapter and controlled acceptance. TikTok/X/YouTube have supervised historical draft checks; this new lifecycle is Instagram-carousel simulation only.

## Remaining priorities

1. Validate paired frame metadata on a separate candidate kernel using a real stream, keeping the installed release intact.
2. Add a bounded live draft-only adapter for the observed Instagram states; no guessed tap targets or publishing path. Reuse this journal and independent before/after checks.
3. Run supervised save/library/reopen acceptance with exact account, all slides and caption, including interrupted responses. Do not upgrade sampled account evidence into continuous-account proof.
4. Extend recognition and draft verification to video/TikTok/X/YouTube, then recurring draft execution and actual analytics. Publishing and messaging remain disabled.

## Build and validation

- Candidate: `output/codex-farm-save-reopen-20261018`.
- DLL SHA-256: `972d143b265c1d0ee2514d0320b88dfbaf05342c9d0d1941f8842f12010fea19`.
- Backend source SHA-256 (16 files, including the new rehearsal module): `915a1f9173859d12ff504d8d891fc0ae9fbe3702581db9322077ced22c84d2db`.
- Release build: zero warnings/errors.
- Full Python suite: **294 passed**, no skips (129.476 seconds). Final focused recovery/HTTP tests: **23 passed** after the last admission change (48.758 seconds); see `rehearsal-final.txt`.
- Preserved three-slide package exercise: **9/9 intended outcomes** on the confirmed real-clock run (normal success plus eight specific review holds), 1.078–2.578 seconds each. All model leases released; no phone commands. The earlier premature freshness hold remains in its separate record.
- Native headless suite: **517 passed**, all commands used mock transport. The new window was rendered into an image without a desktop window.
- Launcher `-ValidateOnly`: exact candidate, isolated data directory, simulation on 9915, no processes started.

Full logs, generated evidence and binaries are preserved privately outside Git in `iMouseXP-2.0-evidence-archive/20261018-farm-save-reopen`. This report and source/tests are committed locally; no push or deployment.
