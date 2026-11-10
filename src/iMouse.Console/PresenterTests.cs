using System.IO;
using System.Windows.Interop;

namespace IMouse2;

public partial class MainWindow
{
    /// <summary>Exercises the actual input handler and frame presenter without Show, an HWND,
    /// a listener or injected input. Every command uses TestHandler.</summary>
    internal static async Task CheckPresenterAsync(Action<string, bool> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "imouse-presenter-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder, "settings.json"), "{\"address\":\"http://localhost:9923\",\"trackPointer\":false}");
        var handler = new TestHandler { OwnershipSupported = true };
        var window = new MainWindow(address => new ApiClient(address, handler, ownership: true), folder);
        try
        {
            window.AutoPreview.IsChecked = false;
            await window.ConnectAsync(); await window._scopeTail;
            window._controlReady = false;
            int sent = handler.Commands.Count;
            await window.SendInputAsync("test", "/mouse/click", new() { ["x"] = 1, ["y"] = 2 });
            check("An input handler that is not ready sends nothing", handler.Commands.Count == sent);

            var stamp = window._previewFreshness.Observe(window._frameEpoch, false,
                new("0123456789abcdef0123456789abcdef", 10, 0, "flowing"))!;
            PreparedFrame Frame(PreviewStamp s) => new() { Width = 4, Height = 4, Bits = 24, Stride = 12, Pixels = new byte[48], PreviewStamp = s };
            long shown = window._live.Frames;
            window._pending = Frame(stamp);
            window.PresentPending(null, EventArgs.Empty);
            check("The presenter applies a current frame to the master image",
                window.PhoneImage.Source == window._live.Source && window._live.Frames == shown + 1
                && window._live.Width == 4 && window._live.Height == 4);
            window.PresentPending(null, EventArgs.Empty);
            check("Empty rendering ticks do not count as displayed frames", window._live.Frames == shown + 1);
            window._pending = Frame(stamp with { Epoch = window._frameEpoch - 1 });
            window.PresentPending(null, EventArgs.Empty);
            check("Obsolete phone frames are never presented", window._live.Frames == shown + 1);
            window._pending = Frame(stamp); window._pending.Width = 0;
            window.PresentPending(null, EventArgs.Empty);
            check("A frame that cannot be applied is not counted as displayed", window._live.Frames == shown + 1);
            check("Presenter checks never show a window or create a native window handle", !window.IsVisible && new WindowInteropHelper(window).Handle == IntPtr.Zero);
        }
        finally { await window.CloseSafelyAsync(); Directory.Delete(folder, true); }
    }
}
