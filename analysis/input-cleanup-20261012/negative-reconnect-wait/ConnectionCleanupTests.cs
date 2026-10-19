using System.Collections.Concurrent;
using System.IO;
using System.Net.Http;
using System.Text.Json;

namespace IMouse2;

internal static class ConnectionCleanupTests
{
    private static TaskCompletionSource Signal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    private static Task Wait(Task task) => task.WaitAsync(TimeSpan.FromSeconds(5));
    private static Task Hold(ApiClient api, string ids = "TEST:01") =>
        api.CommandAsync("/mouse/down", new() { ["id"] = ids, ["button"] = "1" });

    private sealed class Transport : HttpMessageHandler
    {
        internal readonly TestHandler Model = new() { OwnershipSupported = true, StrictRelease = true };
        internal readonly ConcurrentQueue<(string Fun, JsonElement Data)> Requests = new();
        internal Func<string, JsonElement, CancellationToken, Task>? Before;
        internal int Disposals;
        private readonly SemaphoreSlim _modelGate = new(1);
        private HttpMessageInvoker? _inner;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            string fun = ""; JsonElement data = default;
            if (request.Method == HttpMethod.Post)
            {
                using var json = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
                fun = json.RootElement.GetProperty("fun").GetString()!;
                data = json.RootElement.GetProperty("data").Clone();
                Requests.Enqueue((fun, data));
            }
            if (Before is { } before) await before(fun, data, ct);
            await _modelGate.WaitAsync(ct);
            try { _inner ??= new(Model); return await _inner.SendAsync(request, ct); }
            finally { _modelGate.Release(); }
        }
        protected override void Dispose(bool disposing)
        {
            if (disposing) { Interlocked.Increment(ref Disposals); _inner?.Dispose(); }
            base.Dispose(disposing);
        }
        internal int Releases => Requests.Count(r => r.Fun == "/input/release");
    }

    internal static async Task RunAsync(Action<string, bool> check)
    {
        var wire = new Transport();
        var api = new ApiClient("http://localhost:9923", wire, ownership: true);
        await Hold(api);
        var releaseArrived = Signal(); var answer = Signal();
        wire.Before = async (fun, _, ct) => { if (fun == "/input/release") { releaseArrived.TrySetResult(); await answer.Task.WaitAsync(ct); } };
        Task<InputCloseResult> close = api.CloseAsync();
        await Wait(releaseArrived.Task);
        check("Close waits for the held phone's release before disposing transport", !close.IsCompleted && wire.Disposals == 0);
        api.Dispose();
        check("Dispose and repeated Close share the same cleanup operation", ReferenceEquals(close, api.CloseAsync()) && wire.Releases == 1);
        bool rejected = false;
        try { await Hold(api); } catch (ObjectDisposedException) { rejected = true; }
        check("Closing rejects new phone input before release finishes", rejected && wire.Requests.Count(r => r.Fun == "/mouse/down") == 1);
        answer.SetResult();
        var result = await close.WaitAsync(TimeSpan.FromSeconds(5));
        check("Close reports release acknowledgement and disposes transport once", result.Confirmed && result.Phones.Count == 1 && wire.Disposals == 1);
        check("Closing never sends Stop, Resume or a replayed press", !wire.Requests.Any(r => r.Fun is "/input/stop" or "/input/resume") && wire.Releases == 1);

        var two = new Transport();
        await using var pair = new ApiClient("http://localhost:9923", two, ownership: true);
        await Hold(pair, "TEST:01,TEST:04");
        var tokens = two.Model.ActiveLeases.ToDictionary(p => p.Key, p => p.Value);
        two.Model.ReleaseFailed.Add("TEST:04");
        var both = Signal(); var releaseBoth = Signal(); int arrivals = 0;
        two.Before = async (fun, _, ct) =>
        {
            if (fun != "/input/release") return;
            if (Interlocked.Increment(ref arrivals) == 2) both.TrySetResult();
            await releaseBoth.Task.WaitAsync(ct);
        };
        var pairClose = pair.CloseAsync(); await Wait(both.Task);
        check("Independent phone releases begin together instead of serial timeouts", arrivals == 2 && !pairClose.IsCompleted);
        releaseBoth.SetResult(); var pairResult = await pairClose;
        check("A board release failure remains unconfirmed without blocking another phone", !pairResult.Confirmed && pairResult.Phones.Single(p => p.Id == "TEST:01").Confirmed && !pairResult.Phones.Single(p => p.Id == "TEST:04").Confirmed);
        check("Shutdown releases only each phone's captured ownership token", two.Requests.Where(r => r.Fun == "/input/release").All(r =>
            tokens[r.Data.GetProperty("id").GetString()!] == r.Data.GetProperty("token").GetString()));

        var retiring = new Transport();
        await using var releasing = new ApiClient("http://localhost:9923", retiring, ownership: true);
        await Hold(releasing);
        var releaseStarted = Signal(); var finishRelease = Signal();
        retiring.Before = async (fun, _, ct) => { if (fun == "/input/release") { releaseStarted.TrySetResult(); await finishRelease.Task.WaitAsync(ct); } };
        var scopeRelease = releasing.ReleaseInputAsync("TEST:01"); await Wait(releaseStarted.Task);
        var retireClose = releasing.CloseAsync();
        // It is now closed to new operators; the in-flight release still owns its fence.
        bool resumeRejected = false;
        try { await releasing.ResumeInputAsync("TEST:01"); } catch (ObjectDisposedException) { resumeRejected = true; }
        await Task.Delay(40);
        check("Close observes a release already in flight after its token was detached", !retireClose.IsCompleted && retiring.Disposals == 0 && resumeRejected);
        finishRelease.SetResult(); await scopeRelease;
        check("An in-flight scope release is counted once by shutdown", (await retireClose).Confirmed && retiring.Releases == 1);

        var lost = new Transport();
        await using var unknown = new ApiClient("http://localhost:9923", lost, ownership: true);
        await Hold(unknown); lost.Model.ReleaseTimeout = true;
        check("A missing release answer is never reported as confirmed shutdown", !(await unknown.CloseAsync()).Confirmed && lost.Disposals == 1);

        var stopped = new Transport();
        await using var afterStop = new ApiClient("http://localhost:9923", stopped, ownership: true);
        await Hold(afterStop); await afterStop.StopInputAsync("TEST:01");
        check("A completed Stop supplies shutdown confirmation without a stale release", (await afterStop.CloseAsync()).Confirmed && stopped.Releases == 0);

        var failed = new Transport();
        await using var failedRelease = new ApiClient("http://localhost:9923", failed, ownership: true);
        await Hold(failedRelease); failed.Model.ReleaseFailed.Add("TEST:01");
        await failedRelease.ReleaseInputAsync("TEST:01");
        check("A failed prior release is retained even after its token was detached", !(await failedRelease.CloseAsync()).Confirmed);

        var stalled = new Transport(); var unblock = Signal(); var entered = Signal(); var left = Signal();
        await using var bounded = new ApiClient("http://localhost:9923", stalled, ownership: true, closeTimeout: TimeSpan.FromMilliseconds(120));
        await Hold(bounded);
        stalled.Before = async (fun, _, _) =>
        {
            if (fun != "/input/release") return;
            entered.TrySetResult(); await unblock.Task; left.TrySetResult();
        };
        var boundedClose = bounded.CloseAsync(); await Wait(entered.Task);
        var boundedResult = await boundedClose.WaitAsync(TimeSpan.FromSeconds(5));
        check("Shutdown is bounded even when a transport ignores cancellation", !boundedResult.Confirmed && boundedResult.Failure?.Contains("0.12 seconds") == true && stalled.Disposals == 1);
        unblock.SetResult(); await Wait(left.Task);

        // An acquire can finish after cancellation. Exercise the lease client directly
        // so the fake can return the late token even after its cancellation was signalled.
        var acquired = Signal(); var returnAcquire = Signal(); var leaseReleased = Signal();
        using var caller = new CancellationTokenSource();
        await using var late = new InputLeaseClient(async (fun, _, _) =>
        {
            if (fun == "/input/acquire")
            {
                acquired.TrySetResult(); await returnAcquire.Task;
                return JsonSerializer.SerializeToElement(new { leases = new[] { new { id = "TEST:01", token = "private-token" } } });
            }
            if (fun == "/input/release") { leaseReleased.TrySetResult(); throw new ApiException("no release", 33); }
            throw new Exception("Unexpected command: " + fun);
        }, _ => Task.CompletedTask);
        var lateCommand = late.CommandAsync("/mouse/down", new() { ["id"] = "TEST:01" }, caller.Token);
        await Wait(acquired.Task); caller.Cancel(); returnAcquire.SetResult();
        try { await lateCommand; } catch (OperationCanceledException) { }
        await Wait(leaseReleased.Task);
        check("A cancelled acquire retains an unconfirmed release in the close result", !(await late.CloseAsync()).Confirmed);

        var tracker = new ConnectionCleanup();
        var tracked = new Transport(); var continueTracked = Signal(); var trackedArrived = Signal();
        var trackedApi = new ApiClient("http://localhost:9923", tracked, ownership: true);
        await Hold(trackedApi);
        tracked.Before = async (fun, _, ct) => { if (fun == "/input/release") { trackedArrived.TrySetResult(); await continueTracked.Task.WaitAsync(ct); } };
        tracker.Retire(trackedApi); tracker.Retire(trackedApi);
        var drain = tracker.DrainAsync(); await Wait(trackedArrived.Task);
        var second = new Transport(); var secondApi = new ApiClient("http://localhost:9923", second, ownership: true);
        await Hold(secondApi); second.Model.ReleaseTimeout = true; tracker.Retire(secondApi);
        check("Reconnect cleanup stays pending until the previous connection answers", !drain.IsCompleted && tracked.Disposals == 0);
        continueTracked.SetResult(); var records = await drain;
        check("Cleanup includes clients retired while it was already waiting", records.Count == 2 && records.Count(r => !r.Result.Confirmed) == 1 && tracked.Releases == 1);
        check("Repeated cleanup drains preserve the result without another release", (await tracker.DrainAsync()).Count == 2 && tracked.Releases == 1);

        string folder = Path.Combine(Path.GetTempPath(), "imouse-cleanup-tests-" + Guid.NewGuid().ToString("N"));
        try
        {
            check("Cleanup receipt saves in its explicit profile directory", ConnectionCleanup.Save(folder, records) is null && File.Exists(Path.Combine(folder, "last-input-cleanup.json")));
            using (var json = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "last-input-cleanup.json"))))
                check("Cleanup receipt preserves unconfirmed connection results", !json.RootElement.GetProperty("confirmed").GetBoolean() && json.RootElement.GetProperty("connections").GetArrayLength() == 2);
            var warningBytes = File.ReadAllBytes(Path.Combine(folder, "last-input-cleanup-warning.json"));
            var clean = new[] { new ConnectionCleanupRecord(DateTimeOffset.UtcNow, "http://localhost:9923", new InputCloseResult([])) };
            ConnectionCleanup.Save(folder, clean);
            check("A clean close cannot erase an earlier unconfirmed-release warning", warningBytes.SequenceEqual(File.ReadAllBytes(Path.Combine(folder, "last-input-cleanup-warning.json"))));
            check("Cleanup recording never creates a settings file or launcher mirror", !File.Exists(Path.Combine(folder, "settings.json")) && !Directory.Exists(Path.Combine(folder, "data")));
            var unsafeRecord = new[] { new ConnectionCleanupRecord(DateTimeOffset.UtcNow, "http://localhost:9923",
                new InputCloseResult([new("TEST:01", false, "private-token")], "private-token")) };
            ConnectionCleanup.Save(folder, unsafeRecord);
            check("Cleanup receipts exclude raw service error text and private tokens", !File.ReadAllText(Path.Combine(folder, "last-input-cleanup.json")).Contains("private-token"));
            string destination = Path.Combine(folder, "last-input-cleanup.json"); var before = File.ReadAllBytes(destination);
            using (var locked = new FileStream(destination, FileMode.Open, FileAccess.Read, FileShare.Read))
                check("A locked cleanup receipt reports failure instead of false persistence", ConnectionCleanup.Save(folder, clean) is not null);
            check("Failed cleanup receipt replacement preserves the prior complete record", before.SequenceEqual(File.ReadAllBytes(destination)) && !Directory.EnumerateFiles(folder, "*.tmp").Any());
        }
        finally { if (Directory.Exists(folder)) Directory.Delete(folder, true); }
    }
}
