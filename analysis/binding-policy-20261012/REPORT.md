# Unsupported service actions in the console

12 October 2026. Offline work on the combined candidate. No screen control,
phone input, live API calls, service restarts, installation or push.

## Problem and change

The ownership kernel deliberately refuses live board binding, AirPlay
connect/disconnect commands, and board restart. The console still offered those
buttons. Its Auto-bind loop swallowed each refusal and could incorrectly advise
checking a cable or AssistiveTouch after trying every board. This was not a
hardware diagnosis. The kernel source establishes these unsupported operations
in ApiServer.Dispatch and InputRouter.DispatchAsync.

The console now applies an explicit policy for its ownership connection:

- Bind, Unbind and Auto-bind are disabled. The selected saved assignment remains
  visible, with an explanation that setup changes require maintenance.
- Cast/Disc and Start/Stop casting are disabled in both locations. Visible help
  and disabled-button tooltips direct the operator to the phone's Screen
  Mirroring menu and its assigned receiver.
- Both Restart board controls are disabled and explain that restart is not
  implemented. Diagnostics remain available.
- Queued Auto-bind and general action handlers stop before probes, busy-state
  changes or per-phone attempts. The API also refuses these unsupported routes
  locally with code 41, protecting callers that bypass the button handlers.
- Read-only lists, normal mouse/keyboard input, Stop, Resume and release retain
  their existing paths. Explicit legacy/test mode retains its previous command
  behavior; this is a client policy for the current ownership kernel, not an
  inferred or newly negotiated server capability.

Removed the unproven claim that Auto-bind cannot assign the wrong board. Empty
device-list, disconnected and unsupported-text messages no longer direct the
operator to the vendor console. The character set and typing implementation
are unchanged. Missing-space work remains deferred.

## Evidence and limits

The final Release build has zero warnings/errors and **271 self-tests pass**.
Fifteen new checks cover pre-request refusal, direct-command bypass, all four
unsupported routes, absence of POST/discovery/lease requests, read-only
inspection, supported-route availability and explicit legacy compatibility.
The existing ownership, cancellation, text, frame and persistence tests also
pass in this build. All HTTP transport in the suite is mocked.

A separate source copy with the central API guard removed fails with
`Unexpected write in read-only binding check`, as expected. The source hash
inventory records the single mutation for that control; its ApiClient source
before mutation is identical to the final candidate's. Its window source
precedes the additional local general-action entry guard, so this negative
control specifically validates the API boundary, not the UI handler.

Five UI checks were added for disabled binding/actions, assignment/help text and
queued Auto-bind preserving preview without sends. They compile but **were not
run**: no UI suite or window was opened. Actual rendering, tooltips, clicks and
physical phone behavior still require later UI/live acceptance. This work does
not complete guided rack identification, enable missing features or close Gate 5.

Final tested component:

- `candidate-console/`, paired with `candidate-console-manifest.json`.
- DLL SHA-256: `4f8a5fb8f333fa98d0ce9ca427c7429628bc7b54bc9e5a0d25cdd181cfe53186`.
- The source record contains the exact uncommitted snapshot at build time; its
  base revision is 0230f0f. That base alone does not contain the changes.
- Prepared offline only: `output/candidate-runs/service-policy-validated-20261012/`.
  Explicit 9913 endpoint, isolated profile, hover tracking off; not launched.
- Earlier console-build/final-build/service-policy-build/final-console artifacts
  and service-policy-ready preparation are retained as intermediate evidence.
  Negative builds are deliberately broken and are never candidates.

The kernel is unchanged and its persistence manifest still verifies. Its latest
179-test result belongs to the preceding persistence run, not a rerun here.
The existing full review package still contains the preceding persistence
console; it was not silently replaced with these new bytes. The updated console
component and operator guide are preserved separately for the next combined cut.

Installed kernel/console/receiver hashes and operator settings content/timestamp
remain unchanged. See protected-files.json. No physical release gate was signed
off and nothing was promoted.

Source and evidence are committed locally as `1b35159`. The archive
`../iMouseXP-2.0-evidence-archive/20261012-service-actions/` contains 155 files
(23,312,450 bytes) plus its checksum inventory. It preserves the exact tested
source bytes, component builds, negative controls, prepared-but-unlaunched copy,
operator guide and a verified single-branch Git bundle. All hashes verify. It
does not duplicate the earlier full native runtime package. See
archive-verification.json. No backup branch was bundled and nothing was pushed.

## Next investigation

The hover-move pump shares pending coordinates, target IDs and its running flag
between UI and worker threads without synchronizing take/clear/stop. A new
request can arrive between reading the old point and clearing the pending slot,
or while the worker decides to stop. Investigate those interleavings with
deterministic fake transport; preserve target identity and Stop/selection
cancellation. This source risk is not a claimed cause of an earlier phone or
desktop-tool observation.
