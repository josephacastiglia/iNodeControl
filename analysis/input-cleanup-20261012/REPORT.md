# Awaited connection cleanup

12 October 2026. Combined candidate, offline. No screen control, real service
request, phone input, receiver/kernel restart, deployment or promotion.

## Findings and changes

The previous window-close handler called synchronous `ApiClient.Dispose`, which
started owned-input release without awaiting it. Disconnect and reconnect also
discarded the old client before its release response. A scope release detached
its token before awaiting HTTP, so a concurrent close could see no token and
finish before that release answered. See the source markers against `2349ce5`.

The console now retires clients through a shared cleanup tracker. Input and
connection lifetimes are cancelled first. Reconnect waits for retired clients,
and only the newest pending connection can become active. Normal window close
waits before allowing WPF to finish closing. Test-mode success and failure exits
use the same awaited path; an unconfirmed cleanup fails the test exit.

`ApiClient.CloseAsync` is idempotent and returns confirmation per phone. Cleanup
waits for earlier Stop, Resume and release operations and any held-button cleanup.
Independent phones release concurrently with their own tokens. Stop/Resume do
not enter the ordinary action queue. Closing rejects new commands immediately,
invalidates a pending Resume and never sends a new Stop or automatic Resume.

A late lease returned by a cancelled acquisition now retains its release outcome.
A failed board release is not turned into success merely because the lease token
was removed. The existing ownership protocol remains in use; no raw HID path,
new endpoint or replay was introduced.

Each API client has a 15-second default cleanup budget. If that expires, HTTP is
disposed and the result stays unconfirmed, even if a nonstandard transport later
finishes. Connection cleanup does not guarantee physical release: confirmations
describe the service's response/HID write, not observation of the iPhone.

Bounded cleanup receipts are saved atomically in the active profile. Historical
unconfirmed-release evidence is retained separately across a later clean close.
Receipts exclude lease tokens and raw service errors. Disconnect shows uncertain
cleanup in status/Activity. Normal close warns before exit if cleanup or its
record could not be confirmed. Forced termination, crash and OS shutdown remain
outside the guarantee of normal awaited closure.

The operator guide describes the receipt files. Isolated profiles do not write
operator preferences or an adjacent settings mirror. Automated window tests keep
their cleanup records under `qa` before removing the temporary profile.

## Verification

- Release build: zero warnings/errors.
- **348 console self-tests pass**, including 34 new checks. Every transport is
  in-process and fake; no listening server or hardware is used.
- Tests cover delayed release, idempotence, closed-client rejection, per-phone
  parallel release and token scope, failed/missing release, in-flight scope
  release, completed Stop, a transport ignoring cancellation, cancelled acquire,
  tracker changes during a drain, bounded/redacted receipts and atomic-save
  failure without destroying the previous record.
- Nine lifecycle checks instantiate the actual WPF window without `Show` and
  assert no native window handle exists. They cover rapid reconnect, overtaken
  connections, close waiting for release, receipt persistence and legacy readiness.
  These are not mouse, rendering, dialog or physical acceptance tests.
- Two deliberately broken scratch copies fail the intended new checks: removing
  the operator wait allows premature close; removing the reconnect wait activates
  the next connection too early. All other project files match the tested source.
- The first negative-copy preparation stopped on an ambiguous replacement anchor;
  it was corrected before either negative build was executed.
- Installed console, kernel, receiver and operator-settings content hashes match
  the prior record. This comparison does not claim unchanged timestamps.

See `self-tests.json`, `negative-results.json`, `build-result.json` and
`protected-files.json`. The kernel is unchanged; its earlier 179-test result is
historical and was not rerun here. Typing content, chunk size and FKA are unchanged.

## Exact component and package

`candidate-console/` contains the five runtime files copied from the tested
`lifecycle-build/`. `console-manifest.json` verifies all 34 source inputs and five
output files. Its informational base is `2349ce5` plus the recorded source
snapshot, not a claim that the base commit alone contains these fixes.

DLL SHA-256: `54a9d20b4aafa553978b5fb87c2eaa7e34c9ae9d769ec0b76440065d3e93a1fd`.

`output/candidate-runs/input-cleanup-20261012/` is prepared with a separate data
folder, explicit port 9913 and hover tracking off. It has not been launched.

The new review package is `output/staging/combined-input-cleanup-20261012/`.
It combines this console (including the binding policy, hover and drag fixes)
with the previously verified persistence kernel and native receiver/runtime.
It retains the exact source snapshots and current operator/preparation guides.
It is review-only: redistribution notice gaps, clean-PC startup and physical
acceptance remain open. Earlier packages remain unchanged.

## Next

Use the consolidated candidate for the remaining acceptance preparation. Recheck
current rack availability read-only before deciding which API-only acceptance
work can run within existing permissions. Keep the installed release unchanged,
the first-space investigation deferred, and physical gates explicitly open.
