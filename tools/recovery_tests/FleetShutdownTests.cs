using IMouse2.Kernel;

// The fleet uses actual private frame pipes and fake receiver handles. No
// receiver executable is configured and no board or network listener is opened.
static class FleetShutdownTests
{
    public static IEnumerable<(string Name, Func<Task> Run)> Cases()
    {
        yield return ("fleet shutdown joins a receiver cleanup already in progress", DrainsExistingCleanup);
        yield return ("fleet shutdown starts all child cleanup before waiting for one", StopsPeersTogether);
        yield return ("fleet reports unconfirmed child cleanup after stopping its peer", ReportsCleanupFailure);
        yield return ("second concurrent fleet shutdown also waits for cleanup", ConcurrentShutdown);
        yield return ("disposed fleet never starts a receiver later", RefusesStartAfterDisposal);
        yield return ("fleet rejects a second start without creating another child", RefusesSecondStart);
        yield return ("cancelled fleet startup launches no child and joins frame readers", CancelledStartup);
        yield return ("fleet joins startup already in progress and cleans its unpublished child", StopsDuringStartup);
        yield return ("fleet surfaces partial-start cleanup failure with the last PID", PartialStartFailure);
        yield return ("exhausted retries without a child do not invent a cleanup failure", ExhaustedRetries);
        yield return ("fleet shutdown releases its private frame pipe before returning", ReleasesFramePipe);
        yield return ("all failed children are reported to repeated shutdown callers", ReportsAllFailures);
    }
    static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    static TaskCompletionSource Signal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    static ReceiverFleet Fleet(params Child[] children)
    {
        var configs = children.Select((_, i) => new ReceiverConfig("fixture-" + i, (0xAB00 + i).ToString("X4"),
            "iMouse2-fixture-" + i, "imouse-fleet-" + Guid.NewGuid().ToString("N"), 7200 + i * 3,
            "02:11:22:33:44:" + i.ToString("X2"))).ToArray();
        var store = new DeviceStore(Path.Combine(Path.GetTempPath(), "unused-fleet-" + Guid.NewGuid().ToString("N")),
            configs.Select(c => new Phone { deviceid = c.DeviceId, pid = c.BoardPid }));
        var fleet = new ReceiverFleet(configs, store, "", "", "");
        for (int i = 0; i < children.Length; i++)
        {
            var child = children[i];
            fleet.Sessions[i] = fleet.Sessions[i] with { Supervisor = new AirplaySupervisor(() => {
                child.Started.TrySetResult(); return child;
            }, delay: TimeSpan.Zero) };
        }
        return fleet;
    }
    static async Task Start(ReceiverFleet fleet, params Child[] children)
    {
        fleet.Start(CancellationToken.None);
        await Task.WhenAll(children.Select(c => c.Started.Task)).WaitAsync(TimeSpan.FromSeconds(2));
    }
    static async Task DrainsExistingCleanup()
    {
        await using var child = new Child(); var fleet = Fleet(child); Task? close = null;
        try
        {
            await Start(fleet, child); child.Exit.TrySetResult();
            await child.Cleaning.Task.WaitAsync(TimeSpan.FromSeconds(2));
            close = Task.Run(fleet.Dispose);
            await Task.Delay(150);
            Check(!close.IsCompleted, "Fleet returned while the receiver was still cleaning up");
            child.AllowCleanup.Set(); await close.WaitAsync(TimeSpan.FromSeconds(2));
            Check(child.Disposals == 1 && child.Cleaned, "Existing cleanup was skipped or repeated");
        }
        finally { child.AllowCleanup.Set(); if (close is not null) await close; else fleet.Dispose(); }
    }
    static async Task StopsPeersTogether()
    {
        await using var first = new Child(); await using var second = new Child();
        second.AllowCleanup.Set(); var fleet = Fleet(first, second); Task? close = null;
        try
        {
            await Start(fleet, first, second); close = Task.Run(fleet.Dispose);
            await first.Cleaning.Task.WaitAsync(TimeSpan.FromSeconds(2));
            await second.Cleaning.Task.WaitAsync(TimeSpan.FromSeconds(2));
            Check(!close.IsCompleted, "Fleet returned before the slow receiver exited");
        }
        finally { first.AllowCleanup.Set(); second.AllowCleanup.Set(); if (close is not null) await close; else fleet.Dispose(); }
        Check(first.Cleaned && second.Cleaned && first.Disposals == 1 && second.Disposals == 1, "Peer cleanup incomplete");
    }
    static async Task ReportsCleanupFailure()
    {
        await using var first = new Child { FailCleanup = true }; await using var second = new Child();
        first.AllowCleanup.Set(); second.AllowCleanup.Set(); var fleet = Fleet(first, second);
        await Start(fleet, first, second);
        Exception? failure = null;
        try { await Task.Run(fleet.Dispose); } catch (Exception ex) { failure = ex; }
        Check(failure is not null && failure.ToString().Contains("iMouse2-fixture-0")
            && failure.ToString().Contains("fixture cleanup unknown"), "Unconfirmed exit was reported as successful fleet shutdown");
        Check(second.Cleaned && first.Disposals == 1 && second.Disposals == 1, "Failure skipped a peer or retried cleanup");
    }
    static async Task ConcurrentShutdown()
    {
        await using var child = new Child(); var fleet = Fleet(child); Task? first = null, second = null;
        try
        {
            await Start(fleet, child); first = Task.Run(fleet.Dispose);
            await child.Cleaning.Task.WaitAsync(TimeSpan.FromSeconds(2));
            second = Task.Run(fleet.Dispose); await Task.Delay(150);
            Check(!first.IsCompleted && !second.IsCompleted, "A repeated shutdown returned before cleanup finished");
        }
        finally
        {
            child.AllowCleanup.Set();
            if (first is not null) await first;
            if (second is not null) await second;
            if (first is null) fleet.Dispose();
        }
        Check(child.Disposals == 1 && child.Cleaned, "Concurrent shutdown repeated receiver cleanup");
    }
    static async Task RefusesStartAfterDisposal()
    {
        await using var child = new Child(); child.AllowCleanup.Set(); var fleet = Fleet(child);
        fleet.Dispose(); bool refused = false;
        try { fleet.Start(CancellationToken.None); } catch (ObjectDisposedException) { refused = true; }
        finally { fleet.Dispose(); }
        Check(refused && !child.Started.Task.IsCompleted, "A disposed fleet accepted startup");
    }
    static async Task RefusesSecondStart()
    {
        await using var child = new Child(); child.AllowCleanup.Set(); var fleet = Fleet(child);
        try
        {
            await Start(fleet, child); bool refused = false;
            try { fleet.Start(CancellationToken.None); } catch (InvalidOperationException) { refused = true; }
            Check(refused, "Second start was accepted");
        }
        finally { await fleet.ShutdownAsync(); }
        Check(child.Disposals == 1, "Second start duplicated cleanup");
    }
    static async Task CancelledStartup()
    {
        await using var child = new Child(); child.AllowCleanup.Set(); var fleet = Fleet(child);
        using var cancel = new CancellationTokenSource(); cancel.Cancel();
        fleet.Start(cancel.Token); await fleet.ShutdownAsync().WaitAsync(TimeSpan.FromSeconds(2));
        Check(!child.Started.Task.IsCompleted && child.Disposals == 0, "Cancelled start created a child");
        Check(fleet.Sessions.All(s => s.Frames.Delivery.Status == "stopped"), "Frame readers not joined");
    }
    static async Task StopsDuringStartup()
    {
        await using var child = new Child(); child.AllowCleanup.Set();
        using var allowStart = new ManualResetEventSlim(false);
        var fleet = Fleet(child);
        fleet.Sessions[0] = fleet.Sessions[0] with { Supervisor = new AirplaySupervisor(() => {
            child.Started.TrySetResult();
            if (!allowStart.Wait(TimeSpan.FromSeconds(10))) throw new TimeoutException("Fixture startup gate timed out");
            return child;
        }) };
        Task? close = null;
        try
        {
            await Start(fleet, child); close = fleet.ShutdownAsync();
            await Task.Delay(150); Check(!close.IsCompleted, "Shutdown abandoned a factory in progress");
            allowStart.Set(); await close.WaitAsync(TimeSpan.FromSeconds(2));
            Check(child.Cleaned && child.Disposals == 1 && fleet.Sessions[0].Supervisor!.Info.State == "stopped",
                "Unpublished child escaped cleanup");
        }
        finally { allowStart.Set(); await (close ?? fleet.ShutdownAsync()).WaitAsync(TimeSpan.FromSeconds(12)); }
    }
    static async Task Until(Func<bool> ready)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(2));
        while (!ready()) await Task.Delay(1, deadline.Token);
    }
    static async Task PartialStartFailure()
    {
        await using var unused = new Child(); var fleet = Fleet(unused);
        fleet.Sessions[0] = fleet.Sessions[0] with { Supervisor = new AirplaySupervisor(() =>
            throw new ReceiverCleanupException(456, "fixture partial-start cleanup", new IOException("fixture"))) };
        try
        {
            fleet.Start(CancellationToken.None);
            await Until(() => fleet.Sessions[0].Supervisor!.Info.State == "failed");
            Exception? failure = null;
            try { await fleet.ShutdownAsync(); } catch (Exception ex) { failure = ex; }
            Check(failure is not null && failure.ToString().Contains("456") && failure.ToString().Contains("iMouse2-fixture-0"),
                "Partial startup failure lost its identity");
        }
        finally { try { await fleet.ShutdownAsync(); } catch (AggregateException) { } }
    }
    static async Task ExhaustedRetries()
    {
        await using var unused = new Child(); var fleet = Fleet(unused);
        fleet.Sessions[0] = fleet.Sessions[0] with { Supervisor = new AirplaySupervisor(() =>
            throw new IOException("fixture launch failure before a child exists"), 0, TimeSpan.Zero) };
        try
        {
            fleet.Start(CancellationToken.None);
            await Until(() => fleet.Sessions[0].Supervisor!.Info.State == "failed");
            await fleet.ShutdownAsync();
            Check(fleet.Sessions[0].Supervisor!.Info.State == "failed", "Historical startup failure erased");
        }
        finally { await fleet.ShutdownAsync(); }
    }
    static async Task ReleasesFramePipe()
    {
        await using var unused = new Child(); var fleet = Fleet(unused); var session = fleet.Sessions[0];
        fleet.Sessions[0] = session with { Supervisor = null };
        try
        {
            fleet.Start(CancellationToken.None);
            using (var client = new System.IO.Pipes.NamedPipeClientStream(".", session.Config.Pipe,
                System.IO.Pipes.PipeDirection.Out, System.IO.Pipes.PipeOptions.Asynchronous))
            {
                await client.ConnectAsync(2000);
                await Until(() => session.Frames.Delivery.Connected);
                await fleet.ShutdownAsync().WaitAsync(TimeSpan.FromSeconds(2));
                Check(!session.Frames.Delivery.Connected && session.Frames.Delivery.Status == "stopped", "Reader left connected");
            }
            using var rebound = new System.IO.Pipes.NamedPipeServerStream(session.Config.Pipe,
                System.IO.Pipes.PipeDirection.In, 1);
        }
        finally { await fleet.ShutdownAsync(); }
    }
    static async Task ReportsAllFailures()
    {
        await using var first = new Child { FailCleanup = true };
        await using var second = new Child { FailCleanup = true };
        first.AllowCleanup.Set(); second.AllowCleanup.Set(); var fleet = Fleet(first, second);
        await Start(fleet, first, second);
        var a = fleet.ShutdownAsync(); var b = fleet.ShutdownAsync();
        Check(ReferenceEquals(a, b), "Shutdown callers did not share completion");
        AggregateException? failure = null;
        try { await a; } catch (AggregateException ex) { failure = ex; }
        Check(failure?.InnerExceptions.Count == 2 && failure.ToString().Contains("iMouse2-fixture-0")
            && failure.ToString().Contains("iMouse2-fixture-1"), "One child failure hid the other");
        Check(b.IsFaulted && first.Disposals == 1 && second.Disposals == 1, "Repeated shutdown lost failure or repeated disposal");
    }
    sealed class Child : IReceiverHandle, IAsyncDisposable
    {
        public int Id => 123;
        public TaskCompletionSource Started { get; } = Signal();
        public TaskCompletionSource Exit { get; } = Signal();
        public TaskCompletionSource Cleaning { get; } = Signal();
        public ManualResetEventSlim AllowCleanup { get; } = new(false);
        public TaskCompletionSource CleanupFinished { get; } = Signal();
        public int Disposals;
        public bool Cleaned, FailCleanup;
        public Task WaitForExitAsync(CancellationToken ct) => Exit.Task.WaitAsync(ct);
        // Fixture teardown is distinct from the receiver's simulated cleanup.
        public async ValueTask DisposeAsync()
        {
            AllowCleanup.Set();
            if (Started.Task.IsCompleted) await CleanupFinished.Task.WaitAsync(TimeSpan.FromSeconds(12));
            AllowCleanup.Dispose();
        }
        public void Dispose()
        {
            Interlocked.Increment(ref Disposals); Cleaning.TrySetResult();
            try
            {
                if (!AllowCleanup.Wait(TimeSpan.FromSeconds(10))) throw new TimeoutException("Test cleanup gate timed out");
                if (FailCleanup) throw new IOException("fixture cleanup unknown");
                Cleaned = true; Exit.TrySetResult();
            }
            finally { CleanupFinished.TrySetResult(); }
        }
    }
}
