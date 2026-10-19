using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using IMouse2;
using IMouse2.Kernel;

namespace IMouse2.Harness;

// No sockets, native handles, App/MainWindow startup, real IDs or HID connection factory.
// ApiClient's ownership:false mode characterizes text conversion, not lease behavior.
static class KeyboardReports
{
    const string Id = "SIM:KEYBOARD";
    const string Clear = "A200000000000000";
    const string SpaceDown = "A2002C0000000000";
    static readonly List<object> Runs = [];
    static readonly List<object> Checks = [];

    static void Check(string name, bool passed)
    {
        Checks.Add(new { name, passed });
        Console.WriteLine($"{(passed ? "PASS" : "FAIL")} {name}");
        if (!passed) throw new InvalidOperationException(name);
    }

    static async Task<int> Main(string[] args)
    {
        if (args.Length != 1) throw new ArgumentException("One new output directory is required.");
        string output = Path.GetFullPath(args[0]);
        if (Directory.Exists(output)) throw new IOException("Refusing to overwrite an existing run.");
        Directory.CreateDirectory(output);
        var binaries = new[]
        {
            new { name = "candidate b0708e3", path = typeof(ApiClient).Assembly.Location,
                  expected = "E5A51FC6204566FA3B48C650FC239A42B158217D8045D2712850173980303AC3" },
            new { name = "release kernel", path = typeof(InputRouter).Assembly.Location,
                  expected = "BD1A68168E9270F029336CF8E13FF85E9B15FD67951EF545D1E973C2BFE634FC" }
        }.Select(b => new { b.name, b.path, b.expected,
            actual = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(b.path))) }).ToArray();
        int exit = 0;
        string? error = null;
        try
        {
            foreach (var b in binaries) Check(b.name + " binary matches recorded hash", b.actual == b.expected);
            Check("candidate chunk size is 12", ApiClient.TextChunk == 12);
            // Explicit usage sequence is independent of the inverted Ascii decoder.
            var expected = new[] { "A2020B0000000000", "A2000C0000000000", SpaceDown,
                "A200170000000000", "A2000B0000000000", "A200080000000000",
                "A200150000000000", "A200080000000000" };
            await using (var rig = new Rig(output, "first-and-repeat"))
            {
                string[] first = await Text(rig, "first", "Hi there");
                Check("Hi there emits the eight explicit expected key-down reports", Downs(first).SequenceEqual(expected));
                string[] repeat = await Text(rig, "repeat-on-same-router", "Hi there");
                Check("first and repeated sends emit byte-identical keyboard reports", first.SequenceEqual(repeat));
            }
            await using (var rig = new Rig(output, "spaces"))
            {
                await Text(rig, "leading-repeated-trailing", " Hi  there ");
                await Text(rig, "shift-released-before-spaces", "AB C D");
                await Text(rig, "space-at-end-of-first-chunk", "ABCDEFGHIJK there x");
                await Text(rig, "space-at-start-of-second-chunk", "ABCDEFGHIJKL there x");
            }
            await using (var rig = new Rig(output, "separate"))
            {
                var reports = new List<string>();
                foreach (string text in new[] { "Hi", " ", "there" })
                    reports.AddRange(await Text(rig, "separate-" + text.Length + "-" + reports.Count, text));
                Check("separately submitted Hi / space / there has the same eight key downs", Downs(reports).SequenceEqual(expected));
            }
            await using (var rig = new Rig(output, "after-enter"))
            {
                await rig.Api.CommandAsync("/key/sendkey", new() { ["id"] = Id, ["fn_key"] = "Enter" });
                var reports = await Text(rig, "after-enter", "Hi there");
                Check("preceding Enter does not change the text keyboard reports", Downs(reports).SequenceEqual(expected));
            }
            await using (var rig = new Rig(output, "cancel-at-space"))
            {
                using var cancel = new CancellationTokenSource();
                rig.Board.OnReport = hex => { if (hex == SpaceDown) cancel.Cancel(); };
                var result = await rig.Api.SendTextAsync(Id, "Hi there", cancel.Token);
                rig.Board.OnReport = null;
                var reports = rig.Board.All();
                Save(output, "cancel-at-space", reports, rig.Wire.Texts, result);
                Check("cancellation at Space remains cancelled, not completed", result.End == InputEnd.Cancelled);
                Check("no letters after Space are emitted following cancellation", Downs(reports.Select(r => r.Hex)).SequenceEqual(expected.Take(3)));
                Check("cancellation cleanup ends with a neutral keyboard report", reports[^1].Hex == Clear);
            }
        }
        catch (Exception ex) { exit = 1; error = ex.ToString(); Console.Error.WriteLine(error); }
        var report = new { at = DateTimeOffset.Now, offline = true, physicalPhoneTest = false,
            boundary = "IHidTransport.SendAsync argument, not a capture from the physical USB board or iOS",
            limitations = new[] { "No WPF click path", "No HTTP socket or lease protocol", "No board firmware or iOS/FKA emulation",
                "The reused decoder inverts the kernel map; the explicit Hi there bytes and report framing are checked separately" },
            binaries, checks = Checks, runs = Runs, error, exit };
        File.WriteAllText(Path.Combine(output, "results.json"), JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));
        return exit;
    }

    static IEnumerable<string> Downs(IEnumerable<string> reports) => reports.Where(h => h.StartsWith("A2") && h.Substring(4, 2) != "00");

    static async Task<string[]> Text(Rig rig, string name, string text)
    {
        int before = rig.Board.Count, sent = rig.Wire.Texts.Count;
        var result = await rig.Api.SendTextAsync(Id, text);
        var reports = rig.Board.All().Skip(before).ToArray();
        string[] hex = reports.Select(r => r.Hex).ToArray();
        string[] chunks = rig.Wire.Texts.Skip(sent).ToArray();
        Save(rig.Output, name, reports, chunks, result);
        Check(name + ": payload preserves every character and space", string.Concat(chunks) == text);
        Check(name + ": completed; one key-down per requested character", result.End == InputEnd.Completed && Downs(hex).Count() == text.Length);
        Check(name + ": decoder contains the same characters", HidText.Decode(hex) == text);
        Check(name + ": each stroke is neutral / down / neutral, with no hidden prefix key",
            hex.Length == text.Length * 3 && Enumerable.Range(0, text.Length).All(i =>
                hex[3 * i] == Clear && hex[3 * i + 2] == Clear && hex[3 * i + 1].StartsWith("A2") &&
                hex[3 * i + 1].Substring(6) == "0000000000"));
        Check(name + ": one plain usage-44 press for each space", hex.Count(h => h == SpaceDown) == text.Count(c => c == ' '));
        return hex;
    }

    static void Save(string output, string name, Recorded[] reports, IEnumerable<string> chunks, TextDelivery result)
    {
        File.WriteAllLines(Path.Combine(output, name + ".jsonl"), reports.Select(r => JsonSerializer.Serialize(r)), new UTF8Encoding(false));
        Runs.Add(new { name, chunks = chunks.ToArray(), result = new { end = result.End.ToString(), result.Total,
            result.ConfirmedCharacters, result.Sent, result.Confirmed, result.Chunks,
            failureType = result.Failure?.GetType().Name, failureMessage = result.Failure?.Message }, reportCount = reports.Length,
            spaceHoldsMs = reports.Select((r, i) => (r, i)).Where(p => p.r.Hex == SpaceDown && p.i + 1 < reports.Length)
                .Select(p => Math.Round(reports[p.i + 1].Ms - p.r.Ms, 3)).ToArray() });
    }

    sealed record Recorded(int Index, double Ms, string Hex);
    sealed class CaptureBoard : IHidTransport
    {
        readonly List<Recorded> _reports = [];
        readonly Stopwatch _time = Stopwatch.StartNew();
        public Action<string>? OnReport;
        public int Count => _reports.Count;
        public Recorded[] All() => _reports.ToArray();
        public Task SendAsync(byte[] data, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            if (data.Length != 8) throw new ArgumentException("Invalid report length");
            string hex = Convert.ToHexString(data);
            _reports.Add(new(_reports.Count, _time.Elapsed.TotalMilliseconds, hex));
            OnReport?.Invoke(hex);
            return Task.CompletedTask;
        }
        public void Dispose() { }
    }

    sealed class InProcessWire(InputRouter router) : HttpMessageHandler
    {
        public readonly List<string> Texts = [];
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            if (request.Method != HttpMethod.Post || request.RequestUri?.Host != "keyboard.invalid")
                throw new InvalidOperationException("Unexpected request; no networking is implemented.");
            using var doc = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));
            var root = doc.RootElement;
            if (root.GetProperty("fun").GetString() != "/key/sendkey") throw new InvalidOperationException("Only keyboard characterization is permitted.");
            var data = root.GetProperty("data");
            if (data.GetProperty("id").GetString() != Id) throw new InvalidOperationException("Only the simulated ID is permitted.");
            if (data.TryGetProperty("key", out var key)) Texts.Add(key.GetString()!);
            object result = await router.DispatchAsync("/key/sendkey", data, ct);
            return new(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(new { status = 200, data = result }), Encoding.UTF8, "application/json") };
        }
    }

    sealed class Rig : IAsyncDisposable
    {
        public string Output { get; }
        public readonly CaptureBoard Board = new();
        public readonly InProcessWire Wire;
        public readonly ApiClient Api;
        readonly InputRouter _router;
        public Rig(string output, string name)
        {
            Output = output;
            string devices = Path.Combine(output, name + "-simulated-devices.json");
            File.WriteAllText(devices, JsonSerializer.Serialize(new[] { new Phone { deviceid = Id, pid = "F001", uid = "SIM" } }));
            _router = new InputRouter(new DeviceStore(devices), ["F001"], [new PointerCalibration("F001", 500, 1080, 14, 14, 5, 5)], _ => Board);
            Wire = new(_router);
            Api = new("http://keyboard.invalid:9999", Wire, ownership: false);
        }
        public async ValueTask DisposeAsync() { await Api.DisposeAsync(); _router.Dispose(); }
    }
}
