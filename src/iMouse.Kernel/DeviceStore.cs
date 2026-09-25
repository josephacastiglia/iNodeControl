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

    public List<Phone> All()
    {
        lock (_gate) return _phones.Select(Clone).ToList();
    }

    public void Bind(string id, string vid, string pid, string uid)
    {
        lock (_gate)
        {
            var phone = _phones.FirstOrDefault(p => p.deviceid == id);
            if (phone is null) throw new KeyNotFoundException(id);
            phone.vid = vid; phone.pid = pid; phone.uid = uid;
            Save();
        }
    }

    private void Save()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_path)!);
        File.WriteAllText(_path, JsonSerializer.Serialize(_phones, new JsonSerializerOptions { WriteIndented = true }));
    }

    private static Phone Clone(Phone p) => new()
    {
        deviceid = p.deviceid, name = p.name, device_name = p.device_name,
        width = p.width, height = p.height, imgw = p.imgw, imgh = p.imgh,
        vid = p.vid, pid = p.pid, uid = p.uid, version = p.version, gname = p.gname
    };
}
