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
    /// <summary>
    /// --home-sequence: each option's exact reports, and that every option still needs the phone's
    /// lease, runs under its write gate, and is cancelled by Stop with keys and buttons released.
    /// </summary>
    public static async Task HomeSequenceAsync(Action<bool, string> check)
    {
        string directory = Path.Combine(Path.GetTempPath(), "imouse-home-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        string file = Path.Combine(directory, "devices.json");
        File.WriteAllText(file, JsonSerializer.Serialize(new[] { new Phone { deviceid = "one", pid = "C24C", uid = "A" } }));
        var store = new DeviceStore(file);
        const string release = "A200000000000000", tab = "A2002B0000000000", guiH = "A2080B0000000000";
        var expected = new Dictionary<HomeSequence, string[]>
        {
            [HomeSequence.Vendor] = [release, tab, release, release, guiH, release],
            [HomeSequence.CommandH] = [release, guiH, release],
        };
        try
        {
            check(new InputRouter(store, [], []).Home == HomeSequence.Vendor, "Home sequence defaults to the vendor sequence");
            foreach (string bad in new[] { "", "Vendor", "command_h", "tab", "command-wake", "fn-h" })
            {
                bool threw = false;
                try { InputRouter.ParseHomeSequence(bad); } catch (ArgumentException) { threw = true; }
                check(threw, $"--home-sequence rejects \"{bad}\"");
            }
            foreach (var (sequence, reports) in expected)
            {
                var t = new Transport();
                using var input = new InputRouter(store, ["C24C"], [new("C24C", 500, 1080, 14, 14, 5, 5)], _ => t) { Home = sequence };
                await using var sessions = new InputSessions(store, input);
                await Rejected(() => sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", fn_key = "Home" })));
                check(t.Reports.IsEmpty, $"Home ({input.HomeSequenceName}) without the phone's lease sends nothing");
                string token = Lease(sessions, "one");
                check(Code(await sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token, fn_key = "Home" }))) == 0
                    && t.Reports.SequenceEqual(reports), $"Home ({input.HomeSequenceName}) sends exactly its reports");
                check(sequence == HomeSequence.Vendor ? t.Reports.Contains(tab) : !t.Reports.Contains(tab),
                    $"Home ({input.HomeSequenceName}) {(sequence == HomeSequence.Vendor ? "keeps" : "sends no")} Tab");
            }
            // Stop during a command-h Home: the held GUI+H is cancelled and everything is released.
            var held = new Transport { Block = hex => hex == guiH };
            using (var input = new InputRouter(store, ["C24C"], [new("C24C", 500, 1080, 14, 14, 5, 5)], _ => held) { Home = HomeSequence.CommandH })
            await using (var sessions = new InputSessions(store, input))
            {
                string token = Lease(sessions, "one");
                var home = sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token, fn_key = "Home" }));
                await held.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                check(Code(await sessions.DispatchAsync("/mouse/click", Data(new { id = "one", token, x = 14, y = 14 }))) == 409,
                    "A second command during Home (command-h) is refused, not interleaved");
                check(Code(await sessions.StopAsync(Data(new { id = "one" })).WaitAsync(TimeSpan.FromSeconds(2))) == 0 && Code(await home) != 0,
                    "Stop cancels a Home (command-h) in progress");
                check(held.Reports.TakeLast(2).SequenceEqual(new[] { "A100000000000000", release }),
                    "Cancelled Home (command-h) releases mouse and keyboard");
            }
        }
        finally { try { Directory.Delete(directory, true); } catch { } }
    }

    public static async Task NavigationAsync(Action<bool, string> check)
    {
        string directory = Path.Combine(Path.GetTempPath(), "imouse-control-protocol-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        string file = Path.Combine(directory, "devices.json");
        File.WriteAllText(file, JsonSerializer.Serialize(new[] { new Phone { deviceid = "one", pid = "C24C", uid = "A" },
            new Phone { deviceid = "two", pid = "C241", uid = "B" } }));
        var store = new DeviceStore(file);
        PointerCalibration calibration = new("C24C", 500, 1080, 14, 14, 5, 5);
        const string release = "A200000000000000", tab = "A2002B0000000000", fn = "A200000000000002";
        try
        {
            check(Convert.ToHexString(HidProtocol.FnKey(0x52)) == "A200520000000002"
                && Convert.ToHexString(HidProtocol.FnKey(6)) == "A200060000000002", "Fn uses the separate vendor field, never Left Shift");
            foreach (string key in new[] { "AppSwitch", "ControlBar" })
            {
                var t = new Transport();
                using var input = new InputRouter(store, ["C24C"], [calibration], _ => t);
                await using var sessions = new InputSessions(store, input);
                await Rejected(() => sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", fn_key = key })));
                check(t.Reports.IsEmpty, $"Vendor {key} needs ownership before any report");
                string token = Lease(sessions, "one");
                string[] expected = [release, tab, release, fn, key == "AppSwitch" ? "A200520000000002" : "A200060000000002", release];
                check(Code(await sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token, fn_key = key }))) == 0
                    && t.Reports.SequenceEqual(expected), $"Vendor {key} exact reports preserve its selected prelude");
            }
            // The Fn chord has its own release path: Stop during the held prefix or chord must still lift it.
            foreach (string blockedReport in new[] { fn, "A200520000000002" })
            {
                var held = new Transport { Block = hex => hex == blockedReport };
                using var input = new InputRouter(store, ["C24C"], [calibration], _ => held);
                await using var sessions = new InputSessions(store, input);
                string token = Lease(sessions, "one");
                var command = sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token, fn_key = "AppSwitch" }));
                await held.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                check(Code(await sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token, fn_key = "Enter" }))) == 409,
                    "Fn navigation cannot interleave another command: " + blockedReport);
                check(Code(await sessions.StopAsync(Data(new { id = "one" })).WaitAsync(TimeSpan.FromSeconds(2))) == 0
                    && Code(await command) != 0 && held.Reports.TakeLast(2).SequenceEqual(new[] { "A100000000000000", release }),
                    "Stop releases a held Fn prefix/chord: " + blockedReport);
            }
            // Arrow keys (5 Nov): plain usages through Stroke, the Tab/Escape path, with no Fn field.
            foreach (var (arrow, report) in new[] { ("Right", "A2004F0000000000"), ("Left", "A200500000000000"),
                ("Down", "A200510000000000"), ("Up", "A200520000000000") })
            {
                var t = new Transport();
                using var input = new InputRouter(store, ["C24C"], [calibration], _ => t);
                await using var sessions = new InputSessions(store, input);
                await Rejected(() => sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", fn_key = arrow })));
                check(t.Reports.IsEmpty, arrow + " needs ownership before any report");
                string token = Lease(sessions, "one");
                check(Code(await sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token, fn_key = arrow }))) == 0
                    && t.Reports.SequenceEqual(new[] { release, report, release }), arrow + " is one press and one release, exact reports");
                await sessions.DispatchAsync("/mouse/reset", Data(new { id = "one", token }));
                await sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token, fn_key = arrow }));
                await sessions.DispatchAsync("/mouse/click", Data(new { id = "one", token, x = 14, y = 14 }));
                check(t.Reports.Count(r => r == "A100818100000000") == 4, arrow + " keeps the pointer estimate: no second corner reset");

                var held = new Transport { Block = hex => hex == report };
                using var heldInput = new InputRouter(store, ["C24C"], [calibration], _ => held);
                await using var heldSessions = new InputSessions(store, heldInput);
                string heldToken = Lease(heldSessions, "one");
                var command = heldSessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token = heldToken, fn_key = arrow }));
                await held.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                check(Code(await heldSessions.StopAsync(Data(new { id = "one" })).WaitAsync(TimeSpan.FromSeconds(2))) == 0
                    && Code(await command) != 0 && held.Reports.TakeLast(2).SequenceEqual(new[] { "A100000000000000", release }),
                    "Stop during a held " + arrow + " still sends the key release");
            }
            foreach (string wrong in new[] { "UP", "down", "ArrowDown", "PageDown" })
            {
                var t = new Transport();
                using var input = new InputRouter(store, ["C24C"], [calibration], _ => t);
                await using var sessions = new InputSessions(store, input);
                string token = Lease(sessions, "one");
                bool refused = false;
                try { await sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token, fn_key = wrong })); }
                catch (ArgumentException) { refused = true; }
                check(refused && t.Reports.IsEmpty, "Unverified key name is refused and sends nothing: " + wrong);
                // A refusal is not a failure: the kernel stops nothing and the lease goes on working.
                check(Code(sessions.Renew(Data(new { id = "one", token }))) == 0
                    && Code(await sessions.DispatchAsync("/key/sendkey", Data(new { id = "one", token, fn_key = "Enter" }))) == 0
                    && !JsonSerializer.Serialize(sessions.Status()).Contains("\"stopped\":true"),
                    "A refused key leaves the lease valid and the phone not stopped: " + wrong);
            }
        }
        finally { try { Directory.Delete(directory, true); } catch { } }
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

        // A console that gives up on a drag move (its own 8 s HTTP timeout) pauses locally and
        // sends no /mouse/up. The kernel must lift the button without one: at once when the move
        // fails or hits the 8 s command deadline, and by lease expiry or /input/release when the
        // move finished but its answer reached the console too late.
        string dragFile = Path.Combine(Path.GetTempPath(), "imouse-drag-cleanup-" + Guid.NewGuid().ToString("N") + ".json");
        File.WriteAllText(dragFile, JsonSerializer.Serialize(new[] {
            new Phone { deviceid = "one", pid = "C24C" }, new Phone { deviceid = "two", pid = "C241" } }));
        try
        {
            var dragStore = new DeviceStore(dragFile);
            var one = new Transport(); var two = new Transport(); long now = 0;
            using var dragInput = new InputRouter(dragStore, ["C24C", "C241"],
                [new("C24C", 500, 1080, 14, 14, 5, 5), new("C241", 500, 1080, 14, 14, 5, 5)], pid => pid == "C24C" ? one : two);
            await using var drag = new InputSessions(dragStore, dragInput, () => Interlocked.Read(ref now));
            static bool HeldMove(string hex) => hex.StartsWith("A101") && hex != "A101000000000000";
            string[] lifted = ["A100000000000000", "A200000000000000"];
            void Reset(Transport t) { t.Reports.Clear(); t.Disposed = false; t.Fail = null; t.Block = null; }
            async Task<string> Press(string id)
            {
                string token = Lease(drag, id);
                await drag.DispatchAsync("/mouse/move", Data(new { id, token, x = 14, y = 14 }));
                await drag.DispatchAsync("/mouse/down", Data(new { id, token, button = 1 }));
                return token;
            }

            string token = await Press("one");
            one.Fail = HeldMove;
            check(Code(await drag.DispatchAsync("/mouse/move", Data(new { id = "one", token, x = 24, y = 14 }))) != 0 &&
                one.Reports.TakeLast(2).SequenceEqual(lifted) && one.Disposed,
                "A drag move that fails lifts the held button without /mouse/up");
            check(Code(drag.Acquire(Data(new { id = "one" }))) == 409, "A failed drag move latches Stop until Resume");

            token = await Press("two");
            two.Block = HeldMove;
            var cut = drag.DispatchAsync("/mouse/move", Data(new { id = "two", token, x = 24, y = 14 }));
            await two.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
            check(Code(await cut.WaitAsync(TimeSpan.FromSeconds(12))) != 0 && two.Reports.TakeLast(2).SequenceEqual(lifted) && two.Disposed,
                "A drag move cut by the 8 s command deadline lifts the held button without /mouse/up");
            check(Code(drag.Acquire(Data(new { id = "two" }))) == 409, "A drag move cut by the deadline latches Stop until Resume");

            check(Code(drag.Resume(Data(new { id = "one,two" }))) == 0, "Both phones resume after cleanup");
            Reset(one); Reset(two);
            token = await Press("one");
            check(Code(await drag.DispatchAsync("/mouse/move", Data(new { id = "one", token, x = 24, y = 14 }))) == 0 &&
                one.Reports.Last() == "A101010000000000", "A late-answered drag move leaves the button held on the kernel");
            Interlocked.Exchange(ref now, 31_000);   // the console stopped renewing a paused lease
            for (int n = 0; n < 100 && !one.Disposed; n++) await Task.Delay(10);
            check(one.Disposed && one.Reports.TakeLast(2).SequenceEqual(lifted),
                "Lease expiry lifts a button left held by a drag the console gave up on");

            token = await Press("two");
            await drag.DispatchAsync("/mouse/move", Data(new { id = "two", token, x = 24, y = 14 }));
            check(Code(await drag.StopAsync(Data(new { id = "two", token }), release: true)) == 0 &&
                two.Reports.TakeLast(2).SequenceEqual(lifted) && two.Disposed,
                "The release the console sends on Resume lifts a button left held by a drag");

            // A console's release that arrives late, after the kernel closed its lease and a newer
            // controller took the phone and pressed, must change nothing for that controller.
            string stale = token;
            Reset(two);
            string newer = await Press("two");
            int beforeStale = two.Reports.Count;
            await Rejected(() => drag.StopAsync(Data(new { id = "two", token = stale }), release: true));
            check(two.Reports.Count == beforeStale && !two.Disposed && two.Reports.Last() == "A101000000000000" &&
                Code(await drag.DispatchAsync("/mouse/move", Data(new { id = "two", token = newer, x = 24, y = 14 }))) == 0,
                "A stale release is refused and leaves a newer controller's held button and lease alone");
        }
        finally { File.Delete(dragFile); }

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
            using var server = new ApiServer("http://127.0.0.1:19913/api/", apiStore, apiInput, [("iMouse2-test", frames)]);
            Task<object> Request(string fun, object data) => server.Dispatch(Data(new { fun, data }));
            await Rejected(() => Request("/mouse/click", new { id = "one", x = 14, y = 14 }));
            check(transport.Reports.IsEmpty, "API cannot bypass required ownership with a legacy command");
            var acquired = Data(await Request("/input/acquire", new { id = "one" }));
            string token = acquired.GetProperty("leases")[0].GetProperty("token").GetString()!;
            check(Code(await Request("/input/renew", new { id = "one", token })) == 0 &&
                Code(await Request("/mouse/down", new { id = "one", token })) == 0, "API acquisition and renewal reach owned HID dispatch");
            check(Code(await Request("/device/set", new { id = "one", pid = "C241", uid = "wrong" })) == 41 &&
                apiStore.All()[0].pid == "C24C", "API has no live rebinding: /device/set is refused and the assignment stands");
            int beforeVendor = transport.Reports.Count;
            check(Code(await Request("/device/usb/restart", new { id = "one", token })) == 41 &&
                Code(await Request("/device/airplay/disconnect", new { id = "one" })) == 41 &&
                Code(await Request("/device/airplay/connect", new { pid = "C24C" })) == 41 && transport.Reports.Count == beforeVendor,
                "Vendor board-restart and remote mirroring commands are not implemented and write nothing");
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
