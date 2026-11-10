using System.Collections.Concurrent;
using System.Net.Http;
using System.Runtime.ExceptionServices;
using System.Text.Json;

namespace IMouse2;

internal static class DragInputTests
{
    private static TaskCompletionSource Signal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    private static Task Bounded(Task task) => task.WaitAsync(TimeSpan.FromSeconds(5));
    private static bool Cancelled(InputContext scope) => scope.Connection.IsCancellationRequested || scope.ControlToken.IsCancellationRequested;
    private static async Task<Exception?> Outcome(Task task)
    {
        try { await Bounded(task); return null; } catch (Exception ex) { return ex; }
    }
    private static async Task RunDrag(DragGesture gesture, CancellationToken ct)
    {
        var result = await DragInput.RunAsync(gesture, ct);
        if (result.Failure is not null) ExceptionDispatchInfo.Throw(result.Failure);
        if (result.ReleaseFailure is not null) ExceptionDispatchInfo.Throw(result.ReleaseFailure);
    }

    private sealed class Transport : HttpMessageHandler
    {
        internal readonly TestHandler Model = new();
        private HttpMessageInvoker? _invoker;
        internal readonly ConcurrentQueue<(string Fun, JsonElement Data)> Inputs = new();
        internal readonly TaskCompletionSource Down = Signal();
        internal Func<string, JsonElement, CancellationToken, Task>? Before;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            if (request.Method == HttpMethod.Post)
            {
                using var json = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
                string fun = json.RootElement.GetProperty("fun").GetString()!;
                var data = json.RootElement.GetProperty("data").Clone();
                if (fun.StartsWith("/mouse/") || fun == "/key/sendkey") Inputs.Enqueue((fun, data));
                if (fun == "/mouse/down") Down.TrySetResult();
                if (Before is { } before) await before(fun, data, ct);
            }
            _invoker ??= new(Model);
            return await _invoker.SendAsync(request, ct);
        }
        protected override void Dispose(bool disposing) { if (disposing) _invoker?.Dispose(); base.Dispose(disposing); }
    }

    internal static async Task RunAsync(Action<string, bool> check)
    {
        var transport = new Transport();
        await using var api = new ApiClient("http://localhost:9923", transport);
        using var connection = new CancellationTokenSource();
        using var control = new CancellationTokenSource();
        var context = new InputContext(api, "TEST:01,TEST:04", connection.Token, control);

        var mailbox = new DragGesture(context, 10, 20, false);
        mailbox.Move((30, 40)); mailbox.Move((50, 60));
        var next = await mailbox.ReadAsync(default);
        check("A drag mailbox coalesces to its latest complete coordinate", next == ((50, 60), false));
        var waiting = mailbox.ReadAsync(default);
        check("A stationary drag waits for movement or release without polling", !waiting.IsCompleted);
        mailbox.Release((70, 80));
        next = await waiting.WaitAsync(TimeSpan.FromSeconds(5));
        check("Release and its final coordinate arrive atomically", next == ((70, 80), true));
        mailbox.Move((90, 100)); mailbox.Release((110, 120));
        next = await mailbox.ReadAsync(default);
        check("Movement or duplicate release after lift cannot alter the completed gesture", next.Point is null && next.Released);
        var second = new DragGesture(context, 12, 22, true); second.Move((32, 42));
        mailbox.Release();
        check("Releasing an older gesture does not clear the newer gesture's movement", (await second.ReadAsync(default)) == ((32, 42), false));
        using var cancelledWait = new CancellationTokenSource();
        var read = second.ReadAsync(cancelledWait.Token); cancelledWait.Cancel();
        check("Cancellation wakes a stationary held gesture", await Outcome(read) is OperationCanceledException);

        // A new action is accepted while an old up is unanswered, but nothing from
        // that action reaches even the fake HTTP layer until up has completed.
        var upEntered = Signal(); var allowUp = Signal();
        int ups = 0;
        transport.Before = async (fun, _, ct) =>
        {
            if (fun == "/mouse/up" && Interlocked.Increment(ref ups) == 1)
            { upEntered.SetResult(); await allowUp.Task.WaitAsync(ct); }
        };
        // Inline startup makes the first incomplete await deterministic: a broken
        // queue would enter the next action immediately, before this assertion.
        var queue = new InputActionQueue(Cancelled, work => work());
        var firstDrag = new DragGesture(context, 10, 20, false);
        firstDrag.Move((30, 40));
        var firstTask = queue.Enqueue(context, ct => RunDrag(firstDrag, ct));
        await Bounded(transport.Down.Task);
        var nextDrag = new DragGesture(context, 70, 80, false);
        var nextTask = queue.Enqueue(context, ct => RunDrag(nextDrag, ct));
        nextDrag.Release((90, 100));
        var tap = queue.Enqueue(context, ct => api.CommandAsync("/mouse/click", new() { ["id"] = context.Ids, ["x"] = 110, ["y"] = 120 }, ct));
        check("A later gesture cannot send its setup move during an earlier held stroke",
            !transport.Inputs.Any(c => c.Fun == "/mouse/move" && c.Data.GetProperty("x").GetInt32() == 70)
            && !transport.Inputs.Any(c => c.Fun == "/mouse/click"));
        firstDrag.Release((50, 60));
        await Bounded(upEntered.Task);
        check("A second drag and tap stay queued until the first button release is acknowledged",
            !nextTask.IsCompleted && !tap.IsCompleted && transport.Inputs.Count(c => c.Fun == "/mouse/down") == 1
            && !transport.Inputs.Any(c => c.Fun == "/mouse/click"));
        allowUp.SetResult(); await Bounded(Task.WhenAll(firstTask, nextTask, tap));
        var commands = transport.Inputs.ToArray();
        var boundaries = commands.Where(c => c.Fun != "/mouse/move").Select(c => c.Fun).ToArray();
        check("Consecutive gestures keep down-up-down-up-click order", boundaries.SequenceEqual(["/mouse/down", "/mouse/up", "/mouse/down", "/mouse/up", "/mouse/click"]));
        check("The final point of each gesture arrives before its own release",
            commands[Array.FindIndex(commands, c => c.Fun == "/mouse/up") - 1].Data.GetProperty("x").GetInt32() == 50
            && commands[Array.FindLastIndex(commands, c => c.Fun == "/mouse/up") - 1].Data.GetProperty("x").GetInt32() == 90);
        check("Every queued gesture keeps its captured mirror targets", commands.All(c => c.Data.GetProperty("id").GetString() == context.Ids));

        // Delay the worker behind an existing action. Stop then Resume must never
        // lend the fresh token to a drag that was queued under the stopped one.
        var barrier = Signal(); var started = Signal();
        var blocker = queue.Enqueue(context, async _ => { started.SetResult(); await barrier.Task; });
        await Bounded(started.Task);
        using var oldControl = new CancellationTokenSource();
        var old = new InputContext(api, context.Ids, connection.Token, oldControl);
        int beforeStop = transport.Inputs.Count;
        var stale = new DragGesture(old, 130, 140, false); stale.Release((150, 160));
        var staleTask = queue.Enqueue(old, ct => RunDrag(stale, ct)); oldControl.Cancel();
        using var resumed = new CancellationTokenSource();
        var fresh = new InputContext(api, context.Ids, connection.Token, resumed);
        var freshTask = queue.Enqueue(fresh, ct => api.MoveAsync(fresh.Ids, 170, 180, ct));
        barrier.SetResult(); await Bounded(blocker);
        check("A queued drag stopped before dispatch sends no down or movement", await Outcome(staleTask) is OperationCanceledException);
        await Bounded(freshTask);
        check("Resume sends only new input, without replaying the cancelled drag", transport.Inputs.Skip(beforeStop).Select(c => c.Data.GetProperty("x").GetInt32()).SequenceEqual([170]));

        // The lease client's timeout notice itself can cancel the captured token
        // before the action's catch runs. It must remain a timeout + not-sent pair.
        var faultTransport = new Transport();
        await using var faultApi = new ApiClient("http://localhost:9923", faultTransport);
        using var faultControl = new CancellationTokenSource();
        var faultContext = new InputContext(faultApi, "TEST:01", connection.Token, faultControl);
        bool cancelledByNotice = false;
        faultApi.InputNotice += _ => { cancelledByNotice = true; faultControl.Cancel(); };
        var faultQueue = new InputActionQueue(c => c.Connection.IsCancellationRequested || (c.ControlToken.IsCancellationRequested && !cancelledByNotice));
        var failEntered = Signal(); var allowFail = Signal();
        faultTransport.Before = async (fun, data, ct) =>
        {
            if (fun == "/mouse/move" && data.GetProperty("x").GetInt32() == 210)
            { failEntered.SetResult(); await allowFail.Task.WaitAsync(ct); throw new TaskCanceledException("synthetic lost drag response"); }
        };
        var failedDrag = new DragGesture(faultContext, 190, 200, false); failedDrag.Move((210, 220));
        var failedTask = faultQueue.Enqueue(faultContext, ct => RunDrag(failedDrag, ct));
        await Bounded(failEntered.Task);
        var notSent = faultQueue.Enqueue(faultContext, ct => faultApi.MoveAsync("TEST:01", 230, 240, ct));
        allowFail.SetResult();
        check("An owned drag timeout retains the original cancellation exception", await Outcome(failedTask) is OperationCanceledException);
        check("The next queued action reports not sent even when the timeout notice cancelled its token", await Outcome(notSent) is InputNotSentException);
        check("A timed-out owned drag sends no extra up and no later move", faultTransport.Inputs.Select(c => c.Fun).SequenceEqual(["/mouse/move", "/mouse/down", "/mouse/move"]));
        check("The timeout still releases only the held lease through normal cleanup", faultTransport.Model.Commands.Any(c => c.GetProperty("fun").GetString() == "/input/release"));

        // Verify normal hold and legacy release through the same extracted runner.
        var holdTransport = new Transport();
        await using var holdApi = new ApiClient("http://localhost:9923", holdTransport);
        var holdContext = new InputContext(holdApi, "TEST:01", connection.Token, control);
        var hold = new DragGesture(holdContext, 250, 260, true);
        var holdTask = DragInput.RunAsync(hold, default); await Bounded(holdTransport.Down.Task);
        check("A stationary hold presses before lift and remains active", !holdTask.IsCompleted && !holdTransport.Inputs.Any(c => c.Fun == "/mouse/up"));
        hold.Release(); var holdResult = await holdTask.WaitAsync(TimeSpan.FromSeconds(5));
        check("A stationary hold releases once without adding a jitter move or click", holdResult.Released && holdResult.Moves == 0
            && holdTransport.Inputs.Select(c => c.Fun).SequenceEqual(["/mouse/move", "/mouse/down", "/mouse/up"]));

        var stopTransport = new Transport();
        await using var stopApi = new ApiClient("http://localhost:9923", stopTransport);
        using var stopControl = new CancellationTokenSource();
        var stopContext = new InputContext(stopApi, "TEST:01", connection.Token, stopControl);
        var stopQueue = new InputActionQueue(Cancelled);
        var stoppedHold = new DragGesture(stopContext, 310, 320, true);
        var stoppedTask = stopQueue.Enqueue(stopContext, ct => RunDrag(stoppedHold, ct));
        int stopNotices = 0; stopApi.InputNotice += _ => stopNotices++;
        await Bounded(stopTransport.Down.Task);
        stopControl.Cancel();
        await Bounded(stopApi.StopInputAsync("TEST:01"));
        check("Stop bypasses a stationary drag and cancels its action without a pause notice", await Outcome(stoppedTask) is OperationCanceledException && stopNotices == 0);
        check("Stop owns button cleanup rather than appending an obsolete mouse-up", stopTransport.Model.StoppedPhones.Contains("TEST:01")
            && !stopTransport.Inputs.Any(c => c.Fun == "/mouse/up"));
        await Bounded(stopApi.ResumeInputAsync("TEST:01"));
        using var afterStopControl = new CancellationTokenSource();
        var afterStop = new InputContext(stopApi, "TEST:01", connection.Token, afterStopControl);
        await Bounded(stopQueue.Enqueue(afterStop, ct => stopApi.MoveAsync("TEST:01", 330, 340, ct)));
        check("Explicit recovery after a held Stop accepts only the newly requested position", stopTransport.Inputs.Last().Data.GetProperty("x").GetInt32() == 330);

        var releaseTransport = new Transport();
        await using var releaseApi = new ApiClient("http://localhost:9923", releaseTransport);
        releaseTransport.Model.TimeoutFun = "/mouse/up";
        var uncertainRelease = new DragGesture(new(releaseApi, "TEST:01", connection.Token, control), 350, 360, false);
        uncertainRelease.Release((370, 380));
        var releaseResult = await DragInput.RunAsync(uncertainRelease, default);
        check("An unanswered up is reported as release failure and never retried", releaseResult.Failure is null
            && releaseResult.ReleaseFailure is OperationCanceledException && !releaseResult.Released
            && releaseTransport.Inputs.Count(c => c.Fun == "/mouse/up") == 1);
    }
}
