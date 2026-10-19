using System.IO;
using System.Linq;
using System.Windows;

namespace IMouse2;

public partial class App : Application
{
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
                var window = new MainWindow();
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
                var window = new MainWindow();
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
                var window = new MainWindow();
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
                var window = new MainWindow(handler is null ? null : address => new ApiClient(address, handler));
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
