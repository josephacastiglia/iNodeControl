using System.IO;
using IMouse2.Kernel;

namespace IMouse2.Harness;

/// <summary>
/// What a focused iOS text field would receive from a stream of keyboard reports (A2 family).
/// A report with no modifier or Shift only types its character, Tab included (a focused text
/// field inserts a tab). A report carrying Left GUI (Command) or the vendor byte-7 flag is a
/// shortcut and types nothing; it is shown as [GUI+x] or [flag02+x]. Releases type nothing.
/// The character map is the kernel's own HidProtocol.Ascii, inverted, so it cannot drift from it.
/// This models the field only; whether iOS then acts on a shortcut is a phone question.
/// </summary>
static class HidText
{
    private static readonly Dictionary<(byte Modifier, byte Usage), char> Typed = Build();

    private static Dictionary<(byte, byte), char> Build()
    {
        var map = new Dictionary<(byte, byte), char>();
        foreach (char c in Enumerable.Range(32, 95).Select(i => (char)i).Append('\t'))
            map.TryAdd(HidProtocol.Ascii(c), c);
        return map;
    }

    public static string Decode(IEnumerable<string> hexReports)
    {
        var text = new System.Text.StringBuilder();
        foreach (string hex in hexReports)
        {
            if (!hex.StartsWith("A2") || hex.Length < 16) continue;
            byte modifier = Convert.ToByte(hex.Substring(2, 2), 16), usage = Convert.ToByte(hex.Substring(4, 2), 16), flag = Convert.ToByte(hex.Substring(14, 2), 16);
            if (usage == 0) continue;                                      // a release, or a modifier/flag on its own
            char? letter = (usage is >= 4 and <= 29) ? (char)('a' + usage - 4) : null;
            string key = letter?.ToString() ?? $"0x{usage:X2}";
            if (flag != 0) { text.Append($"[flag{flag:X2}+{key}]"); continue; }
            if ((modifier & 0x88) != 0) { text.Append($"[GUI+{key}]"); continue; }
            text.Append(Typed.TryGetValue((modifier, usage), out char c) ? c.ToString() : $"[{modifier:X2}:{usage:X2}]");
        }
        return text.ToString();
    }

    /// <summary>
    /// Home sequences for a phone comparison, as (hex, delay after) steps with the kernel's Stroke
    /// timing: release, 45 ms; key, 60 ms; release, 35 ms. V0 is the kernel's current (vendor)
    /// Home. The same steps are decoded in S9 and written as --hid-replay files, so the bytes a
    /// phone test replays are exactly the bytes the model checked.
    /// </summary>
    public static readonly (string Name, string Description, (string Hex, int DelayMs)[] Steps)[] HomeVariants =
    [
        ("home-v0-vendor", "Current kernel Home: Tab stroke, then Command+H stroke", [.. Stroke(0x00, 0x2B), .. Stroke(0x08, 0x0B)]),
        ("home-v1-command-h", "Command+H stroke only", [.. Stroke(0x08, 0x0B)]),
        ("home-v2-command-wake", "Command pressed alone (types nothing), then Command+H stroke", [.. Stroke(0x08, 0x00), .. Stroke(0x08, 0x0B)]),
    ];

    private static (string, int)[] Stroke(byte modifier, byte usage) =>
        [("A200000000000000", 45), ($"A2{modifier:X2}{usage:X2}0000000000", 60), ("A200000000000000", 35)];

    /// <summary>Writes each Home variant as a JSON file for iMouse2.Kernel.exe --hid-replay PID FILE.</summary>
    public static void WriteHomeReplays(string dir)
    {
        Directory.CreateDirectory(dir);
        foreach (var v in HomeVariants)
        {
            string path = Path.Combine(dir, v.Name + ".json");
            File.WriteAllText(path, System.Text.Json.JsonSerializer.Serialize(v.Steps.Select(s => new { Hex = s.Hex, DelayMs = s.DelayMs }),
                new System.Text.Json.JsonSerializerOptions { WriteIndented = true }));
            Console.WriteLine($"{path}  ({v.Description}; a text field would receive: {Show(Decode(v.Steps.Select(s => s.Hex)))})");
        }
    }

    /// <summary>A decoded string with tabs made visible.</summary>
    public static string Show(string decoded) => decoded.Replace("\t", "\\t");
}
