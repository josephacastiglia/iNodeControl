using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text.Json;

namespace IMouse2;

public sealed record DiagnosticSection(string State, DateTimeOffset ObservedUtc, double ElapsedMs,
    JsonElement? Data, string? Error);
public sealed record DiagnosticReport(int SchemaVersion, DateTimeOffset StartedUtc, DateTimeOffset FinishedUtc,
    bool Partial, string Notice, JsonElement Console, IReadOnlyDictionary<string, DiagnosticSection> Service,
    IReadOnlyDictionary<string, DiagnosticSection> Local);

/// <summary>Bounded, read-only collection. Each section retains its own outcome: a missing
/// service is useful diagnostic evidence and must not prevent saving the local snapshot.</summary>
public static class ConsoleDiagnostics
{
    public static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true, PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower
    };

    public static async Task<DiagnosticReport> CollectAsync(JsonElement snapshot,
        Func<string, CancellationToken, Task<JsonElement>>? get,
        CancellationToken ct = default, TimeSpan? timeout = null, string? dataPath = null)
    {
        var started = DateTimeOffset.UtcNow;
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(ct);
        budget.CancelAfter(timeout ?? TimeSpan.FromSeconds(5));
        var localTask = CleanupDiagnostics.CollectAsync(dataPath, budget.Token);
        var sections = new (string Name, string Route, Func<JsonElement, object> Project)[]
        {
            ("kernel", "/kernel/status", Kernel),
            ("devices", "/device/get", data => Rows(data, "list", DeviceFields)),
            ("boards", "/config/usb/get", data => Rows(data, "list", BoardFields)),
            ("input", "/input/status", data => new { protocol = Optional(data, "protocol"), phones = Rows(data, "phones", InputFields) })
        };
        async Task<KeyValuePair<string, DiagnosticSection>> Read((string Name, string Route, Func<JsonElement, object> Project) item)
        {
            var watch = Stopwatch.StartNew();
            DiagnosticSection Result(string state, JsonElement? data, string? error) =>
                new(state, DateTimeOffset.UtcNow, Math.Round(watch.Elapsed.TotalMilliseconds, 1), data, error);
            if (get is null) return new(item.Name, Result("skipped", null, "Console is disconnected; no service request was sent."));
            try
            {
                budget.Token.ThrowIfCancellationRequested();
                var raw = await get(item.Route, budget.Token).WaitAsync(budget.Token).ConfigureAwait(false);
                var safe = JsonSerializer.SerializeToElement(item.Project(raw), JsonOptions);
                return new(item.Name, Result("ok", safe, null));
            }
            catch (Exception ex)
            {
                // Never copy exception bodies/URLs into an export. Services can echo credentials.
                string error = ex switch
                {
                    OperationCanceledException => ct.IsCancellationRequested ? "Collection cancelled." : "Diagnostic request timed out.",
                    HttpRequestException http => http.StatusCode is { } status ? $"Service returned HTTP {(int)status}." : "Service could not be reached.",
                    ApiException api => $"Service refused diagnostic request (code {api.Code}).",
                    ObjectDisposedException => "Connection closed during collection.",
                    JsonException or InvalidDataException or InvalidOperationException => "Invalid diagnostic response.",
                    _ => "Diagnostic section could not be collected."
                };
                return new(item.Name, Result("unavailable", null, error));
            }
        }
        var results = (await Task.WhenAll(sections.Select(Read)).ConfigureAwait(false)).ToDictionary(x => x.Key, x => x.Value);
        var local = await localTask.ConfigureAwait(false);
        return new(4, started, DateTimeOffset.UtcNow, results.Values.Any(x => x.State != "ok") || local.Values.Any(x => x.State == "unavailable"),
            "Includes device identifiers, service address and recent activity; review before sharing. No screenshots or Send text box contents are collected. " +
            "Sections are sampled separately, not atomically. Missing fields are unknown. Cleanup receipts are historical, not current input state. Video timings describe receiver delivery and console bitmap updates, not physical display latency.",
            snapshot.Clone(), results, local);
    }

    public static async Task SaveAsync(string path, DiagnosticReport report, CancellationToken ct = default)
    {
        string full = Path.GetFullPath(path);
        string temp = Path.Combine(Path.GetDirectoryName(full)!, ".imouse-diagnostics-" + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            await File.WriteAllTextAsync(temp, JsonSerializer.Serialize(report, JsonOptions), ct).ConfigureAwait(false);
            ct.ThrowIfCancellationRequested();
            File.Move(temp, full, overwrite: true);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }

    // Use an allowlist, not a dump of service/config JSON. In particular, ownership tokens,
    // unknown future fields, credentials and hardware serials are never copied as fields.
    private static readonly string[] DeviceFields = ["deviceid", "name", "device_name", "gname", "uid", "vid", "pid", "state", "video_state", "receiver_name", "width", "height", "imgw", "imgh", "rotate", "version", "air_pid"];
    private static readonly string[] BoardFields = ["vid", "pid", "uid", "state"];
    private static readonly string[] InputFields = ["id", "owned", "active", "stopped", "releasing", "release_failed", "message", "generation", "lease_remaining_ms"];
    private static readonly string[] ReceiverFields = ["deviceid", "name", "receiver_pid", "receiver_restarts", "receiver_state", "receiver_message", "live", "frames", "frame_delivery", "frame_age_ms", "frame_session", "frame_message", "frame_pipe_connected"];
    private static readonly string[] BuildFields = ["version", "informational_version", "module_id", "sha256"];
    private static readonly string[] ProcessFields = ["pid", "started_utc", "uptime_seconds", "working_set_bytes", "private_bytes", "cpu_seconds"];

    private static object Kernel(JsonElement data)
    {
        var result = Pick(data, ["input", "input_protocol", "input_leases_required", "home_sequence", "receiver", "receiver_state", "receiver_message", "receiver_pid", "receiver_restarts", "frames", "live", "frame_delivery", "frame_age_ms", "frame_session", "frame_message", "frame_pipe_connected"]);
        if (!result.ContainsKey("input") || !result.ContainsKey("receiver")) throw new InvalidDataException();
        if (data.TryGetProperty("receivers", out _)) result["receivers"] = Rows(data, "receivers", ReceiverFields);
        if (data.TryGetProperty("build_identity", out var build)) result["build_identity"] = Pick(build, BuildFields);
        if (data.TryGetProperty("process", out var process)) result["process"] = Pick(process, ProcessFields);
        if (data.TryGetProperty("control_compatibility", out var controls))
            result["control_compatibility"] = Pick(controls, ["home_sequence", "home_sends_tab", "app_switcher", "phone_setting_detection"]);
        if (data.TryGetProperty("input_configuration", out var input))
            result["input_configuration"] = new { precise_movement_delay_ms = Optional(input, "precise_movement_delay_ms"),
                calibrations = Rows(input, "calibrations", ["pid", "enabled", "width", "height", "origin_x", "origin_y", "pixels_per_unit_x", "pixels_per_unit_y"]) };
        return result;
    }
    private static JsonElement? Optional(JsonElement data, string key) =>
        data.ValueKind == JsonValueKind.Object && data.TryGetProperty(key, out var value) && IsScalar(value) ? value.Clone() : null;
    private static bool IsScalar(JsonElement value) => value.ValueKind is JsonValueKind.Null or JsonValueKind.True or JsonValueKind.False or JsonValueKind.Number or JsonValueKind.String;
    private static Dictionary<string, object?> Pick(JsonElement row, string[] fields)
    {
        if (row.ValueKind != JsonValueKind.Object) throw new InvalidDataException();
        var result = new Dictionary<string, object?>();
        foreach (string field in fields)
            if (row.TryGetProperty(field, out var value))
            {
                if (!IsScalar(value)) throw new InvalidDataException();
                result[field] = value.ValueKind == JsonValueKind.String && value.GetString()!.Length > 1000
                    ? value.GetString()![..1000] + " [truncated]" : value.Clone();
            }
        return result;
    }
    private static object[] Rows(JsonElement data, string key, string[] fields)
    {
        if (data.ValueKind != JsonValueKind.Object || !data.TryGetProperty(key, out var rows)
            || rows.ValueKind != JsonValueKind.Array || rows.GetArrayLength() > 512) throw new InvalidDataException();
        return rows.EnumerateArray().Select(row => (object)Pick(row, fields)).ToArray();
    }

    public static object ProcessSnapshot()
    {
        using var process = Process.GetCurrentProcess();
        return new { pid = process.Id, started_utc = process.StartTime.ToUniversalTime(),
            uptime_seconds = (DateTime.UtcNow - process.StartTime.ToUniversalTime()).TotalSeconds,
            working_set_bytes = process.WorkingSet64, private_bytes = process.PrivateMemorySize64,
            cpu_seconds = process.TotalProcessorTime.TotalSeconds };
    }
}
