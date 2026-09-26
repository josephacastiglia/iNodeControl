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
                File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "data-path.txt"), global::IMouse2.MainWindow.ResolveDataPath());
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
        var main = new MainWindow();
        MainWindow = main;
        ShutdownMode = ShutdownMode.OnMainWindowClose;
        main.Show();
        await main.ConnectAsync();
        try { File.WriteAllText(Path.Combine(AppContext.BaseDirectory, "startup-state.json"), System.Text.Json.JsonSerializer.Serialize(new { visible = main.IsVisible, loaded = main.IsLoaded, visibility = main.Visibility.ToString(), title = main.Title, handle = new System.Windows.Interop.WindowInteropHelper(main).Handle.ToInt64() })); } catch { }
    }
}
