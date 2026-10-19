# Marketing draft interface integration — 18 October 2026

**Offline integration complete; fresh phone acceptance pending.** The two previous
C24C runs validated the bounded diagnostic, not this new job/interface path.
No rack software, phone input, PC control, publishing or messaging was used here.
Nothing is installed, promoted or pushed.

## What is now connected

The native carousel editor has **Check phone draft…** beside its existing review
and offline rehearsal controls. Its window starts the bounded save/reopen check,
polls the durable request, requests cancellation, lists previous runs, and opens
retained frames after cleanup. It saves the request ID and candidate storage
identity before POST. Closing/reopening the window retrieves that same request;
it never replays a phone action. A changed editor revision does not prevent
retrieval of the original result.

The backend snapshots the selected saved revision before admission, uses the
existing single-worker `FarmJobs` journal/OS lock, and retains the workflow journal
and immutable observations. Duplicate submissions retrieve the original request.
A backend restart, an orphaned admission or an uncertain Save remains review-only.
Status/frame/history reads do not contact a phone. Cancellation before admission
leaves a durable tombstone. Losing the interface heartbeat cancels the worker.
Graceful backend shutdown requests cancellation and waits up to 20 seconds for
its worker; forced process death cannot guarantee immediate lease cleanup.

The extracted sequence keeps the verified 19 actions, two saves, all-slide and
full-caption checks, account boundaries, navigation-icon pixels, C24C ownership,
fresh-frame checks and fixed bounds (120 seconds overall, eight seconds/four
captures for settling, 1,500 ms frame age). Only four navigation-icon crops are
packaged in product source; full phone screenshots remain in the evidence archive.
The historical diagnostic files were left unchanged.

Two reporting edges were fixed: failed cleanup revokes `savedDraftVerified`, and
cancellation/deadline refusal at the last journal boundary is recorded as
`not_sent`. Once transport begins, a lost answer stays `outcome_unknown`.

## Deliberately bounded first candidate

- Existing Instagram draft on **C24C / @xs.halle.xo**, already prepared on the phone.
- Only the three-slide test content and exact caption previously validated are
  eligible. Content fingerprint:
  `fa226761c643c72800a2fada366652ae4baa49177cea3e76e5280b71f673a058`.
- No media import, text entry, FKA/settings changes, arbitrary coordinates,
  arbitrary accounts or endpoints, C241, publishing or messaging.
- Off by default. Enabling requires explicit live mode and a local configuration
  pinning the isolated **9916** kernel build and C24C UID. General legacy rack
  commands are disabled in that configured backend; it cannot fall back to 9913.
- A terminal uncertain run keeps the UI bookmark for review. There is no automatic
  resume or “try Save again” control. A verified same-session save/reopen is not
  evidence of persistence across an Instagram/iOS restart.
- `integratedLiveValidated` and `productionAdapterAccepted` remain false.

## Verification

| Check | Result |
|---|---|
| Broad guarded Python suite | 388 passed, no skips (`python-tests.json`, `python-tests.txt`) |
| Final focused service/HTTP/transport checks | 21 passed, no skips (`focused-tests.json`); includes six checks added after broad discovery |
| Extracted sequence and service/evidence link | 12 passed (`extraction-tests.txt`); retained phone images plus fake protocol/OCR metadata, not new live/OCR accuracy evidence |
| Native Release build | Zero warnings/errors; final source/build hashes in `validation.json` |
| Native headless checks | 546 passed; every command used mock transport, no window handle for the new interface |
| Launcher | Both default and explicit candidate `-ValidateOnly` paths passed; separate arguments preserve paths with spaces; no process started |
| Protected files | All 25 prior release/settings hashes unchanged |
| Rack | Read-only process check found no console, kernel or UxPlay receiver running |

The focused set overlaps 15 broad-suite checks: **394 distinct Python product
tests**, not 409. The 12 retained-frame checks are additional. Final targeted
checks cover the implementation added after the broad suite started. No skipped
or simulated check is presented as live acceptance.

Fault coverage includes cancellation before admission, after Save, at the final
pre-dispatch journal boundary and on heartbeat loss; lost submit/Save/reopen
responses; graceful shutdown; a real child process exiting after an uncertain
Save; candidate identity changes; stale frames/OCR failure/wrong account/caption;
record/package/frame corruption; changed revisions; different backend stores;
cross-origin requests; and forbidden transport destinations/functions.

The linked sequence test retrieves every retained frame through the service and
then proves corrupted evidence cannot be shown as a successful result. Synthetic
screens need fewer captures than the previous live runs because those live picker
transitions faded; action count and recognition requirements are unchanged.

## Prepared files and next window

Console: `output/codex-farm-interface-20261018/iMouse2.exe`.

An offline, read-only SQLite snapshot copied just the original test draft and its
assets into `output/codex-farm-interface-20261018/draft-workflow-data/backend/`.
The source library is unchanged. Draft ID `eeb59816-5805-4169-aa1c-d91fe1e2c14f`,
revision 5. `offline-preparation.json` records package/content hashes and paths.
`candidate-workflow-config.json` pins the previously validated test kernel;
writing it did not start or contact that kernel.

The separate candidate launcher accepts `-DraftWorkflowConfig` and uses isolated
settings with hover tracking off and console address 9916. Its default remains
simulation and preserves the existing simulation draft library. Installed release
launchers and settings were not edited. Do not launch it merely to inspect this
report: the next live run needs an explicit coordinated phone window.

Next: recheck source/binary hashes, process/port state and the prepared C24C-only
kernel configuration; start only that isolated receiver; ask the operator to cast
C24C and open the authorized profile. Exercise the native request path without
PC control, verify one complete save/reopen, then a bounded interruption and
read-only result recovery. Prove no replay, final account, cleanup and evidence
integrity; restore the initial rack state. Leave C241 and FKA unchanged. Retain a
new attempt folder instead of reusing the earlier diagnostic evidence.

Expanding to arbitrary drafts/accounts/layouts, app-restart persistence, unattended
recovery navigation and publishing are not accepted by this work.
