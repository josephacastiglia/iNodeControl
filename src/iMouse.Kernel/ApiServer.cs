using System.Net;
using System.Text;
using System.Text.Json;

namespace IMouse2.Kernel;

public sealed class ApiServer : IDisposable
{
    /// <summary>The largest request body read. A command for forty phones with their tokens is about 3 KiB.</summary>
    internal const int MaxBodyBytes = 64 * 1024;
    private sealed class BodyTooLargeException : Exception;
    private readonly HttpListener _http = new();
    private readonly Action _startListening;
    private readonly DeviceStore _store;
    private readonly string _castName;
    private readonly InputRouter _input;
    private readonly InputSessions _inputSessions;
    private readonly Dictionary<string,(string Name,FrameStore Frames)> _sessions;
    // Advertises, restarts or withdraws one receiver by board PID; null when the kernel runs no receivers.
    public ReceiverFleet? Receivers { get; init; }

    public ApiServer(string prefix,DeviceStore store,InputRouter input,IEnumerable<(string Name,FrameStore Frames)> sessions)
        : this(prefix,store,input,sessions,null) { }

    // Listener failure/cancellation can be tested without reserving an OS port.
    internal ApiServer(string prefix,DeviceStore store,InputRouter input,IEnumerable<(string Name,FrameStore Frames)> sessions,Action? startListening)
    {
        _startListening = startListening ?? _http.Start;
        _store = store;
        _input = input;
        _inputSessions = new(store, input);
        _sessions=sessions.ToDictionary(s=>s.Frames.DeviceId);
        _castName=string.Join(" / ",_sessions.Values.Select(s=>s.Name));
        _http.Prefixes.Add(prefix);
    }

    public async Task RunAsync(CancellationToken ct, Action? afterListening = null)
    {
        ct.ThrowIfCancellationRequested();
        _startListening();
        ct.ThrowIfCancellationRequested();
        // Start frame readers/receivers only after the endpoint has been claimed.
        afterListening?.Invoke();
        Console.WriteLine("Listening on " + string.Join(", ", _http.Prefixes.Cast<string>()));
        while (!ct.IsCancellationRequested)
        {
            HttpListenerContext ctx;
            try { ctx = await _http.GetContextAsync().WaitAsync(ct); }
            catch (OperationCanceledException) { break; }
            _ = Task.Run(() => Handle(ctx, ct));
        }
    }

    private async Task Handle(HttpListenerContext ctx, CancellationToken ct)
    {
        bool writingScreenshot = false;
        try
        {
            var req = ctx.Request;
            if (Refusal(req) is { } refusal)
            {
                Write(ctx, Envelope(refusal.Status, new { code = refusal.Status, message = refusal.Message }), refusal.Status);
                return;
            }
            var path = req.Url?.AbsolutePath.TrimEnd('/') ?? "";
            if (req.HttpMethod == "GET" && path.EndsWith("/device/get", StringComparison.OrdinalIgnoreCase))
                Write(ctx, Ok(new { code = 0, list = DeviceList() }));
            else if (req.HttpMethod == "GET" && path.EndsWith("/config/usb/get", StringComparison.OrdinalIgnoreCase))
                Write(ctx, Ok(new { code = 0, list = BoardList() }));
            else if (req.HttpMethod == "GET" && path.EndsWith("/config/imserver/get", StringComparison.OrdinalIgnoreCase))
                Write(ctx, Ok(new { code = 0, air_play_name = _castName }));
            else if (req.HttpMethod == "GET" && path.Contains("/pic/screenshot", StringComparison.OrdinalIgnoreCase))
            {
                string id=req.QueryString["id"] ?? "";
                if(!_sessions.TryGetValue(id,out var session))
                    Write(ctx,Ok(new {code=1,message="Unknown receiver device."}));
                else
                {
                    writingScreenshot = true;
                    var result = await session.Frames.WriteFrameAsync(ctx, id, ct);
                    if (result == FrameWriteResult.Unavailable)
                        Write(ctx, Ok(new { code = 25, message = ScreenshotMessage(session.Frames,session.Name) }));
                    else if (result == FrameWriteResult.Busy)
                    {
                        ctx.Response.Headers["Retry-After"] = "1";
                        Write(ctx, Envelope(503, new { code = 503, message = "Screenshot transfers busy; try again shortly." }), 503);
                    }
                }
            }
            else if (req.HttpMethod == "GET" && path.EndsWith("/input/status", StringComparison.OrdinalIgnoreCase))
                Write(ctx, Ok(_inputSessions.Status()));
            else if (req.HttpMethod == "GET" && path.EndsWith("/kernel/status",StringComparison.OrdinalIgnoreCase))
            {
                Write(ctx, Ok(KernelStatus()));
            }
            else if (req.HttpMethod == "POST")
                Write(ctx, Ok(await Dispatch(ReadBody(req))));
            else
                Write(ctx, Envelope(404, new { code = 41, message = "Unknown path." }));
        }
        catch (OperationCanceledException) when (writingScreenshot)
        {
            try { ctx.Response.Abort(); } catch (ObjectDisposedException) { } catch (HttpListenerException) { }
        }
        catch (KeyNotFoundException ex)
        {
            Write(ctx, Ok(new { code = 1, message = "Device not found: " + ex.Message }));
        }
        catch (ArgumentException ex) { Write(ctx,Ok(new {code=36,message=ex.Message})); }
        catch (InvalidOperationException ex) { Write(ctx,Ok(new {code=409,message=ex.Message})); }
        catch (JsonException ex) { Write(ctx,Ok(new {code=36,message=ex.Message})); }
        catch (BodyTooLargeException)
        {
            try { Write(ctx, Envelope(413, new { code = 413, message = "Request body is larger than " + MaxBodyBytes + " bytes. Nothing was done." }), 413); } catch { }
        }
        catch (Exception ex)
        {
            Console.WriteLine(ex);
            try { Write(ctx, Envelope(500, new { code = 33, message = ex.Message })); } catch { }
        }
    }

    // Kept separate from HTTP so diagnostics can be checked without a listener or HID access.
    // Every receiver reports its own state; there is no single-receiver summary at the top level.
    internal object KernelStatus()
    {
        return new { code = 0, input = "direct-hid", input_protocol = 1, input_leases_required = true,
            build_identity = KernelDiagnostics.BuildIdentity, process = KernelDiagnostics.ProcessSnapshot(),
            input_configuration = _input.DiagnosticConfiguration(),
            control_compatibility = _input.ControlCompatibility(),
            allowed = _input.Allowed, home_sequence = _input.HomeSequenceName, receiver = _castName,
            receivers = _sessions.Select(s =>
            {
                var receiver = s.Value.Frames.Receiver();
                var frame = s.Value.Frames.Delivery;
                return new { deviceid = s.Key, name = s.Value.Name,
                    receiver_pid = receiver.Pid, receiver_restarts = receiver.Restarts,
                    receiver_generation = receiver.Generation,
                    receiver_state = VideoState(receiver, s.Value.Frames),
                    receiver_message = receiver.Message,
                    live = frame.Available, frames = frame.Sequence,
                    frame_delivery = frame.Status, frame_age_ms = frame.AgeMs,
                    frame_session = frame.Session, frame_message = frame.Message,
                    frame_pipe_connected = frame.Connected };
            }).ToArray() };
    }

    internal async Task<object> Dispatch(JsonElement body)
    {
        string fun = body.TryGetProperty("fun", out var f) ? f.GetString() ?? "" : "";
        JsonElement data = body.TryGetProperty("data", out var d) && d.ValueKind == JsonValueKind.Object ? d : default;
        Console.WriteLine(fun);
        return fun switch
        {
            "/input/acquire" => _inputSessions.Acquire(data),
            "/input/status" => _inputSessions.Status(),
            "/input/renew" => _inputSessions.Renew(data),
            "/input/resume" => _inputSessions.Resume(data),
            "/input/stop" => await _inputSessions.StopAsync(data),
            "/input/release" => await _inputSessions.StopAsync(data, release: true),
            "/mouse/move" or "/mouse/down" or "/mouse/up" or "/mouse/click" or "/mouse/reset" or "/mouse/swipe"
                or "/key/sendkey"
                => await _inputSessions.DispatchAsync(fun, data),
            "/device/airplay/connect" => Advertise(data),
            "/device/airplay/restart" or "/device/airplay/withdraw" => await ChangeReceiver(fun, data),
            _ => new { code = 41, message = "Not implemented: " + fun }
        };
    }

    // Starts one held or withdrawn receiver. Mirroring itself is always chosen on the iPhone.
    private object Advertise(JsonElement data)
    {
        if (Receivers is null) return new { code = 41, message = "This kernel runs no receivers." };
        string pid = InputRouter.Text(data, "pid");
        return KernelOptions.BoardId(pid) ? Receivers.Advertise(pid) : new { code = 36, message = "pid must be a four-digit hexadecimal board ID." };
    }

    // One receiver at a time; a phone whose input another controller leases is refused, so a
    // lane's mirror is never cut mid-run. The lane holding the lease may pass its token.
    private async Task<object> ChangeReceiver(string fun, JsonElement data)
    {
        if (Receivers is null) return new { code = 41, message = "This kernel runs no receivers." };
        string pid = InputRouter.Text(data, "pid");
        if (!KernelOptions.BoardId(pid)) return new { code = 36, message = "pid must be a four-digit hexadecimal board ID." };
        pid = pid.ToUpperInvariant();
        if (_inputSessions.LeasedByOther(pid, InputRouter.Text(data, "token")))
            return new { code = 409, message = "Board " + pid + "'s phone has an active input lease. Wait for it to end, or pass that lease's token. Nothing was stopped." };
        bool hold = InputRouter.Text(data, "hold") is var h && (h.Equals("true", StringComparison.OrdinalIgnoreCase) || h == "1");
        return fun == "/device/airplay/withdraw" ? await Receivers.WithdrawAsync(pid) : await Receivers.RestartAsync(pid, hold);
    }

    private static string VideoState(ReceiverInfo rec,FrameStore frames) =>
        frames.State.Live ? "mirroring" : rec.State is "restarting" ? "restarting" : rec.State is "failed" or "held" ? rec.State : "offline";

    private static string ScreenshotMessage(FrameStore frames,string name)
    {
        if (frames.State.Live) return "";
        var rec=frames.Receiver();
        if (rec.State is "restarting") return "Receiver restarting";
        if (rec.State is "failed" or "held") return rec.Message;
        return "No live frame. Select " + name + " in iPhone Screen Mirroring.";
    }

    private List<object> DeviceList()
    {
        return _store.All().Select(p =>
        {
        _sessions.TryGetValue(p.deviceid,out var session);
        var frames=session.Frames;
        var state=frames?.State ?? (Live:false,Width:0,Height:0);
        var rec=frames?.Receiver() ?? new ReceiverInfo("offline","",0,0);
        return (object)new
        {
            p.deviceid,
            p.name,
            user_name = p.name,
            p.device_name,
            gname = p.gname,
            state = state.Live ? 1 : 0,
            video_state = frames is null ? "offline" : VideoState(rec,frames),
            receiver_name=session.Name ?? "",
            width = p.width.ToString(),
            height = p.height.ToString(),
            imgw = state.Live ? state.Width : p.imgw,
            imgh = state.Live ? state.Height : p.imgh,
            air_pid = state.Live ? rec.Pid : 0,
            version = p.version,
            uid = p.uid,
            vid = p.vid,
            pid = p.pid,
            rotate = 0
        }; }).ToList();
    }

    private List<object> BoardList()
    {
        var stored = _store.All().Where(p => p.pid.Length > 0).ToDictionary(p => p.pid, p => p.uid, StringComparer.OrdinalIgnoreCase);
        return HidHost.Enumerate().Select(b => (object)new
        {
            vid = b.Vid,
            pid = b.Pid,
            uid = stored.TryGetValue(b.Pid, out var uid) && uid.Length > 0 ? uid : b.Pid,
            state = _input.Enabled(b.Pid) && stored.ContainsKey(b.Pid) ? 2 : 1
        }).ToList();
    }

    /// <summary>
    /// What is turned away before anything is read or done. This API has no login: the lease tokens
    /// only keep controllers out of each other's way. Its one defence against a web page open on
    /// this PC is that it never serves one. A browser attaches Origin to every cross-site POST,
    /// whatever its content type, and to every scripted cross-site request; no client here is a web
    /// page, so a request that carries Origin is refused whatever it asks for. The kernel sends no
    /// Access-Control header either, so no page is ever told it may send or read. POST bodies must
    /// be JSON, which a plain HTML form cannot send, and are bounded.
    /// </summary>
    private static (int Status, string Message)? Refusal(HttpListenerRequest req)
    {
        if (req.Headers["Origin"] is not null)
            return (403, "Requests from web pages are refused: this API does not accept an Origin header. Nothing was done.");
        if (req.HttpMethod != "POST") return null;
        string type = (req.ContentType ?? "").Split(';')[0].Trim();
        if (!type.Equals("application/json", StringComparison.OrdinalIgnoreCase))
            return (415, "POST bodies must be sent with Content-Type: application/json. Nothing was done.");
        if (req.ContentLength64 > MaxBodyBytes)
            return (413, "Request body is larger than " + MaxBodyBytes + " bytes. Nothing was done.");
        return null;
    }

    private static JsonElement ReadBody(HttpListenerRequest req)
    {
        // Bounded even when no length was declared (a chunked body): stop one read past the cap.
        using var bytes = new MemoryStream();
        byte[] chunk = new byte[4096];
        for (int read; (read = req.InputStream.Read(chunk, 0, chunk.Length)) > 0;)
        {
            if (bytes.Length + read > MaxBodyBytes) throw new BodyTooLargeException();
            bytes.Write(chunk, 0, read);
        }
        bytes.Position = 0;
        using var reader = new StreamReader(bytes, req.ContentEncoding);
        string text = reader.ReadToEnd();
        if (string.IsNullOrWhiteSpace(text)) return default;
        using var doc = JsonDocument.Parse(text);
        return doc.RootElement.Clone();
    }

    private static object Envelope(int status, object data) => new { status, message = status == 200 ? "ok" : "error", data };
    private static object Ok(object data) => Envelope(200, data);

    private static void Write(HttpListenerContext ctx, object payload, int httpStatus = 200)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(payload));
        ctx.Response.StatusCode = httpStatus;
        ctx.Response.ContentType = "application/json; charset=utf-8";
        ctx.Response.ContentLength64 = bytes.Length;
        ctx.Response.OutputStream.Write(bytes);
        ctx.Response.Close();
    }

    public void Dispose()
    {
        try { _http.Stop(); } catch { }
        _inputSessions.DisposeAsync().AsTask().GetAwaiter().GetResult();
        _http.Close();
    }
}
