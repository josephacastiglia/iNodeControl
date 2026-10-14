# Acceptance of the consolidated candidate

This is the next-test record for the combined candidate, not release sign-off.
Package pointers updated 14 October 2026; the recorded checks ran 13 October.

**Current offline package:** `output/staging/combined-timing-20261013`, with
fresh unused preparation at `output/candidate-runs/timing-20261013`.
This combines the preserved shutdown/recovery kernel with the latest console
response timeline, actual-service tooltip/accessibility hint, image-reader
repair and earlier input/recovery changes. All 692 package inventory entries,
embedded source/build records and native runtime verify. Both exact binaries
validate saved C24C-only configuration without windows, connections, listeners,
receivers or settings writes. The strict prepared-launcher and saved-profile
checks pass. See `analysis/combined-timing-package-20261013/REPORT.md`.

The console has 409 headless self-tests; the existing Gate 6 runner has 89
regressions and diagnostics has 20. The unchanged kernel retains recorded
41 recovery, 207 kernel, 34 frame and 14 fake lifetime checks. These results
belong to their recorded builds; they are not a combined physical acceptance
count. Read `analysis/gate6-preflight-20261013/REPORT.md` and
`analysis/fleet-shutdown-20261013/RESUMED-REPORT.md` for exact scope and limits.

The prepared kernel remains C24C-only. It does not satisfy the Gate 6 runner's
separate requirement for both declared phones to stream during timing trials.
UIA invocation, kernel screenshots and internal bitmap timings do not prove
physical-click-to-correct-display latency. No UIA helper was executed in the
latest offline checks.

The previous `combined-shutdown-20261013` and `combined-recovery-20261013`
packages/preparations remain unchanged as historical evidence. The root
launcher is preserved as inert source, not installed or used to start this
candidate. Keep all earlier live results tied to their original binaries.

**13 October update:** the first authorized candidate window failed before
phone input: UxPlay's startup checks required playback/autodetect plugins absent
from the reduced runtime. The original release was restored and both phones
were confirmed mirroring at 04:31 UTC, unowned at generation 0. No C24C/C241
input or FKA change was sent. See `analysis/candidate-live-20261013/REPORT.md`.
Six runtime plugins were added and production renderer startup now passes
offline. The package used for that retry, `output/staging/combined-runtime-guard-20261013`,
also includes a kernel guard that refuses missing/empty startup plugins before
hardware or receiver startup. Its 206 kernel checks and actual CLI comparisons
pass; console, receiver and repaired runtime bytes are unchanged. See
`analysis/runtime-startup-guard-20261013/REPORT.md`.

**Second window, 04:56–05:08 UTC:** this exact package started and mirrored C24C
with zero receiver restarts. Pointer moves, Calculator tap, left/right page
swipes and API Stop/Resume/release passed scoped smoke checks. The upward
bottom-edge swipe did not achieve Home and is recorded as failed. The operator
returned Home physically. Both original receivers were restored live/free at
05:08 UTC; no typing, FKA changes or C241 input. Candidate console UI/timeout/
diagnostic-export checks remain unrun. See
`analysis/candidate-retry-20261013/REPORT.md`. Do not launch the original
incomplete runtime again or treat these scoped results as full acceptance.
The current prepared files are recorded in
`analysis/combined-timing-package-20261013/preparation.json`. The setup script only
copies files and invokes explicit offline validation modes. It cannot launch a
normal kernel, receiver or console window.

## Prepared scope

- Immutable review package: `output/staging/combined-timing-20261013`.
- Fresh unused run: `output/candidate-runs/timing-20261013`. Both binaries pass
  offline validation; console validation runs from a separate matching copy so
  its generated report cannot invalidate the prepared run. The final launcher
  `-CheckOnly` passes. Preserve this inventory until an approved launch.
- Historical live run: `output/candidate-runs/runtime-guard-20261013`. It contains
  receiver logs and is not the new candidate. Its console preparation also has
  a validation report that the strict launcher correctly rejects; the new
  preparation avoids that problem without weakening the guard or altering the old run.
- Kernel configuration: a reviewed structural copy of the installed launcher's
  saved C24C records, selected without changing its identity or calibration.
  One receiver, C24C input only; C241 is absent from this candidate configuration.
- Console: a fresh data folder, explicit `http://127.0.0.1:9913`, hover tracking
  off. It uses the recorded console with retryable ownership-scoped release and
  cleanup history in diagnostic exports. Earlier prepared runs retain their older
  console and remain historical.
- Receiver: the preserved report-parser memory fix and its verified runtime.
  The older runtime's live launch on 13 October failed before video due
  to missing startup plugins; the corrected runtime passed the scoped C24C retry.

Preparation does not grant a test window. Starting this kernel uses the working
port and receiver identity, so it cannot coexist with the installed kernel. A
later swap must follow the interruption/restoration procedure in
[RELEASE-STAGING.md](RELEASE-STAGING.md). Recheck current processes, ownership,
file hashes and physical identity then; old PIDs and status captures expire.

## What can proceed without screen control

| Work | Evidence required | Current status |
|---|---|---|
| Exact candidate files | Source/build manifests, dependency inventory and archived hashes agree | Recorded; checks do not establish physical performance |
| Saved configuration | Both exact binaries validate the isolated directories and address without windows, listeners, receivers or settings changes | See preparation record |
| Input/recovery regressions | Fake transport covers queued work, ownership, cleanup, retries and failure reporting | Existing offline reports; retain their exact build scope |
| Read-only rack observation | Verified process/build identity and API status, without input or service changes | Only when the existing rack is available; observation of the installed build is not acceptance of this candidate |
| API-driven accuracy | Predeclared targets, reviewed reference frames, single attempts, isolation and cleanup evidence | Harness ready offline; physical calibration and qualifying run still pending |

Use the existing tools and evidence. Do not replace the consolidated accuracy
runner or the existing console-latency runner with a parallel implementation.
No unattended test may silently promote a package or start the rack.

## First coordinated candidate window

Run a short smoke check before a long accuracy or endurance run. The initial
window is C24C only; a wider rack stage requires the corresponding physical
scope and configuration. Record each case as passed, failed, blocked or unrun.

| Order | Case | Observable acceptance |
|---|---|---|
| 1 | Startup and identity | Exact candidate processes and intended receiver; isolated settings; C24C has the expected physical identity; connecting/hovering with tracking off sends no input |
| 2 | Basic targeting and gestures | Taps reach predeclared varied targets; drag final point is retained; button release, long press and both swipe directions behave as expected |
| 3 | Stop and timeout | First Stop cancels queued work; no replay; one accurate timeout/not-sent notice; explicit Resume; recorded held-input release confirmation or an honest unknown result |
| 4 | Disconnect/reconnect/close | Old control is released before a new client becomes usable; closing waits for cleanup; a failed release is visible and the receipt survives; no stale action reaches a later session |
| 5 | Video and diagnostics | Fresh/old/unavailable states match actual delivery; export through the real button contains matching build, mapping, input, video and error evidence; after disconnect, historical cleanup remains available and clearly separate from current state |
| 6 | Restoration | Candidate leases/processes accounted for; original files match the saved hashes; original launcher and required mirroring are usable again |

Do not infer success from HTTP code 0 alone. Capture the visible result and
timestamps. Preserve failed trials and unknown cleanup; retries do not turn an
original failure into a pass. Scripted input remains in the lease-aware kernel
path, with no raw HID bypass.

Home still has the known Tab side effect and App Switcher with FKA Off is not
accepted. The missing-space issue is explicitly deferred. Avoid using those
known defects to silently contaminate another test; they remain open Gate 5
requirements and are not waived by this plan.

## Progression after the smoke check

1. **Accuracy/identity:** use `tools/gate4_1000_tap_suite.py`, reviewed target
   references and its original five-second single-attempt rule. At least
   995/1,000 hits; zero unintended-phone actions, double-clicks or stuck inputs.
   Cover the varied positions, transitions, recovery and physical pairs in
   `FINISH-CRITERIA.md`. A C24C-only run is a scoped result, not a 19-phone pass.
2. **Recovery:** test disconnect, receiver failure and exhausted retries only
   in a separately agreed fault window. Preserve the correct receiver name and
   manual-recast instructions; do not promise immediate rediscovery.
3. **Responsiveness/video:** use the existing Gate 6 console-action timing path,
   not API elapsed time. Keep 100 observations per category/profile and all
   misses; evaluate the 500 ms / 2 s percentile rules. Measure incoming unique
   and actually displayed frames over the same interval for Gate 7.
4. **Scale/endurance:** complete 2 → 4 → 8 → 19 with identity/isolation checks,
   then the required 8-hour and 24-hour runs on the final supported setup.
   Declare workload, warm-up and resource budgets before starting.
5. **Release:** complete real diagnostic export, clean-PC loading, dependency
   obligations and operator setup/update/rollback checks. Promotion remains a
   separate explicit decision after evidence meets the written criteria.

Gates 1–2 and the old scoped Gate 4 record retain their historical evidence.
They are not automatically fresh acceptance of every changed candidate binary.
