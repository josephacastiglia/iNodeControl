# Receiver child-process lifetime checks

These tests link production receiver ownership, process adapter, log and supervisor
code. They do not include the kernel HTTP server, HID transport or desktop control.

```powershell
dotnet build tools/receiver_process_tests/ReceiverProcessTests.csproj -c Release -o <scratch>
<scratch>\ReceiverProcessTests.exe
<scratch>\ReceiverProcessTests.exe --real-processes
```

The default **14 cases use fake processes only**. They check confirmed exit before
replacement, partial startup at both reader stages, failed starts before/after
child creation, retry suppression on unconfirmed cleanup, the bounded exit wait,
idempotent/concurrent disposal, natural exit, cancellation and recovery after
confirmed cleanup. A delayed fake exit makes the ordering assertion deterministic.

The explicit `--real-processes` mode runs **six cases with hidden copies of this
test executable**. The production `AirplayProcess` path passes its actual argument
and logging setup to one harmless helper. Other cases inject reader/monitor/kill
failures around real `Process` objects. A delayed termination checks replacement
ordering; an ignored kill exercises the actual five-second exit deadline.

Each real child has a 20-second failsafe. Tests retain a separate process handle
before acting, explicitly clean up deliberately unconfirmed children in `finally`,
and require every created helper's exit confirmation before reporting success.
They do not search for and terminate other applications by name or PID. There are
no listeners, network announcements, UxPlay instances, phone inputs or visible
windows. Do not substitute a receiver executable for the test executable.

The production policy still requests process-tree termination. Its bounded wait
confirms the receiver root's exit, **not all descendant exits or every final log
callback**. These checks do not establish AirPlay rediscovery or phone recasting.
See `analysis/receiver-process-cleanup-20261013/REPORT.md` for the pre-fix failures,
test-runner cleanup correction, exact builds and limits.
