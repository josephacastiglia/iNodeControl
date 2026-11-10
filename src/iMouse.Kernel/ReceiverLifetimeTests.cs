
namespace IMouse2.Kernel;

// Moved on 9 Nov 2026 from the stand-alone project tools/receiver_process_tests, which is deleted: the checks now run
// in this executable's --self-test. Each named case is one self-test check; it passes when none of
// its assertions throws. Fake processes only; nothing is started.
internal static class ReceiverLifetimeTests
{
    internal static async Task RunAsync(Func<string, Func<Task>, Task> record)
    {
        var tests = new (string Name, Func<Task> Run)[] {
            ("replacement waits for confirmed child exit", async () => {
                var process = new FakeProcess { MonitorFailure = true, DelayExit = true };
                int starts = 0; using var cancel = new CancellationTokenSource();
                using var supervisor = new AirplaySupervisor(() => {
                    if (Interlocked.Increment(ref starts) == 1) return new ReceiverProcessLifetime(process);
                    cancel.Cancel(); return new ReceiverProcessLifetime(new FakeProcess());
                }, 1, TimeSpan.Zero);
                var run = Task.Run(() => supervisor.RunAsync(cancel.Token));
                try {
                    await Until(() => process.KillCalls != 0);
                    await Task.Delay(50);
                    Check(starts == 1 && process.Disposals == 0, "replacement started or handle discarded before exit");
                } finally { process.Exit.Set(); await run.WaitAsync(TimeSpan.FromSeconds(3)); }
                Check(starts == 2 && process.Disposals == 1, "confirmed exit did not permit replacement");
            }),
            ("stdout initialization failure cleans up the started child", () => {
                var process = new FakeProcess { ReaderFailure = 1 };
                var failure = Catch(() => new ReceiverProcessLifetime(process));
                Check(failure is IOException && process.Exit.IsSet && process.Disposals == 1, "stdout failure orphaned the child");
                return Task.CompletedTask;
            }),
            ("stderr initialization failure cleans up after stdout began", () => {
                var process = new FakeProcess { ReaderFailure = 2 };
                var failure = Catch(() => new ReceiverProcessLifetime(process));
                Check(failure is IOException && process.OutputStarted && process.Exit.IsSet && process.Disposals == 1, "stderr failure orphaned the child");
                return Task.CompletedTask;
            }),
            ("failed start before child creation disposes only the wrapper", () => {
                var process = new FakeProcess { StartFailure = 1 };
                Check(Catch(() => new ReceiverProcessLifetime(process)) is IOException, "wrong startup error");
                Check(process.Disposals == 1 && process.KillCalls == 0 && !process.Started, "unstarted wrapper leaked or killed");
                return Task.CompletedTask;
            }),
            ("start failure after child creation also confirms cleanup", () => {
                var process = new FakeProcess { StartFailure = 2 };
                Check(Catch(() => new ReceiverProcessLifetime(process)) is IOException, "wrong startup error");
                Check(process.Exit.IsSet && process.Disposals == 1, "partially started process leaked");
                return Task.CompletedTask;
            }),
            ("startup cleanup failure stops all retries and retains both errors", async () => {
                int starts = 0; var process = new FakeProcess { ReaderFailure = 2, KillFailure = true };
                using var supervisor = new AirplaySupervisor(() => { starts++; return new ReceiverProcessLifetime(process); }, 2, TimeSpan.Zero);
                await supervisor.RunAsync(CancellationToken.None);
                Check(starts == 1 && supervisor.Info is { State: "failed", Pid: 123, Restarts: 0 }, "unconfirmed startup cleanup retried");
                Check(supervisor.Info.Message.Contains("reader fixture") && supervisor.Info.Message.Contains("kill fixture"), "lost startup or cleanup reason");
                Check(process.Disposals == 0, "discarded the unconfirmed process handle");
            }),
            ("exit deadline failure blocks replacement", async () => {
                int starts = 0; var process = new FakeProcess { MonitorFailure = true, DelayExit = true, RefuseWait = true };
                using var supervisor = new AirplaySupervisor(() => { starts++; return new ReceiverProcessLifetime(process); }, 2, TimeSpan.Zero);
                await supervisor.RunAsync(CancellationToken.None);
                Check(starts == 1 && supervisor.Info.State == "failed" && supervisor.Info.Message.Contains("exit", StringComparison.OrdinalIgnoreCase), "unconfirmed exit retried");
                Check(process.Disposals == 0 && process.WaitMilliseconds is > 0 and <= 5000, "cleanup was unbounded or discarded the handle");
            }),
            ("ordinary disposal is idempotent", () => {
                var process = new FakeProcess(); var owner = new ReceiverProcessLifetime(process);
                owner.Dispose(); owner.Dispose();
                Check(process.KillCalls == 1 && process.Disposals == 1, "duplicate termination/disposal");
                return Task.CompletedTask;
            }),
            ("already exited child needs no kill", () => {
                var process = new FakeProcess(); var owner = new ReceiverProcessLifetime(process); process.Exit.Set();
                owner.Dispose();
                Check(process.KillCalls == 0 && process.Disposals == 1, "natural exit cleanup");
                return Task.CompletedTask;
            }),
            ("confirmed partial-start cleanup permits a later retry", async () => {
                int starts = 0; var first = new FakeProcess { ReaderFailure = 2 }; using var cancel = new CancellationTokenSource();
                using var supervisor = new AirplaySupervisor(() => {
                    if (++starts == 1) return new ReceiverProcessLifetime(first);
                    Check(first.Exit.IsSet && first.Disposals == 1, "retry preceded startup cleanup");
                    var second = new ReceiverProcessLifetime(new FakeProcess()); cancel.Cancel(); return second;
                }, 1, TimeSpan.Zero);
                await supervisor.RunAsync(cancel.Token);
                Check(starts == 2 && supervisor.Info is { State: "stopped", Restarts: 1 }, "confirmed cleanup blocked recovery");
            }),
            ("cancelled startup still reports unconfirmed cleanup", async () => {
                var process = new FakeProcess { ReaderFailure = 2, KillFailure = true }; using var cancel = new CancellationTokenSource();
                using var supervisor = new AirplaySupervisor(() => { cancel.Cancel(); return new ReceiverProcessLifetime(process); });
                await supervisor.RunAsync(cancel.Token);
                supervisor.Dispose();
                Check(supervisor.Info is { State: "failed", Pid: 123 }, "cancellation hid the orphan warning");
            }),
            ("exit racing the kill request is confirmed successfully", () => {
                var process = new FakeProcess { ExitDuringKill = true }; var owner = new ReceiverProcessLifetime(process);
                owner.Dispose(); Check(process.Disposals == 1 && owner.Id == 0, "natural exit race became cleanup failure");
                return Task.CompletedTask;
            }),
            ("false Start result cannot initialize readers", () => {
                var process = new FakeProcess { StartReturnsFalse = true };
                Check(Catch(() => new ReceiverProcessLifetime(process)) is InvalidOperationException, "false Start accepted");
                Check(!process.OutputStarted && process.Disposals == 1 && process.KillCalls == 0, "unstarted child mishandled");
                return Task.CompletedTask;
            }),
            ("concurrent disposal waits once and releases once", async () => {
                var process = new FakeProcess { DelayExit = true }; var owner = new ReceiverProcessLifetime(process);
                var first = Task.Run(owner.Dispose); await Until(() => process.KillCalls != 0);
                var second = Task.Run(owner.Dispose);
                try {
                    await Task.Delay(50);
                    Check(!first.IsCompleted && !second.IsCompleted && process.Disposals == 0, "concurrent caller claimed cleanup prematurely");
                } finally { process.Exit.Set(); await Task.WhenAll(first, second).WaitAsync(TimeSpan.FromSeconds(2)); }
                Check(process.KillCalls == 1 && process.Disposals == 1, "duplicate concurrent cleanup");
            })
        };
        foreach (var (name, run) in tests) await record(name, run);
    }

    private static void Check(bool value, string reason) { if (!value) throw new Exception(reason); }
    private static Exception? Catch(Action action) { try { action(); return null; } catch (Exception ex) { return ex; } }
    private static async Task Until(Func<bool> ready) {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(2));
        while (!ready()) await Task.Delay(1, deadline.Token);
    }

    private sealed class FakeProcess : IReceiverProcess {
        public bool Started;
        public int ReaderFailure, StartFailure;
        public bool KillFailure, MonitorFailure, DelayExit, RefuseWait, OutputStarted, ExitDuringKill, StartReturnsFalse;
        public int KillCalls, Disposals, WaitMilliseconds;
        public ManualResetEventSlim Exit { get; } = new();
        public int Id => Started ? 123 : throw new InvalidOperationException("not started");
        public bool HasExited => Started ? Exit.IsSet : throw new InvalidOperationException("not started");
        public bool Start() {
            if (StartReturnsFalse) return false;
            if (StartFailure == 1) throw new IOException("start fixture");
            Started = true;
            if (StartFailure == 2) throw new IOException("partial start fixture");
            return true;
        }
        public void BeginOutputReadLine() { if (ReaderFailure == 1) throw new IOException("stdout reader fixture"); OutputStarted = true; }
        public void BeginErrorReadLine() { if (ReaderFailure == 2) throw new IOException("stderr reader fixture"); }
        public Task WaitForExitAsync(CancellationToken ct) => MonitorFailure ? Task.FromException(new IOException("monitor fixture")) : Task.Delay(Timeout.Infinite, ct);
        public bool WaitForExit(int milliseconds) { WaitMilliseconds = milliseconds; return !RefuseWait && Exit.Wait(milliseconds); }
        public void KillTree() {
            Interlocked.Increment(ref KillCalls);
            if (ExitDuringKill) { Exit.Set(); throw new InvalidOperationException("already exited"); }
            if (KillFailure) throw new IOException("kill fixture");
            if (!DelayExit) Exit.Set();
        }
        public void Dispose() => Interlocked.Increment(ref Disposals);
    }
}
