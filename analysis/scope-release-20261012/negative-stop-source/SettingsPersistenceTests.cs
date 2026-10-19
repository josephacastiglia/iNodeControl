using System.IO;
using System.Text;
using System.Text.Json;

namespace IMouse2;

internal static class SettingsPersistenceTests
{
    internal static void Run(Action<string, bool> check)
    {
        string root = Path.Combine(Path.GetTempPath(), "imouse-settings-save-" + Guid.NewGuid().ToString("N"));
        string data = Path.Combine(root, "isolated data"), mirror = Path.Combine(root, "launcher copy");
        string file = Path.Combine(data, "settings.json"), copy = Path.Combine(mirror, "settings.json");
        bool Has(string path, string key, string value)
        {
            using var doc = JsonDocument.Parse(File.ReadAllBytes(path));
            return doc.RootElement.GetProperty(key).ToString() == value;
        }
        bool NoTemps() => !Directory.EnumerateFiles(root, "*.tmp", SearchOption.AllDirectories).Any();
        bool Failed(Action action)
        {
            try { action(); return false; }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return true; }
        }
        try
        {
            check("Isolated preferences create only their requested directory",
                SettingsPersistence.Save(data, null, "http://localhost:9923", false, false) is null
                && File.Exists(file) && !Directory.Exists(mirror));
            check("Preferences preserve explicit hover-off without adding a BOM",
                Has(file, "trackPointer", "False") && !File.ReadAllBytes(file).Take(3).SequenceEqual(Encoding.UTF8.Preamble.ToArray()));
            SettingsPersistence.Save(data, mirror, "http://localhost:9924", true, null);
            using (var doc = JsonDocument.Parse(File.ReadAllBytes(file)))
                check("Legacy preference shape remains address and theme only",
                    doc.RootElement.EnumerateObject().Count() == 2 && Has(file, "theme", "night"));
            check("Successful launcher copy has the same complete bytes", File.ReadAllBytes(file).SequenceEqual(File.ReadAllBytes(copy)));
            byte[] before = File.ReadAllBytes(file), copyBefore = File.ReadAllBytes(copy);
            // This reader permits a naive overwrite, but forbids replacing its open
            // file. It catches regression to truncate-in-place rather than merely
            // testing a lock that would reject either implementation before writing.
            using (var reader = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            {
                check("Failed primary replacement reports a save failure", Failed(() => SettingsPersistence.Save(data, mirror, "http://localhost:9925", false, true)));
                check("Failed primary replacement preserves the old bytes", File.ReadAllBytes(file).SequenceEqual(before));
                check("Failed primary replacement never writes the launcher copy", File.ReadAllBytes(copy).SequenceEqual(copyBefore));
                check("Failed primary replacement cleans its temporary file", NoTemps());
            }
            check("Saving succeeds once the primary file is available",
                SettingsPersistence.Save(data, mirror, "http://localhost:9925", false, true) is null && Has(file, "address", "http://localhost:9925"));
            before = File.ReadAllBytes(copy);
            using (var reader = new FileStream(copy, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            {
                string? warning = SettingsPersistence.Save(data, mirror, "http://localhost:9926", true, false);
                check("Mirror failure explicitly reports that primary preferences were saved", warning?.StartsWith("Preferences saved, but the launcher settings copy") == true);
                check("Mirror failure keeps the successful primary commit", Has(file, "address", "http://localhost:9926"));
                check("Mirror failure preserves the previous launcher copy", File.ReadAllBytes(copy).SequenceEqual(before));
                check("Mirror failure cleans its temporary file", NoTemps());
            }
            check("Later save repairs the launcher copy",
                SettingsPersistence.Save(data, mirror, "http://localhost:9926", true, false) is null && File.ReadAllBytes(file).SequenceEqual(File.ReadAllBytes(copy)));
            check("A shared primary and mirror directory is supported",
                SettingsPersistence.Save(data, Path.Combine(data, "."), "http://localhost:9927", false, null) is null && Has(file, "address", "http://localhost:9927"));
            string blocked = Path.Combine(root, "not a folder");
            File.WriteAllText(blocked, "keep this file");
            copyBefore = File.ReadAllBytes(copy);
            check("Unusable primary directory fails without writing the mirror",
                Failed(() => SettingsPersistence.Save(blocked, mirror, "http://localhost:9928", false, null)) && File.ReadAllBytes(copy).SequenceEqual(copyBefore));
            check("Unusable mirror directory leaves the primary saved with a warning",
                SettingsPersistence.Save(data, blocked, "http://localhost:9929", true, null) is not null && Has(file, "address", "http://localhost:9929"));
            check("Save failures preserve unrelated files and leave no temporary files", File.ReadAllText(blocked) == "keep this file" && NoTemps());
        }
        finally { if (Directory.Exists(root)) Directory.Delete(root, recursive: true); }
    }
}
