using System.Buffers.Binary;
using System.IO;
using System.IO.Pipes;
using System.Text.Json;
using IMouse2.Kernel;

namespace IMouse2.Harness;

/// <summary>
/// Serves a mock kernel for driving the real console by hand: the kernel's own ApiServer and
/// InputRouter with a simulated board and one simulated phone, SIM:01, whose screen is a
/// synthetic 500x1080 frame sent through the real frame pipe. It writes to no board and talks to
/// no phone or receiver. Put tools/input-fault-proxy in front of it to lose answers.
/// The console shows a phone as controllable only when the kernel's board list, which is read
/// from the machine's real USB boards, includes its pid. So the mock phone borrows the pid of a
/// board that is present but bound to no phone; nothing is ever written to that board.
/// Usage: --serve PORT BOARDPID. Runs until the process is stopped.
/// </summary>
static class Serve
{
    public static async Task<int> RunAsync(int port, string boardPid)
    {
        string dir = Path.Combine(Path.GetTempPath(), "imouse-mock-kernel-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        string file = Path.Combine(dir, "devices.json");
        File.WriteAllText(file, JsonSerializer.Serialize(new[] { new Phone { deviceid = Kernel.PhoneId, name = "Mock phone", device_name = "iPhone XR",
            width = 414, height = 896, vid = "720A", pid = boardPid, uid = boardPid } }));
        var board = new Board();
        // Every write goes to the simulated board: the router is given only this transport.
        using var input = new InputRouter(new DeviceStore(file), [boardPid], [new PointerCalibration(boardPid, 500, 1080, 14, 14, 5, 5)], _ => board);
        string pipe = "imouse-mock-kernel-" + Guid.NewGuid().ToString("N");
        using var frames = new FrameStore(pipe, Kernel.PhoneId) { Receiver = () => new("running", "mock", 0, 0) };
        _ = frames.RunAsync();
        using var server = new ApiServer($"http://localhost:{port}/api/", new DeviceStore(file), "mock", input, frames);
        using var stop = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) => { e.Cancel = true; stop.Cancel(); };
        var run = server.RunAsync(stop.Token);
        _ = FeedAsync(pipe, stop.Token);
        Console.WriteLine($"mock kernel on http://localhost:{port}/api/ (simulated board, phone {Kernel.PhoneId})");
        try { await run; } catch (OperationCanceledException) { }
        try { Directory.Delete(dir, true); } catch { }
        return 0;
    }

    /// <summary>A light grey frame with a darker band near the top, ten frames a second.</summary>
    static async Task FeedAsync(string pipe, CancellationToken ct)
    {
        const int w = 500, h = 1080; int stride = (w * 3 + 3) & ~3, length = 54 + stride * h;
        var bmp = new byte[length];
        bmp[0] = (byte)'B'; bmp[1] = (byte)'M';
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(2), length);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(10), 54);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(14), 40);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(18), w);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(22), h);
        BinaryPrimitives.WriteInt16LittleEndian(bmp.AsSpan(26), 1);
        BinaryPrimitives.WriteInt16LittleEndian(bmp.AsSpan(28), 24);
        for (int row = 0; row < h; row++)
            bmp.AsSpan(54 + row * stride, w * 3).Fill(row > h - 120 ? (byte)120 : (byte)225);   // bottom-up rows: the band is at the top
        var prefix = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(prefix, length);
        while (!ct.IsCancellationRequested)
        {
            try
            {
                using var client = new NamedPipeClientStream(".", pipe, PipeDirection.Out, PipeOptions.Asynchronous);
                await client.ConnectAsync(5000, ct);
                while (!ct.IsCancellationRequested)
                {
                    await client.WriteAsync(prefix, ct); await client.WriteAsync(bmp, ct);
                    await Task.Delay(100, ct);
                }
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex) { Console.WriteLine("frame feed: " + ex.Message); await Task.Delay(500, CancellationToken.None); }
        }
    }
}
