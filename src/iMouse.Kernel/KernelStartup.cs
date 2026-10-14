using System.Globalization;
using System.Net;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace IMouse2.Kernel;

/// <summary>Parse and check saved startup inputs without enumerating boards, binding
/// a listener, creating directories, opening frame pipes or starting receivers.</summary>
internal sealed class KernelOptions
{
    private readonly Dictionary<string, string> _values = new(StringComparer.Ordinal);
    private readonly HashSet<string> _flags = new(StringComparer.Ordinal);
    private static readonly HashSet<string> Valued = ["--data-dir", "--input-pid", "--precise-delay",
        "--home-sequence", "--cast-name", "--phone-id", "--frame-pipe", "--receiver", "--receivers", "--receiver-runtime", "--hid-replies-pid"];
    internal string Prefix { get; private set; } = "http://127.0.0.1:9913/api/";
    internal string? HardwareMode { get; private set; }
    internal string[] HardwareArguments { get; private set; } = [];
    internal bool ValidateOnly => _flags.Contains("--validate-startup");
    internal HomeSequence Home { get; private set; }
    internal int PreciseDelayMs { get; private set; } = 7;
    internal string[] Allowed { get; private set; } = [];
    internal string[] ReplyBoards { get; private set; } = [];
    internal string DataDir => Path.GetFullPath(Value("--data-dir", Path.Combine(AppContext.BaseDirectory, "data")));
    internal string Value(string name, string fallback = "") => _values.GetValueOrDefault(name, fallback);
    internal static bool BoardId(string? text) => text is not null && Regex.IsMatch(text, "^[0-9A-Fa-f]{4}$");

    internal static KernelOptions Parse(string[] args)
    {
        var result = new KernelOptions(); bool prefixSeen = false;
        for (int i = 0; i < args.Length; i++)
        {
            string item = args[i];
            if (item.StartsWith("http", StringComparison.OrdinalIgnoreCase))
            {
                if (prefixSeen) throw new ArgumentException("Specify only one HTTP listener address.");
                result.Prefix = ValidatePrefix(item); prefixSeen = true; continue;
            }
            int equals = item.IndexOf('='); string name = equals < 0 ? item : item[..equals];
            if (Valued.Contains(name))
            {
                if (result._values.ContainsKey(name)) throw new ArgumentException("Repeated option: " + name);
                string value = equals >= 0 ? item[(equals + 1)..] : ++i < args.Length ? args[i] : "";
                if (string.IsNullOrWhiteSpace(value) || value.StartsWith("--")) throw new ArgumentException(name + " needs a value.");
                result._values.Add(name, value); continue;
            }
            if (item is "--legacy" or "--validate-startup")
            {
                if (!result._flags.Add(item)) throw new ArgumentException("Repeated option: " + item);
                continue;
            }
            if (item is "--hid-send" or "--hid-replay" or "--hid-caps")
            {
                if (result.HardwareMode is not null) throw new ArgumentException("Choose only one hardware command.");
                result.HardwareMode = item;
                int count = item == "--hid-caps" ? 0 : 2;
                if (args.Length - i - 1 < count) throw new ArgumentException(item + " needs a board PID and payload.");
                result.HardwareArguments = args.Skip(i + 1).Take(count).ToArray(); i += count;
                if (count > 0 && (!BoardId(result.HardwareArguments[0]) || string.IsNullOrWhiteSpace(result.HardwareArguments[1]) || result.HardwareArguments[1].StartsWith("--")))
                    throw new ArgumentException("Invalid hardware command arguments.");
                continue;
            }
            throw new ArgumentException(item == "--precise-movement"
                ? "--precise-movement is deprecated. Use --precise-delay <ms> or default."
                : "Unknown kernel option: " + item);
        }
        if (result.ValidateOnly && result.HardwareMode is not null) throw new ArgumentException("Startup validation cannot include a hardware command.");
        result.Home = InputRouter.ParseHomeSequence(result.Value("--home-sequence", "vendor"));
        if (result._values.TryGetValue("--precise-delay", out string? timing))
        {
            if (result._flags.Contains("--legacy")) throw new ArgumentException("Choose --precise-delay or --legacy, not both.");
            if (!int.TryParse(timing, NumberStyles.None, CultureInfo.InvariantCulture, out int delay) || delay is < 1 or > 15)
                throw new ArgumentException("--precise-delay must be an integer from 1 through 15 milliseconds.");
            result.PreciseDelayMs = delay;
        }
        else if (result._flags.Contains("--legacy")) result.PreciseDelayMs = 0;
        if (result._values.TryGetValue("--input-pid", out string? ids))
        {
            result.Allowed = ids.Split(',', StringSplitOptions.TrimEntries);
            if (result.Allowed.Any(id => !BoardId(id)) || result.Allowed.Distinct(StringComparer.OrdinalIgnoreCase).Count() != result.Allowed.Length)
                throw new ArgumentException("--input-pid needs distinct four-digit hexadecimal board IDs, separated by commas.");
        }
        _ = result.DataDir; // Check path syntax before any hardware work.
        if (result._values.TryGetValue("--hid-replies-pid", out string? replyIds))
        {
            result.ReplyBoards = replyIds.Split(',', StringSplitOptions.TrimEntries);
            if (result.HardwareMode is not null || result.ReplyBoards.Any(id => !BoardId(id))
                || result.ReplyBoards.Distinct(StringComparer.OrdinalIgnoreCase).Count() != result.ReplyBoards.Length
                || result.ReplyBoards.Any(id => !result.Allowed.Contains(id, StringComparer.OrdinalIgnoreCase)))
                throw new ArgumentException("--hid-replies-pid requires distinct enabled input board IDs and normal service mode.");
        }
        return result;
    }

    private static string ValidatePrefix(string value)
    {
        if (!Regex.IsMatch(value, @"^https?://(\[[^\]]+\]|[^/:?#@\s]+):[0-9]+(/[^?#]*)?$", RegexOptions.IgnoreCase)
            || !Uri.TryCreate(value, UriKind.Absolute, out var uri) || uri.Port is < 1 or > 65535 || uri.UserInfo.Length > 0)
            throw new ArgumentException("Listener address needs HTTP(S), an explicit valid port, and no credentials or query.");
        string prefix = value.EndsWith('/') ? value : value + "/";
        // Prefix collection validation does not start a listener or reserve the port.
        using var check = new HttpListener(); check.Prefixes.Add(prefix);
        return prefix;
    }
}

internal sealed record KernelConfiguration(KernelOptions Options, DeviceStore Store,
    List<PointerCalibration> Calibrations, List<ReceiverConfig> Receivers, string ReceiverPath, string RuntimePath)
{
    internal static KernelConfiguration Load(KernelOptions options)
    {
        string devicesPath = Path.Combine(options.DataDir, "devices.json");
        var phones = ReadList<Phone>(devicesPath);
        if (phones.Any(p => string.IsNullOrWhiteSpace(p.deviceid) || p.pid is null || p.uid is null
            || p.name is null || p.device_name is null || p.vid is null || p.version is null || p.gname is null
            || (p.pid.Length > 0 && !KernelOptions.BoardId(p.pid))))
            throw new ArgumentException("Invalid saved phone identity or board PID.");
        if (phones.Select(p => p.deviceid).Distinct(StringComparer.OrdinalIgnoreCase).Count() != phones.Count
            || phones.Where(p => p.pid.Length > 0).Select(p => p.pid).Distinct(StringComparer.OrdinalIgnoreCase).Count() != phones.Count(p => p.pid.Length > 0))
            throw new ArgumentException("Saved phone identities and bound board PIDs must be unique.");
        var store = new DeviceStore(devicesPath, phones);
        string calibrationFile = Path.Combine(options.DataDir, "pointer-calibration.json");
        var calibrations = File.Exists(calibrationFile) ? ReadList<PointerCalibration>(calibrationFile) : [];
        if (calibrations.Any(c => !KernelOptions.BoardId(c.Pid))) throw new ArgumentException("Invalid calibration board PID.");
        // Reuse the router's arithmetic and duplicate-calibration checks. Its constructor
        // and disposal never open transport; connections are created only on dispatch.
        using (var check = new InputRouter(store, options.Allowed, calibrations, preciseDelayMs: options.PreciseDelayMs, replyBoards: options.ReplyBoards)) { }

        List<ReceiverConfig> receivers;
        if (options.Value("--receivers") is { Length: > 0 } file) receivers = ReadList<ReceiverConfig>(Path.GetFullPath(file));
        else
        {
            string id = options.Value("--phone-id", "86:1D:4A:04:2F:F6");
            var phone = phones.SingleOrDefault(p => p.deviceid == id) ?? throw new ArgumentException("Default receiver phone is missing; provide a saved receiver configuration.");
            receivers = [new(id, phone.pid, options.Value("--cast-name", "iMouse2-C24C"), options.Value("--frame-pipe", "iMouse2-C24C-frames"), 7110, "02:49:4D:32:C2:4C")];
        }
        ReceiverFleet.Validate(receivers, phones);
        foreach (string pid in options.Allowed)
        {
            var receiver = receivers.SingleOrDefault(r => r.BoardPid.Equals(pid, StringComparison.OrdinalIgnoreCase));
            if (receiver is null || receiver.DeviceId is "*" or "" || receiver.DeviceId.StartsWith("unbound-", StringComparison.OrdinalIgnoreCase)
                || !calibrations.Any(c => c.Pid.Equals(pid, StringComparison.OrdinalIgnoreCase)))
                throw new ArgumentException("Enabled board " + pid + " needs an explicit receiver binding and valid calibration.");
        }
        string executable = options.Value("--receiver"), runtime = options.Value("--receiver-runtime");
        if (executable.Length > 0)
        {
            executable = Path.GetFullPath(executable);
            if (!File.Exists(executable)) throw new FileNotFoundException("Receiver executable is missing.", executable);
            if (runtime.Length == 0) throw new ArgumentException("--receiver requires an explicit --receiver-runtime directory.");
            runtime = Path.GetFullPath(runtime);
            ReceiverRuntime.ValidateFiles(runtime);
        }
        else if (runtime.Length > 0) throw new ArgumentException("--receiver-runtime requires --receiver.");
        return new(options, store, calibrations, receivers, executable, runtime);
    }

    internal object ValidationReport() => new
    {
        valid = true, scope = "saved configuration only", hardware_accessed = false, listener_started = false,
        receivers_started = false, settings_written = false, build = KernelDiagnostics.BuildIdentity,
        data_directory = Options.DataDir, address = Options.Prefix, allowed = Options.Allowed,
        hid_reply_boards = Options.ReplyBoards,
        precise_delay_ms = Options.PreciseDelayMs, home_sequence = Options.Value("--home-sequence", "vendor"),
        receiver_count = Receivers.Count, receiver_executable = ReceiverPath, receiver_runtime = RuntimePath,
        bindings_complete = Receivers.All(r => r.DeviceId is not ("*" or "") && !r.DeviceId.StartsWith("unbound-", StringComparison.OrdinalIgnoreCase)),
        limitations = new[] { "Physical bindings, targeting and mirroring are not assessed.",
            "Available ports, URL permissions and dependency loading are not tested.",
            ReceiverPath.Length == 0 ? "No receiver executable: frame-pipe hosting only." : "Runtime file presence is not a dependency or build attestation." }
    };

    internal static List<T> ReadList<T>(string path) where T : class
    {
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        CheckProperties(document.RootElement);
        var items = document.RootElement.Deserialize<List<T>>() ?? throw new ArgumentException(Path.GetFileName(path) + " must be an array.");
        if (items.Any(item => item is null)) throw new ArgumentException(Path.GetFileName(path) + " cannot contain null records.");
        return items;
    }
    private static void CheckProperties(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in value.EnumerateObject())
            {
                if (!seen.Add(property.Name)) throw new ArgumentException("Duplicate configuration property: " + property.Name);
                CheckProperties(property.Value);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array) foreach (var item in value.EnumerateArray()) CheckProperties(item);
    }
}
