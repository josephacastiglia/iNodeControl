namespace IMouse2.Kernel;

/// <summary>Eight-byte vendor payloads excluding report ID zero. A0 is probe-only.</summary>
public static class HidProtocol
{
    public static byte[] Mouse(byte buttons = 0, sbyte dx = 0, sbyte dy = 0) =>
        [0xA1, buttons, unchecked((byte)dx), unchecked((byte)dy), 0, 0, 0, 0];
    public static byte[] Key(byte modifier = 0, byte usage = 0) => [0xA2, modifier, usage, 0, 0, 0, 0, 0];

    // MouseKeyItem's separate Fn extension is payload byte 7, not a modifier bit.
    public static byte[] FnKey(byte usage = 0) => [0xA2, 0, usage, 0, 0, 0, 0, 2];

    // Static vendor evidence only. The normal router exposes this solely in its
    // explicitly scoped move-only probe; no button parameter or raw-send endpoint.
    internal static byte[] AbsoluteProbe(int x, int y, int width, int height)
    {
        if (width is < 2 or > 65535 || height is < 2 or > 65535
            || x < 0 || x >= width || y < 0 || y >= height)
            throw new ArgumentException("Absolute probe point must be inside the recorded image.");
        // Vendor mapping uses the image size denominator and truncates fractions.
        int ax = (int)((float)x / width * 32767.0f);
        int ay = (int)((float)y / height * 32767.0f);
        return [0xA0, 0, (byte)ax, (byte)(ax >> 8), (byte)ay, (byte)(ay >> 8), 0, 0];
    }

    // A2 carries standard USB keyboard usages after the vendor prefix. ASCII
    // translation is deliberately explicit: non-ASCII requires an IME, not truncation.
    public static (byte Modifier, byte Usage) Ascii(char c)
    {
        if (c is >= 'a' and <= 'z') return (0, (byte)(4 + c - 'a'));
        if (c is >= 'A' and <= 'Z') return (2, (byte)(4 + c - 'A'));
        if (c is >= '1' and <= '9') return (0, (byte)(30 + c - '1'));
        if (c == '0') return (0, 39);
        const string plain = "\r\u001b\b\t -=[]\\;'`,./";
        const string shifted = "_+{}|:\"~<>?";
        byte[] plainUsages = [40,41,42,43,44,45,46,47,48,49,51,52,53,54,55,56];
        int index = plain.IndexOf(c);
        if (index >= 0) return (0, plainUsages[index]);
        if (c == '\n') return (0, 40);
        const string symbols = "!@#$%^&*()";
        index = symbols.IndexOf(c);
        if (index >= 0) return (2, (byte)(30 + index));
        index = shifted.IndexOf(c);
        byte[] shiftedUsages = [45,46,47,48,49,51,52,53,54,55,56];
        if (index >= 0) return (2, shiftedUsages[index]);
        throw new ArgumentException("Unsupported character U+" + ((int)c).ToString("X4"));
    }
}
