using System.IO;
using System.Reflection;
using System.Security.Cryptography;

namespace IMouse2;

public sealed record ConsoleBuildIdentity(string Version, string InformationalVersion, string ModuleId, string? Sha256)
{
    public string Label => Sha256 is { Length: 64 } ? "Build " + Sha256[..8] : "Build identity unavailable";
    public string Detail => $"Console version {Version}\nModule {ModuleId}\nSHA-256: {Sha256 ?? "unavailable"}\nRecorded when this console started; this identifies bytes, not release acceptance.";
}

public static class ConsoleBuildInfo
{
    // Capture once, before the window connects. An export describes this process's startup
    // identity even if someone subsequently replaces the file at the same path.
    public static ConsoleBuildIdentity Current { get; } = Capture(typeof(ConsoleBuildInfo).Assembly, path =>
    {
        using var file = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant();
    });

    internal static ConsoleBuildIdentity Capture(Assembly assembly, Func<string, string> hash)
    {
        string? digest;
        try
        {
            digest = hash(assembly.Location);
            if (digest.Length != 64 || !digest.All(Uri.IsHexDigit)) digest = null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or NotSupportedException) { digest = null; }
        return new(assembly.GetName().Version?.ToString() ?? "unknown",
            assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion ?? "unknown",
            assembly.ManifestModule.ModuleVersionId.ToString("D"), digest);
    }
}
