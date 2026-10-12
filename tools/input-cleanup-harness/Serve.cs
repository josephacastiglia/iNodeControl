using System.Buffers.Binary;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.IO.Pipes;
using System.Text.Json;
using IMouse2.Kernel;

namespace IMouse2.Harness;

/// <summary>
/// Serves a mock kernel for driving the real console by hand: the kernel's own ApiServer and
/// InputRouter with a simulated board and one simulated phone, SIM:01, whose screen is a
/// synthetic 500x1080 frame sent through the real frame pipe. It writes to no board and talks to
/// no phone or receiver. Put tools/input-fault-proxy in front of it to lose answers.
///
/// It never reaches real hardware, and refuses to start rather than risk it:
/// - The kernel's own board list enumerates the machine's real USB boards. So the ApiServer
///   listens on a free loopback port under a random path segment that only this process knows,
///   and the front listener on PORT answers /config/usb/get with the simulated board alone and
///   forwards everything else there.
/// - A port collision fails startup (exit 3). http.sys shares a port between URL prefixes: a
///   fixed PORT+1 once landed on a proxy's port, and /api/ then went straight to the ApiServer,
///   bypassing both the proxy and this front, so the real boards were enumerated.
/// - After starting, it reads its own board and device lists through PORT and exits (4) unless
///   they are exactly the simulated board and phone.
/// Usage: --serve PORT [BOARDPID]. Runs until the process is stopped.
/// </summary>
static class Serve
{
    public const int PortInUse = 3, SelfCheckFailed = 4;

    public static async Task<int> RunAsync(int port, string boardPid, CancellationToken external = default, Action<string>? ready = null)
    {
        if (PortTaken(port)) { Console.Error.WriteLine($"mock kernel: port {port} is already in use; refusing to start."); return PortInUse; }
        string dir = Path.Combine(Path.GetTempPath(), "imouse-mock-kernel-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        try
        {
            string file = Path.Combine(dir, "devices.json");
            File.WriteAllText(file, JsonSerializer.Serialize(new[] { new Phone { deviceid = Kernel.PhoneId, name = "Mock phone", device_name = "iPhone XR",
                width = 414, height = 896, vid = "720A", pid = boardPid, uid = boardPid } }));
            var board = new Board();
            // Every write goes to the simulated board: the router is given only this transport.
            using var input = new InputRouter(new DeviceStore(file), [boardPid], [new PointerCalibration(boardPid, 500, 1080, 14, 14, 5, 5)], _ => board);
            string pipe = "imouse-mock-kernel-" + Guid.NewGuid().ToString("N");
            using var frames = new FrameStore(pipe, Kernel.PhoneId) { Receiver = () => new("running", "mock", 0, 0) };
            _ = frames.RunAsync();
            var probe = new TcpListener(IPAddress.Loopback, 0); probe.Start();
            int inner = ((IPEndPoint)probe.LocalEndpoint).Port; probe.Stop();
            string secret = Guid.NewGuid().ToString("N");
            using var server = new ApiServer($"http://localhost:{inner}/{secret}/api/", new DeviceStore(file), "mock", input, frames);
            using var stop = CancellationTokenSource.CreateLinkedTokenSource(external);
            ConsoleCancelEventHandler onCancel = (_, e) => { e.Cancel = true; stop.Cancel(); };
            Console.CancelKeyPress += onCancel;
            try
            {
                var run = server.RunAsync(stop.Token);
                _ = FeedAsync(pipe, stop.Token);
                using var listener = new HttpListener();
                listener.Prefixes.Add($"http://localhost:{port}/");
                try { listener.Start(); }
                catch (HttpListenerException ex) { Console.Error.WriteLine($"mock kernel: cannot listen on port {port} ({ex.Message}); refusing to start."); stop.Cancel(); return PortInUse; }
                var front = FrontAsync(listener, $"http://localhost:{inner}/{secret}", boardPid, stop.Token);
                string? problem = await SelfCheckAsync(port, boardPid);
                if (problem is not null) { Console.Error.WriteLine($"mock kernel: self-check failed: {problem}; stopping."); stop.Cancel(); return SelfCheckFailed; }
                Console.WriteLine($"mock kernel on http://localhost:{port}/api/ (simulated board {boardPid}, phone {Kernel.PhoneId}; self-check passed; no real board is enumerated)");
                ready?.Invoke($"http://localhost:{port}");
                try { await Task.WhenAny(run, front, Task.Delay(Timeout.Infinite, stop.Token)); } catch (OperationCanceledException) { }
                stop.Cancel();
                return 0;
            }
            finally { Console.CancelKeyPress -= onCancel; }
        }
        finally { try { Directory.Delete(dir, true); } catch { } }
    }

    /// <summary>True when anything already holds PORT on loopback, http.sys registrations included.</summary>
    public static bool PortTaken(int port)
    {
        foreach (var address in new[] { IPAddress.Loopback, IPAddress.IPv6Loopback })
        {
            var probe = new TcpListener(address, port);
            try { probe.Start(); }
            catch (SocketException ex) when (ex.SocketErrorCode is SocketError.AddressAlreadyInUse or SocketError.AccessDenied) { return true; }
            catch (SocketException) { continue; }   // e.g. IPv6 unavailable
            finally { try { probe.Stop(); } catch { } }
        }
        return false;
    }

    /// <summary>Reads the lists through PORT: they must be exactly this mock's board and phone.</summary>
    static async Task<string?> SelfCheckAsync(int port, string boardPid)
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
        try
        {
            using var boards = JsonDocument.Parse(await client.GetStringAsync($"http://localhost:{port}/api/config/usb/get"));
            var list = boards.RootElement.GetProperty("data").GetProperty("list").EnumerateArray().ToList();
            if (list.Count != 1 || list[0].GetProperty("pid").GetString() != boardPid) return $"board list through port {port} is not exactly the simulated board ({list.Count} entries)";
            using var devices = JsonDocument.Parse(await client.GetStringAsync($"http://localhost:{port}/api/device/get"));
            var phones = devices.RootElement.GetProperty("data").GetProperty("list").EnumerateArray().ToList();
            if (phones.Count != 1 || phones[0].GetProperty("deviceid").GetString() != Kernel.PhoneId) return $"device list through port {port} is not exactly {Kernel.PhoneId}";
            return null;
        }
        catch (Exception ex) { return ex.GetType().Name + ": " + ex.Message; }
    }

    /// <summary>Answers the board list with the simulated board; forwards everything else to the ApiServer.</summary>
    static async Task FrontAsync(HttpListener listener, string inner, string boardPid, CancellationToken ct)
    {
        using var client = new HttpClient { Timeout = Timeout.InfiniteTimeSpan };
        byte[] boards = JsonSerializer.SerializeToUtf8Bytes(new { status = 200, message = "ok",
            data = new { code = 0, list = new[] { new { vid = "720A", pid = boardPid, uid = boardPid, state = 2 } } } });
        while (!ct.IsCancellationRequested)
        {
            HttpListenerContext ctx;
            try { ctx = await listener.GetContextAsync().WaitAsync(ct); }
            catch (OperationCanceledException) { break; }
            _ = Task.Run(async () =>
            {
                try
                {
                    var req = ctx.Request;
                    if (req.HttpMethod == "GET" && req.Url!.AbsolutePath.EndsWith("/config/usb/get", StringComparison.OrdinalIgnoreCase))
                    {
                        ctx.Response.ContentType = "application/json";
                        await ctx.Response.OutputStream.WriteAsync(boards);
                        ctx.Response.Close();
                        return;
                    }
                    using var forward = new HttpRequestMessage(new HttpMethod(req.HttpMethod), inner + req.Url!.PathAndQuery);
                    if (req.HasEntityBody)
                    {
                        using var body = new MemoryStream(); await req.InputStream.CopyToAsync(body);
                        forward.Content = new ByteArrayContent(body.ToArray());
                        if (req.ContentType is { } type) forward.Content.Headers.TryAddWithoutValidation("Content-Type", type);
                    }
                    using var answer = await client.SendAsync(forward, ct);
                    ctx.Response.StatusCode = (int)answer.StatusCode;
                    if (answer.Content.Headers.ContentType is { } ctype) ctx.Response.ContentType = ctype.ToString();
                    await answer.Content.CopyToAsync(ctx.Response.OutputStream, ct);
                    ctx.Response.Close();
                }
                catch { try { ctx.Response.Abort(); } catch { } }
            }, ct);
        }
    }

    /// <summary>
    /// A light grey frame with a darker band near the top and a dark bar that moves down it, so
    /// the picture changes on every frame the way live video does, about thirty frames a second.
    /// </summary>
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
                int bar = 0;
                while (!ct.IsCancellationRequested)
                {
                    int old = bar; bar = (bar + 7) % (h - 160);
                    for (int r = 0; r < 20; r++) bmp.AsSpan(54 + (old + r) * stride, w * 3).Fill(225);
                    for (int r = 0; r < 20; r++) bmp.AsSpan(54 + (bar + r) * stride, w * 3).Fill(60);
                    await client.WriteAsync(prefix, ct); await client.WriteAsync(bmp, ct);
                    await Task.Delay(33, ct);
                }
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex) { Console.WriteLine("frame feed: " + ex.Message); await Task.Delay(500, CancellationToken.None); }
        }
    }
}
