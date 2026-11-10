using System.Diagnostics;

namespace IMouse2.Kernel;

// Moved on 9 Nov 2026 from the stand-alone project tools/receiver_process_tests, which is deleted.
// These cases start real child processes to exercise the real kill and exit-confirmation path.
// The only thing launched is a hidden batch file written for the run (two echo lines, then a
// 25-second ping to 127.0.0.1 as a failsafe), through cmd.exe: no UxPlay, listener, hardware
// transport or phone interaction. Every child is confirmed gone from a retained process handle.
internal static class RealProcessTests
{
    private static string Executable = "";
    private static readonly HashSet<int> Created = [];
    private static readonly HashSet<int> Confirmed = [];
    internal static async Task RunAsync(Func<string, Func<Task>, Task> record)
    {
        string home = Path.Combine(Path.GetTempPath(), "imouse-child-fixture-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(home);
        Executable = Path.Combine(home, "fixture.cmd");
        File.WriteAllText(Executable, "@echo off\r\necho fixture-ready\r\necho fixture-stderr 1>&2\r\nping -n 25 127.0.0.1 >nul\r\n");
        try
        {
            var cases = Cases();
            foreach (var (name, run) in cases) await record(name, run);
            await record("every helper process these cases started was confirmed to have exited", () =>
            {
                Check(Created.Count == cases.Length && Created.SetEquals(Confirmed), $"{Confirmed.Count}/{Created.Count} helper exits confirmed");
                return Task.CompletedTask;
            });
        }
        finally { try { Directory.Delete(home, true); } catch (IOException) { } catch (UnauthorizedAccessException) { } }
    }

    private static (string Name, Func<Task> Run)[] Cases()
    {
        var tests = new (string Name, Func<Task> Run)[] {
            ("production AirplayProcess attaches both logs and confirms exit", async () => {
                string folder = Path.Combine(Path.GetTempPath(), "imouse-child-test-" + Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(folder);
                Process? observer = null;
                try {
                    string log = Path.Combine(folder, "receiver.log");
                    using var receiver = new AirplayProcess(Executable, folder, "offline-receiver-fixture-" + Guid.NewGuid().ToString("N"),
                        "unused-fixture-pipe", "fixture-client", log, 7110, "02:00:00:00:00:01");
                    observer = Observe(receiver.Id);
                    await Until(() => File.Exists(log) && ReadShared(log).Contains("fixture-ready") && ReadShared(log).Contains("fixture-stderr"));
                    receiver.Dispose(); receiver.Dispose();
                    Check(observer.WaitForExit(0) && receiver.Id == 0, "Dispose returned while the child was alive");
                } finally { StopFixture(observer); Directory.Delete(folder, true); }
            }),
            ("partial reader setup failure leaves no running child", () => WithFixture(new Fixture { FailReader = true }, f => {
                Exception? failure = Capture(() => new ReceiverProcessLifetime(f));
                Check(failure is IOException && f.Observer?.WaitForExit(0) == true, "partial startup orphaned its process");
                return Task.CompletedTask;
            })),
            ("replacement follows delayed real child termination", () => WithFixture(new Fixture { FailMonitor = true, DelayKill = true }, async f => {
                using var cancel = new CancellationTokenSource(); int starts = 0; bool exitedBeforeReplacement = false;
                using var supervisor = new AirplaySupervisor(() => {
                    if (++starts == 1) return new ReceiverProcessLifetime(f);
                    exitedBeforeReplacement = f.Observer!.WaitForExit(0);
                    cancel.Cancel(); return new ReceiverProcessLifetime(new Idle());
                }, 1, TimeSpan.Zero);
                var run = Task.Run(() => supervisor.RunAsync(cancel.Token));
                await run.WaitAsync(TimeSpan.FromSeconds(8));
                Check(starts == 2 && exitedBeforeReplacement && f.Observer!.WaitForExit(0), "replacement raced the original child");
                Console.WriteLine("  delayed termination elapsed ms=" + f.CleanupMilliseconds.ToString("F1"));
            })),
            ("failed partial-start cleanup is visible and never retried", () => WithFixture(new Fixture { FailReader = true, DenyKill = true }, async f => {
                int starts = 0;
                using var supervisor = new AirplaySupervisor(() => { starts++; return new ReceiverProcessLifetime(f); }, 2, TimeSpan.Zero);
                await supervisor.RunAsync(CancellationToken.None);
                Check(starts == 1 && supervisor.Info is { State: "failed", Restarts: 0 }
                    && supervisor.Info.Pid == f.Observer!.Id && !f.Observer.HasExited, "failed startup cleanup was retried or hidden");
                Check(supervisor.Info.Message.Contains("reader fixture") && supervisor.Info.Message.Contains("denied fixture"), "lost either failure reason");
                // WithFixture explicitly cleans up this deliberately unconfirmed test child.
            })),
            ("real five-second exit deadline blocks replacement", () => WithFixture(new Fixture { FailMonitor = true, IgnoreKill = true }, async f => {
                int starts = 0;
                using var supervisor = new AirplaySupervisor(() => { starts++; return new ReceiverProcessLifetime(f); }, 2, TimeSpan.Zero);
                var clock = Stopwatch.StartNew();
                await Task.Run(() => supervisor.RunAsync(CancellationToken.None)).WaitAsync(TimeSpan.FromSeconds(12));
                Check(starts == 1 && supervisor.Info.State == "failed" && !f.Observer!.HasExited, "unconfirmed exit triggered replacement");
                Check(clock.Elapsed.TotalSeconds >= 4.8 && clock.Elapsed.TotalSeconds < 12, "deadline not bounded: " + clock.Elapsed);
                Console.WriteLine("  refused exit elapsed ms=" + clock.Elapsed.TotalMilliseconds.ToString("F1"));
            })),
            ("normal requested cancellation confirms child exit", () => WithFixture(new Fixture(), async f => {
                using var cancel = new CancellationTokenSource();
                using var supervisor = new AirplaySupervisor(() => new ReceiverProcessLifetime(f));
                var run = supervisor.RunAsync(cancel.Token); await Until(() => supervisor.Info.State == "running");
                cancel.Cancel(); await run.WaitAsync(TimeSpan.FromSeconds(8));
                Check(f.Observer!.WaitForExit(0) && supervisor.Info.State == "stopped", "shutdown left the child alive");
            }))
        };
        return tests;
    }

    private static async Task WithFixture(Fixture fixture, Func<Fixture, Task> run)
    {
        try { await run(fixture); }
        finally { fixture.Cleanup(); }
    }

    private static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    private static Exception? Capture(Action action) { try { action(); return null; } catch (Exception ex) { return ex; } }
    private static async Task Until(Func<bool> ready)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        while (!ready()) await Task.Delay(10, timeout.Token);
    }
    private static string ReadShared(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        using var reader = new StreamReader(stream); return reader.ReadToEnd();
    }
    private static Process Observe(int id)
    {
        var observer = Process.GetProcessById(id); _ = observer.Handle;
        Created.Add(id);
        Console.WriteLine("  created fixture PID=" + id); return observer;
    }
    private static void StopFixture(Process? observer)
    {
        if (observer is null) return;
        try {
            if (!observer.HasExited) observer.Kill(entireProcessTree: true);
            Check(observer.WaitForExit(5000), "fixture cleanup failed for PID " + observer.Id);
            Confirmed.Add(observer.Id);
            Console.WriteLine("  fixture exit confirmed PID=" + observer.Id);
        } finally { observer.Dispose(); }
    }

    // A replacement that never runs anything, for the case that only needs "a second child".
    private sealed class Idle : IReceiverProcess
    {
        private readonly ManualResetEventSlim _exit = new();
        public int Id => 1;
        public bool HasExited => _exit.IsSet;
        public bool Start() => true;
        public void BeginOutputReadLine() { }
        public void BeginErrorReadLine() { }
        public Task WaitForExitAsync(CancellationToken ct) => Task.Delay(Timeout.Infinite, ct);
        public bool WaitForExit(int milliseconds) => _exit.Wait(milliseconds);
        public void KillTree() => _exit.Set();
        public void Dispose() { }
    }

    private sealed class Fixture : IReceiverProcess
    {
        private readonly Process _process = new() {
            StartInfo = new ProcessStartInfo(Executable) {
                UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardOutput = true, RedirectStandardError = true,
                WorkingDirectory = Path.GetDirectoryName(Executable)!
            }
        };
        public Process? Observer { get; private set; }
        public bool FailReader, FailMonitor, DenyKill, IgnoreKill, DelayKill;
        private Task? _kill;
        private bool _rootDisposed;
        private Stopwatch? _cleanup;
        public double CleanupMilliseconds => _cleanup?.Elapsed.TotalMilliseconds ?? 0;
        public int Id => _process.Id;
        public bool HasExited => _process.HasExited;
        public bool Start() { bool started = _process.Start(); Observer = Observe(_process.Id); return started; }
        public void BeginOutputReadLine() => _process.BeginOutputReadLine();
        public void BeginErrorReadLine() { if (FailReader) throw new IOException("reader fixture"); _process.BeginErrorReadLine(); }
        public Task WaitForExitAsync(CancellationToken ct) => FailMonitor ? Task.FromException(new IOException("monitor fixture")) : _process.WaitForExitAsync(ct);
        public bool WaitForExit(int milliseconds) => _process.WaitForExit(milliseconds);
        public void KillTree()
        {
            if (DenyKill) throw new IOException("kill denied fixture");
            if (IgnoreKill) return;
            _cleanup = Stopwatch.StartNew();
            if (DelayKill) _kill = Task.Run(async () => { await Task.Delay(200); _process.Kill(entireProcessTree: true); });
            else _process.Kill(entireProcessTree: true);
        }
        // Production owner disposes only the raw wrapper after exit. Test-scope
        // disposal additionally cleans a deliberately unconfirmed child via its
        // separately retained handle, never by searching other process names.
        void IDisposable.Dispose() { _kill?.GetAwaiter().GetResult(); _process.Dispose(); _rootDisposed = true; _cleanup?.Stop(); }
        public void Cleanup()
        {
            try { _kill?.GetAwaiter().GetResult(); StopFixture(Observer); }
            finally { if (!_rootDisposed) _process.Dispose(); }
        }
    }
}
