# Accuracy harness and recovery — 12 October 2026

## Completed offline

The prepared Gate 4 v2 implementation is consolidated into the original
`tools/gate4_1000_tap_suite.py` path. The old v2 entry point is a compatibility
shim importing that same module. Existing target configuration and mock tests
are reused. There is no second maintained accuracy runner.

The receiver supervisor now handles shutdown and wait failures correctly, with
bounded retries and explicit failure when child cleanup is unconfirmed. All
changes remain local, uncommitted and unpromoted.

## Accuracy and evidence safeguards

- Reuses varied targets, movement distances, interruption recovery, reviewed
  reference frames and isolation checks from the prepared v2 implementation.
- Refuses unknown ownership, ongoing release and failed cleanup before input.
- Refuses existing run IDs and calibration references rather than overwriting
  evidence. Automatic resume is disabled; a new run needs its own record.
- Records a failed/uncertain trial, stops further input and attempts scoped
  release. Release failure prevents a “complete” result. Interrupted runs are
  labelled stopped. Partial acquisition cleans up only returned approved tokens.
- Suspected crosstalk, stuck input or a double-click stops before another Home
  command. A stale token counts as refused only on explicit kernel code 33.
- Failed setup conditions do not count as passed trials. A short mock run cannot
  pass the 995-of-1,000 criterion, and no summary signs off the overall release.
- Rejects paths in generated names and calibration references outside their
  directory; reference frames must match the expected dimensions.

Historical results are unchanged. The available legacy source and original v2
files are preserved under `before/`, with checksums. That snapshot does not
recover the missing exact source version used for the September live run.

The 14 existing scenario tests now use registered **in-process** mock requests.
An unregistered URL fails instead of falling back to HTTP. These checks open no
network listener or socket. New guard tests replace service boundaries with
fixtures and make no phone or service calls.

## Receiver supervisor fixes

The first 10 focused tests exposed seven failing cases. One additional cleanup
test failed before its repair. The final 12 cases pass.

- Cancelled runs finish as stopped rather than “running” with no child.
- A child is disposed once, including repeated Dispose and startup races.
- Unexpected wait exceptions use the existing bounded recovery budget.
  Only cancellation requested through the supervisor's linked token is shutdown.
- Failed cleanup reports failure and prevents a replacement from starting.
  Disposing the supervisor afterward does not hide that failure.
- A second RunAsync cannot launch another receiver through the same supervisor.
- Invalid delays fail before launch; a failed receiver does not stop a healthy peer.

Retry limits remain finite. No automatic phone recasting or rack restart was
added. This tests supervision with fake handles; it is not proof of iPhone
rediscovery or actual operating-system cleanup under every fault.

## Verification

| Check | Result |
|---|---:|
| Existing accuracy scenarios, in-process mock | 14 passed |
| Accuracy run/evidence safeguards | 17 passed |
| Focused receiver recovery checks | 12 passed |
| Existing kernel self-tests, simulated input | 70 passed |
| Scratch Release kernel build | 0 warnings, 0 errors |
| Kernel source/build manifest verification | 19 source inputs and 6 build files match |
| Canonical self-check and example offline plan | Passed; 1,000 planned trials for one enabled phone |

**113 tests passed in total.** The initial guard run had five failures and one
error across eight checks; those results and the failed recovery checks are
preserved alongside final logs. No UI suite was run.

The first full kernel self-test attempt hit a Windows sandbox access restriction
when connecting its own randomly named synthetic frame pipe. The same scratch
build was then run with approved sandbox escalation and passed all 70 checks.
`--self-test` returns before hardware initialization. It uses fake transports
and synthetic frames; it starts no AirPlay receiver or real kernel listener.

## Preservation and scope

The working installed kernel, console and receiver are unchanged. No phone
input, desktop control, settings changes, receiver advertisement, installed
process restart, deployment or push occurred. The earlier receiver memory fix
and other uncommitted work remain intact.

The scratch kernel comes from `local/coordinator-work`, not a promotion of the
separate console candidate. Its precise source and output hashes are recorded
in `kernel-manifest.json`. Final artifacts and source snapshots are preserved
locally under `../iMouseXP-2.0-evidence-archive/20261012-accuracy-recovery/` with a
verified SHA-256 inventory.

## Still open

Real target calibration, varied physical taps, full-rack mapping and recovery
acceptance require a future coordinated phone window. The harness still uses
screen-level classifiers and cannot independently prove that a static image is
fresh. Home's Tab side effect and the deferred FKA typing issue remain open.

Next offline work can strengthen frame freshness/display accounting and failure
diagnostics. Nothing in this record authorizes live tests or installation.

Usage: `tools/gate4_v2/README.md` and `tools/recovery_tests/README.md`.
