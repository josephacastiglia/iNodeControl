using System.Net;
using IMouse2.Kernel;

if(args.Contains("--self-test")) return await SelfTests.RunAsync();

string Option(string name, string fallback)
{
    int index=Array.IndexOf(args,name);
    return index>=0 && index+1<args.Length ? args[index+1] : fallback;
}
// Parsed first, so a mistyped value fails before any board is enumerated or opened.
HomeSequence homeSequence;
bool fkaPassThroughProbe;
try
{
    homeSequence = InputRouter.ParseHomeSequence(Option("--home-sequence", "vendor"));
    int probeIndex = Array.IndexOf(args, "--fka-pass-through");
    string probeValue = probeIndex < 0 ? "disabled" : probeIndex + 1 < args.Length ? args[probeIndex + 1] : "";
    fkaPassThroughProbe = InputRouter.ParseFkaPassThroughProbe(probeValue);
}
catch (ArgumentException ex) { Console.WriteLine(ex.Message); return 2; }
string dataDir = Path.GetFullPath(Option("--data-dir",Path.Combine(AppContext.BaseDirectory, "data")));
Directory.CreateDirectory(dataDir);
var store = new DeviceStore(Path.Combine(dataDir, "devices.json"));
string prefix = args.FirstOrDefault(a => a.StartsWith("http")) ?? "http://127.0.0.1:9913/api/";
if (!prefix.EndsWith('/')) prefix += "/";

using var cts = new CancellationTokenSource();
using var timerResolution = new TimerResolution();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

var boards = HidHost.Enumerate();
Console.WriteLine($"iMouse 2.0 kernel. {boards.Count} WCH boards (VID_{HidHost.VendorId}). {store.All().Count} saved phones.");
if (args.Contains("--hid-send"))
{
    int arg = Array.IndexOf(args, "--hid-send");
    if (args.Length != arg + 3) throw new ArgumentException("--hid-send PID DATA_HEX (eight data bytes)");
    byte[] report = Convert.FromHexString(args[arg + 2]);
    if (report.Length != 8 || report[0] is not (0xA1 or 0xA2))
        throw new ArgumentException("Only the observed eight-byte mouse/keyboard report families are accepted.");
    using var board = new HidConnection(args[arg + 1]);
    await board.SendAsync(report, cts.Token);
    Console.WriteLine("Output completed on " + args[arg + 1] + ": " + Convert.ToHexString(report));
    return 0;
}
if (args.Contains("--hid-replay"))
{
    int arg = Array.IndexOf(args, "--hid-replay");
    if (args.Length != arg + 3) throw new ArgumentException("--hid-replay PID JSON_FILE");
    var sequence = System.Text.Json.JsonSerializer.Deserialize<List<ReplayReport>>(File.ReadAllText(args[arg + 2]))!;
    var validated = sequence.Select(step => (Bytes: Convert.FromHexString(step.Hex), step.DelayMs)).ToArray();
    if (validated.Any(step => step.Bytes.Length != 8 || step.Bytes[0] is not (0xA1 or 0xA2)
        || step.DelayMs is < 0 or > 5000) || validated.Length > 5000)
        throw new ArgumentException("Invalid observed report sequence.");
    using var board = new HidConnection(args[arg + 1]);
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
    Console.WriteLine($"Completed {validated.Length} reports on {args[arg + 1]}; buttons and keys released.");
    return 0;
}
if (args.Contains("--hid-caps"))
{
    foreach (var b in boards)
    {
        var c = HidHost.Describe(b);
        Console.WriteLine($"{c.Pid}  {c.Open}  page=0x{c.UsagePage:X4} usage=0x{c.Usage:X4}  in={c.InputLen} out={c.OutputLen} feat={c.FeatureLen}");
        if (c.OutputFields.Length > 0) Console.WriteLine("    out: " + c.OutputFields);
        if (c.ReportDescriptorHex.Length > 0) Console.WriteLine("    desc: " + c.ReportDescriptorHex);
    }
    return 0;
}
var calibrationFile=Path.Combine(dataDir,"pointer-calibration.json");
var calibrations=File.Exists(calibrationFile)
    ? System.Text.Json.JsonSerializer.Deserialize<List<PointerCalibration>>(File.ReadAllText(calibrationFile))! : [];
if (args.Contains("--precise-movement"))
    throw new ArgumentException("--precise-movement is deprecated. Use --precise-delay <ms> or default.");
int preciseDelay = Option("--precise-delay", "") is var s && int.TryParse(s, out int d) && d >= 1 && d <= 15
    ? d : (args.Contains("--legacy") ? 0 : 7);
using var input = new InputRouter(store, Option("--input-pid", "").Split(',', StringSplitOptions.RemoveEmptyEntries), calibrations, preciseDelayMs: preciseDelay)
    { Home = homeSequence, FkaPassThroughProbeEnabled = fkaPassThroughProbe };
Console.WriteLine("Direct HID input enabled only for: " + string.Join(",",input.Allowed));
Console.WriteLine("Home sequence: " + input.HomeSequenceName + (homeSequence == HomeSequence.Vendor ? "" : " (test option; not the release default)"));
Console.WriteLine("FKA pass-through probe: " + (fkaPassThroughProbe ? "enabled (test-only; phone mode is not acknowledged)" : "disabled"));
Console.WriteLine("Pointer movement pacing: " + (preciseDelay > 0 ? $"high-resolution {preciseDelay} ms; reset/drag/settle unchanged" : "legacy Task.Delay"));
Console.WriteLine("Video waits on an independent AirPlay receiver.");

string castName=Option("--cast-name","iMouse2-C24C");
string phoneId=Option("--phone-id","86:1D:4A:04:2F:F6");
string pipeName=Option("--frame-pipe","iMouse2-C24C-frames");
string receiverPath=Option("--receiver","");
string receiversFile=Option("--receivers","");
var configs=receiversFile.Length>0
    ? System.Text.Json.JsonSerializer.Deserialize<List<ReceiverConfig>>(File.ReadAllText(receiversFile))!
    : new List<ReceiverConfig>{new(phoneId,store.All().Single(p=>p.deviceid==phoneId).pid,castName,pipeName,7110,"02:49:4D:32:C2:4C")};
using var fleet=new ReceiverFleet(configs,store,receiverPath,Option("--receiver-runtime",""),dataDir);
fleet.Start(cts.Token);
using var server = new ApiServer(prefix, store,input,fleet.Sessions.Select(s=>(s.Config.Name,s.Frames)));
try { await server.RunAsync(cts.Token); }
catch (OperationCanceledException) { }
catch (HttpListenerException ex)
{
    Console.WriteLine("HTTP listen failed: " + ex.Message);
    Console.WriteLine("If this is access denied, run once elevated: netsh http add urlacl url=" + prefix + " user=%USERNAME%");
    return 1;
}
return 0;

record ReplayReport(string Hex, int DelayMs);
