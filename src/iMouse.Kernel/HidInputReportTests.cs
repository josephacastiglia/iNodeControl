namespace IMouse2.Kernel;

internal static class HidInputReportTests
{
    internal static void Run(Action<bool, string> check)
    {
        foreach (int length in new[] { 0, 1, 8, 9, 16, 18, 34 })
        {
            bool rejected = false;
            try { HidInputReport.Parse(new byte[length]); }
            catch (InvalidDataException) { rejected = true; }
            check(rejected, "Input parser rejects incorrect Windows report length " + length);
        }
        byte[] bytes = new byte[17];
        bytes[0] = 1;
        bool wrongId = false;
        try { HidInputReport.Parse(bytes); }
        catch (InvalidDataException) { wrongId = true; }
        check(wrongId, "Input parser refuses an unobserved report ID");
        bytes[0] = 0;
        foreach (byte family in new byte[] { 0xA0, 0xA1 })
        {
            bytes[1] = family;
            var parsed = HidInputReport.Parse(bytes);
            check(parsed.Kind == "vendor-movement-signal" && parsed.IdentifierHex is null,
                "Movement reply is classified only as a vendor signal " + family);
        }
        bytes[1] = 0xA5;
        for (int i = 2; i < bytes.Length; i++) bytes[i] = (byte)(i - 1);
        var identifier = HidInputReport.Parse(bytes);
        check(identifier.IdentifierHex == "010203040506" && identifier.PayloadHex.EndsWith("0D0E0F"),
            "Vendor identifier is six bytes and the unclassified tail is preserved");
        bytes[2] = 0xff;
        check(identifier.IdentifierHex == "010203040506", "Parsed input owns its data independently of the receive buffer");
        foreach (byte family in new byte[] { 0xA6, 0xAF, 0xA2, 0xFE })
        {
            bytes[1] = family;
            var parsed = HidInputReport.Parse(bytes);
            check(parsed.Kind == (family is 0xA6 or 0xAF ? "vendor-status" : "unknown")
                && parsed.IdentifierHex is null && parsed.PayloadHex.Length == 32,
                "Status and unknown replies retain raw bytes without claiming command success " + family);
        }
    }
}
