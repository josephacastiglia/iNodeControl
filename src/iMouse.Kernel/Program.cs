using System.Net;
using System.Text.Json;
using IMouse2.Kernel;

_ = KernelDiagnostics.BuildIdentity; // Capture before any listener or hardware is started.
if (args.Contains("--self-test")) return await SelfTests.RunAsync();

KernelOptions options;
KernelConfiguration? configuration = null;
try
{
    options = KernelOptions.Parse(args);
    if (options.HardwareMode is null) configuration = KernelConfiguration.Load(options);
    if (options.ValidateOnly)
    {
        Console.WriteLine(JsonSerializer.Serialize(configuration!.ValidationReport(), new JsonSerializerOptions { WriteIndented = true }));
        return 0;
    }
}
catch (Exception ex) when (ex is ArgumentException or IOException or UnauthorizedAccessException or JsonException or NotSupportedException)
{
    Console.Error.WriteLine("Startup refused: " + ex.Message);
    return 2;
}

using var cts = new CancellationTokenSource();
using var timerResolution = new TimerResolution();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

// Raw hardware tools remain explicit modes; normal service startup binds first.
if (options.HardwareMode == "--hid-send")
{
    byte[] report = Convert.FromHexString(options.HardwareArguments[1]);
    if (report.Length != 8 || report[0] is not (0xA1 or 0xA2))
        throw new ArgumentException("Only the observed eight-byte mouse/keyboard report families are accepted.");
    using var board = new HidConnection(options.HardwareArguments[0]);
    await board.SendAsync(report, cts.Token);
    Console.WriteLine("Output completed on " + options.HardwareArguments[0] + ": " + Convert.ToHexString(report));
    return 0;
}
if (options.HardwareMode == "--hid-replay")
{
    var sequence = System.Text.Json.JsonSerializer.Deserialize<List<ReplayReport>>(File.ReadAllText(options.HardwareArguments[1]))!;
    var validated = sequence.Select(step => (Bytes: Convert.FromHexString(step.Hex), step.DelayMs)).ToArray();
    if (validated.Any(step => step.Bytes.Length != 8 || step.Bytes[0] is not (0xA1 or 0xA2)
        || step.DelayMs is < 0 or > 5000) || validated.Length > 5000)
        throw new ArgumentException("Invalid observed report sequence.");
    using var board = new HidConnection(options.HardwareArguments[0]);
    try
    {
        foreach (var step in validated)
        {
            await board.SendAsync(step.Bytes, cts.Token);
            if (step.DelayMs > 0) await Task.Delay(step.DelayMs, cts.Token);
        }
    }
    finally
    {
        await board.SendAsync([0xA1,0,0,0,0,0,0,0], CancellationToken.None);
        await board.SendAsync([0xA2,0,0,0,0,0,0,0], CancellationToken.None);
    }
    Console.WriteLine($"Completed {validated.Length} reports on {options.HardwareArguments[0]}; buttons and keys released.");
    return 0;
}
if (options.HardwareMode == "--hid-caps")
{
    var boards = HidHost.Enumerate();
    foreach (var b in boards)
    {
        var c = HidHost.Describe(b);
        Console.WriteLine($"{c.Pid}  {c.Open}  page=0x{c.UsagePage:X4} usage=0x{c.Usage:X4}  in={c.InputLen} out={c.OutputLen} feat={c.FeatureLen}");
        if (c.OutputFields.Length > 0) Console.WriteLine("    out: " + c.OutputFields);
        if (c.ReportDescriptorHex.Length > 0) Console.WriteLine("    desc: " + c.ReportDescriptorHex);
    }
    return 0;
}

var config = configuration!;
Directory.CreateDirectory(options.DataDir);
using var input = new InputRouter(config.Store, options.Allowed, config.Calibrations, preciseDelayMs: options.PreciseDelayMs,
    replyBoards: options.ReplyBoards, absoluteProbeBoard: options.AbsoluteProbeBoard)
    { Home = options.Home, Navigation = options.Navigation };
Console.WriteLine("Direct HID input enabled only for: " + string.Join(",", input.Allowed));
Console.WriteLine("HID reply diagnostics: " + (options.ReplyBoards.Length == 0 ? "off" : string.Join(",", options.ReplyBoards) + " (observation only)"));
Console.WriteLine("Home sequence: " + input.HomeSequenceName + (options.Home == HomeSequence.Vendor ? "" : " (test option; not the release default)"));
Console.WriteLine("Navigation sequence: " + input.NavigationSequenceName + (options.Navigation == NavigationSequence.Vendor ? "" : " (test option; phone compatibility unverified)"));
if (options.AbsoluteProbeBoard is not null) Console.WriteLine("EXPERIMENTAL absolute probe on " + options.AbsoluteProbeBoard + ": moves only; clicks, drags and keys refused.");
Console.WriteLine("Pointer movement pacing: " + (options.PreciseDelayMs > 0 ? $"high-resolution {options.PreciseDelayMs} ms; reset/drag/settle unchanged" : "legacy Task.Delay"));
Console.WriteLine("Video waits on an independent AirPlay receiver.");
var fleet = new ReceiverFleet(config.Receivers, config.Store, config.ReceiverPath, config.RuntimePath, options.DataDir);
var server = new ApiServer(options.Prefix, config.Store, input, fleet.Sessions.Select(s => (s.Config.Name, s.Frames)));
int exitCode = 0;
try
{
    await server.RunAsync(cts.Token, () =>
    {
        var boards = HidHost.Enumerate();
        Console.WriteLine($"iMouse 2.0 kernel. {boards.Count} WCH boards (VID_{HidHost.VendorId}).");
        fleet.Start(cts.Token);
    });
}
catch (OperationCanceledException) when (cts.IsCancellationRequested) { }
catch (HttpListenerException ex)
{
    Console.WriteLine("HTTP listen failed: " + ex.Message);
    Console.WriteLine("No receiver is started before this listener succeeds. Check the address, port and URL permission.");
    exitCode = 1;
}
finally
{
    // Stop accepting input and release its sessions before retiring receivers.
    try { server.Dispose(); }
    finally
    {
        try { await fleet.ShutdownAsync(); }
        catch (Exception ex)
        {
            Console.Error.WriteLine("Receiver shutdown incomplete: " + ex);
            exitCode = 1;
        }
    }
}
return exitCode;

record ReplayReport(string Hex, int DelayMs);
