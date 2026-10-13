using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text;
using IMouse2.Kernel;

// Optional loopback transport probe, not a kernel service. This project contains
// no board enumeration, HID, receiver startup or console/UI implementation.
static class ScreenshotHttpTests
{
    public static async Task<int> RunAsync()
    {
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(25));
        await using var rig = new Rig();
        byte[] frame = Bmp(2048, 2048, 17);
        await rig.Send(frame);
        var portProbe = new TcpListener(IPAddress.Loopback, 0); portProbe.Start();
        int port = ((IPEndPoint)portProbe.LocalEndpoint).Port; portProbe.Stop();
        string path = "/imouse-frame-test-" + Guid.NewGuid().ToString("N") + "/";
        using var listener = new HttpListener();
        listener.Prefixes.Add($"http://localhost:{port}{path}");
        listener.Start(); // A collision fails; never use or stop another listener.
        var requests = new ConcurrentBag<Task>();
        int active = 0, aborted = 0, cancelled = 0, finished = 0;
        var run = Serve();
        using var client = new HttpClient(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(10) };
        var raw = new List<TcpClient>();
        try
        {
            string address = $"http://localhost:{port}{path}";
            using (var initial = await client.GetAsync(address, stop.Token))
            {
                initial.EnsureSuccessStatusCode();
                Check(initial.Content.Headers.ContentType?.MediaType == "image/bmp", "BMP content type");
                Check(initial.Headers.GetValues("X-iMouse-Frame-Sequence").Single() == "1", "sequence header");
                Check((await initial.Content.ReadAsByteArrayAsync(stop.Token)).AsSpan().SequenceEqual(frame), "exact initial bytes");
            }
            var elapsed = Stopwatch.StartNew();
            for (int i = 0; i < 2; i++)
            {
                var socket = new TcpClient { ReceiveBufferSize = 512 };
                raw.Add(socket);
                await socket.ConnectAsync(IPAddress.Loopback, port, stop.Token);
                await socket.GetStream().WriteAsync(Encoding.ASCII.GetBytes($"GET {path} HTTP/1.1\r\nHost: localhost:{port}\r\nConnection: close\r\n\r\n"), stop.Token);
                var headers = new StringBuilder(); byte[] next = new byte[1];
                using var headerLimit = CancellationTokenSource.CreateLinkedTokenSource(stop.Token);
                headerLimit.CancelAfter(TimeSpan.FromSeconds(2));
                while (!headers.ToString().EndsWith("\r\n\r\n", StringComparison.Ordinal))
                {
                    Check(headers.Length < 8192 && await socket.GetStream().ReadAsync(next, headerLimit.Token) == 1, "response headers");
                    headers.Append((char)next[0]);
                }
                Check(headers.ToString().StartsWith("HTTP/1.1 200"), "stalled request begins as a BMP response");
                // Leave the multi-megabyte body unread so the real response write stalls.
            }
            Check(Volatile.Read(ref active) == 2, "two real transfers are still pending");
            using (var busy = await client.GetAsync(address, stop.Token))
                Check(busy.StatusCode == HttpStatusCode.ServiceUnavailable, "third request receives busy without another frame copy");
            frame[^1] = 81; await rig.Send(frame);
            Check(rig.Store.Delivery.Sequence == 2, "producer advances while sockets stop reading");
            await WaitUntil(() => Volatile.Read(ref active) == 0, stop.Token);
            Check(Volatile.Read(ref aborted) == 2 && Volatile.Read(ref cancelled) == 2 && elapsed.Elapsed < TimeSpan.FromSeconds(9), "both unread responses terminate as cancellation at the deadline");
            using (var recovered = await client.GetAsync(address, stop.Token))
            {
                recovered.EnsureSuccessStatusCode();
                Check(recovered.Headers.GetValues("X-iMouse-Frame-Sequence").Single() == "2", "recovered response metadata");
                Check((await recovered.Content.ReadAsByteArrayAsync(stop.Token)).AsSpan().SequenceEqual(frame), "recovered exact bytes");
            }
            Console.WriteLine($"PASS loopback screenshot transport: initial bytes/metadata, 2 blocked readers, busy response, advancing producer, 2 aborts after {elapsed.Elapsed.TotalSeconds:F2}s, exact recovery. Completed sends={finished}.");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("FAIL loopback screenshot transport: " + ex); return 1; }
        finally
        {
            foreach (var socket in raw) socket.Dispose();
            stop.Cancel(); listener.Stop();
            try { await run; } catch (OperationCanceledException) { }
            await Task.WhenAll(requests).WaitAsync(TimeSpan.FromSeconds(3));
        }

        async Task Serve()
        {
            while (!stop.IsCancellationRequested)
            {
                HttpListenerContext context;
                try { context = await listener.GetContextAsync().WaitAsync(stop.Token); }
                catch (HttpListenerException) when (stop.IsCancellationRequested) { return; }
                catch (ObjectDisposedException) when (stop.IsCancellationRequested) { return; }
                requests.Add(Respond(context));
            }
        }
        async Task Respond(HttpListenerContext context)
        {
            Interlocked.Increment(ref active);
            try
            {
                var result = await rig.Store.WriteFrameAsync(context, "fake", stop.Token);
                if (result == FrameWriteResult.Written) Interlocked.Increment(ref finished);
                else { context.Response.StatusCode = result == FrameWriteResult.Busy ? 503 : 404; context.Response.Close(); }
            }
            catch (Exception ex) when (ex is OperationCanceledException or HttpListenerException or IOException or ObjectDisposedException)
            {
                Interlocked.Increment(ref aborted);
                if (ex is OperationCanceledException) Interlocked.Increment(ref cancelled);
                try { context.Response.Abort(); } catch { }
            }
            finally { Interlocked.Decrement(ref active); }
        }
    }

    static async Task WaitUntil(Func<bool> ready, CancellationToken ct)
    { while (!ready()) await Task.Delay(10, ct); }
    static void Check(bool yes, string message) { if (!yes) throw new Exception(message); }
    static byte[] Bmp(int width, int height, byte fill)
    {
        byte[] bmp = new byte[54 + ((width * 3 + 3) & ~3) * height];
        bmp[0] = (byte)'B'; bmp[1] = (byte)'M';
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(2), bmp.Length);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(10), 54);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(14), 40);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(18), width);
        BinaryPrimitives.WriteInt32LittleEndian(bmp.AsSpan(22), height);
        BinaryPrimitives.WriteInt16LittleEndian(bmp.AsSpan(26), 1);
        BinaryPrimitives.WriteInt16LittleEndian(bmp.AsSpan(28), 24);
        bmp.AsSpan(54).Fill(fill); return bmp;
    }
}
