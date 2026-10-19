using IMouse2.Kernel;

var tests = new (string Name, Func<Task> Run)[]
{
    ("cancelled startup never launches and reports stopped", async () => {
        var starts = 0; using var cancel = new CancellationTokenSource(); cancel.Cancel();
        using var s = new AirplaySupervisor(() => { starts++; return new Fake(); });
        await s.RunAsync(cancel.Token);
        Check(starts == 0 && s.Info.State == "stopped", "cancelled start state");
    }),
    ("running cancellation disposes once and reports stopped", async () => {
        var fake = new Fake(); using var cancel = new CancellationTokenSource();
        using var s = new AirplaySupervisor(() => fake);
        var run = s.RunAsync(cancel.Token); cancel.Cancel(); await run.WaitAsync(TimeSpan.FromSeconds(2));
        Check(fake.Disposals == 1 && s.Info is { State: "stopped", Pid: 0 }, "running cancellation cleanup");
    }),
    ("repeated Dispose never disposes a child twice", async () => {
        var fake = new Fake(); var s = new AirplaySupervisor(() => fake);
        var run = s.RunAsync(CancellationToken.None); s.Dispose(); s.Dispose();
        await run.WaitAsync(TimeSpan.FromSeconds(2));
        Check(fake.Disposals == 1, $"dispose count {fake.Disposals}");
    }),
    ("startup exceptions exhaust a finite budget", async () => {
        int starts = 0; using var s = new AirplaySupervisor(() => { starts++; throw new IOException("fake start"); }, 2, TimeSpan.Zero);
        await s.RunAsync(CancellationToken.None);
        Check(starts == 3 && s.Info is { State: "failed", Pid: 0 }, "start budget");
    }),
    ("wait failure cleans up and recovers", async () => {
        var first = new Fake { WaitFailure = new IOException("fake wait") }; var second = new Fake(); int starts = 0;
        using var cancel = new CancellationTokenSource();
        using var s = new AirplaySupervisor(() => ++starts == 1 ? first : second, 1, TimeSpan.Zero);
        var run = s.RunAsync(cancel.Token);
        try { await Until(() => starts == 2 || run.IsCompleted); Check(starts == 2 && first.Disposals == 1, "wait failure must retry"); }
        finally { cancel.Cancel(); try { await run.WaitAsync(TimeSpan.FromSeconds(2)); } catch (IOException) { } }
        Check(second.Disposals == 1, "recovered receiver cleanup");
    }),
    ("unrelated cancellation exception is a failure, not shutdown", async () => {
        int starts = 0; var last = new Fake(); using var cancel = new CancellationTokenSource();
        using var s = new AirplaySupervisor(() => ++starts == 1 ? new Fake { WaitFailure = new OperationCanceledException() } : last, 1, TimeSpan.Zero);
        var run = s.RunAsync(cancel.Token);
        try { await Until(() => starts == 2 || run.IsCompleted); Check(starts == 2, "unrelated cancellation swallowed"); }
        finally { cancel.Cancel(); await run.WaitAsync(TimeSpan.FromSeconds(2)); }
    }),
    ("cancel during backoff prevents replacement", async () => {
        int starts = 0; var dead = new Fake(); dead.Exit.TrySetResult(); using var cancel = new CancellationTokenSource();
        using var s = new AirplaySupervisor(() => { starts++; return dead; }, 3, TimeSpan.FromSeconds(10));
        var run = s.RunAsync(cancel.Token); await Until(() => s.Info.State == "restarting");
        cancel.Cancel(); await run.WaitAsync(TimeSpan.FromSeconds(2));
        Check(starts == 1 && s.Info.State == "stopped", "backoff cancellation");
    }),
    ("negative delay is refused before starting", () => {
        bool refused = false;
        try { using var s = new AirplaySupervisor(() => new Fake(), delay: TimeSpan.FromMilliseconds(-1)); }
        catch (ArgumentOutOfRangeException) { refused = true; }
        Check(refused, "negative delay accepted"); return Task.CompletedTask;
    }),
    ("one failed receiver leaves a healthy peer running", async () => {
        int starts = 0; var healthy = new Fake(); using var cancel = new CancellationTokenSource();
        using var peer = new AirplaySupervisor(() => healthy);
        using var failed = new AirplaySupervisor(() => { starts++; var x = new Fake(); x.Exit.TrySetResult(); return x; }, 1, TimeSpan.Zero);
        var live = peer.RunAsync(cancel.Token); await failed.RunAsync(CancellationToken.None);
        Check(starts == 2 && failed.Info.State == "failed" && peer.Info.State == "running" && healthy.Disposals == 0, "peer isolation");
        cancel.Cancel(); await live;
    }),
    ("cleanup failure stops replacements", async () => {
        int starts = 0; var fake = new Fake { DisposeFailure = true }; fake.Exit.TrySetResult();
        using var s = new AirplaySupervisor(() => { starts++; return fake; }, 2, TimeSpan.Zero);
        await s.RunAsync(CancellationToken.None);
        Check(starts == 1 && s.Info.State == "failed" && s.Info.Message.Contains("cleanup", StringComparison.OrdinalIgnoreCase), "cleanup failure must block replacement");
        s.Dispose(); Check(s.Info.State == "failed", "Dispose must not hide unconfirmed cleanup");
    }),
    ("second run cannot start a second receiver", async () => {
        int starts = 0; using var cancel = new CancellationTokenSource();
        using var s = new AirplaySupervisor(() => { starts++; return new Fake(); });
        var first = s.RunAsync(cancel.Token); bool refused = false;
        try { await s.RunAsync(cancel.Token).WaitAsync(TimeSpan.FromMilliseconds(100)); }
        catch (InvalidOperationException) { refused = true; }
        finally { cancel.Cancel(); await first.WaitAsync(TimeSpan.FromSeconds(2)); }
        Check(refused && starts == 1, "duplicate run allowed");
    }),
    ("dispose inside startup cannot publish a running child", async () => {
        var fake = new Fake(); AirplaySupervisor? s = null;
        s = new AirplaySupervisor(() => { s!.Dispose(); return fake; });
        await s.RunAsync(CancellationToken.None).WaitAsync(TimeSpan.FromSeconds(2));
        Check(s.Info.State == "stopped" && fake.Disposals == 1, "startup cancellation race"); s.Dispose();
    })
};
int passed = 0;
foreach (var (name, run) in tests)
{
    try { await run(); Console.WriteLine("PASS " + name); passed++; }
    catch (Exception ex) { Console.WriteLine("FAIL " + name + ": " + ex.Message); }
}
Console.WriteLine($"{passed}/{tests.Length} recovery checks passed; fake handles only; no sockets, HID, receivers or UI.");
return passed == tests.Length ? 0 : 1;

static void Check(bool value, string message) { if (!value) throw new Exception(message); }
static async Task Until(Func<bool> ready)
{
    using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(2));
    while (!ready()) await Task.Delay(1, deadline.Token);
}
sealed class Fake : IReceiverHandle
{
    public int Id => 123;
    public TaskCompletionSource Exit { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public int Disposals;
    public Exception? WaitFailure;
    public bool DisposeFailure;
    public Task WaitForExitAsync(CancellationToken ct) => WaitFailure is {} ex ? Task.FromException(ex) : Exit.Task.WaitAsync(ct);
    public void Dispose() { Interlocked.Increment(ref Disposals); if (DisposeFailure) throw new IOException("fake cleanup"); Exit.TrySetResult(); }
}
