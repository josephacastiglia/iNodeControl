using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text.Json;
using IMouse2.Kernel;

namespace IMouse2.Harness;

/// <summary>
/// Measures cleanup after an uncertain drag: the real console ApiClient and InputLeaseClient against
/// the real kernel ApiServer and InputSessions, over loopback HTTP, with a simulated board. Faults are
/// injected on the wire (answers lost, requests dropped or refused) and on the board (writes that fail
/// or hang). Everything here is simulated; none of it is evidence about a physical phone.
/// </summary>
static class Harness
{
    const string Id = Kernel.PhoneId;
    static readonly List<object> Results = [];
    static int _failures;

    static async Task<int> Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "--chunk-timing")
            return await ChunkTiming.RunAsync(args.Length > 1 ? args[1] : Path.Combine(AppContext.BaseDirectory, "chunk-timing.json"), args.Length > 2 ? int.Parse(args[2]) : 6,
                args.Length > 3 ? args[3].Split(',').Select(int.Parse).ToArray() : null, args.Length > 4 ? args[4].Split(',').Select(int.Parse).ToArray() : null);
        if (args.Length > 1 && args[0] == "--serve") return await Serve.RunAsync(int.Parse(args[1]), args.Length > 2 ? args[2] : "F001");
        string output = args.Length > 0 ? args[0] : Path.Combine(AppContext.BaseDirectory, "cleanup-harness-results.json");
        await Run("S1 command completed, answer lost", LostAnswer);
        await Run("S2 kernel command deadline", KernelDeadline);
        await Run("S3 kernel command failure", KernelFailure);
        await Run("S4 release refused, explicit Resume retries it", ReleaseRefused);
        await Run("S5 stale release after ownership changed", StaleRelease);
        await Run("S6 release lost, lease-expiry fallback", ReleaseLost);
        await Run("S7 mock kernel refuses a port another listener holds", MockRefusesTakenPort);
        await Run("S8 mock kernel starts, self-checks and serves only the simulated board", MockServesSimulatedBoard);
        await Run("S9 Home: emitted HID reports under a simplified text-field model (not iOS behaviour)", HomeInTextField);
        File.WriteAllText(output, JsonSerializer.Serialize(new { simulated = true, board = "simulated IHidTransport", at = DateTime.Now, failures = _failures, scenarios = Results },
            new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"{(_failures == 0 ? "ALL PASSED" : _failures + " CHECK(S) FAILED")}; results in {output}");
        return _failures == 0 ? 0 : 1;
    }

    sealed class Scenario(string name)
    {
        public readonly List<string> Passed = [], Failed = [];
        public readonly Dictionary<string, object?> Measured = [];
        public void Check(string what, bool ok) { (ok ? Passed : Failed).Add(what); Console.WriteLine($"  {(ok ? "PASS" : "FAIL")} {what}"); }
        public object Report() => new { name, passed = Passed, failed = Failed, measured = Measured };
    }
    static async Task Run(string name, Func<Scenario, Task> body)
    {
        Console.WriteLine(name);
        var s = new Scenario(name);
        try { await body(s); }
        catch (Exception ex) { s.Check("scenario ran to the end (" + ex.GetType().Name + ": " + ex.Message + ")", false); }
        _failures += s.Failed.Count;
        Results.Add(s.Report());
    }

    static double Ms(long from, long to) => Math.Round((to - from) * 1000.0 / Stopwatch.Frequency, 1);
    static async Task<Exception?> Outcome(Task task)
    {
        try { await task; return null; } catch (Exception ex) { return ex; }
    }
    static TaskCompletionSource<InputCleanup> Cleanups(ApiClient api)
    {
        var next = new TaskCompletionSource<InputCleanup>(TaskCreationOptions.RunContinuationsAsynchronously);
        api.InputCleaned += c => next.TrySetResult(c);
        return next;
    }
    /// <summary>Press and start a drag: pointer to the start, button down. Both must succeed.</summary>
    static async Task Press(ApiClient api)
    {
        await api.MoveAsync(Id, 14, 14);
        await api.CommandAsync("/mouse/down", new() { ["id"] = Id, ["button"] = "1" });
    }
    /// <summary>What the console sent after the failure was detected: only the release and a status query are allowed.</summary>
    static void NoReplay(Scenario s, Wire wire, long detected, params string[] allowed)
    {
        var after = wire.Since(detected);
        s.Measured["console requests after detection"] = after;
        s.Check("after the failure only " + string.Join(" and ", allowed) + " went out: no replay, no /mouse/up, no acquire, renewal or Resume",
            after.All(allowed.Contains));
    }
    static void Timing(Scenario s, Kernel kernel, InputCleanup cleanup, long failureStart)
    {
        long? up = kernel.Board.ButtonUpAfter(failureStart);
        s.Measured["cleanup confirmed"] = cleanup.Confirmed;
        s.Measured["cleanup detail"] = cleanup.Phones.Select(p => p.Detail).ToArray();
        s.Measured["detected failure -> cleanup answered (ms)"] = Math.Round(cleanup.Elapsed.TotalMilliseconds, 1);
        s.Measured["detected failure -> button-up report on the board (ms)"] = up is { } at ? Ms(cleanup.DetectedAt, at) : null;
    }

    static int FreePort() { var l = new TcpListener(IPAddress.Loopback, 0); l.Start(); int p = ((IPEndPoint)l.LocalEndpoint).Port; l.Stop(); return p; }

    // S7. The mock must fail startup, not share a port. On 27 Sep an http.sys registration for
    // /api/ on the same port took the mock's requests, and the real boards were enumerated.
    static async Task MockRefusesTakenPort(Scenario s)
    {
        int port = FreePort();
        using (var squatter = new HttpListener())
        {
            squatter.Prefixes.Add($"http://localhost:{port}/api/");
            squatter.Start();
            var result = await Serve.RunAsync(port, "F001").WaitAsync(TimeSpan.FromSeconds(10));
            s.Check("an http.sys listener for /api/ on the port: startup refused (exit 3)", result == Serve.PortInUse);
        }
        port = FreePort();
        var socket = new TcpListener(IPAddress.Loopback, port); socket.Start();
        try
        {
            var result = await Serve.RunAsync(port, "F001").WaitAsync(TimeSpan.FromSeconds(10));
            s.Check("a plain socket on the port: startup refused (exit 3)", result == Serve.PortInUse);
        }
        finally { socket.Stop(); }
    }

    // S8. On a free port the mock starts, passes its own self-check, and answers only with the
    // simulated board and phone through that port.
    static async Task MockServesSimulatedBoard(Scenario s)
    {
        int port = FreePort();
        using var stop = new CancellationTokenSource();
        var started = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        var run = Serve.RunAsync(port, "F001", stop.Token, url => started.TrySetResult(url));
        string url = await started.Task.WaitAsync(TimeSpan.FromSeconds(15));
        using var client = new HttpClient();
        using var boards = JsonDocument.Parse(await client.GetStringAsync(url + "/api/config/usb/get"));
        var list = boards.RootElement.GetProperty("data").GetProperty("list").EnumerateArray().Select(b => b.GetProperty("pid").GetString()).ToArray();
        s.Measured["board list"] = list;
        s.Check("the board list is exactly the simulated board", list is ["F001"]);
        using var status = JsonDocument.Parse(await client.GetStringAsync(url + "/api/kernel/status"));
        s.Check("kernel status answers through the front", status.RootElement.GetProperty("data").GetProperty("input_protocol").GetInt32() == 1);
        stop.Cancel();
        s.Check("stops cleanly when cancelled (exit 0)", await run.WaitAsync(TimeSpan.FromSeconds(10)) == 0);
        s.Check("the port is free again afterwards", !Serve.PortTaken(port));
    }

    // S9. Validates the HID reports the kernel emits for the console's Home button (which sends
    // /key/sendkey fn_key=Home), decoded under a simplified model of a focused text field
    // (HidText). It shows what each --home-sequence option would type; it is not evidence of how
    // iOS responds, which only a phone test can show.
    static async Task HomeInTextField(Scenario s)
    {
        foreach (var sequence in new[] { HomeSequence.Vendor, HomeSequence.CommandH, HomeSequence.CommandWake })
        {
            await using var kernel = new Kernel(sequence);
            await using var api = new ApiClient(kernel.Address, new Wire(), ownership: true);
            string name = sequence switch { HomeSequence.CommandH => "command-h", HomeSequence.CommandWake => "command-wake", _ => "vendor" };
            await api.SendTextAsync(Id, "ab");
            int before = kernel.Board.Reports.Length;
            await api.CommandAsync("/key/sendkey", new() { ["id"] = Id, ["fn_key"] = "Home" });
            string home = HidText.Decode(kernel.Board.Reports.Skip(before).Select(r => r.Hex));
            await api.SendTextAsync(Id, "c");
            string field = HidText.Decode(kernel.Board.Reports.Select(r => r.Hex));
            s.Measured[$"{name}: model field receives for ab, Home, c"] = HidText.Show(field);
            if (sequence == HomeSequence.Vendor)
                s.Check("vendor (release default): the emitted Home includes a Tab, which a focused field would type", home == "\t[GUI+h]" && field == "ab\t[GUI+h]c");
            else
                s.Check($"{name}: the emitted Home has no typed key, only GUI+H", home == "[GUI+h]" && field == "ab[GUI+h]c");
            if (sequence != HomeSequence.Vendor) continue;
            // AppSwitch and ControlBar share the Tab prefix (unchanged here; recorded for later).
            foreach (string fn in new[] { "AppSwitch", "ControlBar" })
            {
                int at = kernel.Board.Reports.Length;
                await api.CommandAsync("/key/sendkey", new() { ["id"] = Id, ["fn_key"] = fn });
                s.Measured[fn + " (unchanged): model field receives"] = HidText.Show(HidText.Decode(kernel.Board.Reports.Skip(at).Select(r => r.Hex)));
            }
        }
    }

    // S1. The kernel completed the held move, but its answer never reached the console, which times
    // out after 8 s. The button is still down on the kernel. A tap queued behind the move must stay
    // unsent. The console releases its own lease at once; the kernel lifts the button.
    static async Task LostAnswer(Scenario s)
    {
        await using var kernel = new Kernel();
        var wire = new Wire(); wire.Plan("/mouse/move", Fault.None, Fault.LoseAnswer);
        await using var api = new ApiClient(kernel.Address, wire, ownership: true);
        var cleaned = Cleanups(api);
        await Press(api);
        long start = Stopwatch.GetTimestamp();
        var move = api.MoveAsync(Id, 24, 14);
        await wire.Answered.Task.WaitAsync(TimeSpan.FromSeconds(5));     // the kernel has finished the move
        s.Check("the kernel finished the move and the button is held", kernel.Board.Held);
        var queued = api.CommandAsync("/mouse/click", new() { ["id"] = Id, ["x"] = 30, ["y"] = 30 });
        var moveOutcome = await Outcome(move);
        var queuedOutcome = await Outcome(queued);
        var cleanup = await cleaned.Task.WaitAsync(TimeSpan.FromSeconds(10));
        s.Check("the move with a lost answer ends as the console's timeout", moveOutcome is TaskCanceledException && cleanup.Cause == InputEnd.TimedOut);
        s.Check("the tap queued behind it is reported as not sent", queuedOutcome is InputNotSentException);
        s.Check("the queued tap never reached the kernel", !wire.Sent("/mouse/click"));
        s.Check("the release is confirmed and the board's button is up", cleanup.Confirmed && !kernel.Board.Held && kernel.Board.ButtonUpAfter(start) is not null);
        Timing(s, kernel, cleanup, start);
        s.Measured["move sent -> failure detected (ms)"] = Ms(start, cleanup.DetectedAt);
        NoReplay(s, wire, cleanup.DetectedAt, "/input/release");
        s.Check("the phone stays paused: the next tap is refused before it leaves",
            await Outcome(api.CommandAsync("/mouse/click", new() { ["id"] = Id, ["x"] = 30, ["y"] = 30 })) is ApiException && !wire.Sent("/mouse/click"));
    }

    // S2. The held move hangs on the board. The kernel's own 8 s deadline and the console's 8 s
    // timeout race; either way the button must come up and the console must report it.
    static async Task KernelDeadline(Scenario s)
    {
        await using var kernel = new Kernel();
        var wire = new Wire();
        await using var api = new ApiClient(kernel.Address, wire, ownership: true);
        var cleaned = Cleanups(api);
        await Press(api);
        kernel.Board.Block = Board.HeldMove;
        long start = Stopwatch.GetTimestamp();
        var outcome = await Outcome(api.MoveAsync(Id, 24, 14));
        var cleanup = await cleaned.Task.WaitAsync(TimeSpan.FromSeconds(10));
        s.Measured["which side ended it"] = cleanup.Cause == InputEnd.TimedOut ? "console timeout first" : "kernel deadline answered first";
        s.Check("the hung move ends as a timeout or a kernel failure", outcome is TaskCanceledException or ApiException);
        s.Check("the release is confirmed and the board's button is up", cleanup.Confirmed && !kernel.Board.Held);
        Timing(s, kernel, cleanup, start);
        NoReplay(s, wire, cleanup.DetectedAt, "/input/release", "/input/status");
    }

    // S3. The board write fails on the held move: the kernel lifts the button itself, closes the
    // lease and answers code 33. The console's release is refused and it confirms from status.
    static async Task KernelFailure(Scenario s)
    {
        await using var kernel = new Kernel();
        var wire = new Wire();
        await using var api = new ApiClient(kernel.Address, wire, ownership: true);
        var cleaned = Cleanups(api);
        await Press(api);
        kernel.Board.Fail = Board.HeldMove;
        long start = Stopwatch.GetTimestamp();
        var outcome = await Outcome(api.MoveAsync(Id, 24, 14));
        var cleanup = await cleaned.Task.WaitAsync(TimeSpan.FromSeconds(10));
        s.Check("the failed move ends as a kernel failure", outcome is ApiException && cleanup.Cause == InputEnd.Failed);
        s.Check("the refused release is confirmed from the kernel's status", cleanup.Confirmed && cleanup.Phones[0].Detail.Contains("already closed") && !kernel.Board.Held);
        Timing(s, kernel, cleanup, start);
        NoReplay(s, wire, cleanup.DetectedAt, "/input/release", "/input/status");
    }

    // S4. The answer is lost and the release itself is refused on the wire (503). That is attempted
    // but not confirmed; the button stays down. Only the operator's Resume tries again.
    static async Task ReleaseRefused(Scenario s)
    {
        await using var kernel = new Kernel();
        var wire = new Wire(); wire.Plan("/mouse/move", Fault.None, Fault.LoseAnswer); wire.Plan("/input/release", Fault.Refuse);
        await using var api = new ApiClient(kernel.Address, wire, ownership: true);
        var cleaned = Cleanups(api);
        await Press(api);
        long start = Stopwatch.GetTimestamp();
        await Outcome(api.MoveAsync(Id, 24, 14));
        var cleanup = await cleaned.Task.WaitAsync(TimeSpan.FromSeconds(10));
        s.Check("a refused release is reported as attempted, not confirmed", !cleanup.Confirmed && cleanup.Phones[0].Detail.StartsWith("the release request failed"));
        s.Check("the button is still down on the kernel", kernel.Board.Held);
        await Task.Delay(1000);
        NoReplay(s, wire, cleanup.DetectedAt, "/input/release");
        long resumeAt = Stopwatch.GetTimestamp();
        await api.ResumeInputAsync(Id);
        long? up = kernel.Board.ButtonUpAfter(resumeAt);
        s.Check("the operator's Resume releases the kept lease and the button comes up", up is not null && !kernel.Board.Held);
        s.Measured["cleanup detail"] = cleanup.Phones[0].Detail;
        s.Measured["Resume pressed -> button-up report (ms)"] = up is { } at ? Ms(resumeAt, at) : null;
        s.Check("input works again after Resume", await Outcome(api.CommandAsync("/mouse/click", new() { ["id"] = Id, ["x"] = 30, ["y"] = 30 })) is null);
    }

    // S5. The release is held on the wire. Meanwhile another controller stops the phone, resumes it,
    // takes a lease and presses. The late release carries the old token: the kernel must refuse it
    // and leave the newer controller's lease and held button alone.
    static async Task StaleRelease(Scenario s)
    {
        await using var kernel = new Kernel();
        var wire = new Wire(); wire.Plan("/mouse/move", Fault.None, Fault.LoseAnswer); wire.Plan("/input/release", Fault.Hold);
        var gate = new TaskCompletionSource(); wire.Gate = gate.Task;
        await using var api = new ApiClient(kernel.Address, wire, ownership: true);
        await using var other = new ApiClient(kernel.Address, new HttpClientHandler { UseProxy = false }, ownership: true);
        var cleaned = Cleanups(api);
        await Press(api);
        await Outcome(api.MoveAsync(Id, 24, 14));
        await wire.Holding.Task.WaitAsync(TimeSpan.FromSeconds(10));
        await other.StopInputAsync(Id);
        await other.ResumeInputAsync(Id);
        await Press(other);
        int before = kernel.Board.Reports.Length;
        gate.SetResult();
        var cleanup = await cleaned.Task.WaitAsync(TimeSpan.FromSeconds(10));
        s.Check("the newer controller's button is still held and the board saw nothing more", kernel.Board.Held && kernel.Board.Reports.Length == before);
        s.Check("the newer controller's lease still works", await Outcome(other.MoveAsync(Id, 20, 14)) is null);
        s.Check("the stale release is reported as confirmed by the kernel's earlier close", cleanup.Confirmed && cleanup.Phones[0].Detail.Contains("already closed"));
        s.Measured["cleanup detail"] = cleanup.Phones[0].Detail;
    }

    // S6. The answer is lost and so is the release. Nothing the console does can lift the button;
    // the kernel's lease expiry does, once the console stops renewing. Measured, not assumed.
    static async Task ReleaseLost(Scenario s)
    {
        await using var kernel = new Kernel();
        var wire = new Wire(); wire.Plan("/mouse/move", Fault.None, Fault.LoseAnswer); wire.Plan("/input/release", Fault.Drop);
        await using var api = new ApiClient(kernel.Address, wire, ownership: true);
        var cleaned = Cleanups(api);
        await Press(api);
        long pressed = Stopwatch.GetTimestamp();
        await Outcome(api.MoveAsync(Id, 24, 14));
        var cleanup = await cleaned.Task.WaitAsync(TimeSpan.FromSeconds(12));
        s.Check("a release with no answer is reported as attempted, not confirmed", !cleanup.Confirmed && cleanup.Phones[0].Detail.StartsWith("no answer"));
        long? up = null;
        for (int i = 0; i < 450 && (up = kernel.Board.ButtonUpAfter(pressed)) is null; i++) await Task.Delay(100);
        s.Check("the kernel's lease expiry lifts the button within 30 s of the last renewal", up is not null && !kernel.Board.Held);
        s.Measured["cleanup detail"] = cleanup.Phones[0].Detail;
        s.Measured["detected failure -> button-up by lease expiry (ms)"] = up is { } at ? Ms(cleanup.DetectedAt, at) : null;
        s.Measured["press -> button-up by lease expiry (ms)"] = up is { } at2 ? Ms(pressed, at2) : null;
        NoReplay(s, wire, cleanup.DetectedAt, "/input/release");
    }
}

/// <summary>A simulated board: records every report with its time; can fail or hang chosen reports.</summary>
sealed class Board : IHidTransport
{
    private readonly List<(long At, string Hex)> _reports = [];
    public Func<string, bool>? Fail, Block;
    /// <summary>A movement report with the button held (A1, buttons 01, non-zero motion).</summary>
    public static bool HeldMove(string hex) => hex.StartsWith("A101") && hex != "A101000000000000";
    public async Task SendAsync(byte[] data, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        string hex = Convert.ToHexString(data);
        lock (_reports) _reports.Add((Stopwatch.GetTimestamp(), hex));
        if (Fail?.Invoke(hex) == true) throw new IOException("Simulated board write failure");
        if (Block?.Invoke(hex) == true) await Task.Delay(Timeout.Infinite, ct);
    }
    public void Dispose() { }
    public (long At, string Hex)[] Reports { get { lock (_reports) return _reports.ToArray(); } }
    /// <summary>The first mouse report with no button at or after the given time.</summary>
    public long? ButtonUpAfter(long since) => Reports.Where(r => r.At >= since && r.Hex.StartsWith("A100")).Select(r => (long?)r.At).FirstOrDefault();
    /// <summary>Whether the last mouse report left the button down.</summary>
    public bool Held => Reports.LastOrDefault(r => r.Hex.StartsWith("A1")).Hex?.StartsWith("A101") == true;
}

enum Fault { None, LoseAnswer, Drop, Refuse, Hold }

/// <summary>The wire between console and kernel, with faults planned per function in order.</summary>
sealed class Wire() : DelegatingHandler(new HttpClientHandler { UseProxy = false })
{
    private readonly List<(long At, string Fun)> _log = [];
    private readonly Dictionary<string, Queue<Fault>> _plan = [];
    public Task Gate = Task.CompletedTask;
    public readonly TaskCompletionSource Holding = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public readonly TaskCompletionSource Answered = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public void Plan(string fun, params Fault[] faults) { lock (_plan) _plan[fun] = new(faults); }
    public string[] Since(long at) { lock (_log) return _log.Where(l => l.At >= at).Select(l => l.Fun).ToArray(); }
    public bool Sent(string fun) { lock (_log) return _log.Any(l => l.Fun == fun); }
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        string fun = request.Method == HttpMethod.Get ? request.RequestUri!.AbsolutePath
            : JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct)).RootElement.GetProperty("fun").GetString()!;
        var fault = Fault.None;
        lock (_plan) if (_plan.TryGetValue(fun, out var queue) && queue.Count > 0) fault = queue.Dequeue();
        lock (_log) _log.Add((Stopwatch.GetTimestamp(), fun));
        switch (fault)
        {
            case Fault.LoseAnswer:
                // The kernel runs the command to the end; its answer never reaches the console.
                using (await base.SendAsync(request, CancellationToken.None)) Answered.TrySetResult();
                await Task.Delay(Timeout.Infinite, ct);
                break;
            case Fault.Drop:
                await Task.Delay(Timeout.Infinite, ct);
                break;
            case Fault.Refuse:
                return new HttpResponseMessage(HttpStatusCode.ServiceUnavailable) { Content = new StringContent("Simulated outage") };
            case Fault.Hold:
                Holding.TrySetResult();
                await Gate.WaitAsync(ct);
                break;
        }
        return await base.SendAsync(request, ct);
    }
}

/// <summary>The real kernel HTTP server and input sessions on a free loopback port, with a simulated board.</summary>
sealed class Kernel : IAsyncDisposable
{
    public const string PhoneId = "SIM:01";
    public readonly Board Board = new();
    public string Address { get; }
    private readonly string _dir;
    private readonly InputRouter _input;
    private readonly FrameStore _frames;
    private readonly ApiServer _server;
    private readonly CancellationTokenSource _stop = new();
    private readonly Task _run;
    public Kernel(HomeSequence home = HomeSequence.Vendor)
    {
        _dir = Path.Combine(Path.GetTempPath(), "imouse-cleanup-harness-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_dir);
        string file = Path.Combine(_dir, "devices.json");
        File.WriteAllText(file, JsonSerializer.Serialize(new[] { new Phone { deviceid = PhoneId, pid = "F001", uid = "SIM" } }));
        var store = new DeviceStore(file);
        _input = new InputRouter(store, ["F001"], [new PointerCalibration("F001", 500, 1080, 14, 14, 5, 5)], _ => Board) { Home = home };
        _frames = new FrameStore("imouse-cleanup-harness-" + Guid.NewGuid().ToString("N"), PhoneId);
        var probe = new TcpListener(IPAddress.Loopback, 0); probe.Start();
        int port = ((IPEndPoint)probe.LocalEndpoint).Port; probe.Stop();
        Address = $"http://localhost:{port}";
        _server = new ApiServer(Address + "/api/", store, "harness", _input, _frames);
        _run = _server.RunAsync(_stop.Token);
    }
    public async ValueTask DisposeAsync()
    {
        _stop.Cancel();
        try { await _run; } catch { }
        _server.Dispose(); _input.Dispose(); _frames.Dispose();
        try { Directory.Delete(_dir, true); } catch { }
    }
}
