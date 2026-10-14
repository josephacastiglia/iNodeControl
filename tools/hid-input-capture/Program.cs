using System.Diagnostics;
using System.Text.Json;
using IMouse2.Kernel;

if (args.SequenceEqual(new[] { "--self-test" }))
{
    int passed = 0;
    void Check(bool ok, string message) { if (!ok) throw new Exception(message); passed++; }
    HidInputReportTests.Run(Check);
    await HidReplyMonitorTests.RunAsync(Check);
    CaptureArguments.Test();
    Console.WriteLine($"{passed} parser/monitor checks and 6 argument cases passed; no device opened.");
    return 0;
}
if (args.Length == 4 && args[0] == "--audit-release")
{
    Console.WriteLine(JsonSerializer.Serialize(ReleaseAudit.Check(args[1], args[2], args[3])));
    return 0;
}
if (!CaptureArguments.TryParse(args, out int seconds))
{
    Console.Error.WriteLine("Usage: hid-input-capture --pid C24C --seconds 1..120");
    return 2;
}

var clock = Stopwatch.StartNew();
void Record(string kind, object detail) => Console.WriteLine(JsonSerializer.Serialize(new
    { kind, elapsed_ms = clock.Elapsed.TotalMilliseconds, utc = DateTime.UtcNow, detail }));
using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(seconds));
Console.CancelKeyPress += (_, e) => { e.Cancel = true; deadline.Cancel(); };
_ = Task.Run(async () =>
{
    while (await Console.In.ReadLineAsync() is { } line)
        if (line == "stop") { deadline.Cancel(); return; }
    deadline.Cancel();
});
try
{
    var boards = HidHost.Enumerate().Where(b => b.Pid == "C24C").ToArray();
    if (boards.Length != 1) throw new InvalidOperationException("Expected exactly one C24C HID collection.");
    var stream = HidInputReader.Open(boards[0]);
    Record("caps", new { input_bytes = 17, output_bytes = 9, access = "GENERIC_READ only" });
    var telemetry = new HidReplyTelemetry();
    int count = 0;
    using var monitor = new HidReplyMonitor(stream, telemetry, bytes =>
    {
        Record("input", new { report_hex = Convert.ToHexString(bytes),
            ios_outcome = "unverified; no command correlation asserted" });
        if (Interlocked.Increment(ref count) >= 4096) deadline.Cancel();
    });
    Record("ready", new { pid = "C24C", report_bytes = 17 });
    await Task.WhenAny(Task.Delay(Timeout.Infinite, deadline.Token), monitor.Completion);
    await monitor.StopAsync();
    if (count >= 4096 || telemetry.Snapshot() is { InvalidReports: > 0 } or { ErrorType: not null })
        throw new IOException("Capture ended with a limit, invalid report or read error; inspect the raw record.");
    Record("closed", new { reports = count, read_cancelled = deadline.IsCancellationRequested,
        observation = telemetry.Snapshot() });
    return 0;
}
catch (Exception ex)
{
    Record("error", new { type = ex.GetType().Name, ex.Message });
    return 1;
}
