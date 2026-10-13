using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text;
using IMouse2;

// Explicit opt-in: real HTTP on an ephemeral loopback port only. No kernel,
// hardware, settings, UI or input endpoints. All peer tasks are awaited on exit.
static class LoopbackTransferProbe
{
    public static async Task<int> Run()
    {
        var listener = new TcpListener(IPAddress.Loopback, 0);
        using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        using var stalledPeer = new CancellationTokenSource();
        Task? server = null;
        try
        {
            listener.Start();
            int port = ((IPEndPoint)listener.LocalEndpoint).Port;
            server = Serve(listener, lifetime.Token, stalledPeer.Token);
            using var api = new ApiClient($"http://127.0.0.1:{port}", ownership: false);
            var buffer = new FrameBuffer(); var clock = Stopwatch.StartNew(); bool timedOut = false;
            try { await api.ScreenshotIntoAsync("synthetic", false, buffer, lifetime.Token); }
            catch (OperationCanceledException) { timedOut = true; }
            finally { stalledPeer.Cancel(); }
            Check(timedOut && !lifetime.IsCancellationRequested && clock.Elapsed.TotalSeconds < 12,
                "Real stalled response did not end at the request deadline");
            Check(buffer.Length == 0 && buffer.Metadata is null, "Partial body remained publishable");
            Console.WriteLine($"PASS real HTTP body timeout after {clock.Elapsed.TotalMilliseconds:0} ms; caller not cancelled");

            bool busy = false;
            try { await api.ScreenshotIntoAsync("synthetic", false, buffer, lifetime.Token); }
            catch (HttpRequestException ex) when (ex.StatusCode == HttpStatusCode.ServiceUnavailable) { busy = true; }
            Check(busy && buffer.Length == 0 && buffer.Metadata is null, "Busy response asserted image evidence");
            Console.WriteLine("PASS real HTTP 503 clears evidence and returns to the caller");

            await api.ScreenshotIntoAsync("synthetic", false, buffer, lifetime.Token);
            Check(buffer.Length == Size && buffer.Metadata?.Sequence == 3, "Chunked image did not recover");
            for (int i = 0; i < Size; i++) Check(buffer.Data[i] == Pixel(i), "Chunked image byte mismatch at " + i);
            await server;
            Console.WriteLine("PASS real chunked HTTP image preserves all bytes across buffer growth and recovers after timeout/503");
            return 0;
        }
        catch (Exception ex) { Console.WriteLine("FAIL " + ex); return 1; }
        finally
        {
            lifetime.Cancel(); stalledPeer.Cancel(); listener.Stop();
            if (server is not null)
                try { await server; } catch (OperationCanceledException) { } catch (SocketException) { }
        }
    }
    const int Size = 3 * 1024 * 1024 + 13;
    static byte Pixel(int at) => at == 0 ? (byte)'B' : at == 1 ? (byte)'M' : (byte)(at % 251);
    static void Check(bool yes, string message) { if (!yes) throw new Exception(message); }
    static async Task Text(NetworkStream stream, string value, CancellationToken ct) =>
        await stream.WriteAsync(Encoding.ASCII.GetBytes(value), ct);
    static async Task Serve(TcpListener listener, CancellationToken ct, CancellationToken stalled)
    {
        for (int request = 1; request <= 3; request++)
        {
            using var peer = await listener.AcceptTcpClientAsync(ct);
            using var stream = peer.GetStream();
            using var reader = new StreamReader(stream, Encoding.ASCII, false, 1024, leaveOpen: true);
            string? first = await reader.ReadLineAsync(ct);
            Check(first?.StartsWith("GET /api/pic/screenshot?id=synthetic&binary=true HTTP/1.1") == true,
                "Unexpected request; only this probe's screenshot GET is allowed");
            while (await reader.ReadLineAsync(ct) is { Length: > 0 }) { }
            if (request == 1)
            {
                await Text(stream, "HTTP/1.1 200 OK\r\nContent-Length: 100\r\nConnection: close\r\n\r\nBMpartial", ct);
                using var stop = CancellationTokenSource.CreateLinkedTokenSource(ct, stalled);
                try { await Task.Delay(Timeout.InfiniteTimeSpan, stop.Token); }
                catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
            }
            else if (request == 2)
                await Text(stream, "HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nRetry-After: 1\r\nConnection: close\r\n\r\n", ct);
            else
            {
                await Text(stream, "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n" +
                    "X-iMouse-Frame-Session: 0123456789abcdef0123456789abcdef\r\nX-iMouse-Frame-Sequence: 3\r\n" +
                    "X-iMouse-Frame-Age-Ms: 0\r\nX-iMouse-Frame-Delivery: flowing\r\n\r\n", ct);
                byte[] chunk = new byte[65536];
                for (int at = 0; at < Size;)
                {
                    int count = Math.Min(chunk.Length, Size - at);
                    for (int i = 0; i < count; i++) chunk[i] = Pixel(at + i);
                    await Text(stream, count.ToString("X") + "\r\n", ct);
                    await stream.WriteAsync(chunk.AsMemory(0, count), ct);
                    await Text(stream, "\r\n", ct); at += count;
                }
                await Text(stream, "0\r\n\r\n", ct);
            }
        }
    }
}
