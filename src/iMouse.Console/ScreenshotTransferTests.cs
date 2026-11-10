using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;

namespace IMouse2;

// Moved on 9 Nov 2026 from the stand-alone project tools/preview_tests, which is deleted.
// Uses the production API reader with synthetic response streams. No sockets or windows;
// every handler refuses non-screenshot requests.
internal static class ScreenshotTransferTests
{
    public static IEnumerable<(string, Func<Task>)> Cases()
    {
        yield return ("stalled image body expires without caller cancellation, disposes and recovers", StalledBody);
        yield return ("headers and body share one deadline", SharedDeadline);
        yield return ("caller cancellation interrupts an image body and next fetch recovers", CallerCancellation);
        yield return ("unknown-length image preserves bytes across reusable buffer growth", UnknownLength);
        yield return ("advertised oversized image is refused before reading its body", AdvertisedLimit);
        yield return ("unadvertised oversized body stops at limit and clears partial evidence", UnadvertisedLimit);
        yield return ("body I/O failure clears partial evidence and disposes response", BodyFailure);
        yield return ("exact image byte limit accepts end of stream", ExactLimit);
        yield return ("a frame fetch is one GET of the kernel's screenshot route for that phone", RequestLine);
    }

    static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
    const int Limit = 64 * 1024 * 1024;
    static readonly byte[] Small = [0x42, 0x4d, 1, 2, 3, 4, 5, 6, 7, 8];
    static HttpResponseMessage Response(Stream stream, long? length = null)
    {
        var response = new HttpResponseMessage(HttpStatusCode.OK) { Content = new StreamContent(stream) };
        response.Content.Headers.ContentLength = length;
        response.Headers.Add("X-iMouse-Frame-Session", "0123456789abcdef0123456789abcdef");
        response.Headers.Add("X-iMouse-Frame-Sequence", "1");
        response.Headers.Add("X-iMouse-Frame-Age-Ms", "0");
        response.Headers.Add("X-iMouse-Frame-Delivery", "flowing");
        return response;
    }
    static HttpResponseMessage Good() => Response(new MemoryStream(Small));
    static async Task Recover(ApiClient api, FrameBuffer buffer)
    {
        await api.ScreenshotIntoAsync("fake", buffer);
        Check(buffer.Span.SequenceEqual(Small) && buffer.Metadata is not null, "Next screenshot did not recover");
    }
    static async Task StalledBody()
    {
        using var body = new Body(async (_, ct) => { await Task.Delay(Timeout.InfiniteTimeSpan, ct); return 0; });
        int requests = 0;
        using var api = new ApiClient("http://offline.invalid", new Handler((_, _) =>
            Task.FromResult(++requests == 2 ? Response(body, 100) : Good())));
        var buffer = new FrameBuffer(); await Recover(api, buffer);
        using var escape = new CancellationTokenSource(TimeSpan.FromSeconds(13));
        bool cancelled = false; var watch = Stopwatch.StartNew();
        try { await api.ScreenshotIntoAsync("fake", buffer, escape.Token); }
        catch (OperationCanceledException) { cancelled = true; }
        Console.WriteLine($"  stalled body ended after {watch.Elapsed.TotalMilliseconds:0} ms; caller cancelled={escape.IsCancellationRequested}");
        Check(cancelled && !escape.IsCancellationRequested, "Only the test escape cancelled the stalled body");
        Check(watch.Elapsed.TotalSeconds >= 7 && watch.Elapsed.TotalSeconds < 12, "Body did not use the eight-second deadline");
        Check(body.Disposed && buffer.Length == 0 && buffer.Metadata is null, "Failure kept old evidence or response alive");
        await Recover(api, buffer);
    }
    static async Task SharedDeadline()
    {
        bool delivered = false;
        using var body = new Body(async (memory, ct) => {
            if (delivered) return 0;
            await Task.Delay(TimeSpan.FromSeconds(6), ct); Small.CopyTo(memory); delivered = true; return Small.Length;
        });
        using var api = new ApiClient("http://offline.invalid", new Handler(async (_, ct) => {
            await Task.Delay(TimeSpan.FromSeconds(3), ct); return Response(body, Small.Length);
        }));
        using var escape = new CancellationTokenSource(TimeSpan.FromSeconds(13));
        bool cancelled = false; var watch = Stopwatch.StartNew(); var buffer = new FrameBuffer();
        try { await api.ScreenshotIntoAsync("fake", buffer, escape.Token); }
        catch (OperationCanceledException) { cancelled = true; }
        Console.WriteLine($"  headers/body ended after {watch.Elapsed.TotalMilliseconds:0} ms; body delivered={delivered}");
        Check(cancelled && !escape.IsCancellationRequested && !delivered, "Header completion reset or ended the request deadline");
        Check(body.Disposed && buffer.Length == 0 && buffer.Metadata is null, "Timed-out body retained evidence");
    }
    static async Task CallerCancellation()
    {
        var reading = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var body = new Body(async (_, ct) => { reading.TrySetResult(); await Task.Delay(Timeout.InfiniteTimeSpan, ct); return 0; });
        int requests = 0;
        using var api = new ApiClient("http://offline.invalid", new Handler((_, _) => Task.FromResult(++requests == 1 ? Response(body) : Good())));
        using var stop = new CancellationTokenSource(); var buffer = new FrameBuffer();
        var fetch = api.ScreenshotIntoAsync("fake", buffer, stop.Token);
        try { await reading.Task.WaitAsync(TimeSpan.FromSeconds(2)); }
        finally { stop.Cancel(); }
        bool cancelled = false;
        try { await fetch.WaitAsync(TimeSpan.FromSeconds(2)); } catch (OperationCanceledException) { cancelled = true; }
        Check(cancelled && body.Disposed && buffer.Length == 0 && buffer.Metadata is null, "Caller cancellation did not finish cleanly");
        await Recover(api, buffer);
    }
    static async Task UnknownLength()
    {
        int size = 3 * 1024 * 1024 + 13;
        using var body = Generated(size);
        using var api = new ApiClient("http://offline.invalid", new Handler((_, _) => Task.FromResult(Response(body))));
        var buffer = new FrameBuffer(); await api.ScreenshotIntoAsync("fake", buffer);
        Check(buffer.Length == size && buffer.Metadata is not null, "Unknown-length image not accepted");
        Check(body.Disposed && body.Bytes == size, "Image not read/disposed completely");
        for (int i = 0; i < size; i++) Check(buffer.Data[i] == Pixel(i), "Lost image prefix or bytes while growing at " + i);
    }
    static async Task AdvertisedLimit()
    {
        using var body = Generated(10);
        using var api = new ApiClient("http://offline.invalid", new Handler((_, _) => Task.FromResult(Response(body, Limit + 1L))));
        var buffer = new FrameBuffer(); bool refused = false;
        try { await api.ScreenshotIntoAsync("fake", buffer); } catch (ApiException) { refused = true; }
        Check(refused && body.Bytes == 0 && body.Disposed, "Oversized advertised body was read or accepted");
        Check(buffer.Length == 0 && buffer.Metadata is null, "Oversized response retained evidence");
    }
    static async Task UnadvertisedLimit()
    {
        using var body = Generated(Limit + 1024 * 1024);
        int requests = 0;
        using var api = new ApiClient("http://offline.invalid", new Handler((_, _) => Task.FromResult(++requests == 1 ? Response(body) : Good())));
        var buffer = new FrameBuffer(); bool refused = false;
        try { await api.ScreenshotIntoAsync("fake", buffer); } catch (ApiException) { refused = true; }
        Check(refused && body.Bytes <= Limit + 1 && buffer.Data.Length <= Limit, "Unknown-size body bypassed the bounded read");
        Check(body.Disposed && buffer.Length == 0 && buffer.Metadata is null, "Oversized partial body retained evidence");
        await Recover(api, buffer);
    }
    static async Task BodyFailure()
    {
        int reads = 0;
        using var body = new Body((memory, _) => {
            if (++reads > 1) throw new IOException("synthetic body failure");
            Small.CopyTo(memory); return ValueTask.FromResult(Small.Length);
        });
        using var api = new ApiClient("http://offline.invalid", new Handler((_, _) => Task.FromResult(Response(body))));
        var buffer = new FrameBuffer(); bool failed = false;
        try { await api.ScreenshotIntoAsync("fake", buffer); } catch (IOException) { failed = true; }
        Check(failed && body.Disposed && buffer.Length == 0 && buffer.Metadata is null, "Partial failed frame remained publishable");
    }
    static async Task ExactLimit()
    {
        using var body = Generated(Limit);
        using var api = new ApiClient("http://offline.invalid", new Handler((_, _) => Task.FromResult(Response(body))));
        var buffer = new FrameBuffer(); await api.ScreenshotIntoAsync("fake", buffer);
        Check(buffer.Length == Limit && buffer.Data.Length <= Limit && buffer.Metadata is not null, "Exact limit rejected or grew beyond limit");
        Check(buffer.Data[0] == 'B' && buffer.Data[^1] == Pixel(Limit - 1) && body.Disposed, "Exact-limit bytes not preserved");
    }
    // The request line the former loopback socket probe pinned, checked at the handler instead.
    static async Task RequestLine()
    {
        var seen = new List<string>();
        using var api = new ApiClient("http://offline.invalid", new Handler((request, _) =>
        {
            seen.Add(request.Method + " " + request.RequestUri!.PathAndQuery);
            return Task.FromResult(Good());
        }));
        await api.ScreenshotIntoAsync("synthetic phone/1", new FrameBuffer());
        Check(seen.SequenceEqual(new[] { "GET /api/pic/screenshot?id=synthetic%20phone%2F1&binary=true" }), "Unexpected screenshot request: " + string.Join(" | ", seen));
    }
    static byte Pixel(long position) => position == 0 ? (byte)'B' : position == 1 ? (byte)'M' : (byte)(position % 251);
    static Body Generated(int size)
    {
        long at = 0;
        return new Body((memory, ct) => {
            ct.ThrowIfCancellationRequested();
            int count = (int)Math.Min(Math.Min(65536, memory.Length), size - at);
            for (int i = 0; i < count; i++) memory.Span[i] = Pixel(at + i);
            at += count; return ValueTask.FromResult(count);
        });
    }
    sealed class Handler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> reply) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            if (request.Method != HttpMethod.Get || request.RequestUri?.AbsolutePath != "/api/pic/screenshot")
                throw new InvalidOperationException("Only synthetic screenshot GETs are allowed");
            return reply(request, ct);
        }
    }
    sealed class Body(Func<Memory<byte>, CancellationToken, ValueTask<int>> read) : Stream
    {
        public bool Disposed { get; private set; }
        public long Bytes { get; private set; }
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
        { int count = await read(buffer, ct); Bytes += count; return count; }
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        protected override void Dispose(bool disposing) { Disposed = true; base.Dispose(disposing); }
    }
}
