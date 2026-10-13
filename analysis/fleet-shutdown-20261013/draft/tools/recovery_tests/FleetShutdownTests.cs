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
        using var child = new Child(); var fleet = Fleet(child); Task? close = null;
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
        using var first = new Child(); using var second = new Child();
        second.AllowCleanup.Set(); var fleet = Fleet(first, second); Task? close = null;
        try
        {
            await Start(fleet, first, second); close = Task.Run(fleet.Dispose);
            await first.Cleaning.Task.WaitAsync(TimeSpan.FromSeconds(2));
            await second.Cleaning.Task.WaitAsync(TimeSpan.FromMilliseconds(600));
            Check(!close.IsCompleted, "Fleet returned before the slow receiver exited");
        }
        finally { first.AllowCleanup.Set(); second.AllowCleanup.Set(); if (close is not null) await close; else fleet.Dispose(); }
        Check(first.Cleaned && second.Cleaned && first.Disposals == 1 && second.Disposals == 1, "Peer cleanup incomplete");
    }
    static async Task ReportsCleanupFailure()
    {
        using var first = new Child { FailCleanup = true }; using var second = new Child();
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
        using var child = new Child(); var fleet = Fleet(child); Task? first = null, second = null;
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
    static Task RefusesStartAfterDisposal()
    {
        using var child = new Child(); child.AllowCleanup.Set(); var fleet = Fleet(child);
        fleet.Dispose(); bool refused = false;
        try { fleet.Start(CancellationToken.None); } catch (ObjectDisposedException) { refused = true; }
        finally { fleet.Dispose(); }
        Check(refused && !child.Started.Task.IsCompleted, "A disposed fleet accepted startup");
        return Task.CompletedTask;
    }
    sealed class Child : IReceiverHandle
    {
        public int Id => 123;
        public TaskCompletionSource Started { get; } = Signal();
        public TaskCompletionSource Exit { get; } = Signal();
        public TaskCompletionSource Cleaning { get; } = Signal();
        public ManualResetEventSlim AllowCleanup { get; } = new(false);
        public int Disposals;
        public bool Cleaned, FailCleanup;
        public Task WaitForExitAsync(CancellationToken ct) => Exit.Task.WaitAsync(ct);
        public void Dispose()
        {
            Interlocked.Increment(ref Disposals); Cleaning.TrySetResult();
            if (!AllowCleanup.Wait(TimeSpan.FromSeconds(5))) throw new TimeoutException("Test cleanup gate timed out");
            if (FailCleanup) throw new IOException("fixture cleanup unknown");
            Cleaned = true; Exit.TrySetResult();
        }
    }
}
