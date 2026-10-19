using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows.Interop;

namespace IMouse2;

internal static class CleanupDiagnosticsTests
{
    private static Task<JsonElement> HealthyService(string route, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        using var json = JsonDocument.Parse(route switch
        {
            "/kernel/status" => "{\"input\":\"fake\",\"receiver\":\"fake\"}",
            "/device/get" or "/config/usb/get" => "{\"list\":[]}",
            "/input/status" => "{\"protocol\":1,\"phones\":[]}",
            _ => throw new InvalidOperationException("Unexpected diagnostic route")
        });
        return Task.FromResult(json.RootElement.Clone());
    }

    internal static async Task RunAsync(Action<string, bool> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "imouse-cleanup-diagnostics-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        string latest = Path.Combine(folder, "last-input-cleanup.json");
        string warning = Path.Combine(folder, "last-input-cleanup-warning.json");
        var snapshot = JsonSerializer.SerializeToElement(new { disconnected = true });
        DateTimeOffset failedAt = DateTimeOffset.UtcNow.AddDays(-1);
        var failed = new[] { new ConnectionCleanupRecord(failedAt, "http://localhost:9923",
            new InputCloseResult([new("TEST:01", false, "HIDDEN raw error")], "HIDDEN failure")) };
        try
        {
            var missing = await CleanupDiagnostics.CollectAsync(folder, CancellationToken.None);
            check("Missing cleanup files stay unknown without being created", missing.Values.All(s => s.State == "missing" && s.Data is null) && !Directory.EnumerateFileSystemEntries(folder).Any());
            var noHistory = await ConsoleDiagnostics.CollectAsync(snapshot, HealthyService, dataPath: folder);
            check("A first-run profile without cleanup history does not make healthy diagnostics partial", !noHistory.Partial && noHistory.Local.Values.All(s => s.State == "missing"));
            int reads = 0;
            var skipped = await CleanupDiagnostics.CollectAsync(null, CancellationToken.None, (_, _) => { reads++; throw new Exception(); });
            check("Unspecified diagnostic profile never falls back to shared operator data", reads == 0 && skipped.Values.All(s => s.State == "skipped"));

            ConnectionCleanup.Save(folder, failed);
            ConnectionCleanup.Save(folder, [new(DateTimeOffset.UtcNow, "http://localhost:9923", new([]))]);
            byte[] latestBytes = File.ReadAllBytes(latest), warningBytes = File.ReadAllBytes(warning);
            var report = await ConsoleDiagnostics.CollectAsync(snapshot, null, dataPath: folder);
            var last = report.Local["last_input_cleanup"].Data!.Value;
            var old = report.Local["historical_cleanup_warning"].Data!.Value;
            check("One diagnostic export includes both clean latest and earlier unconfirmed cleanup", last.GetProperty("confirmed").GetBoolean() && !old.GetProperty("confirmed").GetBoolean());
            check("Saved cleanup is explicitly historical and retains its original event timestamp", old.GetProperty("scope").GetString()!.Contains("not current")
                && old.GetProperty("connections")[0].GetProperty("at").GetDateTimeOffset() == failedAt);
            check("Diagnostic receipt reads do not rewrite or remove either record", latestBytes.SequenceEqual(File.ReadAllBytes(latest)) && warningBytes.SequenceEqual(File.ReadAllBytes(warning)));
            check("Disconnected export preserves cleanup without requiring a service", report.Service.Values.All(s => s.State == "skipped")
                && report.Local.Values.All(s => s.State == "ok" && s.ObservedUtc >= report.StartedUtc && s.ObservedUtc <= report.FinishedUtc));

            var unsafeReceipt = JsonNode.Parse(warningBytes)!.AsObject();
            unsafeReceipt["token"] = "HIDDEN";
            var connection = unsafeReceipt["connections"]![0]!;
            connection["service"] = "http://user:HIDDEN@localhost:9923/private?token=HIDDEN";
            connection["failure"] = "HIDDEN raw service body";
            connection["phones"]![0]!["detail"] = "HIDDEN";
            connection["phones"]![0]!["token"] = "HIDDEN";
            File.WriteAllText(latest, unsafeReceipt.ToJsonString());
            var sanitized = await CleanupDiagnostics.CollectAsync(folder, CancellationToken.None);
            string serialized = JsonSerializer.Serialize(sanitized);
            check("Cleanup export strips URL credentials, raw failure/detail and unknown fields", sanitized["last_input_cleanup"].State == "ok"
                && !serialized.Contains("HIDDEN") && !serialized.Contains("private?") && !serialized.Contains("token"));
            check("Cleanup export retains the service origin and affected phone identity", sanitized["last_input_cleanup"].Data!.Value.GetProperty("connections")[0].GetProperty("service").GetString() == "http://localhost:9923"
                && sanitized["last_input_cleanup"].Data!.Value.GetProperty("connections")[0].GetProperty("phones")[0].GetProperty("id").GetString() == "TEST:01");

            File.WriteAllText(latest, "{broken HIDDEN");
            var malformed = await ConsoleDiagnostics.CollectAsync(snapshot, null, dataPath: folder);
            check("Malformed cleanup leaves the other receipt and console snapshot available", malformed.Partial && malformed.Local["last_input_cleanup"].State == "unavailable"
                && malformed.Local["historical_cleanup_warning"].State == "ok" && !JsonSerializer.Serialize(malformed).Contains("HIDDEN"));
            var localFailure = await ConsoleDiagnostics.CollectAsync(snapshot, HealthyService, dataPath: folder);
            check("A local receipt failure marks the export partial even when every service section succeeds", localFailure.Partial && localFailure.Service.Values.All(s => s.State == "ok"));
            File.WriteAllBytes(latest, warningBytes);
            using (var locked = new FileStream(latest, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            {
                var inaccessible = await CleanupDiagnostics.CollectAsync(folder, CancellationToken.None);
                check("Unreadable cleanup is reported independently without modifying the file", inaccessible["last_input_cleanup"].State == "unavailable" && inaccessible["historical_cleanup_warning"].State == "ok");
            }
            check("A refused cleanup read preserves the original bytes", warningBytes.SequenceEqual(File.ReadAllBytes(latest)));

            using (var large = new FileStream(latest, FileMode.Create, FileAccess.Write)) large.SetLength(CleanupDiagnostics.MaximumBytes + 1L);
            var oversized = await CleanupDiagnostics.CollectAsync(folder, CancellationToken.None);
            check("Oversized cleanup cannot exhaust an export or hide the other receipt", oversized["last_input_cleanup"].State == "unavailable" && oversized["historical_cleanup_warning"].State == "ok");
            var duplicate = Encoding.UTF8.GetString(warningBytes).Replace("\"confirmed\": false", "\"confirmed\": false, \"confirmed\": true");
            File.WriteAllText(latest, duplicate);
            check("Duplicate receipt properties cannot override an unconfirmed result", (await CleanupDiagnostics.CollectAsync(folder, CancellationToken.None))["last_input_cleanup"].State == "unavailable");

            var contradictory = JsonNode.Parse(warningBytes)!;
            contradictory["confirmed"] = true;
            File.WriteAllText(latest, contradictory.ToJsonString());
            check("A contradictory confirmed summary is never exported as release proof", (await CleanupDiagnostics.CollectAsync(folder, CancellationToken.None))["last_input_cleanup"].State == "unavailable");
            var tooMany = JsonNode.Parse(warningBytes)!;
            tooMany["connections"] = new JsonArray(Enumerable.Range(0, 33).Select(_ => tooMany["connections"]![0]!.DeepClone()).ToArray());
            File.WriteAllText(latest, tooMany.ToJsonString());
            check("Unbounded cleanup connection lists are refused", (await CleanupDiagnostics.CollectAsync(folder, CancellationToken.None))["last_input_cleanup"].State == "unavailable");
            var invalidCount = JsonNode.Parse(warningBytes)!;
            invalidCount["connections"]![0]!["phone_count"] = 0;
            File.WriteAllText(latest, invalidCount.ToJsonString());
            check("A receipt cannot hide an affected phone by understating its count", (await CleanupDiagnostics.CollectAsync(folder, CancellationToken.None))["last_input_cleanup"].State == "unavailable");
            var truncated = JsonNode.Parse(warningBytes)!;
            truncated["connections"]![0]!["phone_count"] = 65;
            File.WriteAllText(latest, truncated.ToJsonString());
            check("Saved phone-list truncation remains explicit", (await CleanupDiagnostics.CollectAsync(folder, CancellationToken.None))["last_input_cleanup"].Data!.Value
                .GetProperty("connections")[0].GetProperty("phones_truncated").GetBoolean());

            using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
            reads = 0;
            var stopped = await CleanupDiagnostics.CollectAsync(folder, cancelled.Token, (_, _) => { reads++; throw new Exception(); });
            check("Cancelled local collection does not begin a receipt read", reads == 0 && stopped.Values.All(s => s.State == "unavailable"));
            var held = new TaskCompletionSource<byte[]>(TaskCreationOptions.RunContinuationsAsynchronously);
            var arrived = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            using var budget = new CancellationTokenSource();
            var bounded = CleanupDiagnostics.CollectAsync(folder, budget.Token, (_, _) => { arrived.TrySetResult(); return held.Task; });
            await arrived.Task.WaitAsync(TimeSpan.FromSeconds(5)); budget.Cancel();
            var timed = await bounded.WaitAsync(TimeSpan.FromSeconds(2));
            check("Collection stops waiting for a file reader that ignores cancellation", timed.Values.All(s => s.State == "unavailable"));
            held.SetResult(warningBytes);

            File.WriteAllBytes(latest, latestBytes);
            string export = Path.Combine(folder, "export.json");
            await ConsoleDiagnostics.SaveAsync(export, report);
            using var exported = JsonDocument.Parse(await File.ReadAllTextAsync(export));
            check("Schema 4 export saves historical cleanup beside live service sections", exported.RootElement.GetProperty("schema_version").GetInt32() == 4
                && exported.RootElement.GetProperty("local").GetProperty("historical_cleanup_warning").GetProperty("data").GetProperty("confirmed").GetBoolean() == false);
        }
        finally { Directory.Delete(folder, true); }
    }
}

public partial class MainWindow
{
    internal static async Task CheckCleanupDiagnosticWindowAsync(Action<string, bool> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "imouse-window-diagnostic-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder, "settings.json"), "{\"address\":\"http://localhost:9923\",\"trackPointer\":false}");
        ConnectionCleanup.Save(folder, [new(DateTimeOffset.UtcNow, "http://localhost:9923", new([new("PROFILE:ONLY", false, "unconfirmed")]))]);
        var window = new MainWindow(_ => throw new InvalidOperationException("No connection permitted"), folder);
        try
        {
            window.DetachConnection(); // Actual disconnect transition cancels its former connection lifetime.
            var result = await window.CollectDiagnosticReportAsync();
            check("The actual window export reads its isolated receipt after disconnect", result.Local["historical_cleanup_warning"].State == "ok"
                && result.Local["historical_cleanup_warning"].Data!.Value.GetProperty("connections")[0].GetProperty("phones")[0].GetProperty("id").GetString() == "PROFILE:ONLY");
            check("Window diagnostic collection needs neither a native window nor a service", !window.IsVisible && new WindowInteropHelper(window).Handle == IntPtr.Zero
                && result.Service.Values.All(section => section.State == "skipped"));
        }
        finally { await window.CloseSafelyAsync(); Directory.Delete(folder, true); }
    }
}
