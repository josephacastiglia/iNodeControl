# Cleanup history in the diagnostic export

12 October 2026. Offline product repair; no new physical acceptance claim.

## Result

The existing Export diagnostics action now includes the active console profile's
latest cleanup receipt and retained unconfirmed-cleanup warning. Previously those
files had to be collected separately. The same collection works after Disconnect,
when the old connection's cancellation token has already been cancelled.

Each receipt retains its event timestamps and file checksum, and is labelled
historical, not current phone ownership or physical button state. A later clean
close does not erase the earlier warning. Missing files are unknown; invalid,
oversized, unreadable or cancelled sections are unavailable without losing other
sections. A malformed local receipt marks the export partial even when every
service request succeeds. A first-run profile with no history does not.

The reader uses only the explicitly supplied active directory and two fixed
filenames. It never falls back to operator data. Reads run off the UI thread and
share the existing five-second collection budget. Files are bounded to 4 MiB,
32 connection records and 64 saved phones per connection. Duplicate keys and
contradictory confirmation/counts are rejected; omitted phones remain explicitly
marked. Exported fields exclude raw failures, unknown fields and URL credentials.
The report schema is now 4. No receipt is rewritten by collection.

## Verification

- Release build: zero warnings or errors (`final-build.txt`).
- **372 console self-tests pass**, including 24 new checks (`self-tests.json`).
- The real window's shared collector was exercised after its actual disconnect
  transition, in an isolated profile with no service and no native window handle.
  No window was displayed. This is not a real button/dialog test.
- A separate source copy with only `dataPath: _dataPath` replaced by
  `dataPath: null` fails exactly **The actual window export reads its isolated
  receipt after disconnect**. See `negative-change.json`, `negative-build.txt`
  and `negative-failure.txt`. Product source was not reverted for this control.
- File-lock checks ran with normal temporary-file permissions, not a sandbox
  failure substituted for a real lock. The good run exits 0; the negative exits 1.
- The kernel is unchanged; its prior 179 self-tests were not rerun here.

The first package-preparation attempt looked for the failure file under `qa`;
the test runner actually saves failures beside the executable. The path was
corrected before any component/package directory was created. This did not
change the negative result or product source.

## Build and preparation

`console-manifest.json` records all 36 source inputs and five output files copied
from the successful test build. The build includes the recorded working changes
on base `4b013fa`; its informational commit stamp is not a clean-source claim.
Console DLL SHA-256:
`fc6f39b2db3cad3185e673d7b5794444a78b5ef6f867ef7549159e4e0720bcde`.

`package-result.json` records the new immutable review package and verification.
The unchanged kernel, receiver and native runtime are reused with their existing
provenance. Earlier packages remain intact. The operator guide now explains that
cleanup history is included and remains separate from current input status.

`prepare_candidate.py` reuses the prior C24C-only preparation procedure with only
the recorded console/package/run paths advanced. `preparation.json` and
`run-inventory.json` record the result. The exact console and kernel are invoked
only in their explicit no-window validation modes. This does not start the rack,
connect to a service, test mirroring, send input or authorize a later launch.

Installed binary and operator-settings content hashes are checked against the
previous record. No desktop automation, phone setting change, kernel/receiver
restart, deployment or push occurs. The missing-space investigation stays deferred.

## Remaining acceptance

Use `docs/CANDIDATE-ACCEPTANCE.md` for the physical candidate window. The actual
export button/save dialog and live state correspondence remain untested here.
Home, App Switcher, real accuracy/latency/video/recovery, all-rack identification,
scale, clean-PC loading and final endurance still require their recorded work.
No finish criterion is marked passed by this change.

The external preservation receipt is `archive-verification.json` once completed.
