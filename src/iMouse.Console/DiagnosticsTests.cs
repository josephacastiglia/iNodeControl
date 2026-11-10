using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;

namespace IMouse2;

internal static class DiagnosticsTests
{
    private sealed class Handler : HttpMessageHandler
    {
        internal readonly List<string> Calls = [];
        internal Func<string, CancellationToken, Task<string>>? Reply;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            string path = request.RequestUri!.AbsolutePath[4..]; // /api prefix
            Calls.Add(request.Method + " " + path);
            string data = Reply is null ? Fixture(path) : await Reply(path, ct);
            return new(HttpStatusCode.OK) { Content = new StringContent("{\"status\":200,\"data\":" + data + "}", Encoding.UTF8, "application/json") };
        }
    }
    private static string Fixture(string path) => path switch
    {
        "/kernel/status" => """
        {"code":0,"input":"direct-hid","receiver":"fake-cast","home_sequence":"vendor",
         "build_identity":{"sha256":"test-hash","module_id":"test-module","secret":"HIDDEN"},
         "process":{"pid":123,"working_set_bytes":2048},
         "control_compatibility":{"home_sequence":"command-h","home_sends_tab":false,"phone_setting_detection":false,"secret":"HIDDEN"},
         "input_configuration":{"precise_movement_delay_ms":0,"calibrations":[{"pid":"PID","width":500,"height":1080,"pixels_per_unit_x":5.12,"token":"HIDDEN"}]},
         "receivers":[{"deviceid":"TEST:01","name":"fake-cast","receiver_restarts":3,"receiver_state":"failed",
           "receiver_message":"Restart limit reached","frame_age_ms":null,"live":false,"token":"HIDDEN"}],"password":"HIDDEN"}
        """,
        "/device/get" => """
        {"code":0,"list":[{"deviceid":"TEST:01","uid":"BOARD:01","vid":"VID","pid":"PID","name":"Test phone",
         "receiver_name":"fake-cast","state":0,"serial_number":"HIDDEN","credentials":{"password":"HIDDEN"}}]}
        """,
        "/config/usb/get" => """{"code":0,"list":[{"uid":"BOARD:01","vid":"VID","pid":"PID","state":2,"token":"HIDDEN"}]}""",
        "/input/status" => """
        {"code":0,"protocol":1,"phones":[{"id":"TEST:01","owned":true,"active":false,"stopped":true,"release_failed":true,
        "generation":7,"lease_remaining_ms":321,"token":"HIDDEN","tokens":{"TEST:01":"HIDDEN"}}]}
        """,
        _ => throw new Exception("Unexpected diagnostic route: " + path)
    };

    internal static async Task RunAsync(Action<string, bool> check)
    {
        var snapshot = JsonSerializer.SerializeToElement(new { observed_utc = DateTimeOffset.UtcNow,
            build_identity = ConsoleBuildInfo.Current, selected_device = "TEST:01", activity = new[] { "Input paused" } });
        var h = new Handler();
        using var api = new ApiClient("http://localhost:9913", h);
        var report = await ConsoleDiagnostics.CollectAsync(snapshot, api.GetAsync);
        check("Diagnostics read only the four status routes without acquiring or changing input", h.Calls.Order().SequenceEqual(new[] {
            "GET /config/usb/get", "GET /device/get", "GET /input/status", "GET /kernel/status" }));
        check("Diagnostic sections are timestamped and complete independently", !report.Partial && report.Service.Count == 4
            && report.Service.Values.All(s => s.State == "ok" && s.ObservedUtc >= report.StartedUtc && s.ObservedUtc <= report.FinishedUtc));
        var kernel = report.Service["kernel"].Data!.Value;
        var phone = report.Service["devices"].Data!.Value[0];
        check("Diagnostics retain phone-board-receiver mapping", phone.GetProperty("uid").GetString() == "BOARD:01"
            && phone.GetProperty("pid").GetString() == "PID" && phone.GetProperty("receiver_name").GetString() == "fake-cast");
        check("Diagnostics retain failed recovery and unknown frame age", kernel.GetProperty("receivers")[0].GetProperty("receiver_restarts").GetInt32() == 3
            && kernel.GetProperty("receivers")[0].GetProperty("receiver_message").GetString() == "Restart limit reached"
            && kernel.GetProperty("receivers")[0].GetProperty("frame_age_ms").ValueKind == JsonValueKind.Null);
        check("Diagnostics retain paused ownership state without exporting its token", report.Service["input"].Data!.Value.GetProperty("phones")[0].GetProperty("release_failed").GetBoolean());
        check("Diagnostics retain the running kernel's calibration and movement setting", kernel.GetProperty("input_configuration").GetProperty("calibrations")[0].GetProperty("pixels_per_unit_x").GetDouble() == 5.12
            && kernel.GetProperty("input_configuration").GetProperty("precise_movement_delay_ms").GetInt32() == 0);
        string json = JsonSerializer.Serialize(report, ConsoleDiagnostics.JsonOptions);
        check("Diagnostics retain selected shortcuts without claiming phone settings detection", kernel.GetProperty("control_compatibility").GetProperty("home_sequence").GetString() == "command-h"
            && !kernel.GetProperty("control_compatibility").GetProperty("phone_setting_detection").GetBoolean());
        check("Diagnostics exclude unknown credential, serial and nested fields", !json.Contains("HIDDEN") && !json.Contains("serial_number") && !json.Contains("tokens"));
        check("Diagnostics identify both console and service builds", kernel.GetProperty("build_identity").GetProperty("sha256").GetString() == "test-hash"
            && report.Console.GetProperty("build_identity").GetProperty("Sha256").GetString() == ConsoleBuildInfo.Current.Sha256);

        var disconnected = await ConsoleDiagnostics.CollectAsync(snapshot, null);
        check("Disconnected diagnostics preserve local evidence without service calls", disconnected.Partial && disconnected.Service.Values.All(s => s.State == "skipped")
            && disconnected.Console.GetProperty("activity")[0].GetString() == "Input paused" && h.Calls.Count == 4);

        h.Reply = (path, _) => path == "/config/usb/get"
            ? throw new HttpRequestException("token=HIDDEN", null, HttpStatusCode.Forbidden) : Task.FromResult(Fixture(path));
        var failed = await ConsoleDiagnostics.CollectAsync(snapshot, api.GetAsync);
        check("One failed diagnostic endpoint preserves the other three results", failed.Partial && failed.Service.Count(s => s.Value.State == "ok") == 3
            && failed.Service["boards"].Error == "Service returned HTTP 403.");
        check("Diagnostics never copy a transport exception body", !JsonSerializer.Serialize(failed).Contains("HIDDEN"));

        h.Reply = async (path, ct) => { if (path == "/kernel/status") await Task.Delay(Timeout.Infinite, ct); return Fixture(path); };
        var timer = System.Diagnostics.Stopwatch.StartNew();
        var timed = await ConsoleDiagnostics.CollectAsync(snapshot, api.GetAsync, timeout: TimeSpan.FromMilliseconds(60));
        check("A slow status request is bounded without losing faster sections", timed.Service["kernel"].Error == "Diagnostic request timed out."
            && timed.Service.Count(s => s.Value.State == "ok") == 3 && timer.Elapsed < TimeSpan.FromSeconds(2));
        using var cancelled = new CancellationTokenSource(); cancelled.Cancel(); int calls = h.Calls.Count;
        var stopped = await ConsoleDiagnostics.CollectAsync(snapshot, api.GetAsync, cancelled.Token);
        check("Cancelled export sends no further requests and keeps the local snapshot", h.Calls.Count == calls
            && stopped.Service.Values.All(s => s.Error == "Collection cancelled.") && stopped.Console.GetProperty("selected_device").GetString() == "TEST:01");
        h.Reply = (path, _) => Task.FromResult(path == "/device/get" ? "{\"code\":0,\"list\":{}}" : Fixture(path));
        var malformed = await ConsoleDiagnostics.CollectAsync(snapshot, api.GetAsync);
        check("Malformed diagnostic lists are unavailable rather than empty success", malformed.Service["devices"].State == "unavailable"
            && malformed.Service.Count(s => s.Value.State == "ok") == 3);
        h.Reply = (path, _) => Task.FromResult(path == "/kernel/status" ? "{\"code\":0,\"input\":\"direct-hid\",\"receiver\":\"legacy\"}" : Fixture(path));
        var legacy = await ConsoleDiagnostics.CollectAsync(snapshot, api.GetAsync);
        check("Older kernel diagnostics leave unsupported build and frame details unknown", !legacy.Partial
            && !legacy.Service["kernel"].Data!.Value.TryGetProperty("build_identity", out _)
            && !legacy.Service["kernel"].Data!.Value.TryGetProperty("receivers", out _));

        string folder = Path.Combine(Path.GetTempPath(), "imouse-diagnostics-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        try
        {
            string path = Path.Combine(folder, "report.json");
            await ConsoleDiagnostics.SaveAsync(path, report);
            using var parsed = JsonDocument.Parse(await File.ReadAllTextAsync(path));
            check("Diagnostic JSON round trips the selected snapshot and service health", parsed.RootElement.GetProperty("schema_version").GetInt32() == 4
                && parsed.RootElement.GetProperty("service").GetProperty("kernel").GetProperty("data").GetProperty("receivers")[0].GetProperty("receiver_state").GetString() == "failed");
            string original = await File.ReadAllTextAsync(path);
            bool refused = false;
            using (var locked = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.None))
                try { await ConsoleDiagnostics.SaveAsync(path, disconnected); }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { refused = true; }
            check("A failed export replacement preserves the previous report and removes its temporary file", refused
                && await File.ReadAllTextAsync(path) == original && Directory.GetFiles(folder).Length == 1);
            await ConsoleDiagnostics.SaveAsync(path, disconnected);
            check("A successful replacement saves a partial offline report", JsonDocument.Parse(await File.ReadAllTextAsync(path)).RootElement.GetProperty("partial").GetBoolean());
        }
        finally { Directory.Delete(folder, recursive: true); }
    }
}
