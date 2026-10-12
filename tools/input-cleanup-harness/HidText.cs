using System.IO;
using IMouse2.Kernel;

namespace IMouse2.Harness;

/// <summary>
/// What a focused iOS text field would receive from a stream of keyboard reports (A2 family).
/// A report with no modifier or Shift only types its character, Tab included (a focused text
/// field inserts a tab). A report carrying Left GUI (Command) or the vendor byte-7 flag is a
/// shortcut and types nothing; it is shown as [GUI+x] or [flag02+x]. Releases type nothing.
/// The character map is the kernel's own HidProtocol.Ascii, inverted, so it cannot drift from it.
/// A simplified model of the field only: it validates emitted reports, and says nothing about
/// whether iOS acts on a shortcut or what a real field does with it.
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

    /// <summary>A decoded string with tabs made visible.</summary>
    public static string Show(string decoded) => decoded.Replace("\t", "\\t");
}
