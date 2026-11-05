using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace IMouse2;

internal sealed partial class FarmDraftRehearsalWindow
{
    private sealed class TestHandler : HttpMessageHandler
    {
        internal string? Id;
        internal int Starts, Cancels;
        internal bool Missing, Running, Live;
        internal readonly List<string> Routes = [];
        internal object Record() => new { id = Id, source = "simulation", state = Running ? "running" : "review_required", reason = "Save reply lost; no replay.", cleanup = "confirmed",
            request = new { scenario = "save_reply_lost", revision = 3 }, draftChangedSinceRun = true, savedDraftVerified = false, accountContinuityProven = false, automaticInputAllowed = false,
            recovery = "Inspect the saved result. Do not replay Save.", actions = new[] { new { kind = "save_draft", state = "outcome_unknown" } },
            reconciliation = new { status = "matching_screen_after_unknown_reply" }, evidenceManifest = new { frame1 = new { } }, captureRoles = new { frame1 = "library" } };
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            string route = request.RequestUri!.AbsolutePath; Routes.Add(route);
            if (request.Method == HttpMethod.Post)
            {
                if (route.EndsWith("/cancel")) { Cancels++; return Response(new { protocolVersion = 2, cancellationRequested = true }); }
                Starts++; Id = JsonSerializer.Deserialize<JsonElement>(await request.Content!.ReadAsStringAsync(token)).GetProperty("id").GetString();
                throw new HttpRequestException("Lost response");
            }
            if (route == "/health") return Response(new { protocolVersion = 2, draftRehearsalVersion = 1, executionMode = Live ? "live" : "simulate" });
            if (route == "/api/farm/draft-rehearsals") return Response(new { protocolVersion = 2, rehearsals = Id is null ? Array.Empty<object>() : new[] { Record() } });
            if (route.Contains("/frames/")) return Response(new { protocolVersion = 2, frame = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=" });
            return Missing ? Response(new { error = "Result unavailable" }, HttpStatusCode.NotFound) : Response(new { protocolVersion = 2, rehearsal = Record() });
        }
        private static HttpResponseMessage Response(object body, HttpStatusCode code = HttpStatusCode.OK) => new(code) { Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json") };
    }

    internal static async Task CheckHeadlessAsync(Action<string, bool> check)
    {
        var handler = new TestHandler(); using var http = new HttpClient(handler);
        var window = new FarmDraftRehearsalWindow(new FarmApiClient(http, "http://rehearsal-test.invalid"), Guid.NewGuid().ToString(), 3, "Test carousel");
        try
        {
            await window.RunAsync(window.InitializeAsync);
            check("Draft rehearsal opens with read-only history and explicit simulation", handler.Starts == 0 && window._start.IsEnabled && window._status.Text.Contains("fault scenario"));
            await window.RunAsync(window.StartAsync);
            check("Lost rehearsal response retains its ID and disables a duplicate start", handler.Starts == 1 && window._pending == handler.Id && !window._start.IsEnabled && window._recover.IsEnabled);
            handler.Missing = true; await window.RunAsync(window.RecoverAsync);
            check("Missing rehearsal result does not silently authorize another attempt", window._pending == handler.Id && !window._start.IsEnabled && handler.Starts == 1);
            handler.Missing = false; handler.Running = true; await window.RunAsync(window.RecoverAsync);
            check("Running rehearsal remains pending after status recovery", window._pending == handler.Id && !window._start.IsEnabled);
            window._busy = true; window.Buttons(); await window.CancelAsync(); window._busy = false;
            check("Rehearsal cancellation remains available while a request is busy", handler.Cancels == 1 && window._cancel.IsEnabled);
            handler.Running = false; await window.RunAsync(window.RecoverAsync);
            check("Terminal rehearsal recovery retrieves rather than replaying Save", handler.Starts == 1 && window._pending is null && window._start.IsEnabled);
            check("Rehearsal distinguishes matching reconciliation from verified app persistence", window._status.Text.Contains("No phone draft") && window._status.Text.Contains("Outcome unknown") && window._status.Text.Contains("not replayed") && window._status.Text.Contains("older revision"));
            await window.RunAsync(window.ViewAsync);
            check("Rehearsal preview reads a retained simulated frame", window._preview.Source is not null && handler.Starts == 1);
            handler.Live = true; await window.RunAsync(window.InitializeAsync);
            check("Live backend cannot enable the offline rehearsal start button", !window._start.IsEnabled);
            check("Rehearsal window uses only health and local rehearsal routes", handler.Routes.All(r => r == "/health" || r.StartsWith("/api/farm/draft-rehearsals")));
            handler.Live = false; await window.RunAsync(window.InitializeAsync); await window.RunAsync(() => window.ShowAsync(handler.Id!));
            check("Rehearsal selections display plain labels instead of serialized records", window._scenario.SelectedItem!.ToString() == "Complete save and reopen" && window._frames.SelectedItem!.ToString() == "Library");
            var content = (FrameworkElement)window.Content; content.Measure(new Size(850, 800)); content.Arrange(new Rect(0, 0, 850, 800)); content.UpdateLayout();
            var image = new RenderTargetBitmap(850, 800, 96, 96, PixelFormats.Pbgra32);
            var background = new DrawingVisual(); using (var drawing = background.RenderOpen()) drawing.DrawRectangle(window.Background, null, new Rect(0, 0, 850, 800));
            image.Render(background); image.Render(content); var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(image));
            using (var file = System.IO.File.Create(System.IO.Path.Combine(InstallLayout.RunFiles, "qa", "farm-draft-rehearsal-headless.png"))) png.Save(file);
            check("Draft rehearsal renders without creating a desktop window", content.IsArrangeValid && new WindowInteropHelper(window).Handle == IntPtr.Zero);
        }
        finally { window.Close(); }
    }
}
