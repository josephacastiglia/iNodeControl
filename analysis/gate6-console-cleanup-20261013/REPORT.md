# Timing-runner console cleanup — 13 October 2026

## Outcome

The existing Gate 6 runner now attempts normal candidate Disconnect after any attempted UIA input, including an incomplete helper response, visual miss or operator interruption. It no longer treats killing its helper as sufficient cleanup. This is test tooling only; no product source, binary, release package or installed launcher changed.

## Behavior

- Possible console ownership is marked before both setup and measured UIA actions. A timeout can no longer bypass finalization by occurring before a success flag.
- Cleanup opens Settings and invokes Disconnect once. The console's existing path cancels pending work and releases its own lease tokens. There is no forced release, Stop, Home, API input fallback, retry or automatic reconnect.
- The runner waits for the console's exact disconnected/released state, then reads kernel input status. Confirmation requires both that console result and explicit unowned/inactive/not-releasing/no-release-failure fields for every planned target. Missing, malformed, duplicate or owned rows remain unconfirmed. A free phone alone cannot prove the console disconnected.
- The helper retains its 20-second overall deadline; the script allows two seconds to find Disconnect and twelve seconds for its completion. The following read-only status request has a three-second socket timeout. Only the helper can be terminated; the console is never killed.
- Every helper checks the candidate executable, process creation FILETIME and window process. PID reuse or an explicit path mismatch is refused. Selection and mirror checks also apply to cleanup. If a guard fails, cleanup is recorded as uncertain rather than bypassing it.
- The run manifest records process identity. Cleanup records distinguish attempted actions, console confirmation and target status. Original trial failures survive cleanup failure. A final `done` message is printed only after cleanup succeeds.
- The dedicated candidate window remains open, disconnected. Restoring the installed console remains part of the coordinated operator workflow. Failure before any UIA attempt is recorded as `no_action_attempted`, not as proof that no pre-existing lease exists.

## Verification

| Check | Result |
|---|---|
| Six initial regressions on preserved old runner | All fail: five assertion failures and one error |
| Full Python runner suite | 65 passed; 21 new checks |
| Built-in synthetic self-check | Passed |
| Generated action and Disconnect PowerShell scripts | Parse-only passed; never executed |
| Native process metadata | Read only the test process; creation FILETIME exactly matches .NET |
| Protected installed/configuration/settings files | All 25 static hashes match the saved restoration baseline |

The tests replace all rack requests and UI helper invocations with fakes. Existing subprocess tests launch harmless Python children only. The new native identity check reads its own test process; the independent comparison asks PowerShell only for that process's start time. Neither generated UIA helper was executed, no native application window was controlled, and no current rack status was queried. Receiver log files, which can change during ordinary use, are excluded from the static hash comparison.

`negative-tests.txt` preserves the failures before the repair. `runner-tests.txt`, `self-check.txt`, `powershell-parse.json` and `verification.json` preserve final results. `source-manifest.json` identifies exact source snapshots. The negative test failures do not mean the console product itself failed to release: the defect was the runner never requesting that cleanup.

## Limits and next step

This does **not** establish that real WPF accessibility controls are found and invoked correctly on the candidate desktop. That still needs a coordinated test, including a helper timeout after the console accepts input. Changed selection, a closed/unresponsive candidate, unavailable controls or unconfirmed release stop the run with explicit uncertainty; no disruptive fallback is attempted.

Candidate isolation and complete ownership/preparation preflight remain the next useful offline extension. Continue in this runner. Actual physical-click-to-correct-display timing, per-trial UIA setup and reviewed visual correctness are still open. No release gate is advanced, and missing-space/FKA work stays deferred.

All changes remain local on `local/combined-candidate-20261012`, based on `1a4926d`. Nothing is pushed, promoted or deployed. Evidence is copied and hash-verified in `iMouseXP-2.0-evidence-archive/20261013-gate6-console-cleanup`; see `archive-receipt.json`. This archive is on the same disk, not an off-machine backup.
