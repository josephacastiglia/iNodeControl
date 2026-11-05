using System.IO;
using System.Text.Json;
using System.Windows.Interop;

namespace IMouse2;

public partial class MainWindow
{
    /// <summary>Exercises actual handlers/presentation/export without Show, an HWND,
    /// a listener or injected input. Every command uses TestHandler.</summary>
    internal static async Task CheckResponseTimingAsync(Action<string, bool> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "imouse-response-timing-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder, "settings.json"), "{\"address\":\"http://localhost:9923\",\"trackPointer\":false}");
        var trace = new ResponseTiming(); var handler = new TestHandler { OwnershipSupported = true };
        var window = new MainWindow(address => new ApiClient(address, handler, ownership: true), folder, trace);
        try
        {
            window.AutoPreview.IsChecked = false;
            await window.ConnectAsync(); await window._scopeTail;
            await window.SendInputAsync("test", "/key/sendkey", new() { ["fn_key"] = "Home" }, origin: "test_handler");
            var events = trace.Snapshot().Events;
            var requested = events.Last(e => e.Kind == "action_requested");
            var action = events.Where(e => e.ActionId == requested.ActionId).ToArray();
            check("Actual input handler records request, queued start and completion", action.Select(e => e.Kind)
                .SequenceEqual(new[] { "action_requested", "command_started", "action_finished" })
                && action[^1].Outcome == "command_completed" && requested.Operation == "Home");
            window._controlReady = false;
            int sent = handler.Commands.Count;
            await window.SendInputAsync("test", "/mouse/click", new() { ["x"] = 1, ["y"] = 2 });
            check("A blocked input is recorded without being sent", trace.Snapshot().Events[^1].Outcome == "not_ready" && handler.Commands.Count == sent);

            var stamp = window._previewFreshness.Observe(window._frameEpoch, false,
                new("0123456789abcdef0123456789abcdef", 10, 0, "flowing"))!;
            PreparedFrame Frame(PreviewStamp s) => new() { Width = 4, Height = 4, Bits = 24, Stride = 12, Pixels = new byte[48], PreviewStamp = s };
            window._pending = Frame(stamp);
            int count = trace.Snapshot().Events.Count(e => e.Kind == "bitmap_applied");
            window.PresentPending(null, EventArgs.Empty);
            var applied = trace.Snapshot().Events.Last(e => e.Kind == "bitmap_applied");
            check("Actual presenter records successful bitmap application with delivery identity",
                window.PhoneImage.Source == window._live.Source && applied.FrameSequence == 10
                && applied.Epoch == window._frameEpoch && applied.Width == 4 && applied.Height == 4);
            window.PresentPending(null, EventArgs.Empty);
            check("Empty rendering ticks do not count as displayed frames", trace.Snapshot().Events.Count(e => e.Kind == "bitmap_applied") == count + 1);
            window._pending = Frame(stamp with { Epoch = window._frameEpoch - 1 });
            window.PresentPending(null, EventArgs.Empty);
            check("Obsolete phone frames do not enter the presentation timeline", trace.Snapshot().Events.Count(e => e.Kind == "bitmap_applied") == count + 1);
            window._pending = Frame(stamp); window._pending.Width = 0;
            window.PresentPending(null, EventArgs.Empty);
            check("Failed bitmap application does not enter the timeline", trace.Snapshot().Events.Count(e => e.Kind == "bitmap_applied") == count + 1);
            var report = await window.CollectDiagnosticReportAsync();
            var exported = report.Console.GetProperty("response_timing");
            check("Actual diagnostics export includes bounded monotonic timing evidence",
                exported.GetProperty("timestamp_frequency").GetInt64() > 0 && exported.GetProperty("dropped_events").GetInt64() == 0
                && exported.GetProperty("events").GetArrayLength() == trace.Snapshot().Events.Length);
            check("Timing checks never show a window or create a native window handle", !window.IsVisible && new WindowInteropHelper(window).Handle == IntPtr.Zero);
            string qa = Path.Combine(InstallLayout.RunFiles, "qa"); Directory.CreateDirectory(qa);
            File.WriteAllText(Path.Combine(qa, "response-timing-diagnostics.json"), JsonSerializer.Serialize(report, ConsoleDiagnostics.JsonOptions));
        }
        finally { await window.CloseSafelyAsync(); Directory.Delete(folder, true); }
    }
}
