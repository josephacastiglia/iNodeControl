using System.Net;
using System.Text.Json;
using IMouse2.Kernel;

_ = KernelDiagnostics.BuildIdentity; // Capture before any listener or hardware is started.
if (args.Contains("--self-test")) return await SelfTests.RunAsync();

KernelOptions options;
KernelConfiguration config;
try
{
    options = KernelOptions.Parse(args);
    config = KernelConfiguration.Load(options);
    if (options.ValidateOnly)
    {
        Console.WriteLine(JsonSerializer.Serialize(config.ValidationReport(), new JsonSerializerOptions { WriteIndented = true }));
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

if (options.ConsoleLog is { } consoleLog)
{
    // Detached (WMI) launch has no redirected console: write what the console would show to a file.
    var log = new StreamWriter(new FileStream(consoleLog, FileMode.Append, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete)) { AutoFlush = true };
    Console.SetOut(log); Console.SetError(log);
}
Console.WriteLine("Kernel pid " + Environment.ProcessId + " started " + DateTime.UtcNow.ToString("o") + ".");
Directory.CreateDirectory(options.DataDir);
using var input = new InputRouter(config.Store, options.Allowed, config.Calibrations)
    { Home = options.Home };
Console.WriteLine("Direct HID input enabled only for: " + string.Join(",", input.Allowed));
Console.WriteLine("Home sequence: " + input.HomeSequenceName + (options.Home == HomeSequence.Vendor ? "" : " (test option; not the release default)"));
Console.WriteLine($"Pointer movement pacing: high-resolution {InputRouter.MoveDelayMs} ms; reset/drag/settle unchanged");
Console.WriteLine("Video waits on an independent AirPlay receiver.");
var fleet = new ReceiverFleet(config.Receivers, config.Store, config.ReceiverPath, config.RuntimePath, options.DataDir);
var server = new ApiServer(options.Prefix, config.Store, input, fleet.Sessions.Select(s => (s.Config.Name, s.Frames)))
    { Receivers = fleet };
if (options.HeldReceivers.Length > 0) Console.WriteLine("Receivers held until released: " + string.Join(",", options.HeldReceivers));
if (options.StopFile is { } stopFile) Console.WriteLine("Graceful stop: write this PID to " + stopFile + ".");
var stopWatch = options.StopFile is { } watched ? new KernelStopFile(watched, Environment.ProcessId).WatchAsync(cts) : Task.CompletedTask;
int exitCode = 0;
try
{
    await server.RunAsync(cts.Token, () =>
    {
        var boards = HidHost.Enumerate();
        Console.WriteLine($"iMouse 2.0 kernel. {boards.Count} WCH boards (VID_{HidHost.VendorId}).");
        fleet.Start(cts.Token, options.HeldReceivers);
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
