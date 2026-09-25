// Hosts the real kernel ApiServer + InputSessions + InputRouter + FrameStore on 127.0.0.1
// with a logging HID transport. Every HID report the kernel would send is printed as
//   HID <pid> <hex>
// so tests can prove which inputs reached (or never reached) a phone.
using System.IO.Pipes;
using System.Text.Json;
using IMouse2.Kernel;

string port = args.Length > 0 ? args[0] : "9950";
string tag = Guid.NewGuid().ToString("N")[..8];
string dir = Path.Combine(Path.GetTempPath(), "nt-kernel-harness-" + tag);
Directory.CreateDirectory(dir);
string devices = Path.Combine(dir, "devices.json");
File.WriteAllText(devices, JsonSerializer.Serialize(new[]
{
    new Phone { deviceid = "HARNESS:01", name = "Harness 1", pid = "C24C", uid = "C24CBFBD", width = 414, height = 896 },
    new Phone { deviceid = "HARNESS:02", name = "Harness 2", pid = "C241", uid = "C241BFBD", width = 414, height = 896 },
}));
var store = new DeviceStore(devices);
var gate = new object();
IHidTransport Open(string pid) => new LoggingTransport(pid, gate);
using var input = new InputRouter(store, ["C24C", "C241"],
    [new("C24C", 500, 1080, 14, 14, 5.1, 5.1), new("C241", 500, 1080, 14, 14, 5.1, 5.1)], Open, preciseDelayMs: 0);
using var frames1 = new FrameStore("nt-harness-1-" + tag, "HARNESS:01");
using var frames2 = new FrameStore("nt-harness-2-" + tag, "HARNESS:02");
_ = frames1.RunAsync();
_ = frames2.RunAsync();
using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };
_ = Task.Run(async () =>
{
    // Only phone 1 gets video; phone 2 stays "no live frame" (code 25).
    using var pipe = new NamedPipeClientStream(".", "nt-harness-1-" + tag, PipeDirection.Out);
    await pipe.ConnectAsync(cts.Token);
    byte[] bmp = MakeBmp(500, 1080), prefix = BitConverter.GetBytes(bmp.Length);
    while (!cts.IsCancellationRequested)
    {
        bmp[54 + (bmp.Length - 54) / 2]++; // change one pixel so frames differ
        await pipe.WriteAsync(prefix, cts.Token);
        await pipe.WriteAsync(bmp, cts.Token);
        await pipe.FlushAsync(cts.Token);
        await Task.Delay(100, cts.Token);
    }
});
using var server = new ApiServer($"http://127.0.0.1:{port}/api/", store, input, [("iMouse2-H1", frames1), ("iMouse2-H2", frames2)]);
var run = server.RunAsync(cts.Token);
Console.WriteLine("READY " + port);
Console.Out.Flush();
// With --exit-on-stdin-close the harness stops when its parent test process goes away.
if (args.Contains("--exit-on-stdin-close")) _ = Task.Run(() => { Console.In.ReadToEnd(); cts.Cancel(); });
try { await run; } catch (OperationCanceledException) { }
return 0;

static byte[] MakeBmp(int w, int h)
{
    int stride = (w * 3 + 3) & ~3;
    var b = new byte[54 + stride * h];
    b[0] = (byte)'B'; b[1] = (byte)'M';
    BitConverter.GetBytes(b.Length).CopyTo(b, 2);
    BitConverter.GetBytes(54).CopyTo(b, 10);
    BitConverter.GetBytes(40).CopyTo(b, 14);
    BitConverter.GetBytes(w).CopyTo(b, 18);
    BitConverter.GetBytes(h).CopyTo(b, 22);
    BitConverter.GetBytes((short)1).CopyTo(b, 26);
    BitConverter.GetBytes((short)24).CopyTo(b, 28);
    for (int i = 54; i < b.Length; i++) b[i] = (byte)(i * 7);
    return b;
}

sealed class LoggingTransport(string pid, object gate) : IHidTransport
{
    public Task SendAsync(byte[] data, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        lock (gate) { Console.WriteLine($"HID {pid} {Convert.ToHexString(data)}"); Console.Out.Flush(); }
        return Task.CompletedTask;
    }
    public void Dispose() { }
}
