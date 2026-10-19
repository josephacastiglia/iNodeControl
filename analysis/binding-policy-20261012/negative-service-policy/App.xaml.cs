using System.IO;
using System.Linq;
using System.Windows;

namespace IMouse2;

public partial class App : Application
{
    private string? _testData;

    // Test modes run on a throwaway data folder so they never read or save the operator's
    // %APPDATA%\iMouse2. That also means a live mode cannot pick up the saved service address,
    // so it has to be given one: guessing could point a test that sends taps at the wrong service.
    private MainWindow CreateTestWindow(string[] args, bool live, Func<string, ApiClient>? factory = null)
    {
        var address = args.FirstOrDefault(a => a.StartsWith("--address="))?["--address=".Length..];
        if (live && string.IsNullOrWhiteSpace(address))
            throw new Exception("Live test modes need --address=<service url>, for example --address=http://127.0.0.1:9913. They use their own data folder and do not read the address saved in %APPDATA%\\iMouse2.");
        _testData = Path.Combine(Path.GetTempPath(), "iMouse2-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(_testData);
        var window = new MainWindow(factory, _testData);
        if (!string.IsNullOrWhiteSpace(address)) window.AddressBox.Text = address;
        return window;
    }

    /// <summary>
    /// The folder --data-dir names (<c>--data-dir=&lt;path&gt;</c> or <c>--data-dir &lt;path&gt;</c>), or null
    /// when the flag is absent. A console started with it reads and writes settings only there: no
    /// %APPDATA%\iMouse2, no seeding from it, no data\settings.json mirror beside the exe.
    /// </summary>
    internal static string? DataDirArgument(string[] args)
    {
        var matches = args.Select((arg, index) => (arg, index))
            .Where(p => p.arg == "--data-dir" || p.arg.StartsWith("--data-dir=", StringComparison.Ordinal)).ToArray();
        if (matches.Length == 0) return null;
        if (matches.Length != 1) throw new ArgumentException("Give --data-dir only once.");
        int i = matches[0].index;
        string raw = (args[i] == "--data-dir" ? (i + 1 < args.Length ? args[i + 1] : "") : args[i]["--data-dir=".Length..]).Trim().Trim('"');
        if (raw.Length == 0 || raw.StartsWith("--", StringComparison.Ordinal))
            throw new ArgumentException("--data-dir needs a folder, for example --data-dir=\"C:\\iMouse2 candidate\\data\".");
        // A relative path would depend on whoever started the process; say which folder is meant.
        if (!Path.IsPathFullyQualified(raw)) throw new ArgumentException("--data-dir must be a full path such as C:\\...; got \"" + raw + "\".");
        // Windows normalizes trailing dots/spaces in GetFullPath; inspect the spelling first.
        string rawRoot = Path.GetPathRoot(raw) ?? "";
        if (raw[rawRoot.Length..].Split('\\', '/').Any(part => part.EndsWith('.') || part.EndsWith(' ')))
            throw new ArgumentException("--data-dir cannot contain folder names ending in a dot or space.");
        string full;
        try { full = Path.GetFullPath(raw); }
        catch (Exception ex) { throw new ArgumentException("--data-dir is not a usable folder path: \"" + raw + "\" (" + ex.Message + ")."); }
        // GetFullPath no longer rejects characters Windows cannot store, so check each folder name.
        var root = Path.GetPathRoot(full) ?? "";
        if (string.Equals(full.TrimEnd('\\', '/'), root.TrimEnd('\\', '/'), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("--data-dir must name a dedicated folder below a drive or share root.");
        full = full.TrimEnd('\\', '/');
        if (full[root.Length..].Split('\\', '/').Any(part => part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0
                || part.EndsWith('.') || part.EndsWith(' ')
                || System.Text.RegularExpressions.Regex.IsMatch(part, @"^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)", System.Text.RegularExpressions.RegexOptions.IgnoreCase)))
            throw new ArgumentException("--data-dir contains an invalid or reserved folder name.");
        if (File.Exists(full)) throw new ArgumentException("--data-dir names a file, not a folder: \"" + full + "\".");
        var shared = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "iMouse2");
        if (string.Equals(full, Path.GetFullPath(shared).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("--data-dir names the shared operator folder " + shared + "; leave --data-dir out to use it.");
        return full;
    }

    /// <summary>--address=&lt;url&gt;, or null. Normal startup honours it only together with --data-dir.</summary>
    internal static string? AddressArgument(string[] args)
    {
        var values = args.Where(a => a.StartsWith("--address=", StringComparison.Ordinal)).ToArray();
        if (values.Length > 1) throw new ArgumentException("Give --address only once.");
        return values.FirstOrDefault()?["--address=".Length..].Trim().Trim('"') is { Length: > 0 } value ? value : null;
    }

    // Candidate startup validates before constructing a window or writing settings. Never
    // infer a port by finding its digits elsewhere in an IPv6 address or hostname.
    internal static string CandidateAddress(string[] args, string dataDir)
    {
        string? address = AddressArgument(args);
        if (address is null && args.Any(a => a.StartsWith("--address=", StringComparison.Ordinal)))
            throw new ArgumentException("--address needs an explicit service URL and port.");
        if (address is null)
        {
            string file = Path.Combine(dataDir, "settings.json");
            if (File.Exists(file))
            {
                using var settings = System.Text.Json.JsonDocument.Parse(File.ReadAllText(file));
                if (settings.RootElement.TryGetProperty("address", out var saved)
                    && saved.ValueKind == System.Text.Json.JsonValueKind.String)
                    address = saved.GetString();
            }
        }
        if (string.IsNullOrWhiteSpace(address))
            throw new ArgumentException("No service address for --data-dir. Pass --address=<url> with an explicit port, or set address in its settings.json. Nothing was connected.");
        var endpoint = ApiClient.NormalizeEndpoint(address);
        string qualified = address.Contains("://", StringComparison.Ordinal) ? address : "http://" + address;
        string authority = qualified[(qualified.IndexOf("://", StringComparison.Ordinal) + 3)..].Split('/')[0];
        var port = System.Text.RegularExpressions.Regex.Match(authority, @"^(?:\[[^\]]+\]|[^:]+):([0-9]+)$");
        if (!port.Success || !int.TryParse(port.Groups[1].Value, out int declared) || declared < 1 || declared > 65535 || declared != endpoint.Port)
            throw new ArgumentException("With --data-dir, name the service port explicitly, for example http://127.0.0.1:9913.");
        return endpoint.GetLeftPart(UriPartial.Authority) + (endpoint.IsDefaultPort ? ":" + declared : "");
    }

    private void FailStartup(string message)
    {
        try { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "startup-failure.txt"), message); } catch { }
        MessageBox.Show(message, "iMouse 2.0");
        Shutdown(2);
    }

    protected override void OnExit(ExitEventArgs e)
    {
        if (_testData is not null) try { Directory.Delete(_testData, true); } catch { }
        base.OnExit(e);
    }

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        DispatcherUnhandledException += (_, args) =>
        {
            args.Handled = true;
            try { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "unhandled-error.txt"), args.Exception.ToString()); } catch { }
            MessageBox.Show("The console encountered an error:\n" + args.Exception.Message, "iMouse 2.0");
        };
        if (e.Args.Contains("--validate-startup"))
        {
            // Offline preflight for candidate launchers: no window, connection or settings write.
            string report = Path.Combine(AppContext.BaseDirectory, "startup-validation.json");
            try
            {
                string folder = DataDirArgument(e.Args) ?? throw new ArgumentException("Startup validation requires an explicit --data-dir.");
                string address = CandidateAddress(e.Args, folder);
                File.WriteAllText(report, System.Text.Json.JsonSerializer.Serialize(new {
                    valid = true, dataDirectory = folder, address, connected = false, settingsWritten = false,
                    build = ConsoleBuildInfo.Current }, new System.Text.Json.JsonSerializerOptions { WriteIndented = true }));
                Shutdown(0);
            }
            catch (Exception ex)
            {
                try { File.WriteAllText(report, System.Text.Json.JsonSerializer.Serialize(new {
                    valid = false, error = ex.Message, connected = false, settingsWritten = false })); } catch { }
                Shutdown(1);
            }
            return;
        }
        if (e.Args.Contains("--print-data-path"))
        {
            try
            {
                // With --data-dir, report that folder without touching %APPDATA% or creating anything.
                File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "data-path.txt"), DataDirArgument(e.Args) ?? global::IMouse2.MainWindow.ResolveDataPath());
                Shutdown(0);
            }
            catch (Exception ex)
            {
                try { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "data-path-failure.txt"), ex.ToString()); } catch { }
                Shutdown(1);
            }
            return;
        }
        if (e.Args.Contains("--self-test"))
        {
            try { await SelfTests.RunAsync(); Shutdown(0); }
            catch (Exception ex) { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "self-test-failure.txt"), ex.ToString()); Shutdown(1); }
            return;
        }
        if (e.Args.Contains("--wall-test"))
        {
            try
            {
                var window = CreateTestWindow(e.Args, live: true);
                window.Show();
                var tileArg = e.Args.FirstOrDefault(a => a.StartsWith("--tile-ms="));
                await window.RunWallAsync(tileArg is null ? 0 : int.Parse(tileArg["--tile-ms=".Length..]));
                window.Close();
                Shutdown(0);
            }
            catch (Exception ex) { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "wall-test-failure.txt"), ex.ToString()); Shutdown(1); }
            return;
        }
        if (e.Args.Contains("--mirror-test"))
        {
            try
            {
                var window = CreateTestWindow(e.Args, live: true);
                window.Show();
                await window.RunMirrorAsync();
                window.Close();
                Shutdown(0);
            }
            catch (Exception ex) { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "mirror-test-failure.txt"), ex.ToString()); Shutdown(1); }
            return;
        }
        if (e.Args.Contains("--fps-test"))
        {
            try
            {
                var window = CreateTestWindow(e.Args, live: true);
                window.Show();
                await window.RunFpsAsync();
                window.Close();
                Shutdown(0);
            }
            catch (Exception ex) { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "fps-test-failure.txt"), ex.ToString()); Shutdown(1); }
            return;
        }
        if (e.Args.Contains("--smoke-test") || e.Args.Contains("--ui-test"))
        {
            try
            {
                bool fake = e.Args.Contains("--ui-test");
                var handler = fake ? new TestHandler() : null;
                var window = CreateTestWindow(e.Args, live: !fake, handler is null ? null : address => new ApiClient(address, handler));
                await window.RunSmokeAsync(fake, handler);
                window.Close();
                Shutdown(0);
            }
            catch (Exception ex) { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "smoke-test-failure.txt"), ex.ToString()); Shutdown(1); }
            return;
        }
        MainWindow main;
        string? dataDir;
        try { dataDir = DataDirArgument(e.Args); }
        catch (ArgumentException ex) { FailStartup(ex.Message); return; }
        if (dataDir is null) main = new MainWindow();   // unchanged: %APPDATA%\iMouse2, seeding and the mirror
        else
        {
            string address;
            try
            {
                address = CandidateAddress(e.Args, dataDir);
                Directory.CreateDirectory(dataDir);
            }
            catch (Exception ex) when (ex is ArgumentException or IOException or UnauthorizedAccessException or System.Text.Json.JsonException or InvalidOperationException)
            { FailStartup("Candidate configuration is not usable: " + ex.Message); return; }
            main = new MainWindow(dataPath: dataDir);
            main.AddressBox.Text = address;
        }
        MainWindow = main;
        ShutdownMode = ShutdownMode.OnMainWindowClose;
        main.Show();
        await main.ConnectAsync();
        try { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "startup-state.json"), System.Text.Json.JsonSerializer.Serialize(new { visible = main.IsVisible, loaded = main.IsLoaded, visibility = main.Visibility.ToString(), title = main.Title, handle = new System.Windows.Interop.WindowInteropHelper(main).Handle.ToInt64() })); } catch { }
    }
}
