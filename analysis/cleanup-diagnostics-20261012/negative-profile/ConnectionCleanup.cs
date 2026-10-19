using System.IO;
using System.Text.Json;

namespace IMouse2;

internal sealed record ConnectionCleanupRecord(DateTimeOffset RecordedAt, string Service, InputCloseResult Result);

/// <summary>Tracks retired clients until cleanup finishes, including rapid reconnects.</summary>
internal sealed class ConnectionCleanup
{
    private readonly object _gate = new();
    private readonly Dictionary<Task<InputCloseResult>, string> _pending = new();
    private readonly Queue<ConnectionCleanupRecord> _history = new();

    internal void Retire(ApiClient? api)
    {
        if (api is null) return;
        var service = new UriBuilder(api.Endpoint.Scheme, api.Endpoint.Host, api.Endpoint.Port).Uri.GetLeftPart(UriPartial.Authority);
        lock (_gate) _pending.TryAdd(api.CloseAsync(), service);
    }

    internal async Task<IReadOnlyList<ConnectionCleanupRecord>> DrainAsync()
    {
        while (true)
        {
            KeyValuePair<Task<InputCloseResult>, string>[] tasks;
            lock (_gate)
            {
                tasks = _pending.ToArray();
                if (tasks.Length == 0) return _history.ToArray();
            }
            await Task.WhenAll(tasks.Select(p => p.Key)).ConfigureAwait(false);
            lock (_gate)
                foreach (var task in tasks)
                    if (_pending.Remove(task.Key))
                    {
                        _history.Enqueue(new(DateTimeOffset.UtcNow, task.Value, task.Key.Result));
                        while (_history.Count > 32) _history.Dequeue();
                    }
        }
    }

    internal static string? Save(string dataPath, IReadOnlyList<ConnectionCleanupRecord> records)
    {
        if (records.Count == 0) return null;
        try
        {
            static string Clip(string text, int max) => text.Length <= max ? text : text[..max] + "…";
            var receipt = new
            {
                recorded_at = DateTimeOffset.UtcNow,
                confirmed = records.All(r => r.Result.Confirmed),
                // These are summaries, never lease tokens or typed content.
                connections = records.TakeLast(32).Select(r => new
                {
                    at = r.RecordedAt, service = Clip(r.Service, 512), confirmed = r.Result.Confirmed,
                    failure = r.Result.Failure is not null ? "Cleanup did not complete with confirmation." : null,
                    phone_count = r.Result.Phones.Count,
                    phones = r.Result.Phones.Take(64).Select(p => new { id = Clip(p.Id, 128), confirmed = p.Confirmed,
                        detail = p.Confirmed ? "No managed lease remains or the service confirmed release." : "Release unconfirmed; inspect this phone." })
                })
            };
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(receipt, new JsonSerializerOptions { WriteIndented = true });
            SettingsPersistence.WriteAtomic(Path.Combine(dataPath, "last-input-cleanup.json"), bytes);
            // A later clean close must not silently erase evidence of an earlier
            // unconfirmed release. This is a historical warning, not current status.
            if (!receipt.confirmed) SettingsPersistence.WriteAtomic(Path.Combine(dataPath, "last-input-cleanup-warning.json"), bytes);
            return null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        { return "Input cleanup finished, but its diagnostic record could not be saved: " + ex.Message; }
    }
}
