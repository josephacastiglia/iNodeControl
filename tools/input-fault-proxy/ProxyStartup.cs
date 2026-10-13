using System.Text.Json;

namespace IMouse2.FaultProxy;

internal static class ProxyStartup
{
    internal static void Write(string path, string listen, string upstream)
    {
        string temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(temp, JsonSerializer.Serialize(new { pid = Environment.ProcessId, listen, upstream, at_utc = DateTimeOffset.UtcNow }));
            File.Move(temp, path, overwrite: false);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }

    internal static int SelfTest()
    {
        string folder = Path.Combine(Path.GetTempPath(), "imouse-proxy-receipt-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        try
        {
            string path = Path.Combine(folder, "ready.json");
            Write(path, "http://localhost:1/", "http://localhost:2");
            string original = File.ReadAllText(path);
            using var data = JsonDocument.Parse(original);
            if (data.RootElement.GetProperty("pid").GetInt32() != Environment.ProcessId
                || data.RootElement.GetProperty("listen").GetString() != "http://localhost:1/"
                || data.RootElement.GetProperty("upstream").GetString() != "http://localhost:2") throw new Exception("Wrong startup identity.");
            bool refused = false;
            try { Write(path, "changed", "changed"); } catch (IOException) { refused = true; }
            if (!refused || File.ReadAllText(path) != original || Directory.GetFiles(folder).Length != 1) throw new Exception("Existing startup record was not preserved.");
            Console.WriteLine("2 startup receipt checks passed; no listener or upstream connection opened.");
            return 0;
        }
        finally { Directory.Delete(folder, recursive: true); }
    }
}
