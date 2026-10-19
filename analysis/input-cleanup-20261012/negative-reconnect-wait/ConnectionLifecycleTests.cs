using System.IO;
using System.Text.Json;
using System.Windows.Interop;

namespace IMouse2;

public partial class MainWindow
{
    /// <summary>Exercises real connection/window lifetimes without Show, an HWND,
    /// injected input, a network listener or hardware. Every client uses fake HTTP.</summary>
    internal static async Task CheckConnectionLifecycleAsync(Action<string, bool> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "imouse-lifecycle-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder, "settings.json"), "{\"address\":\"http://localhost:9923\",\"trackPointer\":false}");
        var handlers = new List<TestHandler>(); var clients = new List<ApiClient>();
        var window = new MainWindow(address =>
        {
            var h = new TestHandler { OwnershipSupported = true };
            handlers.Add(h); var api = new ApiClient(address, h, ownership: true); clients.Add(api); return api;
        }, folder);
        var gate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var closeGate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        try
        {
            window.AutoPreview.IsChecked = false;
            await window.ConnectAsync(); await window._scopeTail;
            check("Lifecycle checks never show a window or create a native window handle", !window.IsVisible && new WindowInteropHelper(window).Handle == IntPtr.Zero);
            await clients[0].MoveAsync("TEST:01", 10, 20);
            handlers[0].ReleaseGate = gate.Task;
            var reconnect = window.ConnectAsync();
            await handlers[0].ReleaseWaiting.Task.WaitAsync(TimeSpan.FromSeconds(5));
            check("Reconnect disables input and waits while the old connection releases", !reconnect.IsCompleted && window._api is null && !window._controlReady);
            var newer = window.ConnectAsync();
            check("A newer Connect can replace a waiting connection without starting it", clients.Count == 3 && window._api is null && !newer.IsCompleted);
            gate.SetResult(); await Task.WhenAll(reconnect, newer); await window._scopeTail;
            check("Only the latest Connect becomes the active client", window._api == clients[2] && window._connected && window._controlReady);
            check("The overtaken unused client was closed without taking a lease", handlers[1].ActiveLeases.Count == 0 && (await clients[1].CloseAsync()).Confirmed);
            await clients[2].MoveAsync("TEST:01", 20, 30);
            handlers[2].ReleaseGate = closeGate.Task;
            bool closed = false; window.Closed += (_, _) => closed = true;
            var closing = window.CloseSafelyAsync();
            await handlers[2].ReleaseWaiting.Task.WaitAsync(TimeSpan.FromSeconds(5));
            check("The window cannot finish closing while its release is unanswered", !closed && !closing.IsCompleted && window._api is null && !window.IsEnabled);
            closeGate.SetResult(); await closing;
            check("The window closes after cleanup and persists its isolated receipt", closed && File.Exists(Path.Combine(folder, "last-input-cleanup.json")) && string.IsNullOrEmpty(window.CleanupWarning));
            using var record = JsonDocument.Parse(File.ReadAllText(Path.Combine(folder, "last-input-cleanup.json")));
            check("Rapid reconnect and close record every retired connection", record.RootElement.GetProperty("connections").GetArrayLength() == 3);

            var legacy = new MainWindow(address => new ApiClient(address, new TestHandler()), folder);
            try
            {
                legacy.AutoPreview.IsChecked = false; await legacy.ConnectAsync();
                check("Explicit legacy test connections retain input readiness", legacy._connected && legacy._controlReady && legacy._api?.UsesInputOwnership == false);
            }
            finally { await legacy.CloseSafelyAsync(); }
        }
        finally
        {
            gate.TrySetResult(); closeGate.TrySetResult();
            await window.CloseSafelyAsync();
            foreach (var client in clients) await client.DisposeAsync();
            if (Directory.Exists(folder)) Directory.Delete(folder, true);
        }
    }
}
