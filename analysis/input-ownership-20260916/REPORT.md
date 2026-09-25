# Per-phone input ownership: kernel milestone

Implemented 16 September 2026. Status: **offline checks passed; console integration
and live validation remain open. This is not deployed to the desktop shortcut.**

## Current baseline correction

The newer [Grok deployment verification](../precise-candidate-deploy-20260915/verification.json)
and [gap audit](../finish-criteria-audit-20260916/GAPS.md) supersede the earlier
isolated precise-movement success. C241 failed repeatable targeting tests and the
kernel was rolled back. The physical cause is not established. Keep the established
movement timing; do not enable `--precise-movement` or promote either rejected build.

## What changed

- Added `InputSessions`, the mandatory ownership boundary for HTTP input in this
  new kernel build. Each phone has a distinct random lease token.
- A lease spans a workflow or an entire multi-request down/move/up gesture.
  The same phone accepts at most one active command. Concurrent commands get
  code 409 instead of becoming a backlog of delayed taps.
- Different phones can run commands concurrently. Explicit group requests validate
  all targets, coordinates, and tokens before starting any input. Individual
  outcomes are returned; physical execution is not an all-or-nothing transaction.
- Stop requires no lease, revokes existing tokens, cancels active work, releases
  mouse and keyboard, and latches the phone stopped. Resume is explicit, and a
  new lease is required. A release failure blocks resume and remains visible.
- Normal lease release performs cleanup without a Stop latch. Abandoned leases
  expire; a 100 ms watchdog initiates release even if the client vanishes while
  holding a mouse button. Leases use monotonic elapsed time.
- Propagated cancellation through HID writes and movement/keyboard/settle delays.
  Cleanup uses independent, transport-bounded release writes. Existing packet
  sequences, calibration, Home invalidation, and delay values are preserved.
- Shutdown cancels and drains input before disposing the API. Live binding changes
  are rejected in this build; changing configured identity requires a verified
  kernel restart. A changed saved UID detected by the session boundary revokes
  ownership instead of adopting the new binding.

This boundary coordinates clients using our kernel. It cannot prevent an external
vendor process or a diagnostic tool from directly opening the shared HID device.
Exclusive hardware ownership still needs the separate independence test.

## Validation

Build succeeded with zero warnings/errors. **70 kernel checks passed**, including
the previous 41 checks and 29 added ownership/API checks. No real HID transport
was opened. API route checks use the actual dispatcher without starting an HTTP
listener; they are not network/UI end-to-end tests.

New coverage includes missing/wrong tokens; atomic group acquisition rejection;
two phones progressing independently; same-phone concurrency rejection; Stop
during active key input; release of held mouse input; stale tokens after Resume;
multi-request drag ownership; invalid batch preflight; explicit successful group
input; renewal and expiry; autonomous expiry cleanup; changed UID; failed release
and blocked Resume; actual API acquire/renew/stop/resume routes; forbidden live
rebinding; and shutdown during active input.

Evidence: [self-tests.txt](self-tests.txt). Exact build/source hashes are in
`build-manifest.json`. Original edited files are preserved in `before/`.

## Limits and next step

- The current desktop console does not acquire leases or provide these Stop/Resume
  controls. **Do not point the desktop launcher at this kernel yet.**
- This is the foundation for concurrent workflows, not an implemented scheduler.
- Default lease duration is 30 seconds, adjustable from 1 to 120 seconds. A controller
  must renew its lease while working. Commands have an eight-second execution
  deadline; long typing should be deliberately chunked by the client, not retried
  wholesale on timeout.
- Cancellation initiates release promptly, but real USB completion is bounded by
  driver/transport behavior. Existing HID writes have two-second timeouts; Stop
  may wait for an in-flight operation plus mouse/key cleanup. Mock results do not
  establish live stop latency or prove that a disconnected phone received release.
- A normal lease release invalidates pointer state. Do not acquire/release a fresh
  lease for every hover packet; hold it across the active control session/gesture.
- Tokens provide ownership coordination, not user authentication. Stop and Resume
  are operator controls on the local API. API hardening remains a separate task.
- Hover coalescing belongs in the client. The kernel intentionally has no deferred
  command queue in this milestone. It never silently drops a click or button-up.

Next: integrate the console with lease acquisition/renewal and prominent Stop and
Resume controls; run console mocks; only then validate on C24C and C241 with other
phones untouched. Follow with guided binding/profile setup and atomic configuration.

## Build

`release/iMouse2-kernel-ownership/iMouse2.Kernel.exe`

The desktop shortcut, launchers, deployed kernel/console binaries, UxPlay,
calibration, firewall, and vendor services were not changed in this milestone.

Offline check:

```powershell
dotnet build src/iMouse.Kernel/iMouse.Kernel.csproj -c Release -o release/iMouse2-kernel-ownership --no-restore
& ./release/iMouse2-kernel-ownership/iMouse2.Kernel.exe --self-test
```
