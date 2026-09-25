using System.Collections.Concurrent;
using System.Text.Json;

namespace IMouse2.Kernel;

internal static class InputSessionTests
{
    private sealed class Transport : IHidTransport
    {
        public ConcurrentQueue<string> Reports = new();
        public Func<string, bool>? Block;
        public Func<string, bool>? Fail;
        public TaskCompletionSource Entered = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Unblock = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool Disposed;
        public async Task SendAsync(byte[] data, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            string hex = Convert.ToHexString(data);
            Reports.Enqueue(hex);
            if (Fail?.Invoke(hex) == true) throw new IOException("Test release failure");
            if (Block?.Invoke(hex) == true) { Entered.TrySetResult(); await Unblock.Task.WaitAsync(ct); }
        }
        public void Dispose() => Disposed = true;
    }
    private static JsonElement Data(object value) => JsonSerializer.SerializeToElement(value);
    private static int Code(object value) => Data(value).GetProperty("code").GetInt32();
    private static string Lease(InputSessions sessions, string id)
    {
        var result = Data(sessions.Acquire(Data(new { id })));
        if (result.GetProperty("code").GetInt32() != 0) throw new Exception("Cannot acquire test lease");
        return result.GetProperty("leases")[0].GetProperty("token").GetString()!;
    }
    private static async Task Rejected(Func<Task<object>> action)
    {
        try { await action(); } catch (InvalidOperationException) { return; }
        throw new Exception("Expected ownership rejection");
    }
    public static async Task RunAsync(Action<bool, string> check)
    {
        string directory = Path.Combine(Path.GetTempPath(), "imouse-ownership-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        string file = Path.Combine(directory, "devices.json");
        File.WriteAllText(file, JsonSerializer.Serialize(new[] {
            new Phone { deviceid = "one", pid = "C24C", uid = "A" },
            new Phone { deviceid = "two", pid = "C241", uid = "B" }
        }));
        var store = new DeviceStore(file);
        var a = new Transport(); var b = new Transport();
        int opened = 0;
        using var input = new InputRouter(store, ["C24C", "C241"],
            [new("C24C", 500, 1080, 14, 14, 5, 5), new("C241", 500, 1080, 14, 14, 5, 5)],
            pid => { Interlocked.Increment(ref opened); return pid == "C24C" ? a : b; });
        long clock = 0;
        await using var sessions = new InputSessions(store, input, () => Interlocked.Read(ref clock));
        try
        {
            await Rejected(() => sessions.DispatchAsync("/mouse/click", Data(new { id = "one", x = 14, y = 14 })));
            check(opened == 0, "Missing ownership token sends no HID");
            string first = Lease(sessions, "one");
            check(Code(sessions.Acquire(Data(new { id = "one,two" }))) == 409,
                "Batch acquisition conflicts atomically");
            string second = Lease(sessions, "two");
            check(first != second && !JsonSerializer.Serialize(sessions.Status()).Contains(first),
                "Per-phone tokens are distinct and status does not reveal them");
            await Rejected(() => sessions.DispatchAsync("/mouse/click", Data(new { id = "two", token = first, x = 14, y = 14 })));
            check(opened == 0, "One phone token cannot control another phone");

            a.Block = hex => hex == "A200040000000000";
            var held = sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token = first, key = "a" }));
            await a.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
            check(Code(await sessions.DispatchAsync("/mouse/click", Data(new { id = "one", token = first, x = 14, y = 14 }))) == 409,
                "Concurrent command on same phone is rejected without queuing");
            check(Code(await sessions.DispatchAsync("/mouse/click", Data(new { id = "two", token = second, x = 14, y = 14 })).WaitAsync(TimeSpan.FromSeconds(2))) == 0 && !held.IsCompleted,
                "Second phone runs while first phone command is active");
            check(Code(await sessions.StopAsync(Data(new { id = "one" })).WaitAsync(TimeSpan.FromSeconds(2))) == 0,
                "Stop interrupts active keyboard input and waits for cleanup");
            check(Code(await held) != 0 && a.Reports.TakeLast(2).SequenceEqual(new[] { "A100000000000000", "A200000000000000" }),
                "Cancellation releases mouse and keyboard without cancelled token");
            check(a.Disposed && Code(sessions.Acquire(Data(new { id = "one" }))) == 409,
                "Stop closes transport and latches stopped state");
            check(Code(await sessions.DispatchAsync("/key/sendkey", Data(new { id = "two", token = second, fn_key = "Enter" }))) == 0,
                "Stopping one phone preserves other phone ownership");
            check(Code(sessions.Resume(Data(new { id = "one" }))) == 0, "Explicit resume allows fresh ownership");
            await Rejected(() => sessions.DispatchAsync("/mouse/click", Data(new { id = "one", token = first, x = 14, y = 14 })));
            check(true, "Old tokens cannot replay input after resume");

            a.Block = null; a.Reports.Clear();
            first = Lease(sessions, "one");
            await sessions.DispatchAsync("/mouse/move", Data(new { id = "one", token = first, x = 14, y = 14 }));
            await sessions.DispatchAsync("/mouse/down", Data(new { id = "one", token = first, button = 1 }));
            check(Code(sessions.Acquire(Data(new { id = "one" }))) == 409, "Lease spans separate gesture commands");
            await sessions.DispatchAsync("/mouse/move", Data(new { id = "one", token = first, x = 24, y = 14 }));
            await sessions.DispatchAsync("/mouse/up", Data(new { id = "one", token = first, button = 1 }));
            check(a.Reports.Contains("A101010000000000"), "Owned multi-request drag preserves held-button movement");
            int beforeA = a.Reports.Count, beforeB = b.Reports.Count;
            await Rejected(() => sessions.DispatchAsync("/mouse/click", Data(new { id = "one,two", tokens = new Dictionary<string, string> { ["one"] = first, ["two"] = "invalid" }, x = 14, y = 14 })));
            check(a.Reports.Count == beforeA && b.Reports.Count == beforeB, "Invalid group token rejects all targets before output");
            bool invalid = false;
            try { await sessions.DispatchAsync("/mouse/click", Data(new { id = "one,two", tokens = new Dictionary<string, string> { ["one"] = first, ["two"] = second }, x = 9999, y = 14 })); }
            catch (ArgumentException) { invalid = true; }
            check(invalid && a.Reports.Count == beforeA && b.Reports.Count == beforeB, "Group coordinates validated before either board receives input");
            check(Code(await sessions.DispatchAsync("/mouse/click", Data(new { id = "one,two", tokens = new Dictionary<string, string> { ["one"] = first, ["two"] = second }, x = 14, y = 14 }))) == 0,
                "Explicit group input succeeds with both independently acquired leases");
            await sessions.DispatchAsync("/mouse/down", Data(new { id = "one", token = first }));
            check(Code(await sessions.StopAsync(Data(new { id = "one", token = first }), release: true)) == 0 &&
                a.Reports.TakeLast(2).SequenceEqual(new[] { "A100000000000000", "A200000000000000" }),
                "Releasing idle lease releases held inputs");
            first = Lease(sessions, "one");
            check(Code(sessions.Renew(Data(new { id = "one", token = first }))) == 0, "Controller can renew its own lease");
            Interlocked.Exchange(ref clock, 30_001);
            await Rejected(() => Task.FromResult(sessions.Renew(Data(new { id = "one", token = first }))));
            await sessions.StopAsync(Data(new { id = "one,two" }));
            check(Code(sessions.Acquire(Data(new { id = "one" }))) == 409, "Expired lease cannot be revived and requires explicit resume");
            sessions.Resume(Data(new { id = "one,two" }));
            first = Lease(sessions, "one");
            // Simulate a saved binding changing outside the API. No old lease may survive.
            store.Bind("one", "", "C24C", "CHANGED");
            await Rejected(() => sessions.DispatchAsync("/mouse/reset", Data(new { id = "one", token = first })));
            check(true, "Changed board UID invalidates existing lease");
        }
        finally { await sessions.DisposeAsync(); File.Delete(file); Directory.Delete(directory); }

        // Separate fixture: expiry watchdog must release a held button even when
        // the client disappears without making another HTTP request.
        string expiryFile = Path.Combine(Path.GetTempPath(), "imouse-expiry-" + Guid.NewGuid().ToString("N") + ".json");
        File.WriteAllText(expiryFile, JsonSerializer.Serialize(new[] { new Phone { deviceid = "one", pid = "C24C" } }));
        try
        {
            var expiryStore = new DeviceStore(expiryFile);
            var transport = new Transport(); long now = 0;
            using var expiryInput = new InputRouter(expiryStore, ["C24C"], [new("C24C",500,1080,14,14,5,5)], _ => transport);
            await using var expiry = new InputSessions(expiryStore, expiryInput, () => Interlocked.Read(ref now));
            string token = Lease(expiry, "one");
            await expiry.DispatchAsync("/mouse/down", Data(new { id = "one", token }));
            Interlocked.Exchange(ref now, 31_000);
            for (int n = 0; n < 100 && !transport.Disposed; n++) await Task.Delay(10);
            check(transport.Disposed && transport.Reports.TakeLast(2).SequenceEqual(new[] { "A100000000000000", "A200000000000000" }),
                "Expiry watchdog releases abandoned held input without another request");
        }
        finally { File.Delete(expiryFile); }

        // Cleanup failure must remain visible, not turn into a successful Stop.
        string failureFile = Path.Combine(Path.GetTempPath(), "imouse-release-" + Guid.NewGuid().ToString("N") + ".json");
        File.WriteAllText(failureFile, JsonSerializer.Serialize(new[] { new Phone { deviceid = "one", pid = "C24C" } }));
        try
        {
            var failStore = new DeviceStore(failureFile); var transport = new Transport();
            using var failInput = new InputRouter(failStore, ["C24C"], [new("C24C",500,1080,14,14,5,5)], _ => transport);
            await using var failing = new InputSessions(failStore, failInput);
            string token = Lease(failing, "one");
            await failing.DispatchAsync("/mouse/down", Data(new { id = "one", token }));
            transport.Fail = hex => hex == "A100000000000000";
            check(Code(await failing.StopAsync(Data(new { id = "one" }))) == 33 && Code(failing.Resume(Data(new { id = "one" }))) == 409,
                "Failed release is reported and blocks resume");
            check(transport.Reports.Last() == "A200000000000000", "Keyboard release is still attempted when mouse release fails");
        }
        finally { File.Delete(failureFile); }

        string apiFile = Path.Combine(Path.GetTempPath(), "imouse-session-api-" + Guid.NewGuid().ToString("N") + ".json");
        File.WriteAllText(apiFile, JsonSerializer.Serialize(new[] { new Phone { deviceid = "one", pid = "C24C" } }));
        try
        {
            var apiStore = new DeviceStore(apiFile); var transport = new Transport();
            using var apiInput = new InputRouter(apiStore, ["C24C"], [new("C24C",500,1080,14,14,5,5)], _ => transport);
            using var frames = new FrameStore("unused-session-test-" + Guid.NewGuid().ToString("N"), "one");
            // Exercise actual API dispatch without opening a listener, pipe, or board.
            using var server = new ApiServer("http://127.0.0.1:19913/api/", apiStore, "iMouse2-test", apiInput, frames);
            Task<object> Request(string fun, object data) => server.Dispatch(Data(new { fun, data }));
            await Rejected(() => Request("/mouse/click", new { id = "one", x = 14, y = 14 }));
            check(transport.Reports.IsEmpty, "API cannot bypass required ownership with a legacy command");
            var acquired = Data(await Request("/input/acquire", new { id = "one" }));
            string token = acquired.GetProperty("leases")[0].GetProperty("token").GetString()!;
            check(Code(await Request("/input/renew", new { id = "one", token })) == 0 &&
                Code(await Request("/mouse/down", new { id = "one", token })) == 0, "API acquisition and renewal reach owned HID dispatch");
            check(Code(await Request("/device/set", new { id = "one", pid = "C241", uid = "wrong" })) == 41 &&
                apiStore.All()[0].pid == "C24C", "API forbids live rebinding under active input");
            check(Code(await Request("/input/stop", new { id = "one" })) == 0 &&
                Code(await Request("/input/resume", new { id = "one" })) == 0, "API Stop and Resume use the ownership boundary");
            token = Data(await Request("/input/acquire", new { id = "one" })).GetProperty("leases")[0].GetProperty("token").GetString()!;
            transport.Block = hex => hex == "A200040000000000";
            var active = Request("/key/sendkey", new { id = "one", token, key = "a" });
            await transport.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
            await Task.Run(server.Dispose).WaitAsync(TimeSpan.FromSeconds(2));
            check(Code(await active) != 0 && transport.Disposed && transport.Reports.Last() == "A200000000000000",
                "Kernel API shutdown cancels active input and drains release before returning");
        }
        finally { File.Delete(apiFile); }
    }
}
