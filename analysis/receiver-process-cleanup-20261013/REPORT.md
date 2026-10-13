# Confirm receiver exit and clean partial starts

13 October 2026. Offline repair after `61e7d4d` on
`local/combined-candidate-20261012`. No rack API, UxPlay receiver, desktop control,
phone input, FKA change or installed-release operation occurred. No gate advanced.

## Failure and repair

The old receiver constructor started the child and then attached its two log
readers without failure cleanup. Its disposal requested process-tree termination
and immediately discarded the process wrapper. A partial start could therefore
orphan a child, and successful disposal did not establish that the root exited.

Startup/disposal were first extracted behind a narrow process adapter with their
original ordering intact. Eight of nine initial fake-process checks failed:
delayed exit allowed premature replacement, reader/partial-start errors leaked
ownership, unconfirmed cleanup retried, and repeated disposal ran twice. The
already-exited case passed. Original extraction, supervisor and test sources,
binary and log are retained in the `before` record.

The production `AirplayProcess` now delegates lifecycle ownership to
`ReceiverProcessLifetime`; arguments, environment, names and logging are unchanged.

- After requesting termination, wait up to five seconds for the receiver root
  to exit before disposing its wrapper. Concurrent/repeated disposal does not
  send duplicate termination requests. Natural exit racing a kill is accepted
  only after exit is observed.
- If Start or either reader initializer fails after a child exists, clean it up
  before rethrowing the original startup error. A failure before child creation
  disposes only the unstarted wrapper. A false Start result is refused.
- If exit or cleanup cannot be confirmed, throw a typed cleanup failure carrying
  the last known PID. The supervisor treats that failure as terminal even during
  startup/cancellation: no replacement, both startup/cleanup errors retained.
  Confirmed cleanup still permits the existing bounded retry policy.

The existing process-tree kill policy is unchanged. The new wait confirms the
**root receiver only**, not every descendant or completion of every log callback.
This distinction follows the documented [Kill semantics](https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.process.kill)
and [bounded WaitForExit semantics](https://learn.microsoft.com/en-us/dotnet/api/system.diagnostics.process.waitforexit?view=net-8.0).
It is not a claim that the historical AirPlay rediscovery issue is fixed.

## Verification

| Check | Result |
|---|---|
| Original extracted lifecycle | **1/9**, eight intended failures |
| Final deterministic lifetime cases | **14/14**, fake processes only |
| Real hidden child-process cases | **6/6**, every created child exit confirmed through a separately retained handle |
| Delayed real termination | Replacement began only after root exit; cleanup about **237 ms** including an injected 200 ms delay |
| Actual exit deadline | Deliberately ignored termination request failed after about **5,014 ms**, no replacement |
| Recovery/logging regressions | **29/29** |
| Final kernel self-tests | **207 passed**, fake HID and synthetic private pipes only |
| Release builds | Zero warnings/errors |

The real tests launch only hidden copies of `ReceiverProcessTests.exe`. One
invokes the actual `AirplayProcess` constructor and checks both output logs;
the others wrap real `Process` objects with injected reader/monitor/termination
faults. No listener, network announcement, UxPlay, HID or UI is included. Tests
explicitly terminate their own deliberately unconfirmed helpers in `finally`.
`final-real-process-tests.txt` confirms all six retained handles exited, and
`helpers-after-final-run.json` is empty.

### Test-runner correction

The first real run printed 6/6, but its `using` scope selected an explicit
interface disposal method intended only for the raw wrapper. It skipped the
test-only cleanup of two deliberately unconfirmed live helpers. The first result
is **not accepted**. Those helpers had a 20-second self-exit failsafe; the later
inventory was empty. That observation does not supply per-child exit timing.
The first source and log are kept as `RealProcessTests-first.cs.txt` and
`first-real-process-tests-incomplete-cleanup.txt`; its executable was superseded
during rebuilding, so it is not claimed as an exact archived build.

The corrected runner calls its cleanup explicitly in `finally` and fails unless
the created/exited handle sets match. The accepted run completed in about six
seconds and verified all six exits. No helper process remains. A restricted CIM
inventory attempt was denied; the supported process-list check returned empty.

## Build identity and remaining work

Final kernel: `final-kernel/iMouse2.Kernel.dll`, SHA-256
`a45b38a3c628acee07310345ac638c1cfdf553fa32927fd92bc73b6649828877`.
`kernel-manifest.json` records exact source/output bytes. The process/recovery
test manifests include all linked production sources. Final, initial failing
and the separate intermediate build are preserved outside the checkout with
checksums; see `archive-verification.json`.

No real receiver crash, descendant-tree containment, phone rediscovery, recast,
native library teardown, console acceptance or full-rack endurance was tested.
Normal output-drain completion remains the framework's async-exit behavior;
forced cleanup does not add an unbounded log-drain wait. Shutdown may spend up
to five seconds per unresponsive root. No guarantee of fully bounded OS kill
execution or factory startup is added.

The console, receiver/runtime and installed files are unchanged. This kernel
contains the preceding screenshot/retry repairs but is not in the previously
live-tested immutable package. Prepare a new review package with these accumulated
repairs; do not replace files inside a historical package or inherit its physical
acceptance. Nothing was pushed, installed, promoted or deployed.
