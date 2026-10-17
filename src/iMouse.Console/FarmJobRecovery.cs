using System.IO;
using System.Text.Json;

namespace IMouse2;

internal sealed record FarmJobBookmark(string Id, string Mode, string Action, bool OwnsInput);

internal sealed class FarmJobRecovery(string folder)
{
    private string FilePath => Path.Combine(folder, "farm-pending-job.json");
    internal FarmJobBookmark? Load()
    {
        if (!File.Exists(FilePath)) return null;
        var bookmark = JsonSerializer.Deserialize<FarmJobBookmark?>(File.ReadAllBytes(FilePath));
        if (bookmark is not null && (!Guid.TryParse(bookmark.Id, out _) || bookmark.Mode is not ("simulate" or "live") || string.IsNullOrWhiteSpace(bookmark.Action)))
            throw new InvalidOperationException("Saved farm job is invalid; no new job will start until it is reconciled.");
        return bookmark;
    }
    internal void Save(FarmJobBookmark? bookmark) => SettingsPersistence.WriteAtomic(FilePath, JsonSerializer.SerializeToUtf8Bytes(bookmark));
}
