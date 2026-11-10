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

/// <summary>The saved phone/board assignments, fixed for the life of the kernel. Changing one means
/// stopping the kernel, editing devices.json and starting it again through startup validation.</summary>
public sealed class DeviceStore
{
    private readonly List<Phone> _phones;

    public DeviceStore(string path)
    {
        _phones = File.Exists(path)
            ? JsonSerializer.Deserialize<List<Phone>>(File.ReadAllText(path)) ?? []
            : [];
    }

    // Startup has already read and validated these bytes; do not reread a file
    // that another process could replace between validation and use.
    internal DeviceStore(IEnumerable<Phone> phones) => _phones = phones.Select(Clone).ToList();

    public List<Phone> All() => _phones.Select(Clone).ToList();

    private static Phone Clone(Phone p) => new()
    {
        deviceid = p.deviceid, name = p.name, device_name = p.device_name,
        width = p.width, height = p.height, imgw = p.imgw, imgh = p.imgh,
        vid = p.vid, pid = p.pid, uid = p.uid, version = p.version, gname = p.gname
    };
}
