using System.IO;

namespace IMouse2;

/// <summary>
/// Where the console writes and what it starts, in a build folder (today) or an installed Marketing Farm.
/// Installed, Farm.ps1 sets IMOUSE_FARM_DATA (the per-machine data folder), IMOUSE_FARM_HOME (the version's
/// farm code) and IMOUSE_FARM_PYTHON. Without IMOUSE_FARM_DATA every answer is what the console used before.
/// </summary>
internal static class InstallLayout
{
    private static string? Env(string name)
    {
        var value = Environment.GetEnvironmentVariable(name);
        return string.IsNullOrWhiteSpace(value) ? null : value;
    }

    private static string? Data => Env("IMOUSE_FARM_DATA");

    public static bool Installed => Data is not null;

    /// <summary>The console's own startup, failure and QA files: beside iMouse2.exe in a build, &lt;data&gt;\console
    /// when installed, so an installed version folder is never written.</summary>
    public static string RunFiles
    {
        get
        {
            if (Data is null) return AppContext.BaseDirectory;
            var folder = Path.Combine(Data, "console");
            Directory.CreateDirectory(folder);
            return folder;
        }
    }

    /// <summary>The installed farm server script (IMOUSE_FARM_HOME\tools\imouse_farm_server.py), or null to search
    /// above the console's folder as before.</summary>
    public static string? InstalledFarmServer
    {
        get
        {
            var home = Installed ? Env("IMOUSE_FARM_HOME") : null;
            if (home is null) return null;
            var script = Path.Combine(home, "tools", "imouse_farm_server.py");
            return File.Exists(script) ? script : null;
        }
    }

    /// <summary>The farm server script to start: the installed one, else the first tools\imouse_farm_server.py
    /// found in or above <paramref name="startDirectory"/>, the console's folder or the current directory.</summary>
    public static string? ResolveFarmServerScriptPath(string? startDirectory = null)
    {
        // Installed: the current version's farm code (Farm.ps1 sets IMOUSE_FARM_HOME); never a folder above it.
        if (InstalledFarmServer is string installed) return installed;
        foreach (var root in new[] { startDirectory, AppContext.BaseDirectory, Environment.CurrentDirectory })
        {
            if (string.IsNullOrWhiteSpace(root)) continue;
            for (var dir = new DirectoryInfo(root); dir is not null; dir = dir.Parent)
            {
                var candidate = Path.Combine(dir.FullName, "tools", "imouse_farm_server.py");
                if (File.Exists(candidate)) return candidate;
            }
        }
        return null;
    }

    /// <summary>The Python that runs the farm server: IMOUSE_FARM_PYTHON when installed, else "python" from PATH.</summary>
    public static string Python => (Installed ? Env("IMOUSE_FARM_PYTHON") : null) ?? "python";

    /// <summary>The folder a started farm server works in and keeps output\ under: the data folder when installed,
    /// else the folder holding tools\ (the checkout), as before.</summary>
    public static string FarmStateRoot(string serverScript) =>
        Data ?? (Path.GetDirectoryName(Path.GetDirectoryName(serverScript)) ?? AppContext.BaseDirectory);
}
