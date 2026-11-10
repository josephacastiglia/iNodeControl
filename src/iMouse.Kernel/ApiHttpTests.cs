using System.Collections.Concurrent;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;

namespace IMouse2.Kernel;

/// <summary>
/// The API as a client meets it: a real HttpListener in this process on an unused loopback port,
/// with a recording HID transport and a synthetic frame. Never a port a live kernel uses.
/// </summary>
internal static class ApiHttpTests
{
    private sealed class Board : IHidTransport
    {
        public readonly ConcurrentQueue<string> Reports = new();
        public Task SendAsync(byte[] data, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested(); Reports.Enqueue(Convert.ToHexString(data)); return Task.CompletedTask;
        }
        public void Dispose() { }
    }

    /// <summary>A loopback port nothing is listening on, and never one the product uses.</summary>
    internal static int UnusedLoopbackPort()
    {
        while (true)
        {
            var probe = new TcpListener(IPAddress.Loopback, 0); probe.Start();
            int port = ((IPEndPoint)probe.LocalEndpoint).Port; probe.Stop();
            if (port is not (9911 or 9913 or 9915 or 9916 or 9926)) return port;
        }
    }

    private sealed record Answer(int Http, JsonElement Data, string[] Headers, string ContentType, byte[] Bytes)
    {
        public int Code => Data.ValueKind == JsonValueKind.Object && Data.TryGetProperty("code", out var c) ? c.GetInt32() : -1;
    }

    public static async Task RunAsync(Action<bool, string> check)
    {
        var board = new Board();
        var store = new DeviceStore([new Phone { deviceid = "one", pid = "C24C", uid = "A" }]);
        using var input = new InputRouter(store, ["C24C"], [new PointerCalibration("C24C", 500, 1080, 14, 14, 5, 5)], _ => board);
        using var frames = new FrameStore("api-http-tests-never-opened", "one");
        string root = "http://127.0.0.1:" + UnusedLoopbackPort() + "/api/";
        using var stop = new CancellationTokenSource();
        using var server = new ApiServer(root, store, input, [("Test receiver", frames)]);
        var listening = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var run = server.RunAsync(stop.Token, () => listening.TrySetResult());
        await await Task.WhenAny(listening.Task, run);
        using var http = new HttpClient(new SocketsHttpHandler { UseProxy = false, AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(10) };
        var seenHeaders = new List<string>();

        // A transport failure (the listener dropped the connection) is reported as Http 0.
        async Task<Answer> Send(HttpMethod method, string path, string? body = null, string? contentType = "application/json",
            string? origin = null, bool chunked = false, (string Name, string Value)? extra = null)
        {
            using var request = new HttpRequestMessage(method, root + path);
            if (origin is not null) request.Headers.TryAddWithoutValidation("Origin", origin);
            if (extra is { } header) request.Headers.TryAddWithoutValidation(header.Name, header.Value);
            if (body is not null)
            {
                var content = new ByteArrayContent(Encoding.UTF8.GetBytes(body));
                if (contentType is not null) content.Headers.TryAddWithoutValidation("Content-Type", contentType);
                request.Content = content;
                if (chunked) request.Headers.TransferEncodingChunked = true;
            }
            try
            {
                using var response = await http.SendAsync(request);
                byte[] bytes = await response.Content.ReadAsByteArrayAsync();
                var names = response.Headers.Concat(response.Content.Headers).Select(h => h.Key).ToArray();
                lock (seenHeaders) seenHeaders.AddRange(names);
                string type = response.Content.Headers.ContentType?.MediaType ?? "";
                JsonElement data = default;
                if (type == "application/json")
                    using (var doc = JsonDocument.Parse(bytes))
                        data = doc.RootElement.TryGetProperty("data", out var d) ? d.Clone() : default;
                return new((int)response.StatusCode, data, names, type, bytes);
            }
            catch (HttpRequestException) { return new(0, default, [], "", []); }
        }
        static string Call(string fun, object data) => JsonSerializer.Serialize(new { fun, data });
        async Task<JsonElement> Phone()
            => (await Send(HttpMethod.Get, "input/status")).Data.GetProperty("phones").EnumerateArray().Single(p => p.GetProperty("id").GetString() == "one");
        async Task<bool> Untouched() => !(await Phone()).GetProperty("owned").GetBoolean() && board.Reports.IsEmpty;
        string acquire = Call("/input/acquire", new { id = "one" });

        try
        {
            // What every real client sends still works, end to end.
            var status = await Send(HttpMethod.Get, "kernel/status");
            check(status is { Http: 200, Code: 0, ContentType: "application/json" } && status.Data.GetProperty("input_leases_required").GetBoolean(),
                "A plain GET is answered over HTTP");

            // --- A web page must not be able to drive a phone -------------------------------------
            // Browsers attach Origin to every cross-site POST, whatever its content type, and to every
            // scripted cross-site request. No client of this API is a web page.
            foreach (string origin in new[] { "http://evil.example", "null", "http://127.0.0.1:9915", "http://localhost" })
            {
                var refused = await Send(HttpMethod.Post, "", acquire, origin: origin);
                check(refused is { Http: 403, Code: 403 } && await Untouched(), "A POST with Origin " + origin + " is refused with 403 and acquires nothing");
            }
            var formPost = await Send(HttpMethod.Post, "", acquire, contentType: "text/plain", origin: "http://evil.example");
            check(formPost.Http == 403 && await Untouched(), "A cross-site form POST (text/plain with Origin) is refused");
            var scriptedGet = await Send(HttpMethod.Get, "device/get", origin: "http://evil.example");
            check(scriptedGet is { Http: 403, Code: 403 }, "A GET with an Origin header is refused too");
            var preflight = await Send(HttpMethod.Options, "", origin: "http://evil.example", extra: ("Access-Control-Request-Method", "POST"));
            check(preflight.Http == 403, "A CORS preflight is refused, so no page is ever told it may send");

            // --- Bodies: JSON only, and bounded ---------------------------------------------------
            foreach (string? type in new[] { "text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "application/jsonp", null })
            {
                var refused = await Send(HttpMethod.Post, "", acquire, contentType: type);
                check(refused is { Http: 415, Code: 415 } && await Untouched(), "A POST sent as " + (type ?? "no content type") + " is refused with 415 and acquires nothing");
            }
            string padded = Call("/input/acquire", new { id = "one", pad = new string('x', ApiServer.MaxBodyBytes) });
            var tooLong = await Send(HttpMethod.Post, "", padded);
            check(tooLong.Http is 413 or 0 && await Untouched(), "A body over the size cap is refused and acquires nothing");
            var tooLongChunked = await Send(HttpMethod.Post, "", padded, chunked: true);
            check(tooLongChunked.Http is 413 or 0 && await Untouched(), "A chunked body over the size cap is refused and acquires nothing");
            check(ApiServer.MaxBodyBytes == 64 * 1024, "The body cap is 64 KiB, far above any real request");

            // --- The same requests from a real client ---------------------------------------------
            string atCap = acquire + new string(' ', ApiServer.MaxBodyBytes - Encoding.UTF8.GetByteCount(acquire));
            var leased = await Send(HttpMethod.Post, "", atCap, contentType: "application/json; charset=utf-8");
            check(leased is { Http: 200, Code: 0 }, "A JSON body of exactly the cap, sent as application/json with a charset, is accepted");
            string token = leased.Data.GetProperty("leases")[0].GetProperty("token").GetString()!;
            var key = await Send(HttpMethod.Post, "", Call("/key/sendkey", new { id = "one", token, fn_key = "Enter" }));
            check(key is { Http: 200, Code: 0 } && board.Reports.SequenceEqual(new[] { "A200000000000000", "A200280000000000", "A200000000000000" }),
                "A leased key command sent over HTTP writes exactly its reports");
            var chunkedOk = await Send(HttpMethod.Post, "", Call("/input/renew", new { id = "one", token }), chunked: true);
            check(chunkedOk is { Http: 200, Code: 0 }, "A small chunked JSON body is accepted");
            var release = await Send(HttpMethod.Post, "", Call("/input/release", new { id = "one", token }));
            check(release is { Http: 200, Code: 0 } && !(await Phone()).GetProperty("owned").GetBoolean(), "The lease is released over HTTP");
            var unknown = await Send(HttpMethod.Post, "", Call("/no/such", new { }));
            check(unknown is { Http: 200, Code: 41 }, "An unknown function is answered as not implemented");
            var broken = await Send(HttpMethod.Post, "", "{not json");
            check(broken is { Http: 200, Code: 36 }, "A malformed JSON body is answered as invalid");

            // --- Screenshots over HTTP ------------------------------------------------------------
            var noPhone = await Send(HttpMethod.Get, "pic/screenshot?id=nobody&binary=true");
            check(noPhone is { Http: 200, Code: 1 }, "A screenshot of an unknown phone is answered as not found");
            var noFrame = await Send(HttpMethod.Get, "pic/screenshot?id=one&binary=true");
            check(noFrame is { Http: 200, Code: 25 }, "A screenshot before any frame is answered as no frame, not as a picture");
            using var feed = new FrameStoreTests.Feed(); using var reading = new CancellationTokenSource();
            var reader = frames.ReadConnectionAsync(feed, reading.Token);
            byte[] bmp = FrameStoreTests.Bmp(); feed.Put(FrameStoreTests.Packet(bmp));
            for (int i = 0; i < 2000 && frames.Frames < 1; i++) await Task.Delay(1);
            var picture = await Send(HttpMethod.Get, "pic/screenshot?id=one&binary=true");
            check(picture is { Http: 200, ContentType: "image/bmp" } && picture.Bytes.AsSpan().SequenceEqual(bmp)
                && picture.Headers.Contains("X-iMouse-Frame-Sequence") && picture.Headers.Contains("X-iMouse-Frame-Session")
                && picture.Headers.Contains("X-iMouse-Frame-Age-Ms") && picture.Headers.Contains("Cache-Control"),
                "A screenshot is the frame's exact bytes as image/bmp with its delivery headers");
            var pictureFromPage = await Send(HttpMethod.Get, "pic/screenshot?id=one&binary=true", origin: "http://evil.example");
            check(pictureFromPage.Http == 403 && pictureFromPage.ContentType != "image/bmp", "A page's scripted request for a screenshot gets no picture");
            reading.Cancel(); await reader;

            string[] cors; lock (seenHeaders) cors = seenHeaders.Where(h => h.StartsWith("Access-Control-", StringComparison.OrdinalIgnoreCase)).ToArray();
            check(cors.Length == 0 && seenHeaders.Count > 0, "No answer, accepted or refused, carries an Access-Control header");
        }
        finally
        {
            stop.Cancel();
            try { await run; } catch (OperationCanceledException) { }
        }
    }
}
