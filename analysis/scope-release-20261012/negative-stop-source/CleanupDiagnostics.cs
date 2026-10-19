using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;

namespace IMouse2;

/// <summary>Read only the active profile's bounded cleanup receipts. Historical
/// service confirmations are never presented as the phone's current state.</summary>
internal static class CleanupDiagnostics
{
    internal const int MaximumBytes = 4 * 1024 * 1024;
    internal const string Scope = "Historical cleanup receipts from this console profile; not current ownership or physical button state. Sections may have been saved at different times.";

    internal static async Task<IReadOnlyDictionary<string, DiagnosticSection>> CollectAsync(string? dataPath,
        CancellationToken ct, Func<string, CancellationToken, Task<byte[]>>? read = null)
    {
        var files = new[] { (Key: "last_input_cleanup", File: "last-input-cleanup.json"),
            (Key: "historical_cleanup_warning", File: "last-input-cleanup-warning.json") };
        async Task<KeyValuePair<string, DiagnosticSection>> Section(string key, string name)
        {
            var watch = Stopwatch.StartNew();
            DiagnosticSection Result(string state, JsonElement? data, string? error) =>
                new(state, DateTimeOffset.UtcNow, Math.Round(watch.Elapsed.TotalMilliseconds, 1), data, error);
            if (dataPath is null) return new(key, Result("skipped", null, "No active profile was supplied; no cleanup receipt was read."));
            try
            {
                ct.ThrowIfCancellationRequested();
                // Opening a redirected profile can block synchronously. Do not do it
                // on WPF's thread, and stop waiting when the collection budget ends.
                string path = Path.Combine(dataPath, name);
                byte[] bytes = await Task.Run(() => (read ?? ReadBoundedAsync)(path, ct), ct).WaitAsync(ct).ConfigureAwait(false);
                if (bytes.Length > MaximumBytes) throw new InvalidDataException();
                var data = Project(bytes);
                return new(key, Result("ok", data, null));
            }
            catch (Exception ex)
            {
                if (ex is FileNotFoundException or DirectoryNotFoundException)
                    return new(key, Result("missing", null, "No saved cleanup receipt is present; this does not confirm release."));
                string error = ex switch
                {
                    OperationCanceledException => "Cleanup receipt collection cancelled or timed out.",
                    JsonException or InvalidDataException or InvalidOperationException or FormatException or KeyNotFoundException => "Cleanup receipt is invalid or exceeds its limits.",
                    _ => "Cleanup receipt could not be read."
                };
                // Do not include exception bodies, paths or raw receipt fields.
                return new(key, Result("unavailable", null, error));
            }
        }
        return (await Task.WhenAll(files.Select(f => Section(f.Key, f.File))).ConfigureAwait(false))
            .ToDictionary(pair => pair.Key, pair => pair.Value);
    }

    private static async Task<byte[]> ReadBoundedAsync(string path, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0) throw new InvalidDataException();
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read,
            FileShare.ReadWrite | FileShare.Delete, 8192, FileOptions.Asynchronous | FileOptions.SequentialScan);
        if (stream.Length > MaximumBytes) throw new InvalidDataException();
        using var output = new MemoryStream();
        byte[] buffer = new byte[8192];
        while (true)
        {
            int count = await stream.ReadAsync(buffer, ct).ConfigureAwait(false);
            if (count == 0) return output.ToArray();
            if (output.Length + count > MaximumBytes) throw new InvalidDataException();
            output.Write(buffer, 0, count);
        }
    }

    private static JsonElement Project(byte[] bytes)
    {
        using var document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 16 });
        var root = document.RootElement;
        UniqueProperties(root);
        bool confirmed = root.GetProperty("confirmed").GetBoolean();
        var connections = Array(root, "connections", 32);
        var projected = connections.EnumerateArray().Select(connection =>
        {
            bool released = connection.GetProperty("confirmed").GetBoolean();
            var failure = connection.GetProperty("failure");
            if (failure.ValueKind is not (JsonValueKind.String or JsonValueKind.Null)) throw new InvalidDataException();
            bool failed = failure.ValueKind == JsonValueKind.String;
            int count = connection.GetProperty("phone_count").GetInt32();
            var phones = Array(connection, "phones", 64);
            if (count < phones.GetArrayLength()) throw new InvalidDataException();
            var selected = phones.EnumerateArray().Select(phone => new
            {
                id = Text(phone, "id", 129), confirmed = phone.GetProperty("confirmed").GetBoolean()
            }).ToArray();
            if (released && (failed || selected.Any(phone => !phone.confirmed))) throw new InvalidDataException();
            return new
            {
                at = connection.GetProperty("at").GetDateTimeOffset(),
                service = Service(Text(connection, "service", 2048)), confirmed = released,
                failure = failed ? "Cleanup did not complete with confirmation." : null,
                phone_count = count, phones_truncated = count > selected.Length, phones = selected
            };
        }).ToArray();
        if (confirmed != projected.All(connection => connection.confirmed)) throw new InvalidDataException();
        return JsonSerializer.SerializeToElement(new
        {
            scope = Scope, recorded_at = root.GetProperty("recorded_at").GetDateTimeOffset(), confirmed,
            receipt_sha256 = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(), connections = projected
        }, ConsoleDiagnostics.JsonOptions);
    }

    private static JsonElement Array(JsonElement item, string name, int maximum)
    {
        var value = item.GetProperty(name);
        if (value.ValueKind != JsonValueKind.Array || value.GetArrayLength() > maximum) throw new InvalidDataException();
        return value;
    }

    private static string Text(JsonElement item, string name, int maximum)
    {
        var value = item.GetProperty(name);
        if (value.ValueKind != JsonValueKind.String || value.GetString() is not { Length: > 0 } text || text.Length > maximum)
            throw new InvalidDataException();
        return text;
    }

    private static string Service(string text)
    {
        if (!Uri.TryCreate(text, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https")) throw new InvalidDataException();
        return new UriBuilder(uri.Scheme, uri.Host, uri.Port).Uri.GetLeftPart(UriPartial.Authority);
    }

    private static void UniqueProperties(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in value.EnumerateObject())
            {
                if (!names.Add(property.Name)) throw new InvalidDataException();
                UniqueProperties(property.Value);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
            foreach (var child in value.EnumerateArray()) UniqueProperties(child);
    }
}
