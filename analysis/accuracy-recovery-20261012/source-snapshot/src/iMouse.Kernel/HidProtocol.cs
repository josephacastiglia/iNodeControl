namespace IMouse2.Kernel;

/// <summary>Observed C24C report families; all arrays exclude report ID zero.</summary>
public static class HidProtocol
{
    public static byte[] Mouse(byte buttons = 0, sbyte dx = 0, sbyte dy = 0) =>
        [0xA1, buttons, unchecked((byte)dx), unchecked((byte)dy), 0, 0, 0, 0];
    public static byte[] Key(byte modifier = 0, byte usage = 0) => [0xA2, modifier, usage, 0, 0, 0, 0, 0];

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
