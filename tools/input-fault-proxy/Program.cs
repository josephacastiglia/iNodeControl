using System.Diagnostics;
using System.Net;
using System.Text;
using System.Text.Json;

namespace IMouse2.FaultProxy;

/// <summary>
/// A loopback proxy for live validation. It forwards every request to the running kernel unchanged,
/// and when armed it lets exactly one chosen command reach the kernel but withholds the kernel's
/// answer, so the console sees its own 8 s timeout while the phone saw the command. Point a candidate
/// console at it; the kernel, the release and the phone's settings are not touched.
///
///   InputFaultProxy --listen http://localhost:9923/ --upstream http://127.0.0.1:9913 --log proxy-log.jsonl
///   GET http://localhost:9923/proxy/lose?fun=/mouse/move&amp;skip=2   lose the answer to the 3rd /mouse/move from now
///   GET http://localhost:9923/proxy/disarm                           GET http://localhost:9923/proxy/status
///
/// Every command (POST) is logged with the kernel's own answer code, withheld or not.
/// </summary>
static class Proxy
{
    // Only input commands can be armed, plus /input/status for a read-only check of the proxy itself.
    // Never the ownership calls: losing an acquire, release, stop or resume is not what is being tested.
    static readonly HashSet<string> Losable = ["/mouse/move", "/mouse/down", "/mouse/up", "/mouse/click", "/key/sendkey", "/input/status"];
    static readonly HttpClient Upstream = new(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(30) };
    static readonly object Sync = new();
    static string? _armed;
    static int _skip, _lost;
    static string _upstream = "";
    static StreamWriter _log = StreamWriter.Null;

    static async Task<int> Main(string[] args)
    {
        if (args.Contains("--self-test")) return ProxyStartup.SelfTest();
        string Arg(string name, string fallback) { int i = Array.IndexOf(args, name); return i >= 0 && i + 1 < args.Length ? args[i + 1] : fallback; }
        string listen = Arg("--listen", "http://localhost:9923/");
        _upstream = Arg("--upstream", "http://127.0.0.1:9913").TrimEnd('/');
        string readyFile = Arg("--ready-file", "");
        if (readyFile.Length > 0 && !Path.IsPathFullyQualified(readyFile)) throw new ArgumentException("--ready-file needs an absolute path.");
        _log = new StreamWriter(Arg("--log", Path.Combine(AppContext.BaseDirectory, "proxy-log.jsonl")), append: true) { AutoFlush = true };
        using var http = new HttpListener();
        http.Prefixes.Add(listen);
        http.Start();
        // Publish only after this process has successfully registered its listener.
        if (readyFile.Length > 0) ProxyStartup.Write(readyFile, listen, _upstream);
        Console.WriteLine($"Forwarding {listen} to {_upstream}. Arm with GET {listen}proxy/lose?fun=/mouse/move&skip=0");
        Log("start", "", 0, "", $"listening on {listen}, upstream {_upstream}", 0);
        while (true)
        {
            var ctx = await http.GetContextAsync();
            _ = Task.Run(() => HandleAsync(ctx));
        }
    }

    static async Task HandleAsync(HttpListenerContext ctx)
    {
        ctx.Response.Headers["X-iMouse-FaultProxy-Pid"] = Environment.ProcessId.ToString(System.Globalization.CultureInfo.InvariantCulture);
        var request = ctx.Request;
        long started = Stopwatch.GetTimestamp();
        string path = request.Url!.PathAndQuery, fun = "";
        try
        {
            if (request.Url.AbsolutePath.StartsWith("/proxy/", StringComparison.OrdinalIgnoreCase)) { await ControlAsync(ctx); return; }
            byte[] body = [];
            if (request.HasEntityBody) { using var copy = new MemoryStream(); await request.InputStream.CopyToAsync(copy); body = copy.ToArray(); }
            if (request.HttpMethod == "POST")
                try { fun = JsonDocument.Parse(body).RootElement.GetProperty("fun").GetString() ?? ""; } catch { }
            bool lose = false;
            lock (Sync)
                if (fun.Length > 0 && fun == _armed)
                {
                    if (_skip > 0) _skip--;
                    else { lose = true; _armed = null; _lost++; }
                }
            using var forward = new HttpRequestMessage(new HttpMethod(request.HttpMethod), _upstream + path);
            if (body.Length > 0)
            {
                forward.Content = new ByteArrayContent(body);
                if (request.ContentType is { } type) forward.Content.Headers.TryAddWithoutValidation("Content-Type", type);
            }
            using var answer = await Upstream.SendAsync(forward);
            byte[] bytes = await answer.Content.ReadAsByteArrayAsync();
            string code = "";
            if (fun.Length > 0) try { code = JsonDocument.Parse(bytes).RootElement.GetProperty("data").GetProperty("code").ToString(); } catch { }
            if (lose)
            {
                // The kernel has run the command. Hold the console's request until its own timeout gives
                // up, then drop the connection: the answer never arrives.
                Log(request.HttpMethod, fun, (int)answer.StatusCode, code, "ANSWER WITHHELD", started);
                await Task.Delay(TimeSpan.FromSeconds(20));
                ctx.Response.Abort();
                return;
            }
            ctx.Response.StatusCode = (int)answer.StatusCode;
            if (answer.Content.Headers.ContentType is { } contentType) ctx.Response.ContentType = contentType.ToString();
            ctx.Response.ContentLength64 = bytes.Length;
            await ctx.Response.OutputStream.WriteAsync(bytes);
            ctx.Response.Close();
            if (request.HttpMethod == "POST") Log(request.HttpMethod, fun, (int)answer.StatusCode, code, "", started);
        }
        catch (Exception ex)
        {
            Log(request.HttpMethod, fun, 0, "", "proxy error on " + path + ": " + ex.Message, started);
            try { ctx.Response.Abort(); } catch { }
        }
    }

    static async Task ControlAsync(HttpListenerContext ctx)
    {
        string action = ctx.Request.Url!.AbsolutePath.ToLowerInvariant(), reply;
        lock (Sync)
        {
            if (action == "/proxy/lose")
            {
                string fun = ctx.Request.QueryString["fun"] ?? "";
                if (!Losable.Contains(fun)) reply = "refused: only " + string.Join(", ", Losable) + " can be armed";
                else { _armed = fun; _skip = int.TryParse(ctx.Request.QueryString["skip"], out int skip) && skip >= 0 ? skip : 0; reply = $"armed: withhold the answer to {fun} after passing {_skip}"; }
            }
            else if (action == "/proxy/disarm") { _armed = null; _skip = 0; reply = "disarmed"; }
            else reply = $"armed={_armed ?? "none"} skip={_skip} withheld so far={_lost}";
        }
        Log("GET", "", 200, "", "control " + action + ": " + reply, Stopwatch.GetTimestamp());
        var bytes = Encoding.UTF8.GetBytes(reply + "\n");
        ctx.Response.ContentType = "text/plain; charset=utf-8";
        ctx.Response.ContentLength64 = bytes.Length;
        await ctx.Response.OutputStream.WriteAsync(bytes);
        ctx.Response.Close();
    }

    static void Log(string method, string fun, int status, string code, string note, long started) =>
        Write(new { at = DateTimeOffset.Now.ToString("O"), method, fun, status, code, note, ms = started == 0 ? 0 : Math.Round(Stopwatch.GetElapsedTime(started).TotalMilliseconds, 1) });
    static void Write(object entry) { string line = JsonSerializer.Serialize(entry); lock (Sync) _log.WriteLine(line); }
}
