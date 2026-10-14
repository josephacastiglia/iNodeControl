# Candidate timing preflight — offline preparation

13 October 2026. Extends the existing Gate 6 runner and adds the active service
address to the console's connection tooltip/accessibility hint. No live rack
request, desktop control, phone input, receiver restart or promotion ran.

## What changed

The old runner could proceed with an owned or stopped phone, a wrong device
under the expected receiver name, a stalled second phone or a receiver replaced
during preflight. Five targeted regressions fail on the preserved old source.

The runner now requires two advancing, identity-matched streams with stable
receiver PID/session, the lease protocol, and explicit idle/not-stopped input
state before acquisition. Refusals retain observations and cleanup state without
acquiring a lease. Before each trial, a newly owned or changed-generation
observer phone aborts the run; it does not disturb that controller.

UIA mode requires the candidate's exact PID, executable, managed DLL hash and
absolute isolated data directory. It checks process lifetime around the command
line read, refuses test flags/shared settings/vendor defaults, and verifies the
saved endpoint and hover-off profile again before each action. Windows argument
parsing is shared with the existing diagnostics collector.

Each action helper checks the actual connected service, current hover state,
selected phone, mirror mode and visible/enabled button. The console exposes the
active client's origin, not the editable address box; pending reconnect,
unavailability and closure clear it. Existing normal-Disconnect cleanup remains
scoped to the bound process/selection, including if the profile changes.

## Verification

| Check | Result and scope |
|---|---|
| Release console build | Clean; zero warnings/errors; five output files preserved |
| Console self-tests | 409 pass; seven new lifecycle checks, fake HTTP, no native window |
| Existing timing-runner suite | 89 pass; 24 more than the prior 65-check version |
| Negative control | Five unsafe preflights proceed on the old runner and fail the new tests |
| Shared diagnostics suite | 20 pass after argument-parser extraction |
| Runner built-in self-check | Pass |
| Generated action/disconnect scripts | PowerShell parses both; neither executed |
| Protected installed files | All 25 static baseline hashes unchanged; active logs excluded |

Strict path resolution in the managed sandbox refused temporary paths; that
failed attempt is retained. The final offline regression suite ran with a narrow
sandbox exception. Console self-tests also used the previously necessary
filesystem exception. Neither exception enabled live HTTP or desktop actions in
the tests. Two runner tests start only harmless Python children for pipe timing.

`console-manifest.json` records exact sources and output bytes from HEAD
`01e2f60` plus this turn's uncommitted source. `final-source/` preserves those
sources, and `source-manifest.json` includes the runner and diagnostics parser.
The self-test log, parse results and protected-file hashes are alongside this
report. These are local records, not independently attested binaries.

## Limits and next use

Preflight snapshots cannot provide continuous exclusivity, prove physical phone
identity or prevent another controller acting between checks. Kernel leases still
govern every input. Current UIA mode targets C24C only and requires both declared
phones streaming; it is not compatible with a C24C-only kernel smoke profile.

The helper uses UI Automation InvokePattern, not physical mouse clicks. Native
accessibility delivery, cleanup and actual click-to-correct-display timing remain
unvalidated on this build. Heuristic frame changes and the opt-in bitmap timeline
cannot close Gate 6. No gate or known Home/typing defect is marked fixed here.

The next combined review package includes this console and its earlier response
timeline; see `../combined-timing-package-20261013/REPORT.md`. Its preparation is
offline only and is not authorization for a live test.
