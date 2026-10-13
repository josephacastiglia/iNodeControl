using System.IO;
using System.Text;
using System.Text.Json;

namespace IMouse2;

/// <summary>The primary preferences file is authoritative. The launcher copy is
/// best effort, and is never written for an isolated candidate or test profile.</summary>
internal static class SettingsPersistence
{
    internal static string? Save(string dataPath, string? mirrorPath, string address,
        bool night, bool? trackPointer)
    {
        var values = new Dictionary<string, object> { ["address"] = address, ["theme"] = night ? "night" : "light" };
        if (trackPointer is { } track) values["trackPointer"] = track;
        byte[] bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(values));
        string primary = Path.GetFullPath(Path.Combine(dataPath, "settings.json"));
        WriteAtomic(primary, bytes);
        if (mirrorPath is null) return null;
        try
        {
            string mirror = Path.GetFullPath(Path.Combine(mirrorPath, "settings.json"));
            if (!string.Equals(primary, mirror, StringComparison.OrdinalIgnoreCase)) WriteAtomic(mirror, bytes);
            return null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            // The primary commit succeeded. Do not roll it back or tell the operator
            // their preferences were lost because an optional launcher copy failed.
            return "Preferences saved, but the launcher settings copy could not be updated: " + ex.Message;
        }
    }

    internal static void WriteAtomic(string path, byte[] bytes)
    {
        string folder = Path.GetDirectoryName(path)!;
        Directory.CreateDirectory(folder);
        string temp = Path.Combine(folder, ".imouse-settings-" + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            using (var stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                stream.Write(bytes);
                stream.Flush(flushToDisk: true);
            }
            // A sibling file keeps the replacement on one volume. Never truncate
            // the old settings before the complete new document has been flushed.
            File.Move(temp, path, overwrite: true);
        }
        finally
        {
            try { File.Delete(temp); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        }
    }
}
