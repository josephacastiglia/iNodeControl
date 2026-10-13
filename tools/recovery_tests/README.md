# Offline receiver recovery tests

This small executable links production `AirplaySupervisor.cs` and `ReceiverLog.cs`
directly and uses fake receiver handles and disposable log files. It has no kernel server, HID transport, UxPlay
process, frame pipe or desktop control.

From the repository root:

```powershell
dotnet run --project tools/recovery_tests/RecoveryTests.csproj -c Release --property:UseSharedCompilation=false
```

The 29 cases cover cancelled startup, running cancellation, repeated disposal,
startup failure/retry exhaustion, wait failure recovery, unrelated cancellation
exceptions, cancellation during backoff, invalid delay, healthy-peer isolation,
cleanup failure, duplicate supervision, and disposal during startup. Every
asynchronous assertion has a bounded wait.

Retry counts mean replacement attempts begun, including attempts whose factory
throws. The initial launch and cancelled waits do not count; exhaustion at a
budget of five reports five, not six. The failure reason stays visible during
backoff and after exhaustion, then clears when a replacement starts successfully.
Disposing a failed supervisor preserves its diagnostic record. Failed cleanup
retains a last known PID when available, explicitly marked as unconfirmed; that
PID is not evidence the process is alive and must not be used alone to kill it.
Failure to read an identity cannot prevent the cleanup attempt.

Logging checks cover bounded rotation, Unicode truncation, simultaneous callbacks,
failed writes and recovery, failed rotation without active-log loss, preserving one
oversized historical generation, EOF, and warning visibility without changing the
receiver's lifecycle state. The normal log keeps the current file and `.1`, each
up to 4 MiB for new output. An existing oversized log is retained once until the
next rotation. File errors are visible in per-phone kernel status and retry on the
next line. They do not stop the receiver. Raw logs still need review before sharing.

Some Windows sandboxes refuse file rename even within the disposable directory.
Keep that failure record and run the same built test under approved unrestricted
execution when necessary; do not call a denied rotation a successful test.

Cleanup failure must leave a visible failed state and prevent a replacement:
the supervisor cannot assume a failed disposal stopped the old process. A
shutdown disposes each owned handle once and reports stopped. Retry exhaustion
remains finite; recovery never recasts a phone.

The existing kernel `--self-test` suite supplies broader simulated input and
frame-pipe checks. Build it into a scratch folder and use that build only. This
focused suite does not establish AirPlay rediscovery, actual process cleanup,
phone recovery or full-rack endurance.
