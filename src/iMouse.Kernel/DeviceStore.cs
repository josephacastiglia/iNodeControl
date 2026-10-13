using System.Text.Json;

namespace IMouse2.Kernel;

public sealed class Phone
{
    public string deviceid { get; set; } = "";
    public string name { get; set; } = "";
    public string device_name { get; set; } = "iPhone";
    public int width { get; set; }
    public int height { get; set; }
    public int imgw { get; set; } = 500;
    public int imgh { get; set; } = 1080;
    public string vid { get; set; } = "";
    public string pid { get; set; } = "";
    public string uid { get; set; } = "";
    public string version { get; set; } = "";
    public string gname { get; set; } = "Ungrouped";
}

public sealed class DeviceStore
{
    private readonly string _path;
    private readonly object _gate = new();
    private List<Phone> _phones;

    public DeviceStore(string path)
    {
        _path = path;
        _phones = File.Exists(path)
            ? JsonSerializer.Deserialize<List<Phone>>(File.ReadAllText(path)) ?? []
            : [];
    }

    // Startup has already read and validated these bytes; do not reread a file
    // that another process could replace between validation and use.
    internal DeviceStore(string path, IEnumerable<Phone> phones)
    {
        _path = path;
        _phones = phones.Select(Clone).ToList();
    }

    public List<Phone> All()
    {
        lock (_gate) return _phones.Select(Clone).ToList();
    }

    public void Bind(string id, string vid, string pid, string uid)
    {
        lock (_gate)
        {
            var next = _phones.Select(Clone).ToList();
            var phone = next.FirstOrDefault(p => p.deviceid == id);
            if (phone is null) throw new KeyNotFoundException(id);
            phone.vid = vid; phone.pid = pid; phone.uid = uid;
            Save(next);
            _phones = next;
        }
    }

    private void Save(List<Phone> phones)
    {
        string path = Path.GetFullPath(_path);
        string folder = Path.GetDirectoryName(path)!;
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(phones, new JsonSerializerOptions { WriteIndented = true });
        Directory.CreateDirectory(folder);
        string temp = Path.Combine(folder, ".imouse-bindings-" + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            using (var stream = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                stream.Write(bytes);
                stream.Flush(flushToDisk: true);
            }
            File.Move(temp, path, overwrite: true);
        }
        finally
        {
            try { File.Delete(temp); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
        }
    }

    private static Phone Clone(Phone p) => new()
    {
        deviceid = p.deviceid, name = p.name, device_name = p.device_name,
        width = p.width, height = p.height, imgw = p.imgw, imgh = p.imgh,
        vid = p.vid, pid = p.pid, uid = p.uid, version = p.version, gname = p.gname
    };
}
