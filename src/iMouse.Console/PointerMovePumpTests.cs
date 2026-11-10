using System.Collections.Concurrent;
using System.Net.Http;
using System.Text.Json;

namespace IMouse2;

internal static class PointerMovePumpTests
{
    private static TaskCompletionSource Signal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    private static Task Bounded(Task task) => task.WaitAsync(TimeSpan.FromSeconds(5));

    private sealed class Scheduler
    {
        internal readonly Queue<Func<Task>> Work = new();
        internal void Start(Func<Task> work) => Work.Enqueue(work);
        internal Task Run() => Work.Dequeue()();
    }

    // All HTTP requests terminate in TestHandler. This gate delays only one synthetic
    // move's response, so ordering is checked in the real lease client, without a server.
    private sealed class MoveGateHandler : HttpMessageHandler
    {
        private readonly HttpMessageInvoker _mock = new(new TestHandler());
        internal readonly TaskCompletionSource Entered = Signal(), Release = Signal();
        internal readonly ConcurrentQueue<string> Inputs = new();
        private int _moves;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            if (request.Method == HttpMethod.Post)
            {
                using var json = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
                string fun = json.RootElement.GetProperty("fun").GetString()!;
                if (fun.StartsWith("/mouse/")) Inputs.Enqueue(fun);
                if (fun == "/mouse/move" && Interlocked.Increment(ref _moves) == 1)
                {
                    Entered.TrySetResult();
                    await Release.Task.WaitAsync(ct);
                }
            }
            return await _mock.SendAsync(request, ct);
        }
        protected override void Dispose(bool disposing) { if (disposing) _mock.Dispose(); base.Dispose(disposing); }
    }

    internal static async Task RunAsync(Action<string, bool> check)
    {
        await using var api = new ApiClient("http://localhost:9923", new TestHandler());
        await using var otherApi = new ApiClient("http://localhost:9923", new TestHandler());
        using var connection = new CancellationTokenSource();
        using var control = new CancellationTokenSource();
        PointerMove Move(int x, string ids = "TEST:01") => new(api, ids, x, x + 1, connection.Token, control.Token);

        var scheduler = new Scheduler();
        var sent = new List<PointerMove>();
        var gate = Signal();
        var pump = new PointerMovePump((move, _) => { sent.Add(move); return gate.Task; }, scheduler.Start);
        pump.Post(Move(1)); pump.Post(Move(2));
        check("Hover queues one worker and coalesces before dispatch", scheduler.Work.Count == 1 && pump.IsRunning);
        var worker = scheduler.Run();
        pump.Post(Move(3)); pump.Post(Move(4));
        check("A pending hover does not dispatch while the prior move is in flight", sent.Select(m => m.X).SequenceEqual([2]));
        gate.SetResult(); await Bounded(worker);
        check("The last hover received during a send is delivered exactly once", sent.Select(m => m.X).SequenceEqual([2, 4]) && !pump.IsRunning);
        pump.Post(Move(5)); await Bounded(scheduler.Run());
        check("Arrival after idle starts another worker instead of stranding a hover", sent[^1].X == 5 && !pump.IsRunning && pump.WhenIdle.IsCompleted);

        scheduler = new(); sent.Clear();
        pump = new((move, _) => { sent.Add(move); return Task.CompletedTask; }, scheduler.Start);
        pump.Post(Move(10));
        using var nextControl = new CancellationTokenSource();
        var newScope = new PointerMove(otherApi, "TEST:02,TEST:03", 70, 80, connection.Token, nextControl.Token);
        pump.Post(newScope); await Bounded(scheduler.Run());
        check("Coordinates, mirror targets, client and control lifetime are replaced together", sent.Count == 1 && sent[0] == newScope);

        using var stopped = new CancellationTokenSource();
        scheduler = new(); sent.Clear();
        pump = new((move, _) => { sent.Add(move); return Task.CompletedTask; }, scheduler.Start);
        pump.Post(Move(12) with { Control = stopped.Token });
        stopped.Cancel();
        // Resume exists before the delayed worker starts. It cannot lend its token to 12.
        using var resumed = new CancellationTokenSource();
        await Bounded(scheduler.Run());
        check("Stop before worker startup prevents the original movement", sent.Count == 0);
        pump.Post(Move(13) with { Control = resumed.Token }); await Bounded(scheduler.Run());
        check("Explicit Resume can send a new movement without replaying the stopped one", sent.Select(m => m.X).SequenceEqual([13]));

        scheduler = new(); sent.Clear(); gate = Signal();
        CancellationToken observed = default;
        pump = new((move, ct) => { sent.Add(move); observed = ct; return move.X == 20 ? gate.Task : Task.CompletedTask; }, scheduler.Start);
        using var oldControl = new CancellationTokenSource();
        pump.Post(Move(20) with { Control = oldControl.Token }); worker = scheduler.Run();
        oldControl.Cancel();
        check("An in-flight hover retains the cancellation token from its own control scope", observed.IsCancellationRequested);
        pump.Post(newScope); gate.SetException(new OperationCanceledException()); await Bounded(worker);
        check("Failure of an old scope does not erase a new phone's pending hover", sent.Count == 2 && sent[1] == newScope);

        scheduler = new(); sent.Clear(); gate = Signal();
        pump = new((move, _) => { sent.Add(move); return gate.Task; }, scheduler.Start);
        pump.Post(Move(30)); worker = scheduler.Run(); pump.Post(Move(31));
        gate.SetException(new TimeoutException("synthetic lost response")); await Bounded(worker);
        pump.Post(Move(32));
        check("A failed owned hover is not replayed and pauses its queued scope", sent.Select(m => m.X).SequenceEqual([30]) && scheduler.Work.Count == 0);
        gate = Signal(); gate.SetResult();
        pump.Post(Move(33) with { Control = resumed.Token }); await Bounded(scheduler.Run());
        check("A new control lifetime can move after an uncertain hover outcome", sent[^1].X == 33);

        scheduler = new(); sent.Clear();
        pump = new((move, _) => { sent.Add(move); return Task.CompletedTask; }, scheduler.Start);
        pump.Post(Move(40)); pump.ClearPending(); await Bounded(scheduler.Run());
        check("Beginning a gesture or disabling tracking discards unsent hover", sent.Count == 0);
        pump.Post(Move(41)); pump.Close(); pump.Post(Move(42)); await Bounded(scheduler.Run());
        check("Closing the window prevents pending and later hover dispatch", sent.Count == 0 && !pump.IsRunning);
        using var disconnected = new CancellationTokenSource(); disconnected.Cancel();
        scheduler = new();
        pump = new((_, _) => throw new Exception("No send expected"), scheduler.Start);
        pump.Post(Move(1) with { Connection = disconnected.Token }); pump.Post(Move(2, ""));
        check("Disconnected and empty scopes do not start pointer work", scheduler.Work.Count == 0);

        var transport = new MoveGateHandler();
        await using var owned = new ApiClient("http://localhost:9923", transport);
        scheduler = new(); pump = new(start: scheduler.Start);
        pump.Post(Move(60) with { Api = owned }); worker = scheduler.Run();
        await Bounded(transport.Entered.Task);
        pump.Post(Move(61) with { Api = owned }); pump.ClearPending();
        var down = owned.CommandAsync("/mouse/down", new() { ["id"] = "TEST:01", ["button"] = "1" });
        check("Gesture submission waits behind the dispatched hover in the real lease queue",
            !down.IsCompleted && transport.Inputs.SequenceEqual(["/mouse/move"]));
        transport.Release.SetResult(); await Bounded(Task.WhenAll(worker, down));
        check("A cleared pending hover never lands after gesture down", transport.Inputs.SequenceEqual(["/mouse/move", "/mouse/down"]));
        await owned.CommandAsync("/mouse/up", new() { ["id"] = "TEST:01", ["button"] = "1" });

        // Exercise concurrent producers and worker exit, then require a unique final
        // position. Intermediate positions may coalesce; the final one must not vanish.
        var concurrent = new ConcurrentQueue<PointerMove>();
        pump = new((move, _) => { concurrent.Enqueue(move); return Task.CompletedTask; });
        await Task.WhenAll(Enumerable.Range(0, 4).Select(i => Task.Run(() =>
        {
            for (int j = 0; j < 250; j++) pump.Post(Move(i * 250 + j));
        })));
        pump.Post(Move(2000)); await Bounded(pump.WhenIdle);
        check("Concurrent hover arrivals finish at the final requested position", concurrent.Last().X == 2000 && !pump.IsRunning);
    }
}
