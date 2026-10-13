namespace IMouse2.Kernel;

/// <summary>Reject an obviously incomplete runtime before normal startup opens
/// hardware, listeners or receiver processes. This never loads native code.</summary>
internal static class ReceiverRuntime
{
    // AirplayProcess uses appsink video and fakesink audio. UxPlay still checks
    // playback/autodetect and initializes its AAC/ALAC audio pipelines in that
    // mode. Keep these entry points aligned with runtime_audit.py and the
    // production-renderer startup probe; imported DLLs need that fuller audit.
    private static readonly string[] RequiredFiles = [
        "libexec/gstreamer-1.0/gst-plugin-scanner.exe",
        "lib/gstreamer-1.0/libgstapp.dll",
        "lib/gstreamer-1.0/libgstcoreelements.dll",
        "lib/gstreamer-1.0/libgstlibav.dll",
        "lib/gstreamer-1.0/libgstvideoparsersbad.dll",
        "lib/gstreamer-1.0/libgstvideoconvertscale.dll",
        "lib/gstreamer-1.0/libgstplayback.dll",
        "lib/gstreamer-1.0/libgstautodetect.dll",
        "lib/gstreamer-1.0/libgstaudioconvert.dll",
        "lib/gstreamer-1.0/libgstaudioresample.dll",
        "lib/gstreamer-1.0/libgstvolume.dll",
        "lib/gstreamer-1.0/libgstlevel.dll"
    ];

    internal static void ValidateFiles(string runtime)
    {
        if (!Directory.Exists(Path.Combine(runtime, "bin")) || !Directory.Exists(Path.Combine(runtime, "lib", "gstreamer-1.0")))
            throw new ArgumentException("Receiver runtime is missing its bin or plugin directory. Verify the dependency package.");
        var missing = RequiredFiles.Where(relative =>
        {
            var file = new FileInfo(Path.Combine(runtime, relative));
            return !file.Exists || file.Length == 0;
        }).ToArray();
        if (missing.Length > 0)
            throw new ArgumentException("Receiver runtime has missing or empty required files: " + string.Join(", ", missing)
                + ". Verify the dependency package before starting the kernel.");
    }
}
