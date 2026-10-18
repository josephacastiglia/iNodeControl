# Automatic handling of the five draft review holds

18 October 2026. Offline follow-up to `farm-live-layout-20261018`. **All five archived cases pass the new bounded transition replay.** The complete simulated draft workflow also handles the known loading changes without manual review. Fresh C24C execution of this controller remains unvalidated; live automatic movement, publishing and messaging remain disabled.

This pass used retained phone images, generated app frames, local Windows OCR and temporary offline test services. No rack API, phone input, PC control, installed-console launch or phone-setting change was needed.

## What changed

| Earlier hold | Automatic handling prepared offline | Evidence / remaining limit |
|---|---|---|
| 04: Create sheet omitted Reel in OCR | A product recognizer requires eight exact, positioned labels and the sheet's pixel layout. The sheet takes precedence over the profile behind it. Post means the format-selection row only. | Two retained frames pass. Missing/shifted/duplicate anchors and an obscured sheet refuse. Account text behind the sheet is not counted as visible identity. |
| 05: Picker home indicator faded | Re-capture while the change is confined to the known indicator region. Require a new pair that passes the original protected-grid comparison before continuing. | Archived replay uses four frames. The final comparison still protects the indicator; it is never ignored for a ready decision. |
| 06: Old reviewed picker frame disagreed | Decisions use a new pair of independently fresh observations within one authenticated run, instead of requiring approval of an old screenshot. | Two retained frames pass. New owner, stream, account expectation, stale frame or repeated sequence stops the wait. |
| 08: Editor changed after opening | Require the correct full-size source slide, position/count and toolbar on every capture. A changing suggested-audio header may request another capture, without selecting audio or sending input. | Three retained frames pass. The final comparison still includes the header. Tiny action-control changes, wrong media or a dialog stop immediately. |
| 11: Next OCR failed | Preserve the exact label-only crop fix from `ef25f5e` and require that proof again for the decision frame. | Two retained editor frames pass. Missing/old proof remains a hold; account/caption text is never repaired. |

## Bounded waiting

`tools/farm_transitions.py` accepts capture, ownership/cancellation check, current-evidence read and journal callbacks. It has no action or transport callback. It allows at most **four captures and six seconds** per transition, with a 150 ms pause between attempts.

Every capture must be recognized, fresh under the existing 1,500 ms budget, settled, tied to C24C, and authenticated under the same lease/run, stream, receiver, observer and expected account. Frame sequence must advance. An intervening wrong screen or failed check cannot be erased by a later matching frame. The final immutable record is rechecked and re-aged before returning; the workflow revalidates it again when journalling/dispatching its action.

Only two known changes can request another read: the picker's indicator and the editor's suggestion header. The diagnostic comparison that identifies an indicator fade cannot return ready. An unknown change, stale frame, cancellation, dialog or ownership discontinuity remains a hold. The waiter never retries Save, reopens a draft twice, changes a target, dismisses a dialog or resets a timeout.

## Workflow integration

The existing offline rehearsal now includes profile → Create → Post-format picker → Drafts → the prepared draft. It then verifies all slides/caption, saves once, reopens and verifies again. The prepared draft is seeded in the model; no media-import success is invented.

Create, picker and editor action boundaries use the shared waiter. Its attempts are journalled with observation IDs and comparison results. Lost Save/reopen responses still receive only the existing read-only reconciliation and require review. Cancellation, process-crash recovery, durable evidence and ownership cleanup remain in the same implementation.

The candidate launcher and backend source fingerprint both include the new module. The native console/kernel binaries are unchanged. The HTTP test client uses the console's 30-second budget for the longer complete rehearsal POST; Stop and status retain their existing short test budget. No product timeout was increased.

## Evidence

- `replay_holds.py` validates each input against the preceding live archive's SHA-256 inventory, then runs actual Windows OCR. `replay-final/results.json` records **5/5 replay passes**, with capture counts 2, 4, 2, 3 and 2.
- Replay source: `iMouseXP-2.0-evidence-archive/20261018-farm-live-layout`. The capture context and clock in this replay are simulated. Frames span the earlier supervised steps and separate leases, so this does **not** prove a continuous live run or settling within six real seconds.
- `replay-first/` is retained: the initial picker sequence supplied only three archived frames and exhausted them before a stable pair. The final sequence includes the next existing frame; no pixels or original records were changed.
- Dedicated transition tests cover bounded waits, wrong media/count, changed controls/library, missing Next proof, dialogs, cancellation, deadlines, reused frames, context changes and final evidence expiry/tampering.
- Added integrated model tests cover both known loading changes in a complete workflow and cancellation during settling without another Save or navigation.
- `python-tests-final.txt` records **370/370 Python tests passed, no skips, in 310.722 seconds**, including 13 dedicated transition tests and two new integrated workflow cases. Earlier restricted/failed runs are retained separately. Local socket access was blocked in the sandbox; permitted loopback tests use the existing network allowlist and cannot connect to the rack.
- The unrestricted HTTP check exposed the old test-only five-second full-rehearsal timeout. The complete POST test now has the same 30-second budget as the console; the cancellation boundary test and product time limits were kept unchanged.
- `launcher-validation.json` records `-ValidateOnly`, simulation mode and no process startup. Backend source hash: `dd5c58b3745f173a59b0d18af9445bd570d3978d79026a3932ca52712abd4ca3`.
- All 25 monitored installed-release/settings files match their baseline hashes. The unchanged native candidate DLL is `49cab77c792b532b17b51283654ac9a2621ce1ae0d7058d8f45c8c05951ffd1b`; no native rebuild was necessary for these Python/launcher changes.

## Remaining acceptance

This is the offline transition implementation and rehearsal integration. The shared checks still need fresh C24C validation through the bounded live adapter, under one owned run, with real frame delivery and OCR timings. Quiet-frame handling, unexpected transitions, real interruption/recovery, account continuity and native-window-to-phone completion remain acceptance work. No installed release or live automatic route is promoted by these replay results.

Evidence and exact source bytes are archived under `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261018-farm-transition-holds` with checksums. The earlier live archive is retained unchanged.
