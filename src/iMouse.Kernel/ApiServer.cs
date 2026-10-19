using System.Net;
using System.Text;
using System.Text.Json;

namespace IMouse2.Kernel;

public sealed class ApiServer : IDisposable
{
    private readonly HttpListener _http = new();
    private readonly DeviceStore _store;
    private readonly string _castName;
    private readonly InputRouter _input;
    private readonly InputSessions _inputSessions;
    private readonly FrameStore _frames;
    private readonly Dictionary<string,(string Name,FrameStore Frames)> _sessions;

    public ApiServer(string prefix, DeviceStore store, string castName, InputRouter input, FrameStore frames)
        : this(prefix,store,input,[(castName,frames)]) { }

    public ApiServer(string prefix,DeviceStore store,InputRouter input,IEnumerable<(string Name,FrameStore Frames)> sessions)
    {
        _store = store;
        _input = input;
        _inputSessions = new(store, input);
        _sessions=sessions.ToDictionary(s=>s.Frames.DeviceId);
        _frames=_sessions.Values.First().Frames;
        _castName=string.Join(" / ",_sessions.Values.Select(s=>s.Name));
        _http.Prefixes.Add(prefix);
    }

    public async Task RunAsync(CancellationToken ct)
    {
        _http.Start();
        Console.WriteLine("Listening on " + string.Join(", ", _http.Prefixes.Cast<string>()));
        while (!ct.IsCancellationRequested)
        {
            HttpListenerContext ctx;
            try { ctx = await _http.GetContextAsync().WaitAsync(ct); }
            catch (OperationCanceledException) { break; }
            _ = Task.Run(() => Handle(ctx));
        }
    }

    private async Task Handle(HttpListenerContext ctx)
    {
        try
        {
            var req = ctx.Request;
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
                else if(!session.Frames.WriteFrame(ctx,id))
                    Write(ctx, Ok(new { code = 25, message = ScreenshotMessage(session.Frames,session.Name) }));
            }
            else if (req.HttpMethod == "GET" && path.EndsWith("/input/status", StringComparison.OrdinalIgnoreCase))
                Write(ctx, Ok(_inputSessions.Status()));
            else if (req.HttpMethod == "GET" && path.EndsWith("/kernel/status",StringComparison.OrdinalIgnoreCase))
            {
                var rec=_frames.Receiver();
                Write(ctx,Ok(new {code=0,input="direct-hid",input_protocol=1,input_leases_required=true,allowed=_input.Allowed,home_sequence=_input.HomeSequenceName,fka_pass_through_probe_enabled=_input.FkaPassThroughProbeEnabled,receiver=_castName,
                    receiver_state=VideoState(rec),receiver_message=ScreenshotMessage(),
                    receiver_pid=rec.Pid,receiver_restarts=rec.Restarts,frames=_frames.Frames,live=_frames.State.Live,
                    receivers=_sessions.Select(s=>new {deviceid=s.Key,name=s.Value.Name,
                        receiver_pid=s.Value.Frames.Receiver().Pid,receiver_restarts=s.Value.Frames.Receiver().Restarts,
                        receiver_state=VideoState(s.Value.Frames.Receiver(),s.Value.Frames),
                        live=s.Value.Frames.State.Live,frames=s.Value.Frames.Frames}).ToArray()}));
            }
            else if (req.HttpMethod == "POST")
                Write(ctx, Ok(await Dispatch(ReadBody(req))));
            else
                Write(ctx, Envelope(404, new { code = 41, message = "Unknown path." }));
        }
        catch (KeyNotFoundException ex)
        {
            Write(ctx, Ok(new { code = 1, message = "Device not found: " + ex.Message }));
        }
        catch (ArgumentException ex) { Write(ctx,Ok(new {code=36,message=ex.Message})); }
        catch (InvalidOperationException ex) { Write(ctx,Ok(new {code=409,message=ex.Message})); }
        catch (JsonException ex) { Write(ctx,Ok(new {code=36,message=ex.Message})); }
        catch (Exception ex)
        {
            Console.WriteLine(ex);
            try { Write(ctx, Envelope(500, new { code = 33, message = ex.Message })); } catch { }
        }
    }

    internal async Task<object> Dispatch(JsonElement body)
    {
        string fun = body.TryGetProperty("fun", out var f) ? f.GetString() ?? "" : "";
        JsonElement data = body.TryGetProperty("data", out var d) && d.ValueKind == JsonValueKind.Object ? d : default;
        Console.WriteLine(fun);
        return fun switch
        {
            "/device/set" => new { code = 41, message = "Live binding changes are disabled in the ownership build. Stop the kernel and verify saved phone/board/receiver configuration before restarting." },
            "/input/acquire" => _inputSessions.Acquire(data),
            "/input/status" => _inputSessions.Status(),
            "/input/renew" => _inputSessions.Renew(data),
            "/input/resume" => _inputSessions.Resume(data),
            "/input/stop" => await _inputSessions.StopAsync(data),
            "/input/release" => await _inputSessions.StopAsync(data, release: true),
            "/mouse/move" or "/mouse/down" or "/mouse/up" or "/mouse/click" or "/mouse/reset" or "/mouse/swipe"
                or "/key/sendkey" or "/device/usb/restart"
                => await _inputSessions.DispatchAsync(fun, data),
            "/device/airplay/connect" or "/device/airplay/disconnect"
                => new { code = 41, message = "Choose or stop " + _castName + " in the iPhone's Screen Mirroring menu." },
            _ => new { code = 41, message = "Not implemented: " + fun }
        };
    }

    private object Bind(JsonElement data)
    {
        string id = Str(data, "id");
        string vid = Str(data, "vid");
        string pid = Str(data, "pid");
        string uid = Str(data, "uid");
        if (string.IsNullOrEmpty(id)) return new { code = 36, message = "id required" };
        _store.Bind(id, vid, pid, uid);
        return new { code = 0, id };
    }

    private string VideoState(ReceiverInfo rec,FrameStore? frames=null) =>
        (frames??_frames).State.Live ? "mirroring" : rec.State is "restarting" or "starting" ? "restarting" : rec.State is "failed" ? "failed" : "offline";

    private string ScreenshotMessage(FrameStore? frames=null,string? name=null)
    {
        frames??=_frames;
        var rec=frames.Receiver();
        if (frames.State.Live) return "";
        if (rec.State is "restarting" or "starting") return "Receiver restarting";
        if (rec.State == "failed") return rec.Message;
        return "No live frame. Select " + (name??_sessions[frames.DeviceId].Name) + " in iPhone Screen Mirroring.";
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

    private static string Str(JsonElement obj, string name) =>
        obj.ValueKind == JsonValueKind.Object && obj.TryGetProperty(name, out var v) && v.ValueKind != JsonValueKind.Null ? v.ToString() : "";

    private static JsonElement ReadBody(HttpListenerRequest req)
    {
        using var reader = new StreamReader(req.InputStream, req.ContentEncoding);
        string text = reader.ReadToEnd();
        if (string.IsNullOrWhiteSpace(text)) return default;
        using var doc = JsonDocument.Parse(text);
        return doc.RootElement.Clone();
    }

    private static object Envelope(int status, object data) => new { status, message = status == 200 ? "ok" : "error", data };
    private static object Ok(object data) => Envelope(200, data);

    private static void Write(HttpListenerContext ctx, object payload)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(payload));
        ctx.Response.StatusCode = 200;
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
