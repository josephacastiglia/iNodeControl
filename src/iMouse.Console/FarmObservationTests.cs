using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.IO;

namespace IMouse2;

internal sealed partial class FarmObservationWindow
{
    private sealed class Handler : HttpMessageHandler
    {
        internal JsonElement? Saved;
        internal List<string> Routes = [];
        internal int Captures;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            string path = request.RequestUri!.AbsolutePath; Routes.Add(path);
            if (request.Method == HttpMethod.Post)
            {
                Captures++;
                var input = JsonSerializer.Deserialize<JsonElement>(await request.Content!.ReadAsStringAsync(token));
                Saved = JsonSerializer.SerializeToElement(new { id = input.GetProperty("id").GetString(), state = "observed", expected = new { platform = "tiktok", account = "test.account" }, expired = true,
                    reason = "Permission prompt needs inspection.", freshness = "unavailable", stable = true,
                    result = new { screen = "permission_prompt", accountStatus = "not_visible", captionStatus = "needs_review" } });
                throw new HttpRequestException("Lost capture response");
            }
            object result;
            if (path.EndsWith("/frame"))
            {
                var pixels = new byte[16 * 16 * 4]; var image = BitmapSource.Create(16, 16, 96, 96, PixelFormats.Bgra32, null, pixels, 64);
                var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(image)); using var bytes = new MemoryStream(); encoder.Save(bytes);
                result = new { protocolVersion = 2, frame = Convert.ToBase64String(bytes.ToArray()) };
            }
            else if (path == "/api/farm/observations") result = new { protocolVersion = 2, observations = Saved is null ? Array.Empty<JsonElement>() : new[] { Saved.Value } };
            else result = new { protocolVersion = 2, observation = Saved };
            return new(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(result), Encoding.UTF8, "application/json") };
        }
    }
    internal static async Task CheckHeadlessAsync(Action<string, bool> check)
    {
        var handler = new Handler(); using var http = new HttpClient(handler);
        var window = new FarmObservationWindow(new FarmApiClient(http, "http://observation-test.invalid"));
        try
        {
            await window.RunAsync(window.RefreshHistoryAsync);
            check("Opening screen review reads history without capturing a phone", handler.Captures == 0);
            window._account.Text = "test.account"; window._platform.SelectedIndex = 1;
            await window.RunAsync(window.CaptureAsync);
            check("Lost observation response retains its ID and disables another capture", window._pending is not null && !window._read.IsEnabled && window._recover.IsEnabled);
            await window.RunAsync(window.RecoverAsync);
            check("Observation recovery retrieves the saved frame without recapturing", handler.Captures == 1 && window._pending is null && window._frame.Source is not null);
            check("Screen review exposes permission interruptions and expired observations", window._status.Text.Contains("permission_prompt") && window._status.Text.Contains("expired") && window._status.Text.Contains("not_visible"));
            check("Screen review never calls input or publishing routes", handler.Routes.All(p => p.StartsWith("/api/farm/observations")));
            var fresh = JsonSerializer.SerializeToElement(new { id = "saved-frame", state = "observed", expected = new { platform = "tiktok", account = "test.account" }, expired = false,
                reason = "Expected account text is visible.", freshness = "recent", stable = true,
                result = new { screen = "profile", accountStatus = "exact_text_match", captionStatus = "not_requested" },
                frameEvidence = new { currentAgeUpperBoundMs = 100, reason = "Paired metadata.", meaning = "Receiver delivery, not iOS capture time." },
                workflowReview = new { status = "blocked", blockers = new[] { "Persisted draft is not verified." } } });
            await window.ApplyAsync(fresh, 50);
            window.UpdateFreshnessNotice(0);
            check("Screen review distinguishes receiver delivery from phone capture", window._status.Text.Contains("not iOS capture time") && window._freshnessNotice.Text.Contains("Recent receiver delivery only"));
            window.UpdateFreshnessNotice(1351);
            check("Screen review expires its local freshness label without another phone request", window._freshnessNotice.Text.Contains("old or its age is unverified") && handler.Captures == 1);
            check("Screen review displays the specific remaining draft evidence gaps", window._status.Text.Contains("Persisted draft is not verified"));
            var content = (FrameworkElement)window.Content; content.Measure(new Size(860, 780)); content.Arrange(new Rect(0, 0, 860, 780)); content.UpdateLayout();
            var bitmap = new RenderTargetBitmap(860, 780, 96, 96, PixelFormats.Pbgra32);
            var background = new DrawingVisual(); using (var drawing = background.RenderOpen()) drawing.DrawRectangle(window.Background, null, new Rect(0, 0, 860, 780));
            bitmap.Render(background); bitmap.Render(content); var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap));
            Directory.CreateDirectory(Path.Combine(AppContext.BaseDirectory, "qa"));
            using (var file = File.Create(Path.Combine(AppContext.BaseDirectory, "qa", "farm-observation-headless.png"))) png.Save(file);
            check("Screen review renders headlessly without opening a native window", content.IsArrangeValid && new WindowInteropHelper(window).Handle == IntPtr.Zero);
        }
        finally { window.Close(); }
    }
}

internal sealed partial class FarmPreparationWindow
{
    private sealed class Handler : HttpMessageHandler
    {
        internal List<string> Bodies = [], Routes = [];
        internal bool LoseResponse = true;
        internal string? CancelledRequest;
        internal string DraftId = Guid.NewGuid().ToString();
        internal bool Legacy;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            string path = request.RequestUri!.AbsolutePath; Routes.Add(path);
            if (request.Method == HttpMethod.Post)
            {
                string body = await request.Content!.ReadAsStringAsync(token);
                if (path.EndsWith("/pause")) CancelledRequest = JsonSerializer.Deserialize<JsonElement>(body).GetProperty("cancel_request_id").GetString();
                else { Bodies.Add(body); if (LoseResponse) { LoseResponse = false; throw new HttpRequestException("Lost configuration response"); } }
            }
            object? draft = Legacy ? null : new { id = DraftId, revision = 1 };
            var item = new Dictionary<string, object> { ["id"] = 12, ["platform"] = "instagram", ["caption"] = "Original review copy", ["stagedFiles"] = new[] { "slide_a.jpg", "slide_b.jpg" } };
            if (draft is not null)
            {
                item["localDraft"] = draft; item["generation"] = new string('a', 32); item["manifestSha256"] = new string('b', 64);
                item["stagedFiles"] = new[] { "slide_a.jpg", "slide_b.jpg", "video.mp4" };
            }
            var runs = new[] { new { state = "succeeded", id = "saved-run", contentItems = new[] { item } },
                               new { state = "failed", id = "failed-run", contentItems = new[] { item } } };
            var response = new { protocolVersion = 2, preparationSchedule = new { config = new { state = "paused", reason = "No future work", nextDue = 2000000000.0 }, runs, workerRunning = false, workerError = (string?)null } };
            return new(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(response), Encoding.UTF8, "application/json") };
        }
    }
    internal static async Task CheckHeadlessAsync(Action<string, bool> check)
    {
        var handler = new Handler(); using var http = new HttpClient(handler);
        var window = new FarmPreparationWindow(new FarmApiClient(http, "http://preparation-test.invalid"), Path.GetTempPath(), "simulate");
        try
        {
            await window.RunAsync(window.RefreshAsync);
            check("Opening preparation schedule does not start recurring work", handler.Bodies.Count == 0);
            await window.RunAsync(window.StartAsync);
            check("Unknown schedule outcome preserves its original request and freezes edits", window._pending is not null && !window._minutes.IsEnabled);
            await window.RunAsync(window.StartAsync);
            check("Retrying schedule configuration reuses identical ID and content", handler.Bodies.Count == 2 && handler.Bodies[0] == handler.Bodies[1] && window._pending is null);
            handler.LoseResponse = true; await window.RunAsync(window.StartAsync); string? pending = window._pendingId;
            await window.RunAsync(window.PauseAsync);
            check("Pause cancels the pending configuration ID so delayed requests cannot restart it", pending is not null && handler.CancelledRequest == pending && window._pending is null);
            check("Preparation reports a stopped worker and never calls phone routes", window._status.Text.Contains("worker is not running") && handler.Routes.All(p => p.StartsWith("/api/farm/preparation-schedule")));
            check("Preparation history shows the saved copy and file references for review", window._runs.Text.Contains("Original review copy") && window._runs.Text.Contains("slide_a.jpg") && window._runs.Text.Contains("item 12"));
            check("A completed run opens its specific local carousel without regeneration", window.SelectedDraftId() == handler.DraftId && window._openDraft.IsEnabled && window._runs.Text.Contains("Not an Instagram draft"));
            check("A completed run identifies its original video batch for preparation", window.SelectedVideoBatch()?.Generation == new string('a', 32) && window._openVideo.IsEnabled);
            window._history.SelectedIndex = 1;
            await window.RunAsync(window.RefreshAsync);
            check("Refreshing preparation history keeps the selected run and refuses failed output", (window._history.SelectedItem as PreparedRun)?.Id == "failed-run" && !window._openDraft.IsEnabled);
            handler.Legacy = true; window._history.SelectedIndex = 0; await window.RunAsync(window.RefreshAsync);
            check("Old runs without a saved snapshot stay readable but never open the latest batch", window._runs.Text.Contains("Original review copy") && !window._openDraft.IsEnabled && !window._openVideo.IsEnabled);
            handler.Legacy = false; await window.RunAsync(window.RefreshAsync);
            var content = (FrameworkElement)window.Content; content.Measure(new Size(720, 820)); content.Arrange(new Rect(0, 0, 720, 820)); content.UpdateLayout();
            var bitmap = new RenderTargetBitmap(720, 820, 96, 96, PixelFormats.Pbgra32);
            var background = new DrawingVisual(); using (var drawing = background.RenderOpen()) drawing.DrawRectangle(window.Background, null, new Rect(0, 0, 720, 820));
            bitmap.Render(background); bitmap.Render(content); var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap));
            using (var file = File.Create(Path.Combine(AppContext.BaseDirectory, "qa", "farm-preparation-headless.png"))) png.Save(file);
            check("Preparation schedule renders without showing a desktop window", content.IsArrangeValid && new WindowInteropHelper(window).Handle == IntPtr.Zero);
        }
        finally { window.Close(); }
    }
}
