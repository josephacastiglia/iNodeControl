namespace IMouse2;

/// <summary>The current farm test scope is one explicitly identified phone.</summary>
internal static class FarmTargetPolicy
{
    internal const string DeviceId = "86:1D:4A:04:2F:F6";

    internal static bool IsC24C(string? id) =>
        string.Equals(id, DeviceId, StringComparison.OrdinalIgnoreCase) ||
        string.Equals(id, "C24C", StringComparison.OrdinalIgnoreCase);
}
