using System.Buffers.Binary;
using System.IO.Pipes;
using System.Text.Json;

namespace IMouse2.Kernel;

/// <summary>One receiver restarted or withdrawn without touching the others. Fake receivers and a
/// recording goodbye: no UxPlay, no socket, no HID, no listener.</summary>
internal static class ReceiverFleetTests
{
    private sealed class Log
    {
        private readonly List<string> _items = [];
        public void Add(string item) { lock (_items) _items.Add(item); }
        public string[] Items { get { lock (_items) return [.. _items]; } }
    }

    private sealed class Fake(int id, string board, Log log, ManualResetEventSlim? stopGate = null, bool unconfirmed = false) : IReceiverHandle
    {
        private readonly TaskCompletionSource _exit = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public int Id { get; } = id;
        public bool Disposed { get; private set; }
        public Task WaitForExitAsync(CancellationToken ct) => _exit.Task.WaitAsync(ct);
        public void Dispose()
        {
            if (Disposed) return;
            stopGate?.Wait(TimeSpan.FromSeconds(10));
            log.Add("stop " + board + " " + Id);
            if (unconfirmed) throw new TimeoutException("simulated: exit not confirmed");
            Disposed = true; _exit.TrySetResult();
        }
    }

    private sealed class Goodbye(Log log) : IReceiverWithdrawal
    {
        public bool Fail;
        public IReadOnlyList<string> Withdraw(ReceiverConfig receiver)
        {
            if (Fail) throw new IOException("simulated: no interface");
            log.Add("goodbye " + receiver.Name);
            return ["192.0.2.1"];
        }
    }

    private sealed class Rig : IAsyncDisposable
    {
        public readonly Log Log = new();
        public readonly Goodbye Goodbye;
        public readonly Dictionary<string, List<Fake>> Started = new(StringComparer.OrdinalIgnoreCase);
        public readonly ReceiverFleet Fleet;
        public readonly ReceiverConfig[] Configs;
        public ManualResetEventSlim? NextStopGate;
        public bool NextUnconfirmed;
        private readonly CancellationTokenSource _cts = new();
        public Rig(string devices)
        {
            Goodbye = new(Log);
            string tag = Guid.NewGuid().ToString("N")[..8];
            Configs = [new("test-one", "C24C", "iMouse2-T18", "fleet-one-" + tag, 7110, "02:49:4D:32:C2:4C"),
                new("test-two", "C214", "iMouse2-T20", "fleet-two-" + tag, 7130, "02:49:4D:32:C2:14")];
            Fleet = new ReceiverFleet(Configs, new DeviceStore(devices), c =>
            {
                lock (Started)
                {
                    if (!Started.TryGetValue(c.BoardPid, out var list)) Started[c.BoardPid] = list = [];
                    var fake = new Fake(list.Count + 1, c.BoardPid, Log, NextStopGate, NextUnconfirmed);
                    NextStopGate = null; NextUnconfirmed = false;
                    list.Add(fake);
                    Log.Add("start " + c.BoardPid + " " + fake.Id);
                    return fake;
                }
            }, Goodbye, maxRestarts: 2, restartDelay: TimeSpan.FromMilliseconds(1));
        }
        public void Start(params string[] hold) => Fleet.Start(_cts.Token, hold);
        public int Count(string board) { lock (Started) return Started.TryGetValue(board, out var l) ? l.Count : 0; }
        public Fake Last(string board) { lock (Started) return Started[board][^1]; }
        public ReceiverInfo Info(int index) => Fleet.Sessions[index].Frames.Receiver();
        public async Task Running(int index, int generation)
        {
            for (int i = 0; i < 200 && !(Info(index) is { State: "running" } info && info.Generation == generation); i++)
                await Task.Delay(10);
        }
        public async Task<int> WaitStarts(string board, int count)
        {
            for (int i = 0; i < 200 && Count(board) < count; i++) await Task.Delay(10);
            await Task.Delay(20);   // A stray extra start would show up here.
            return Count(board);
        }
        public async ValueTask DisposeAsync()
        {
            try { await Fleet.ShutdownAsync(); } catch (AggregateException) { }
            _cts.Dispose();
        }
    }

    private static int Code(object response) => JsonSerializer.SerializeToElement(response).GetProperty("code").GetInt32();
    private static JsonElement Json(object response) => JsonSerializer.SerializeToElement(response);

    internal static async Task RunAsync(Action<bool, string> check, string devices, InputRouter router, byte[] bmp)
    {
        // The C# goodbye is byte for byte the one tools/mdns_goodbye.py sends (its test pins the same hex).
        check(Convert.ToHexString(MdnsGoodbye.Packet(new("x", "C24C", "iMouse2-T1", "p", 7110, "02:49:4D:32:C2:4C"))) ==
            "000084000000000200000000085F616972706C6179045F746370056C6F63616C00000C00010000000000200A694D6F757365322D5431085F616972706C6179045F746370056C6F63616C00055F72616F70045F746370056C6F63616C00000C000100000000002A1730323439344433324332344340694D6F757365322D5431055F72616F70045F746370056C6F63616C00",
            "AirPlay goodbye packet matches mdns_goodbye.py byte for byte");

        await using (var rig = new Rig(devices))
        {
            rig.Start();
            await rig.Running(0, 1); await rig.Running(1, 1);
            var other = rig.Last("C214");
            check(rig.Info(0) is { State: "running", Pid: 1, Generation: 1 } && rig.Info(1) is { State: "running", Generation: 1 },
                "Fleet starts every unheld receiver as generation 1");

            // Frames on the other receiver stay live through this receiver's restart.
            using var client = new NamedPipeClientStream(".", rig.Configs[1].Pipe, PipeDirection.Out, PipeOptions.Asynchronous);
            await client.ConnectAsync(3000);
            byte[] size = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(size, bmp.Length);
            await client.WriteAsync(size); await client.WriteAsync(bmp); await client.FlushAsync();
            var otherFrames = rig.Fleet.Sessions[1].Frames;
            for (int i = 0; i < 100 && !otherFrames.State.Live; i++) await Task.Delay(10);

            var restarted = Json(await rig.Fleet.RestartAsync("c24c"));
            await rig.Running(0, 2);
            var log = rig.Log.Items;
            int stop = Array.IndexOf(log, "stop C24C 1"), bye = Array.IndexOf(log, "goodbye iMouse2-T18"), again = Array.IndexOf(log, "start C24C 2");
            check(restarted.GetProperty("code").GetInt32() == 0 && restarted.GetProperty("withdrawn").GetBoolean()
                && restarted.GetProperty("started").GetBoolean() && rig.Info(0) is { State: "running", Pid: 2, Generation: 2 },
                "Restart replaces one receiver: generation 2 running with its own new child");
            check(stop >= 0 && stop < bye && bye < again,
                "Restart confirms the old child's exit, then sends the goodbye, then starts the new child");
            check(!other.Disposed && rig.Count("C214") == 1 && rig.Info(1) is { State: "running", Generation: 1 }
                && !log.Skip(stop).Any(l => l.Contains("C214") || l.Contains("T20")),
                "Restarting one receiver never stops, withdraws or restarts another");
            check(otherFrames.State.Live, "The other phone's mirror frames stay live through the restart");

            var withdrawn = Json(await rig.Fleet.WithdrawAsync("C214"));
            check(withdrawn.GetProperty("code").GetInt32() == 0 && other.Disposed && rig.Info(1).State == "held"
                && rig.Info(1).Message.Contains("withdrawn") && rig.Log.Items.Contains("goodbye iMouse2-T20") && rig.Count("C214") == 1,
                "Withdraw stops one receiver, sends its goodbye and holds it");
            check(rig.Info(0) is { State: "running", Pid: 2 } && !rig.Last("C24C").Disposed, "Withdrawing one receiver leaves the other running");
            check(rig.Fleet.IsHeld("C214") && Code(rig.Fleet.Advertise("C214")) == 0 && await rig.WaitStarts("C214", 2) == 2,
                "A withdrawn receiver is advertised again by /device/airplay/connect");
            await rig.Running(1, 2);
            check(rig.Info(1) is { State: "running", Generation: 2 }, "Re-advertised receiver runs as the next generation");

            var heldRestart = Json(await rig.Fleet.RestartAsync("C24C", hold: true));
            check(heldRestart.GetProperty("code").GetInt32() == 0 && !heldRestart.GetProperty("started").GetBoolean()
                && rig.Info(0).State == "held" && rig.Count("C24C") == 2,
                "Restart with hold stops and withdraws, and starts nothing");
            var stale = Json(await rig.Fleet.WithdrawAsync("C24C"));
            check(stale.GetProperty("code").GetInt32() == 0 && !stale.GetProperty("stopped").GetBoolean()
                && rig.Log.Items.Count(l => l == "goodbye iMouse2-T18") == 3,
                "Withdrawing an already stopped receiver re-sends the goodbye for a stale name");
            await rig.Fleet.RestartAsync("C24C");
            await rig.Running(0, 3);
            check(rig.Info(0) is { State: "running", Generation: 3 }, "Restart of a held receiver starts it");

            rig.Goodbye.Fail = true;
            var noGoodbye = Json(await rig.Fleet.RestartAsync("C24C"));
            await rig.Running(0, 4);
            check(noGoodbye.GetProperty("code").GetInt32() == 0 && !noGoodbye.GetProperty("withdrawn").GetBoolean() && rig.Info(0).State == "running",
                "A failed goodbye is reported but does not block the restart");
            check(Code(await rig.Fleet.WithdrawAsync("C24C")) == 34 && rig.Info(0).State == "held",
                "Withdraw reports a goodbye that could not be sent");
            rig.Goodbye.Fail = false;
            check(Code(rig.Fleet.Advertise("FFFF")) == 36 && Code(await rig.Fleet.RestartAsync("FFFF")) == 36,
                "Unknown boards are refused");
        }

        // A restart in flight refuses a second change to the same receiver, and not the other one.
        await using (var rig = new Rig(devices))
        {
            using var gate = new ManualResetEventSlim(false);
            rig.NextStopGate = gate;
            rig.Start("C214");
            await rig.Running(0, 1);
            var slow = rig.Fleet.RestartAsync("C24C");
            for (int i = 0; i < 100 && rig.Info(0).State != "restarting"; i++) await Task.Delay(10);
            check(rig.Info(0).State == "restarting" && Code(await rig.Fleet.RestartAsync("C24C")) == 409
                && Code(rig.Fleet.Advertise("C24C")) == 409, "A second change to a restarting receiver is refused");
            check(Code(rig.Fleet.Advertise("C214")) == 0, "Another receiver can be advertised while one restarts");
            gate.Set();
            check(Code(await slow) == 0, "The slow restart completes once its child exits");
            await rig.Running(0, 2);
        }

        // Shutdown during a restart: the stop finishes, nothing new starts.
        await using (var rig = new Rig(devices))
        {
            using var gate = new ManualResetEventSlim(false);
            rig.NextStopGate = gate;
            rig.Start("C214");
            await rig.Running(0, 1);
            var slow = rig.Fleet.RestartAsync("C24C");
            for (int i = 0; i < 100 && rig.Info(0).State != "restarting"; i++) await Task.Delay(10);
            var shutdown = rig.Fleet.ShutdownAsync();
            await Task.Delay(50);
            gate.Set();
            await shutdown;
            check(Code(await slow) == 42 && rig.Count("C24C") == 1 && rig.Count("C214") == 0,
                "Shutdown during a restart lets the stop finish and starts nothing");
        }

        // An unconfirmed exit: nothing withdrawn, nothing started, the board blocked, the other untouched.
        await using (var rig = new Rig(devices))
        {
            rig.NextUnconfirmed = true;
            rig.Start("C214");
            await rig.Running(0, 1);
            var stuck = Json(await rig.Fleet.RestartAsync("C24C"));
            check(stuck.GetProperty("code").GetInt32() == 33 && rig.Count("C24C") == 1 && !rig.Log.Items.Any(l => l.StartsWith("goodbye"))
                && rig.Info(0).State == "failed", "An unconfirmed exit withdraws nothing and starts no second child");
            check(Code(rig.Fleet.Advertise("C24C")) == 409 && Code(await rig.Fleet.RestartAsync("C24C")) == 409,
                "A board with an unconfirmed exit refuses further starts");
            check(Code(rig.Fleet.Advertise("C214")) == 0, "The other receiver is still usable");
            bool reported = false;
            try { await rig.Fleet.ShutdownAsync(); } catch (AggregateException ex) { reported = ex.InnerExceptions.Any(e => e.Message.Contains("unconfirmed")); }
            check(reported, "Kernel shutdown still reports the earlier unconfirmed exit");
        }

        // The HTTP control: a phone another controller leases is never cut.
        await using (var rig = new Rig(devices))
        {
            rig.Start();
            await rig.Running(0, 1); await rig.Running(1, 1);
            var store = new DeviceStore(devices);
            using var api = new ApiServer("http://127.0.0.1:1/api/", store, router,
                rig.Fleet.Sessions.Select(s => (s.Config.Name, s.Frames)), () => { }) { AdvertiseReceiver = rig.Fleet.Advertise, Receivers = rig.Fleet };
            JsonElement Body(string fun, object data) => JsonSerializer.SerializeToElement(new { fun, data });
            var lease = Json(await api.Dispatch(Body("/input/acquire", new { id = "test-one" })));
            string token = lease.GetProperty("leases")[0].GetProperty("token").GetString()!;
            check(Code(await api.Dispatch(Body("/device/airplay/restart", new { pid = "C24C" }))) == 409 && rig.Count("C24C") == 1,
                "Restart of a leased phone's receiver is refused without its token; nothing stopped");
            check(Code(await api.Dispatch(Body("/device/airplay/withdraw", new { pid = "C24C", token = "wrong" }))) == 409,
                "Withdraw with another controller's token is refused");
            check(Code(await api.Dispatch(Body("/device/airplay/restart", new { pid = "C214" }))) == 0 && await rig.WaitStarts("C214", 2) == 2,
                "An unleased phone's receiver restarts while another phone is leased");
            check(Code(await api.Dispatch(Body("/device/airplay/restart", new { pid = "C24C", token }))) == 0 && await rig.WaitStarts("C24C", 2) == 2,
                "The lease holder can restart its own phone's receiver");
            check(Code(await api.Dispatch(Body("/input/renew", new { id = "test-one", token }))) == 0,
                "A receiver restart leaves the input lease intact");
            check(Code(await api.Dispatch(Body("/device/airplay/restart", new { pid = "12" }))) == 36, "Malformed board IDs are refused");
            var held = Json(await api.Dispatch(Body("/device/airplay/restart", new { pid = "C214", hold = true })));
            check(held.GetProperty("code").GetInt32() == 0 && rig.Info(1).State == "held", "hold=true over HTTP leaves the receiver withdrawn");
            check(Code(await api.Dispatch(Body("/device/airplay/connect", new { pid = "C214" }))) == 0 && await rig.WaitStarts("C214", 3) == 3,
                "connect re-advertises a withdrawn receiver over HTTP");
            await rig.Running(0, 2);
            var rows = Json(api.KernelStatus()).GetProperty("receivers");
            check(rows[0].GetProperty("receiver_generation").GetInt32() == 2 && rows[0].GetProperty("receiver_state").GetString() is "offline" or "mirroring",
                "Kernel status reports each receiver's generation");
            await api.Dispatch(Body("/input/release", new { id = "test-one", token }));
        }
    }
}
