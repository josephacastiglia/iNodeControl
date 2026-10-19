using System.Text.Json;

namespace IMouse2.Kernel;

internal static class DeviceStoreTests
{
    internal static void Run(Action<bool, string> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "imouse-binding-save-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        string file = Path.Combine(folder, "devices.json");
        var phones = new[]
        {
            new Phone { deviceid = "one", name = "Desk · 测试", gname = "未分组", pid = "ABCD", uid = "old", width = 500, height = 1080 },
            new Phone { deviceid = "two", name = "Other phone", pid = "ABCE", uid = "other" }
        };
        try
        {
            File.WriteAllBytes(file, JsonSerializer.SerializeToUtf8Bytes(phones));
            var store = new DeviceStore(file);
            byte[] original = File.ReadAllBytes(file);
            bool missing = false;
            try { store.Bind("missing", "1234", "ABCF", "new"); }
            catch (KeyNotFoundException) { missing = true; }
            check(missing && File.ReadAllBytes(file).SequenceEqual(original), "Unknown phone binding leaves the saved file unchanged");
            using (var reader = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            {
                bool refused = false;
                try { store.Bind("one", "1234", "ABCF", "new"); }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { refused = true; }
                check(refused, "Binding replacement failure is reported to the caller");
                check(store.All()[0].pid == "ABCD" && store.All()[0].uid == "old", "Failed binding save preserves the in-memory assignment");
                check(File.ReadAllBytes(file).SequenceEqual(original), "Failed binding save preserves the complete previous file");
                check(!Directory.EnumerateFiles(folder, "*.tmp").Any(), "Failed binding save removes its own temporary file");
            }
            store.Bind("one", "1234", "ABCF", "new");
            var reloaded = new DeviceStore(file).All();
            check(reloaded[0].vid == "1234" && reloaded[0].pid == "ABCF" && reloaded[0].uid == "new", "Binding save recovers after the replacement lock is released");
            check(JsonSerializer.Serialize(store.All()) == JsonSerializer.Serialize(reloaded), "Successful binding save publishes the same memory and disk snapshot");
            check(reloaded[0].name == phones[0].name && reloaded[0].gname == phones[0].gname && reloaded[0].width == 500 && reloaded[0].height == 1080,
                "Binding replacement preserves Unicode names and phone metadata");
            check(JsonSerializer.Serialize(reloaded[1]) == JsonSerializer.Serialize(phones[1]), "Binding replacement leaves other phones unchanged");
            reloaded[0].uid = "external edit";
            check(store.All()[0].uid == "new", "Caller snapshots cannot change saved or in-memory assignments");
            string created = Path.Combine(folder, "new data", "devices.json");
            var seeded = new DeviceStore(created, phones);
            seeded.Bind("one", "1234", "ABCF", "new");
            check(new DeviceStore(created).All()[0].uid == "new", "Validated binding snapshots can create a fresh saved file");
            check(!Directory.EnumerateFiles(folder, "*.tmp", SearchOption.AllDirectories).Any(), "Successful binding saves leave no temporary files");
        }
        finally { Directory.Delete(folder, recursive: true); }
    }
}
