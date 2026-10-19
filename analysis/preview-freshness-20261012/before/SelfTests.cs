using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace IMouse2;

public sealed class TestHandler : HttpMessageHandler
{
    public List<JsonElement> Commands { get; } = [];
    public int PostAttempts { get; private set; }
    public int ErrorCode { get; set; }
    public bool BrokenJson { get; set; }
    public bool Base64Image { get; set; }
    public bool EmptyList { get; set; }
    public bool FailHttp { get; set; }
    public int DelayMs { get; set; }

    // --- Ownership protocol simulation ---
    public bool OwnershipSupported { get; set; }
    public Dictionary<string, string> ActiveLeases { get; } = new();
    public HashSet<string> ExpiredLeases { get; } = new();
    public HashSet<string> StoppedPhones { get; } = new();
    public Dictionary<string, long> PhoneGenerations { get; } = new();
    public bool FailAcquire { get; set; }
    public string? FailAcquirePhone { get; set; }
    public int TokenCounter { get; private set; }

    public void ExpireLease(string id)
    {
        ActiveLeases.Remove(id);
        ExpiredLeases.Add(id);
    }
    public const string Fixture = """
    {"status":200,"data":{"code":0,"list":[
      {"deviceid":"TEST:01","name":"Test phone 01","device_name":"iPhone XR","gname":"Test devices","state":1,"width":"414","height":"896","imgw":500,"imgh":1080,"air_pid":4321,"version":"18.0","uid":"TEST-BOARD-01","receiver_name":"iMouse2-C24C"},
      {"deviceid":"TEST:02","name":"Test phone 02","device_name":"iPhone 12 Pro","gname":"Test devices","state":0,"width":390,"height":844,"version":"18.0"},
      {"deviceid":"TEST:03","name":"Test phone 03","device_name":"iPhone XR","gname":"Spare devices","state":0,"width":414,"height":896,"version":"18.0"},
      {"deviceid":"TEST:04","name":"Test phone 04","device_name":"iPhone XR","gname":"Test devices","state":1,"width":"414","height":"896","imgw":500,"imgh":1080,"air_pid":4322,"version":"18.0","uid":"TEST-BOARD-04","receiver_name":"iMouse2-C241"},
      {"deviceid":"TEST:05","name":"Test phone 05","device_name":"iPhone SE","gname":"Test devices","state":1,"width":"375","height":"667","imgw":375,"imgh":812,"air_pid":4323,"version":"18.0","uid":"TEST-BOARD-05"}]}}
    """;
    public const string Boards = """
    {"status":200,"data":{"code":0,"list":[
      {"vid":"720A","pid":"B001","uid":"TEST-BOARD-01","ver":"c.n","state":2},
      {"vid":"720A","pid":"B002","uid":"TEST-BOARD-02","ver":"c.n","state":1},
      {"vid":"720A","pid":"B004","uid":"TEST-BOARD-04","ver":"c.n","state":2},
      {"vid":"720A","pid":"B005","uid":"TEST-BOARD-05","ver":"c.n","state":2}]}}
    """;
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
    {
        if (request.Method == HttpMethod.Post) PostAttempts++;
        if (DelayMs > 0) await Task.Delay(DelayMs, ct);
        if (FailHttp) return new(HttpStatusCode.ServiceUnavailable) { Content = new StringContent("Unavailable") };
        if (BrokenJson) return Json("<html>not the iMouse API</html>");
        if (ErrorCode != 0) return Json(JsonSerializer.Serialize(new { status = 200, data = new { code = ErrorCode, message = "Test service error" } }));
        if (request.Method == HttpMethod.Post)
        {
            using var d = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
            var root = d.RootElement.Clone();
            Commands.Add(root);
            string fun = root.TryGetProperty("fun", out var funProp) ? funProp.GetString() ?? "" : "";
            var data = root.TryGetProperty("data", out var dataProp) ? dataProp : default;

            if (fun == "/input/acquire")
            {
                string idStr = data.TryGetProperty("id", out var idProp) ? idProp.GetString() ?? "" : "";
                var ids = idStr.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
                if (FailAcquire || ids.Any(id => id == FailAcquirePhone || StoppedPhones.Contains(id)))
                {
                    return Json(JsonSerializer.Serialize(new { status = 200, data = new { code = 409, message = "Ownership conflict or stopped" } }));
                }
                var leases = new List<object>();
                foreach (var id in ids)
                {
                    var token = $"MOCK-TOKEN-{++TokenCounter}-{id}";
                    ActiveLeases[id] = token;
                    ExpiredLeases.Remove(id);
                    leases.Add(new { id, token, lease_ms = 30000 });
                }
                return Json(JsonSerializer.Serialize(new { status = 200, data = new { code = 0, leases } }));
            }
            if (fun == "/input/renew")
            {
                string id = data.TryGetProperty("id", out var idProp) ? idProp.GetString() ?? "" : "";
                string token = data.TryGetProperty("token", out var tokProp) ? tokProp.GetString() ?? "" : "";
                if (ExpiredLeases.Contains(id) || !ActiveLeases.TryGetValue(id, out var active) || active != token || StoppedPhones.Contains(id))
                {
                    return Json(JsonSerializer.Serialize(new { status = 200, data = new { code = 409, message = "Expired or invalid token" } }));
                }
                return Json("{\"status\":200,\"data\":{\"code\":0}}");
            }
            if (fun == "/input/release")
            {
                string idStr = data.TryGetProperty("id", out var idProp) ? idProp.GetString() ?? "" : "";
                var ids = idStr.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
                if (data.TryGetProperty("token", out var tokProp))
                {
                    string token = tokProp.GetString() ?? "";
                    foreach (var id in ids)
                    {
                        if (ActiveLeases.TryGetValue(id, out var active) && active == token)
                            ActiveLeases.Remove(id);
                    }
                }
                else if (data.TryGetProperty("tokens", out var mapProp) && mapProp.ValueKind == JsonValueKind.Object)
                {
                    foreach (var id in ids)
                    {
                        if (mapProp.TryGetProperty(id, out var t) && ActiveLeases.TryGetValue(id, out var active) && active == t.GetString())
                            ActiveLeases.Remove(id);
                    }
                }
                else
                {
                    foreach (var id in ids) ActiveLeases.Remove(id);
                }
                return Json("{\"status\":200,\"data\":{\"code\":0}}");
            }
            if (fun == "/input/stop")
            {
                string idStr = data.TryGetProperty("id", out var idProp) ? idProp.GetString() ?? "" : "";
                var ids = idStr.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
                foreach (var id in ids)
                {
                    ActiveLeases.Remove(id);
                    StoppedPhones.Add(id);
                    PhoneGenerations[id] = PhoneGenerations.GetValueOrDefault(id, 1) + 1;
                }
                return Json("{\"status\":200,\"data\":{\"code\":0}}");
            }
            if (fun == "/input/status")
            {
                var phones = new[] { "TEST:01", "TEST:02", "TEST:03", "TEST:04", "TEST:05" }
                    .Select(id => new
                    {
                        id,
                        owned = ActiveLeases.ContainsKey(id),
                        stopped = StoppedPhones.Contains(id),
                        generation = PhoneGenerations.GetValueOrDefault(id, 1)
                    });
                return Json(JsonSerializer.Serialize(new { status = 200, data = new { code = 0, phones } }));
            }
            if (fun == "/input/resume")
            {
                string idStr = data.TryGetProperty("id", out var idProp) ? idProp.GetString() ?? "" : "";
                var ids = idStr.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
                if (data.TryGetProperty("expected_generations", out var genProp) && genProp.ValueKind == JsonValueKind.Object)
                {
                    foreach (var id in ids)
                    {
                        if (genProp.TryGetProperty(id, out var g) && g.GetInt64() != PhoneGenerations.GetValueOrDefault(id, 1))
                            return Json(JsonSerializer.Serialize(new { status = 200, data = new { code = 409, message = "Generation mismatch" } }));
                    }
                }
                foreach (var id in ids)
                {
                    StoppedPhones.Remove(id);
                    PhoneGenerations[id] = PhoneGenerations.GetValueOrDefault(id, 1) + 1;
                }
                return Json("{\"status\":200,\"data\":{\"code\":0}}");
            }
            if (OwnershipSupported && (fun.StartsWith("/mouse/") || fun == "/key/sendkey"))
            {
                string idStr = data.TryGetProperty("id", out var idProp) ? idProp.GetString() ?? "" : "";
                var ids = idStr.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
                if (ids.Length == 0) return Json(JsonSerializer.Serialize(new { status = 200, data = new { code = 36, message = "No target" } }));
                if (data.TryGetProperty("tokens", out var tokensProp) && tokensProp.ValueKind == JsonValueKind.Object)
                {
                    foreach (var id in ids)
                    {
                        if (StoppedPhones.Contains(id) || ExpiredLeases.Contains(id) ||
                            !tokensProp.TryGetProperty(id, out var t) ||
                            !ActiveLeases.TryGetValue(id, out var active) || active != t.GetString())
                        {
                            return Json(JsonSerializer.Serialize(new { status = 200, data = new { code = 409, message = "Ownership conflict or stopped" } }));
                        }
                    }
                }
                else if (data.TryGetProperty("token", out var tokProp))
                {
                    string token = tokProp.GetString() ?? "";
                    foreach (var id in ids)
                    {
                        if (StoppedPhones.Contains(id) || ExpiredLeases.Contains(id) ||
                            !ActiveLeases.TryGetValue(id, out var active) || active != token)
                        {
                            return Json(JsonSerializer.Serialize(new { status = 200, data = new { code = 409, message = "Ownership conflict or stopped" } }));
                        }
                    }
                }
                else
                {
                    return Json(JsonSerializer.Serialize(new { status = 200, data = new { code = 409, message = "Input lease token required" } }));
                }
            }

            return Json("{\"status\":200,\"data\":{\"code\":0}}");
        }
        if (request.RequestUri!.AbsolutePath.EndsWith("/kernel/status"))
        {
            if (!OwnershipSupported) return new(HttpStatusCode.NotFound);
            return Json("{\"status\":200,\"data\":{\"code\":0,\"input_protocol\":1,\"input_leases_required\":true}}");
        }
        if (request.RequestUri!.AbsolutePath.EndsWith("/device/get")) return Json(EmptyList ? "{\"status\":200,\"data\":{\"code\":0,\"list\":[]}}" : Fixture);
        if (request.RequestUri.AbsolutePath.EndsWith("/config/usb/get")) return Json(Boards);
        if (request.RequestUri.AbsolutePath.EndsWith("/config/imserver/get"))
            return Json("{\"status\":200,\"data\":{\"code\":0,\"air_play_name\":\"iMouse2-C214\"}}");
        if (request.RequestUri.AbsolutePath.EndsWith("/pic/screenshot"))
        {
            byte[] png = TestImage();
            return Base64Image ? Json(JsonSerializer.Serialize(new { status = 200, data = new { code = 0, image = Convert.ToBase64String(png) } })) : new(HttpStatusCode.OK) { Content = new ByteArrayContent(png) };
        }
        return new(HttpStatusCode.NotFound);
    }
    private static HttpResponseMessage Json(string text) => new(HttpStatusCode.OK) { Content = new StringContent(text, Encoding.UTF8, "application/json") };
    private static byte[] TestImage()
    {
        var visual = new DrawingVisual();
        using (var d = visual.RenderOpen())
        {
            d.DrawRectangle(new SolidColorBrush(Color.FromRgb(20, 49, 63)), null, new Rect(0, 0, 414, 896));
            d.DrawRoundedRectangle(new SolidColorBrush(Color.FromRgb(54, 99, 108)), null, new Rect(26, 170, 362, 260), 25, 25);
            var font = new Typeface("Segoe UI");
            d.DrawText(new FormattedText("09:41", System.Globalization.CultureInfo.InvariantCulture, FlowDirection.LeftToRight, font, 64, Brushes.White, 1), new Point(112, 62));
            d.DrawText(new FormattedText("PREVIEW TEST", System.Globalization.CultureInfo.InvariantCulture, FlowDirection.LeftToRight, font, 25, Brushes.White, 1), new Point(113, 226));
            d.DrawText(new FormattedText("Synthetic screen image\nNo phone actions sent", System.Globalization.CultureInfo.InvariantCulture, FlowDirection.LeftToRight, font, 20, Brushes.White, 1), new Point(87, 286));
            for (int i = 0; i < 8; i++) d.DrawRoundedRectangle(new SolidColorBrush(Color.FromRgb((byte)(80 + i * 10), 156, 158)), null, new Rect(28 + (i % 4) * 96, 474 + (i / 4) * 104, 68, 68), 16, 16);
            d.DrawRoundedRectangle(Brushes.White, null, new Rect(140, 866, 134, 5), 3, 3);
        }
        var bitmap = new RenderTargetBitmap(414, 896, 96, 96, PixelFormats.Pbgra32); bitmap.Render(visual);
        // BMP, not PNG: binary=true on the real service returns an uncompressed DIB, and
        // the fast decode path only accepts that. The fixture must match the real shape.
        var opaque = new FormatConvertedBitmap(bitmap, PixelFormats.Bgr24, null, 0);
        var encoder = new BmpBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(opaque)); using var stream = new MemoryStream(); encoder.Save(stream); return stream.ToArray();
    }
}

public static class SelfTests
{
    public static async Task RunAsync()
    {
        var passed = new List<string>();
        void Check(string name, bool ok) { if (!ok) throw new Exception("Failed: " + name); passed.Add(name); }
        async Task Reject(string name, Func<Task> action) { try { await action(); } catch (Exception ex) when (ex is ApiException or HttpRequestException or OperationCanceledException or ArgumentException) { passed.Add(name); return; } throw new Exception("Expected failure: " + name); }
        Check("Default service endpoint", ApiClient.NormalizeEndpoint("localhost").ToString() == "http://localhost:9911/api");
        Check("Explicit custom port", ApiClient.NormalizeEndpoint("http://localhost:1234/api").Port == 1234);
        Check("Explicit standard port retained", ApiClient.NormalizeEndpoint("http://localhost:80").Port == 80);
        await Reject("Reject credentials in endpoint", () => { ApiClient.NormalizeEndpoint("http://name:secret@localhost"); return Task.CompletedTask; });
        await Reject("Reject unrelated URL path", () => { ApiClient.NormalizeEndpoint("http://localhost/other"); return Task.CompletedTask; });
        Check("Center coordinate uses phone logical size", CoordinateMapper.Map(200, 400, 400, 800, 500, 1000, 390, 780) == (195, 390));
        Check("Horizontal letterbox ignored", CoordinateMapper.Map(10, 300, 600, 600, 500, 1000, 390, 780) == null);
        Check("Letterboxed center correct", CoordinateMapper.Map(300, 300, 600, 600, 500, 1000, 390, 780) == (195, 390));
        Check("Vertical letterbox ignored", CoordinateMapper.Map(300, 20, 600, 600, 1000, 500, 780, 390) == null);
        Check("Invalid dimensions block pointer input", CoordinateMapper.Map(1, 1, 0, 600, 500, 1000, 390, 780) == null);
        Check("Right boundary excluded", CoordinateMapper.Map(400, 200, 400, 800, 500, 1000, 390, 780) == null);
        Check("Bottom-right coordinate bounded", CoordinateMapper.Map(399.9, 799.9, 400, 800, 500, 1000, 390, 780) == (389, 779));
        var handler = new TestHandler(); using var api = new ApiClient("localhost", handler);
        var devices = await api.DevicesAsync();
        Check("Parse fixture device count", devices.Count == 5);
        Check("Respect offline state", devices.Count(d => d.Online) == 3);
        Check("Accept numeric and string dimensions", devices[0].Width == 414 && devices[1].Width == 390);
        Check("Group and binding parsed", devices[0].Group == "Test devices" && devices[0].Hardware == "TEST-BOARD-01");
        Check("Binary screenshot accepted", ApiClient.IsImage(await api.ScreenshotAsync("TEST:01")));
        handler.Base64Image = true;
        Check("Base64 screenshot accepted", ApiClient.IsImage(await api.ScreenshotAsync("TEST:01")));
        await api.CommandAsync("/key/sendkey", new() { ["id"] = "TEST:01", ["key"] = "a\"b\\c" });
        Check("Command JSON correctly escapes typed text", handler.Commands[0].GetProperty("data").GetProperty("key").GetString() == "a\"b\\c");
        Check("Command target explicit", handler.Commands[0].GetProperty("data").GetProperty("id").GetString() == "TEST:01");
        handler.ErrorCode = 25;
        await Reject("HTTP 200 with operation failure rejected", () => api.DevicesAsync());
        await Reject("Screenshot JSON error not treated as image", () => api.ScreenshotAsync("TEST:01"));
        handler.ErrorCode = 0; handler.BrokenJson = true;
        await Reject("Malformed response rejected", () => api.DevicesAsync());
        handler.BrokenJson = false; handler.FailHttp = true;
        await Reject("HTTP errors rejected", () => api.DevicesAsync());
        handler.FailHttp = false; handler.EmptyList = true;
        Check("Empty list is valid", (await api.DevicesAsync()).Count == 0);
        handler.DelayMs = 1000;
        using var cts = new CancellationTokenSource(20);
        await Reject("Cancellation stops outstanding requests", () => api.DevicesAsync(cts.Token));
        handler.DelayMs = 0; handler.EmptyList = false;
        var boards = await api.BoardsAsync();
        Check("Board list parsed", boards.Count == 4);
        Check("Board state 2 means a phone is attached", boards[0].PhoneAttached && !boards[1].PhoneAttached);
        var withBoard = (await api.DevicesAsync())[0];
        Check("Mirror geometry parsed separately from logical size", withBoard.ImageWidth == 500 && withBoard.ImageHeight == 1080 && withBoard.Width == 414);
        Check("AirPlay session id parsed", withBoard.AirPid == 4321);
        withBoard.BoardState = 2;
        Check("Both channels ready reports control and video", withBoard.ControlReady && withBoard.VideoReady);
        withBoard.BoardState = 1;
        Check("Board without phone is not controllable while still mirroring", !withBoard.ControlReady && withBoard.VideoReady);
        Check("Channel summary states both channels", withBoard.ChannelSummary.Contains("No phone on board") && withBoard.ChannelSummary.Contains("Mirroring"));
        Check("Restarting receiver is labelled for the operator",
            Device.FromJson(JsonDocument.Parse("""{"deviceid":"x","state":0,"video_state":"restarting"}""").RootElement).VideoStatus == "Receiver restarting");
        Check("Per-phone receiver name is parsed",
            Device.FromJson(JsonDocument.Parse("""{"deviceid":"x","state":1,"receiver_name":"iMouse2-C241"}""").RootElement).ReceiverName == "iMouse2-C241");

        var frame = new LiveFrame();
        Check("Non-image payload rejected by decoder", frame.Prepare(new byte[] { 1, 2, 3 }) is null);
        Check("Truncated BMP rejected", frame.Prepare(Bmp(4, 3, true)[..40]) is null);
        var up = frame.Prepare(Bmp(4, 3, true));
        Check("Bottom-up BMP decoded", up is { Width: 4, Height: 3 });
        Check("Top-down BMP decoded", frame.Prepare(Bmp(4, 3, false)) is { Width: 4, Height: 3 });
        Check("Prepared frame is drawable", frame.Present(up!) && frame.Width == 4 && frame.Height == 3);
        Check("Decoder reuses one bitmap across frames", ReferenceEquals(frame.Source, Reuse(frame)));
        Check("Bottom-up rows are flipped to top-down", TopLeftIsMarker(frame));

        // Buffers must be recycled: allocating 1.6 MB per frame at 30 fps would hand the
        // collector 45 MB/s, which shows up as periodic hitching in the live view.
        var first = frame.Prepare(Bmp(64, 64, true))!;
        var firstBuffer = first.Pixels;
        frame.Recycle(first);
        Check("Frame buffers are pooled, not reallocated", ReferenceEquals(frame.Prepare(Bmp(64, 64, true))!.Pixels, firstBuffer));

        // Repeat detection is what stops the UI redrawing frames the mirror never changed.
        var sample = Bmp(64, 64, true);
        var copy = (byte[])sample.Clone();
        Check("Identical frames are recognised", LiveFrame.SameAsPrevious(sample, copy));
        copy[54 + 3 * 40] ^= 0xFF;
        Check("A single changed pixel defeats repeat detection", !LiveFrame.SameAsPrevious(sample, copy));
        Check("Different-sized frames are never treated as equal", !LiveFrame.SameAsPrevious(sample, Bmp(32, 32, true)));
        Check("No previous frame counts as changed", !LiveFrame.SameAsPrevious(null, sample));

        // Auto-bind depends on this telling a moved pointer apart from an unchanged screen.
        var blank = Bmp(64, 64, true);
        var dotted = (byte[])blank.Clone();
        int stride64 = (64 * 3 + 3) & ~3;
        for (int y = 30; y < 34; y++)
            for (int x = 30; x < 34; x++)
            { int i = 54 + y * stride64 + x * 3; dotted[i] = dotted[i + 1] = dotted[i + 2] = 255; }
        Check("Region diff sees a local change", FrameRegion.MeanDifference(blank, dotted, 32, 32, 6) > 1.0);
        Check("Region diff ignores an untouched area", FrameRegion.MeanDifference(blank, dotted, 8, 8, 4) == 0);
        Check("Image-space taps map to mirror pixels", CoordinateMapper.Map(200, 400, 400, 800, 500, 1000, 500, 1000) == (250, 500));

        // Enlarging the master view must not move where a tap lands. The wall layout lets
        // the operator resize the master with a splitter, so the same point on the phone
        // has to map to the same image pixel at every display size.
        var atSmall  = CoordinateMapper.Map(125, 270, 250, 540, 500, 1080, 500, 1080);
        var atMedium = CoordinateMapper.Map(250, 540, 500, 1080, 500, 1080, 500, 1080);
        var atLarge  = CoordinateMapper.Map(500, 1080, 1000, 2160, 500, 1080, 500, 1080);
        Check("Tap mapping is identical at every master size", atSmall == atMedium && atMedium == atLarge);
        Check("Centre of the view maps to centre of the phone", atMedium == (250, 540));

        // Same again with the view letterboxed - a wide panel around a tall phone.
        var wideSmall = CoordinateMapper.Map(300, 150, 400, 300, 500, 1080, 500, 1080);
        var wideLarge = CoordinateMapper.Map(600, 300, 800, 600, 500, 1080, 500, 1080);
        Check("Letterboxed mapping is size-invariant too", wideSmall == wideLarge);

        // A quarter-point, to catch any off-by-scale rather than only the exact centre.
        var q1 = CoordinateMapper.Map(62.5, 135, 250, 540, 500, 1080, 500, 1080);
        var q2 = CoordinateMapper.Map(250, 540, 1000, 2160, 500, 1080, 500, 1080);
        Check("Quarter point maps the same at 4x scale", q1 == q2 && q1 == (125, 270));

        // --- reusable receive buffers ---
        // Every frame is ~1.6 MB, over the large-object threshold, so allocating one per
        // fetch made every frame a large-object allocation: measured at 488 MB/s and 496
        // gen-2 collections in eight seconds with a single phone on screen.
        var reuse = new FrameBuffer();
        var firstArray = reuse.Data;
        await api.ScreenshotIntoAsync("TEST:01", false, reuse);
        Check("Pooled fetch fills the buffer with an image", ApiClient.IsImage(reuse.Span));
        Check("Pooled fetch records the real length", reuse.Length > 8 && reuse.Length <= reuse.Data.Length);
        int firstLength = reuse.Length;
        await api.ScreenshotIntoAsync("TEST:01", false, reuse);
        Check("A second fetch reuses the same array", ReferenceEquals(reuse.Data, firstArray));
        Check("A second fetch does not leave stale length behind", reuse.Length == firstLength);
        handler.Base64Image = true;
        await api.ScreenshotIntoAsync("TEST:01", false, reuse);
        Check("Pooled fetch still handles a base64 JSON reply", ApiClient.IsImage(reuse.Span));
        handler.Base64Image = false;
        handler.ErrorCode = 25;
        await Reject("Pooled fetch rejects a service error", () => api.ScreenshotIntoAsync("TEST:01", false, reuse));
        handler.ErrorCode = 0;

        var grow = new FrameBuffer();
        grow.Data[0] = 7; grow.Data[1] = 9; grow.Length = 2;
        int before = grow.Data.Length;
        grow.Ensure(before + 1000);
        Check("Growing the buffer keeps what was already in it",
            grow.Data.Length > before && grow.Data[0] == 7 && grow.Data[1] == 9);
        Check("Ensure does not shrink or reallocate when it already fits",
            ReferenceEquals(grow.Data, ((Func<byte[]>)(() => { var d = grow.Data; grow.Ensure(4); return d; }))()));

        // --- shrinking a frame for a wall tile ---
        var tiles = new LiveFrame();
        Check("Full-size prepare is unchanged when no limit is given",
            tiles.Prepare(Bmp(64, 64, true).AsSpan(), 0) is { Width: 64, Height: 64 });
        Check("A frame smaller than the limit is left alone",
            tiles.Prepare(Bmp(64, 64, true).AsSpan(), 200) is { Width: 64, Height: 64 });
        var small = tiles.Prepare(Bmp(64, 64, true).AsSpan(), 16);
        Check("A frame larger than the limit is reduced by a whole factor",
            small is { Width: 16, Height: 16, Bits: 24 });
        Check("The reduced frame's stride matches its width", small!.Stride == small.Width * 3);
        Check("The reduced frame has exactly the pixels it claims",
            small.Pixels.Length >= small.Stride * small.Height);
        var odd = tiles.Prepare(Bmp(50, 108, true).AsSpan(), 25);
        Check("Reduction handles sizes that do not divide evenly", odd is { Height: 27, Width: 12 });

        // Averaging, not point-sampling: a checkerboard must come out mid-grey rather than
        // whichever square the sampler happened to land on.
        var checker = Checkerboard(32, 32);
        var averaged = tiles.Prepare(checker.AsSpan(), 16)!;
        Check("Shrinking averages whole blocks rather than picking one pixel",
            averaged.Pixels[0] > 100 && averaged.Pixels[0] < 155);

        Check("Span repeat detection agrees with the array version",
            LiveFrame.SameAsPrevious(checker.AsSpan(), checker.AsSpan())
            && !LiveFrame.SameAsPrevious(ReadOnlySpan<byte>.Empty, checker.AsSpan()));

        // A gesture that leaves the picture must still produce a coordinate. The strict
        // mapper returns null there, which froze drags mid-stroke and made a fast flick
        // send nothing at all; the clamping mapper carries the stroke to the edge.
        Check("Strict mapper rejects a point past the right edge",
            CoordinateMapper.Map(430, 400, 400, 800, 500, 1080, 500, 1080) == null);
        Check("Clamped mapper carries it to the right edge",
            CoordinateMapper.MapClamped(430, 400, 400, 800, 500, 1080, 500, 1080) is { X: 499 });
        Check("Clamped mapper carries a point above the top down to y 0",
            CoordinateMapper.MapClamped(200, -60, 400, 800, 500, 1080, 500, 1080) is { Y: 0 });
        Check("Clamped mapper carries a point below the bottom to the last row",
            CoordinateMapper.MapClamped(200, 5000, 400, 800, 500, 1080, 500, 1080) is { Y: 1079 });
        Check("Clamped mapper agrees with the strict one inside the picture",
            CoordinateMapper.MapClamped(200, 400, 400, 800, 500, 1080, 500, 1080)
            == CoordinateMapper.Map(200, 400, 400, 800, 500, 1080, 500, 1080));
        Check("Clamped mapper still refuses impossible dimensions",
            CoordinateMapper.MapClamped(10, 10, 0, 800, 500, 1080, 500, 1080) == null);
        // Letterboxed: a point in the grey margin belongs to the nearest edge of the phone.
        Check("Clamped mapper folds the letterbox onto the edge",
            CoordinateMapper.MapClamped(5, 300, 600, 600, 500, 1080, 500, 1080) is { X: 0 });

        await RunOwnershipTestsAsync(passed);

        var qa = Path.Combine(AppContext.BaseDirectory, "qa"); Directory.CreateDirectory(qa);
        File.WriteAllText(Path.Combine(qa, "self-tests.json"), JsonSerializer.Serialize(new { passed = passed.Count, tests = passed, allCommandsUsedMockTransport = true, at = DateTime.Now }, new JsonSerializerOptions { WriteIndented = true }));
    }

    public static async Task RunOwnershipTestsAsync(List<string> passed)
    {
        void Check(string name, bool ok) { if (!ok) throw new Exception("Failed: " + name); passed.Add(name); }
        async Task Reject(string name, Func<Task> action)
        {
            try { await action(); }
            catch (Exception ex) when (ex is ApiException or HttpRequestException or OperationCanceledException or ArgumentException)
            {
                passed.Add(name);
                return;
            }
            throw new Exception("Expected failure: " + name);
        }

        // 1. Unsupported kernel refused: explicit refusal, notice banner, 0 mouse/key commands sent
        var hUnsupported = new TestHandler { OwnershipSupported = false };
        using (var apiUnsupported = new ApiClient("localhost", hUnsupported, ownership: true))
        {
            string notice = "";
            apiUnsupported.InputNotice += m => notice = m;
            await Reject("Unsupported kernel refused before sending input", () =>
                apiUnsupported.CommandAsync("/mouse/click", new() { ["id"] = "TEST:01", ["x"] = 100, ["y"] = 200 }));
            Check("Unsupported kernel refusal provides explanatory message", notice.Contains("ownership-enabled kernel"));
            Check("Unsupported kernel sends zero mouse or key requests",
                !hUnsupported.Commands.Any(c => c.GetProperty("fun").GetString()!.StartsWith("/mouse/") || c.GetProperty("fun").GetString() == "/key/sendkey"));
        }

        // 2. Automatic lease acquisition before input
        var h = new TestHandler { OwnershipSupported = true };
        using (var api = new ApiClient("localhost", h, ownership: true))
        {
            await api.CommandAsync("/mouse/click", new() { ["id"] = "TEST:01", ["x"] = 100, ["y"] = 200 });
            Check("Acquires lease before sending mouse click",
                h.Commands.Count == 2 && h.Commands[0].GetProperty("fun").GetString() == "/input/acquire");
            Check("Acquire requests target phone",
                h.Commands[0].GetProperty("data").GetProperty("id").GetString() == "TEST:01");
            Check("Mouse click carries acquired token map",
                h.Commands[1].GetProperty("fun").GetString() == "/mouse/click" &&
                h.Commands[1].GetProperty("data").GetProperty("tokens").TryGetProperty("TEST:01", out _));
            string firstToken = h.Commands[1].GetProperty("data").GetProperty("tokens").GetProperty("TEST:01").GetString()!;

            // 3. One lease held across multi-request gesture (drag)
            int beforeGesture = h.Commands.Count;
            await api.MoveAsync("TEST:01", 100, 200);
            await api.CommandAsync("/mouse/down", new() { ["id"] = "TEST:01", ["button"] = "1" });
            await api.MoveAsync("TEST:01", 150, 250);
            await api.CommandAsync("/mouse/up", new() { ["id"] = "TEST:01", ["button"] = "1" });
            var gestureCommands = h.Commands.Skip(beforeGesture).ToList();
            Check("Gesture sends move, down, move, up", gestureCommands.Count == 4);
            Check("One lease reused across entire gesture with zero additional acquires",
                !gestureCommands.Any(c => c.GetProperty("fun").GetString() == "/input/acquire"));
            Check("All gesture actions carry the exact same lease token",
                gestureCommands.All(c => c.GetProperty("data").GetProperty("tokens").GetProperty("TEST:01").GetString() == firstToken));

            // 4. Independent client identities
            using (var api2 = new ApiClient("localhost", h, ownership: true))
            {
                await api2.CommandAsync("/mouse/click", new() { ["id"] = "TEST:04", ["x"] = 50, ["y"] = 50 });
                var api2Acquires = h.Commands.Where(c => c.GetProperty("fun").GetString() == "/input/acquire" && c.GetProperty("data").GetProperty("id").GetString() == "TEST:04").ToList();
                Check("Second client acquires independent lease", api2Acquires.Count > 0);
                string client2Token = h.Commands[^1].GetProperty("data").GetProperty("tokens").GetProperty("TEST:04").GetString()!;
                Check("Client tokens are distinct", client2Token != firstToken);

                // 5. Other-phone isolation
                await api.StopInputAsync("TEST:01");
                Check("Stopping phone one sends /input/stop",
                    h.Commands[^1].GetProperty("fun").GetString() == "/input/stop" &&
                    h.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01");
                await api2.CommandAsync("/mouse/click", new() { ["id"] = "TEST:04", ["x"] = 60, ["y"] = 60 });
                Check("Other phone remains controllable after one phone is stopped",
                    h.Commands[^1].GetProperty("fun").GetString() == "/mouse/click" &&
                    h.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:04");

                // 7. Stop while busy prevents stale commands
                int beforeStoppedCommand = h.Commands.Count;
                await Reject("Stopped phone rejects new commands with explanation", () =>
                    api.CommandAsync("/mouse/click", new() { ["id"] = "TEST:01", ["x"] = 10, ["y"] = 20 }));
                Check("Zero mouse commands sent to stopped phone", h.Commands.Count == beforeStoppedCommand);

                // 8. Explicit Resume clears stop and requires fresh lease
                await api.ResumeInputAsync("TEST:01");
                Check("Resume sends /input/resume with expected generation",
                    h.Commands[^1].GetProperty("fun").GetString() == "/input/resume" &&
                    h.Commands[^1].GetProperty("data").GetProperty("expected_generations").TryGetProperty("TEST:01", out _));
                await api.CommandAsync("/mouse/click", new() { ["id"] = "TEST:01", ["x"] = 10, ["y"] = 20 });
                var newAcquire = h.Commands[^2];
                Check("Command after Resume acquires a fresh lease",
                    newAcquire.GetProperty("fun").GetString() == "/input/acquire" &&
                    newAcquire.GetProperty("data").GetProperty("id").GetString() == "TEST:01");
                string resumedToken = h.Commands[^1].GetProperty("data").GetProperty("tokens").GetProperty("TEST:01").GetString()!;
                Check("Resumed token is fresh and not the revoked token", resumedToken != firstToken);
            }
        }

        // 6. Fast background renewal during work (injectable 40ms interval)
        var hRenew = new TestHandler { OwnershipSupported = true };
        using (var apiRenew = new ApiClient("localhost", hRenew, ownership: true, renewalInterval: TimeSpan.FromMilliseconds(40)))
        {
            await apiRenew.CommandAsync("/mouse/click", new() { ["id"] = "TEST:01", ["x"] = 10, ["y"] = 20 });
            await Task.Delay(130);
            int renewCount = hRenew.Commands.Count(c => c.GetProperty("fun").GetString() == "/input/renew");
            Check("Background renewal fires periodically during work", renewCount >= 2);
        }

        // 9. Group membership and atomic token map
        var hGroup = new TestHandler { OwnershipSupported = true };
        using (var apiGroup = new ApiClient("localhost", hGroup, ownership: true))
        {
            await apiGroup.CommandAsync("/key/sendkey", new() { ["id"] = "TEST:01,TEST:04", ["fn_key"] = "Home" });
            Check("Group input preflights and acquires both phones together",
                hGroup.Commands[0].GetProperty("fun").GetString() == "/input/acquire" &&
                hGroup.Commands[0].GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04");
            var groupKey = hGroup.Commands[1];
            Check("Group input carries per-phone tokens map",
                groupKey.GetProperty("data").GetProperty("tokens").TryGetProperty("TEST:01", out _) &&
                groupKey.GetProperty("data").GetProperty("tokens").TryGetProperty("TEST:04", out _));
        }

        // 10. Expiry handling with controllable mock clock
        var hExpire = new TestHandler { OwnershipSupported = true };
        using (var apiExpire = new ApiClient("localhost", hExpire, ownership: true))
        {
            await apiExpire.CommandAsync("/mouse/click", new() { ["id"] = "TEST:01", ["x"] = 100, ["y"] = 200 });
            hExpire.ExpireLease("TEST:01");
            string expireNotice = "";
            apiExpire.InputNotice += m => expireNotice = m;
            await Reject("Expired lease rejects command with ownership failure", () =>
                apiExpire.CommandAsync("/mouse/click", new() { ["id"] = "TEST:01", ["x"] = 100, ["y"] = 200 }));
            Check("Expired lease raises input notice",
                expireNotice.Contains("Input paused") || expireNotice.Contains("Expired") || expireNotice.Contains("token"));
        }

        // 11. Stop during drag: exactly one Stop, zero /mouse/up, zero /mouse/move, zero error logged
        var hDrag = new TestHandler { OwnershipSupported = true };
        using (var apiDrag = new ApiClient("localhost", hDrag, ownership: true))
        {
            await apiDrag.CommandAsync("/mouse/down", new() { ["id"] = "TEST:01", ["button"] = "1" });
            int countBeforeStop = hDrag.Commands.Count;
            await apiDrag.StopInputAsync("TEST:01");
            var commandsAfterStop = hDrag.Commands.Skip(countBeforeStop).ToList();
            Check("Stop sends exactly one /input/stop",
                commandsAfterStop.Count(c => c.GetProperty("fun").GetString() == "/input/stop") == 1);
            Check("Zero mouse commands sent after stop",
                !commandsAfterStop.Any(c => c.GetProperty("fun").GetString()!.StartsWith("/mouse/")));
        }

        // 12. Stop scope is deliberately broader than lease scope
        var hScopeDev = new TestHandler { OwnershipSupported = true };
        using (var apiScopeDev = new ApiClient("localhost", hScopeDev, ownership: true))
        {
            var devList = await apiScopeDev.DevicesAsync();
            var master = devList.First(d => d.Id == "TEST:01");
            var eligible = devList.First(d => d.Id == "TEST:04");
            var mismatched = devList.First(d => d.Id == "TEST:05");
            master.IsChecked = true; eligible.IsChecked = true; mismatched.IsChecked = true;
            var inputFollowers = new[] { eligible, mismatched }.Where(d => d.ImageWidth == master.ImageWidth && d.ImageHeight == master.ImageHeight).Select(d => d.Id);
            string inputScope = string.Join(',', new[] { master.Id }.Concat(inputFollowers).Distinct().Order());
            string stopScope = string.Join(',', new[] { master, eligible, mismatched }.Where(d => d.IsChecked).Select(d => d.Id).Distinct().Order());
            Check("Input scope excludes mismatched follower", !inputScope.Contains("TEST:05") && inputScope == "TEST:01,TEST:04");
            Check("Stop scope deliberately includes mismatched follower", stopScope.Contains("TEST:05") && stopScope == "TEST:01,TEST:04,TEST:05");
        }

        // 13. Scope change releases old lease and acquires fresh lease
        var hScope = new TestHandler { OwnershipSupported = true };
        using (var apiScope = new ApiClient("localhost", hScope, ownership: true))
        {
            await apiScope.CommandAsync("/mouse/click", new() { ["id"] = "TEST:01", ["x"] = 10, ["y"] = 20 });
            Check("Controlled phone one acquires lease", hScope.ActiveLeases.ContainsKey("TEST:01"));
            await apiScope.ReleaseInputAsync("TEST:01");
            Check("Releasing phone one revokes its lease", !hScope.ActiveLeases.ContainsKey("TEST:01"));
            Check("Release sent for phone one",
                hScope.Commands[^1].GetProperty("fun").GetString() == "/input/release" &&
                hScope.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01");
            apiScope.ReadyInputScope("TEST:04");
            await apiScope.CommandAsync("/mouse/click", new() { ["id"] = "TEST:04", ["x"] = 30, ["y"] = 40 });
            Check("Controlling phone four acquires fresh lease", hScope.ActiveLeases.ContainsKey("TEST:04"));
            Check("Phone four has distinct token",
                hScope.Commands[^1].GetProperty("data").GetProperty("tokens").TryGetProperty("TEST:04", out _));
        }

        // 14. Disconnect releases all active leases
        var hDisc = new TestHandler { OwnershipSupported = true };
        var apiDisc = new ApiClient("localhost", hDisc, ownership: true);
        await apiDisc.CommandAsync("/mouse/click", new() { ["id"] = "TEST:01", ["x"] = 10, ["y"] = 20 });
        await apiDisc.CommandAsync("/mouse/click", new() { ["id"] = "TEST:04", ["x"] = 30, ["y"] = 40 });
        Check("Two active leases before disconnect", hDisc.ActiveLeases.Count == 2);
        await apiDisc.DisposeAsync();
        Check("Disconnect releases all active leases", hDisc.ActiveLeases.Count == 0);
        Check("Release commands recorded on disconnect",
            hDisc.Commands.Any(c => c.GetProperty("fun").GetString() == "/input/release"));
    }

    /// <summary>Builds a 24-bit BMP whose marker pixel is red at the visual top-left.</summary>
    /// <summary>A 1px black/white checkerboard, so point-sampling and averaging differ.</summary>
    private static byte[] Checkerboard(int width, int height)
    {
        var bmp = Bmp(width, height, true);
        int offset = BitConverter.ToInt32(bmp, 10);
        int bits = BitConverter.ToInt16(bmp, 28);
        int bytesPerPixel = bits / 8, stride = (width * bytesPerPixel + 3) & ~3;
        for (int y = 0; y < height; y++)
            for (int x = 0; x < width; x++)
            {
                byte v = (byte)(((x + y) & 1) == 0 ? 0 : 255);
                int at = offset + y * stride + x * bytesPerPixel;
                for (int c = 0; c < bytesPerPixel; c++) bmp[at + c] = v;
            }
        return bmp;
    }

    private static byte[] Bmp(int width, int height, bool bottomUp)
    {
        int stride = (width * 3 + 3) & ~3, offset = 54, size = offset + stride * height;
        var b = new byte[size];
        b[0] = 0x42; b[1] = 0x4D;
        BitConverter.GetBytes(size).CopyTo(b, 2);
        BitConverter.GetBytes(offset).CopyTo(b, 10);
        BitConverter.GetBytes(40).CopyTo(b, 14);
        BitConverter.GetBytes(width).CopyTo(b, 18);
        BitConverter.GetBytes(bottomUp ? height : -height).CopyTo(b, 22);
        BitConverter.GetBytes((short)1).CopyTo(b, 26);
        BitConverter.GetBytes((short)24).CopyTo(b, 28);
        // Visual top row is the last stored row when the bitmap is bottom-up.
        int markerRow = bottomUp ? height - 1 : 0;
        int p = offset + markerRow * stride;
        b[p] = 0; b[p + 1] = 0; b[p + 2] = 255;
        return b;
    }
    private static BitmapSource? Reuse(LiveFrame frame) { var f = frame.Prepare(Bmp(4, 3, true)); if (f is not null) frame.Present(f); return frame.Source; }
    private static bool TopLeftIsMarker(LiveFrame frame)
    {
        var prepared = frame.Prepare(Bmp(4, 3, true));
        if (prepared is null || !frame.Present(prepared)) return false;
        if (frame.Source is not BitmapSource s) return false;
        var px = new byte[4 * 3];
        s.CopyPixels(new Int32Rect(0, 0, 4, 1), px, 4 * 3, 0);
        return px[0] == 0 && px[1] == 0 && px[2] == 255;
    }
}
