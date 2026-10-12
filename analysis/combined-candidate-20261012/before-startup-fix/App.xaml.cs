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
        int i = Array.FindIndex(args, a => a == "--data-dir" || a.StartsWith("--data-dir=", StringComparison.Ordinal));
        if (i < 0) return null;
        string raw = (args[i] == "--data-dir" ? (i + 1 < args.Length ? args[i + 1] : "") : args[i]["--data-dir=".Length..]).Trim().Trim('"');
        if (raw.Length == 0 || raw.StartsWith("--", StringComparison.Ordinal))
            throw new ArgumentException("--data-dir needs a folder, for example --data-dir=\"C:\\iMouse2 candidate\\data\".");
        // A relative path would depend on whoever started the process; say which folder is meant.
        if (!Path.IsPathFullyQualified(raw)) throw new ArgumentException("--data-dir must be a full path such as C:\\...; got \"" + raw + "\".");
        string full;
        try { full = Path.GetFullPath(raw).TrimEnd('\\', '/'); }
        catch (Exception ex) { throw new ArgumentException("--data-dir is not a usable folder path: \"" + raw + "\" (" + ex.Message + ")."); }
        // GetFullPath no longer rejects characters Windows cannot store, so check each folder name.
        var root = Path.GetPathRoot(full) ?? "";
        if (full[root.Length..].Split('\\', '/').Any(part => part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0))
            throw new ArgumentException("--data-dir contains characters a folder name cannot have: \"" + raw + "\".");
        if (File.Exists(full)) throw new ArgumentException("--data-dir names a file, not a folder: \"" + full + "\".");
        var shared = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "iMouse2");
        if (string.Equals(full, Path.GetFullPath(shared).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("--data-dir names the shared operator folder " + shared + "; leave --data-dir out to use it.");
        return full;
    }

    /// <summary>--address=&lt;url&gt;, or null. Normal startup honours it only together with --data-dir.</summary>
    internal static string? AddressArgument(string[] args) =>
        args.FirstOrDefault(a => a.StartsWith("--address=", StringComparison.Ordinal))?["--address=".Length..].Trim().Trim('"') is { Length: > 0 } a ? a : null;

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
            try { Directory.CreateDirectory(dataDir); }
            catch (Exception ex) { FailStartup("--data-dir could not be created: \"" + dataDir + "\" (" + ex.Message + ")."); return; }
            main = new MainWindow(dataPath: dataDir);
            // An isolated folder has no operator address to fall back on, and the built-in default
            // is the vendor service on 9911. Connect only to an address someone chose explicitly.
            string? address = AddressArgument(e.Args) ?? main.SavedAddress;
            if (address is null)
            {
                main.Close();
                FailStartup("No service address for --data-dir \"" + dataDir + "\". Pass --address=<url> or put one in its settings.json. Not connecting, so nothing can reach the default service on 9911.");
                return;
            }
            Uri endpoint;
            try { endpoint = ApiClient.NormalizeEndpoint(address); }
            catch (ArgumentException ex) { main.Close(); FailStartup("Service address \"" + address + "\" is not usable: " + ex.Message); return; }
            // NormalizeEndpoint fills in 9911 when no port is written; here the port must be chosen, not assumed.
            if (!address.Contains(":" + endpoint.Port, StringComparison.Ordinal))
            {
                main.Close();
                FailStartup("Service address \"" + address + "\" names no port. With --data-dir give it explicitly, for example http://127.0.0.1:9913, so it cannot default to 9911.");
                return;
            }
            main.AddressBox.Text = address;
        }
        MainWindow = main;
        ShutdownMode = ShutdownMode.OnMainWindowClose;
        main.Show();
        await main.ConnectAsync();
        try { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "startup-state.json"), System.Text.Json.JsonSerializer.Serialize(new { visible = main.IsVisible, loaded = main.IsLoaded, visibility = main.Visibility.ToString(), title = main.Title, handle = new System.Windows.Interop.WindowInteropHelper(main).Handle.ToInt64() })); } catch { }
    }
}
