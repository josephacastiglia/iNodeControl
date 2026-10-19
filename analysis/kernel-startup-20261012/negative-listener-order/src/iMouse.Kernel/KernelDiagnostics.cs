using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;

namespace IMouse2.Kernel;

internal static class KernelDiagnostics
{
    // Initialize at startup, so file replacement cannot silently change this running
    // process's identity. Hashes identify bytes, not release approval.
    internal static readonly object BuildIdentity = CaptureBuild();
    private static object CaptureBuild()
    {
        var assembly = typeof(KernelDiagnostics).Assembly;
        string? hash;
        try { using var file = File.OpenRead(assembly.Location); hash = Convert.ToHexString(SHA256.HashData(file)).ToLowerInvariant(); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or NotSupportedException) { hash = null; }
        return new { version = assembly.GetName().Version?.ToString(),
            informational_version = assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
            module_id = assembly.ManifestModule.ModuleVersionId.ToString("D"), sha256 = hash };
    }
    internal static object ProcessSnapshot()
    {
        using var process = Process.GetCurrentProcess();
        return new { pid = process.Id, started_utc = process.StartTime.ToUniversalTime(),
            uptime_seconds = (DateTime.UtcNow - process.StartTime.ToUniversalTime()).TotalSeconds,
            working_set_bytes = process.WorkingSet64, private_bytes = process.PrivateMemorySize64,
            cpu_seconds = process.TotalProcessorTime.TotalSeconds };
    }
}
