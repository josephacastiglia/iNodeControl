namespace IMouse2.Kernel;

/// <summary>Vendor input payload classification, not acknowledgement of an iOS action.</summary>
public sealed record HidInputReport(byte Family, string Kind, string PayloadHex, string? IdentifierHex)
{
    public const int WindowsReportLength = 17;

    public static HidInputReport Parse(ReadOnlySpan<byte> windowsReport)
    {
        if (windowsReport.Length != WindowsReportLength || windowsReport[0] != 0)
            throw new InvalidDataException("Expected a 17-byte input report with report ID zero.");
        var payload = windowsReport[1..];
        string kind = payload[0] switch
        {
            0xA0 or 0xA1 => "vendor-movement-signal",
            0xA5 => "vendor-identifier",
            0xA6 or 0xAF => "vendor-status",
            _ => "unknown"
        };
        return new(payload[0], kind, Convert.ToHexString(payload),
            payload[0] == 0xA5 ? Convert.ToHexString(payload.Slice(1, 6)) : null);
    }
}
