# Receiver retries and failure records

13 October 2026. Offline work following `941fa79` on
`local/combined-candidate-20261012`. No rack endpoint, desktop, receiver or phone
was operated. Installed files remain unchanged; no gate advanced.

## Reproduced defects

The supervisor incremented its restart count before checking the limit or waiting.
An initial launch plus two replacements reported three restarts when exhausted.
Even a cancelled delay counted an attempt that never happened. Startup and
wait-monitor errors appeared on stdout but were replaced by a generic crash
message in status. Disposal erased an exhausted supervisor's failed state.
Failed cleanup discarded the last known receiver PID.

Eight regression cases were added before changing production behavior. The
original code passed **21/28**, failing seven new cases. The sandboxed run also
failed three existing file-rotation cases because file rename was denied; the
same binary outside that restriction passed those three. Both runs are retained.
`AirplaySupervisor-before.cs.txt` and `Program-before.cs.txt` were copied before
the original test build. The recovery-on-success case already passed.

## Changes

- Count a replacement when its launch attempt is claimed, not when waiting for
  it. Failed starts count, the initial launch does not, and cancelled waits do
  not consume an attempt. The existing maximum number of launches is unchanged.
- Preserve the latest startup/wait reason during backoff and at exhaustion.
  Successful startup clears the previous reason. Unexpected exit is identified
  separately; this change does not capture a native process's exit code.
- Preserve terminal failure through disposal and cancellation. Ordinary requested
  shutdown still reports stopped.
- On failed cleanup, retain the PID obtained before disposal and label it
  explicitly **last known**. A failed identity lookup cannot skip cleanup; the
  message then says unknown. The PID is diagnostic, not proof of a live process
  or authority to kill a process by that number.
- The default remains five replacement attempts, with the same two-second wait.
  Failed cleanup still prevents replacements. No automatic recast was added.

## Validation and identity

| Check | Result |
|---|---|
| Original supervisor with new tests | 21/28; seven intended failures |
| Final focused recovery/logging suite | **29/29**; includes the extra identity-lookup failure case |
| Final kernel self-tests | **207 passed**; simulated HID/private frame pipes, no hardware |
| Diagnostic integration | Top-level and per-phone status retain the actual exhausted count and failure message; no listener opened |
| Both Release builds | Zero warnings/errors |

Final kernel: `final-kernel/iMouse2.Kernel.dll`, SHA-256
`83f7e6edd82286bb48f76ce4a20a9eb52377d5155801499589609b5aae97aa57`.
`kernel-manifest.json` records exact source/output bytes.
`recovery-tests-manifest.json` explicitly includes the linked production files.
`before-manifest.json` identifies the original regression build and snapshots.
`intermediate-kernel-self-tests.txt` belongs to an earlier development build;
only `final-kernel-self-tests.txt` is evidence for the final binary.

## Remaining limits

This is not a receiver-process termination test. `AirplayProcess.Dispose` still
requests process-tree termination and disposes the handle without explicitly
waiting for confirmed exit. Review and test that boundary next using disposable
local child processes, not rack receivers. A factory that starts a process and
then throws also needs cleanup review. These are source-review findings, not
demonstrated causes of the earlier physical rediscovery delay.

No live crash, retry exhaustion, process cleanup, AirPlay rediscovery or console
display test ran. The console and native receiver are unchanged. The final kernel
includes the earlier screenshot backpressure repair, but its detailed frame/HTTP
and cleanup-harness results belong to that earlier build and were not rerun here.

The new kernel has not been packaged, installed, promoted or pushed. Preserve the
previous immutable review package and live result as historical; prepare a new
package before another approved live window. Exact builds, source snapshots and
evidence are copied to the external evidence archive with checksums. See
`archive-verification.json` for the receipt and protected-file verification.
