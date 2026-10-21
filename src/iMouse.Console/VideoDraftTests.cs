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

internal sealed partial class VideoDraftWindow
{
    private sealed class TestHandler : HttpMessageHandler
    {
        internal object? SavedDraft;
        internal int Creates;
        internal bool LoseResponse = true;
        internal bool DropBeforeSave;
        internal bool BusyBeforeSave;
        internal bool ServerErrorAfterSave;
        internal List<string> CreateBodies = [];
        internal List<string> Routes = [];
        internal List<string> Queries = [];
        internal string Generation = new string('a', 32);
        internal string Format = "tt_video";
        internal string? CreatedId;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            var path = request.RequestUri!.AbsolutePath; Routes.Add(path);
            Queries.Add(request.RequestUri!.Query);
            if (request.Method == HttpMethod.Post)
            {
                Creates++;
                var body = await request.Content!.ReadAsStringAsync(token); CreateBodies.Add(body);
                if (DropBeforeSave) { DropBeforeSave = false; throw new HttpRequestException("Request never reached storage"); }
                if (BusyBeforeSave)
                {
                    BusyBeforeSave = false;
                    return new(HttpStatusCode.Conflict) { Content = new StringContent("{\"error\":\"Preparation busy\"}", Encoding.UTF8, "application/json") };
                }
                var data = JsonDocument.Parse(body).RootElement; CreatedId = data.GetProperty("id").GetString();
                SavedDraft = new { id = data.GetProperty("id").GetString(), revision = 1, title = "Test video", caption = "DRAFT ONLY", platform = Format switch { "ig_reel" => "Instagram", "x_video" => "X", "yt_short" => "YouTube", _ => "TikTok" }, format = Format,
                    video = new { seconds = 2.0, codec = "h264", width = 720, height = 1280, fitted = true, upscaled = true }, published = false, savedInApp = false };
                if (ServerErrorAfterSave)
                    return new(HttpStatusCode.InternalServerError) { Content = new StringContent("{\"error\":\"Response failed after saving\"}", Encoding.UTF8, "application/json") };
                if (LoseResponse) throw new HttpRequestException("Response lost after local save");
            }
            if (request.Method == HttpMethod.Get && path.StartsWith("/api/farm/video-drafts/") && SavedDraft is null)
                return new(HttpStatusCode.NotFound) { Content = new StringContent("{\"error\":\"Video draft not saved yet\"}", Encoding.UTF8, "application/json") };
            object payload = path == "/api/farm/video-sources"
                ? new { protocolVersion = 2, sources = new[] { new { name = "batch.mp4", sha256 = new string('c', 64), sourceGeneration = Generation, manifestSha256 = new string('b', 64), caption = "Prepared batch caption" } } }
                : path == "/api/farm/video-drafts" && request.Method == HttpMethod.Get
                ? new { protocolVersion = 2, drafts = SavedDraft is null ? Array.Empty<object>() : new[] { SavedDraft } }
                : new { protocolVersion = 2, draft = SavedDraft };
            return new(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json") };
        }
    }

    internal static async Task CheckHeadlessAsync(Action<string, bool> check)
    {
        var handler = new TestHandler(); using var http = new HttpClient(handler);
        var window = new VideoDraftWindow(new FarmApiClient(http, "http://video-test.invalid"));
        try
        {
            window._sources.ItemsSource = new[] { new Source("test.mp4", new string('a', 64)) }; window._sources.SelectedIndex = 0;
            window._caption.Text = "DRAFT ONLY";
            check("Video preparation opens without a transfer or phone request", handler.Creates == 0 && !window._transfer.IsEnabled);
            await window.RunAsync(window.PrepareAsync);
            check("A lost video preparation response keeps its ID for recovery", window._pending is not null && !window._transfer.IsEnabled && handler.Creates == 1);
            check("An unknown video outcome blocks selecting a different saved copy", !window._saved.IsEnabled && !window._caption.IsEnabled);
            await window.RunAsync(window.PrepareAsync);
            check("Video draft recovery reads the saved copy without reencoding", window._draft is not null && window._pending is null && handler.Creates == 1 && window._transfer.IsEnabled);
            check("Video preparation explains margins and source enlargement", window._status.Text.Contains("Margins") && window._status.Text.Contains("enlarged"));
            window._caption.Text = "Edited caption";
            check("Editing preparation fields invalidates transfer of a stale saved copy", !window._transfer.IsEnabled && window._draft is null);
            window._saved.SelectedIndex = 0;
            check("Saved video library can recover a previous immutable copy", window._transfer.IsEnabled && window._draft is not null);
            check("Selecting a saved video shows its stored caption and destination", window._caption.Text == "DRAFT ONLY" && window._title.Text == "Test video" && window._format.SelectedIndex == 0 && window._sources.SelectedIndex == -1);
            var content = (FrameworkElement)window.Content; content.Measure(new Size(650, 740)); content.Arrange(new Rect(0, 0, 650, 740)); content.UpdateLayout();
            var bitmap = new RenderTargetBitmap(650, 740, 96, 96, PixelFormats.Pbgra32);
            var background = new DrawingVisual(); using (var draw = background.RenderOpen()) draw.DrawRectangle(window.Background, null, new Rect(0, 0, 650, 740));
            bitmap.Render(background); bitmap.Render(content); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
            string qa = Path.Combine(AppContext.BaseDirectory, "qa"); Directory.CreateDirectory(qa);
            using (var file = File.Create(Path.Combine(qa, "video-draft-headless.png"))) encoder.Save(file);
            check("Video draft view renders without desktop control or a native window", content.IsArrangeValid && new WindowInteropHelper(window).Handle == IntPtr.Zero && !window.IsVisible);
            check("Preparing a video never calls phone, publishing or messaging routes", handler.Routes.All(p => p.StartsWith("/api/farm/video-drafts")));
        }
        finally { window.Close(); }
        var missingHandler = new TestHandler { DropBeforeSave = true, BusyBeforeSave = true, LoseResponse = false };
        using var missingHttp = new HttpClient(missingHandler);
        var missing = new VideoDraftWindow(new FarmApiClient(missingHttp, "http://video-test.invalid"));
        try
        {
            missing._sources.ItemsSource = new[] { new Source("test.mp4", new string('a', 64)) }; missing._sources.SelectedIndex = 0;
            missing._caption.Text = "DRAFT ONLY";
            await missing.RunAsync(missing.PrepareAsync);
            check("A video request lost before storage remains recoverable without phone input", missing._pending is not null && missingHandler.SavedDraft is null && !missing._transfer.IsEnabled);
            await missing.RunAsync(missing.PrepareAsync);
            check("A busy backend preserves video recovery identity and blocks transfer", missing._pending is not null && !missing._transfer.IsEnabled && missingHandler.SavedDraft is null);
            await missing.RunAsync(missing.PrepareAsync);
            check("A confirmed missing video retries the identical ID and original content", missing._draft is not null && missing._pending is null && missingHandler.Creates == 3 && missingHandler.CreateBodies.Distinct().Count() == 1);
            check("Recovery checks storage before retrying preparation", missingHandler.Routes.Count > 2 && missingHandler.Routes[1].StartsWith("/api/farm/video-drafts/") && missingHandler.Routes[2] == "/api/farm/video-drafts");
        }
        finally { missing.Close(); }
        var failedResponse = new TestHandler { ServerErrorAfterSave = true, LoseResponse = false };
        using var failedHttp = new HttpClient(failedResponse);
        var recoverable = new VideoDraftWindow(new FarmApiClient(failedHttp, "http://video-test.invalid"));
        try
        {
            recoverable._sources.ItemsSource = new[] { new Source("test.mp4", new string('a', 64)) }; recoverable._sources.SelectedIndex = 0;
            await recoverable.RunAsync(recoverable.PrepareAsync);
            bool retained = recoverable._pending is not null && !recoverable._transfer.IsEnabled;
            await recoverable.RunAsync(recoverable.PrepareAsync);
            check("A server error after saving recovers the same video without creating a duplicate", retained && recoverable._draft is not null && failedResponse.Creates == 1 && recoverable._pending is null);
        }
        finally { recoverable.Close(); }
        var batchHandler = new TestHandler(); using var batchHttp = new HttpClient(batchHandler);
        var batch = new VideoDraftWindow(new FarmApiClient(batchHttp, "http://video-test.invalid"), new Batch(new string('a', 32), new string('b', 64)));
        try
        {
            await batch.RunAsync(batch.InitializeAsync);
            check("Opening a scheduled video uses that batch and preserves its original caption", batch._caption.Text == "Prepared batch caption" &&
                batchHandler.Queries.Any(q => q.Contains("generation=" + new string('a', 32))) && batchHandler.Creates == 0);
            await batch.RunAsync(batch.PrepareAsync);
            var sent = JsonSerializer.Deserialize<JsonElement>(batchHandler.CreateBodies.Single());
            check("Video preparation pins the selected generation and checksum through lost-response recovery", batch._pending is not null &&
                sent.GetProperty("source_generation").GetString() == new string('a', 32) && sent.GetProperty("manifest_sha256").GetString() == new string('b', 64));
            await batch.RunAsync(batch.PrepareAsync);
            check("Pinned video recovery retrieves its saved copy without creating a second one", batchHandler.Creates == 1 && batch._pending is null);
        }
        finally { batch.Close(); }
        batchHandler.Generation = new string('d', 32);
        var wrongBatch = new VideoDraftWindow(new FarmApiClient(batchHttp, "http://video-test.invalid"), new Batch(new string('a', 32), new string('b', 64)));
        try
        {
            await wrongBatch.RunAsync(wrongBatch.InitializeAsync);
            check("A different video batch cannot silently replace the requested run", wrongBatch._sources.SelectedItem is null && wrongBatch._status.Text.Contains("another batch") && !wrongBatch._transfer.IsEnabled);
        }
        finally { wrongBatch.Close(); }
        string folder = Path.Combine(Path.GetTempPath(), "video-reel-window-" + Guid.NewGuid()); Directory.CreateDirectory(folder);
        var reelHandler = new TestHandler { LoseResponse = false, Format = "ig_reel" }; using var reelHttp = new HttpClient(reelHandler);
        var reel = new VideoDraftWindow(new FarmApiClient(reelHttp, "http://video-test.invalid"), dataFolder: folder);
        var plain = new VideoDraftWindow(new FarmApiClient(reelHttp, "http://video-test.invalid"));
        try
        {
            reel._sources.ItemsSource = new[] { new Source("reel.mp4", new string('a', 64)) }; reel._sources.SelectedIndex = 0; reel._format.SelectedIndex = 3;
            check("Reel draft action stays disabled before a saved Instagram Reel copy exists", !reel._reel.IsEnabled && reelHandler.Creates == 0);
            await reel.RunAsync(reel.PrepareAsync);
            var candidate = reel.ReelWindow();
            check("A saved Instagram Reel copy enables only the bounded Reel candidate window", reel._reel.IsEnabled && candidate is not null && candidate.Route == "/api/farm/reel-creations"
                && candidate.Capability == "reelCreation" && candidate.BookmarkPath.EndsWith("farm-pending-reel-creation.json") && candidate.DraftId == reelHandler.CreatedId && !candidate.InspectAvailable);
            check("Opening the Reel candidate sends no phone, transfer or creation request", reelHandler.Routes.All(p => p.StartsWith("/api/farm/video-drafts")));
            candidate?.Close();
            reel._caption.Text = "Edited caption";
            check("Editing the caption disables the Reel draft action for the stale copy", !reel._reel.IsEnabled && reel.ReelWindow() is null);
            reelHandler.Format = "tt_video"; reel._format.SelectedIndex = 0; reel._sources.SelectedIndex = 0;
            await reel.RunAsync(reel.PrepareAsync);
            check("Other video formats never offer the Reel draft action", reel._draft is not null && !reel._reel.IsEnabled && reel.ReelWindow() is null);
            var tiktok = reel.TikTokWindow();
            check("A saved TikTok video copy enables only the bounded TikTok candidate window", reel._tiktok.IsEnabled && tiktok is not null
                && tiktok.Route == "/api/farm/tiktok-creations" && tiktok.Capability == "tiktokCreation" && tiktok.BookmarkPath.EndsWith("farm-pending-tiktok-creation.json")
                && tiktok.DraftId == reelHandler.CreatedId && !tiktok.InspectAvailable && reelHandler.Routes.All(p => p.StartsWith("/api/farm/video-drafts")));
            tiktok?.Close();
            plain._draft = reel._draft; reelHandler.Format = "ig_reel";
            check("Without a candidate data folder the Reel action is absent", !plain._reel.IsEnabled && plain.ReelWindow() is null);
            check("Without a candidate data folder the TikTok action is absent", !plain._tiktok.IsEnabled && plain.TikTokWindow() is null);
            reel._caption.Text = "Edited TikTok caption";
            check("Editing the caption disables the TikTok draft action for the stale copy", !reel._tiktok.IsEnabled && reel.TikTokWindow() is null);
            reelHandler.Format = "x_video"; reel._format.SelectedIndex = 1; reel._sources.SelectedIndex = 0;
            await reel.RunAsync(reel.PrepareAsync);
            var xWindow = reel.XWindow();
            check("A saved X video copy enables only the bounded X candidate window", reel._x.IsEnabled && !reel._tiktok.IsEnabled && !reel._reel.IsEnabled && xWindow is not null
                && xWindow.Route == "/api/farm/x-creations" && xWindow.Capability == "xCreation" && xWindow.BookmarkPath.EndsWith("farm-pending-x-creation.json")
                && xWindow.DraftId == reelHandler.CreatedId && !xWindow.InspectAvailable && reelHandler.Routes.All(p => p.StartsWith("/api/farm/video-drafts")));
            check("An X copy never offers the YouTube draft action", !reel._youtube.IsEnabled && reel.YouTubeWindow() is null);
            xWindow?.Close();
            plain._draft = reel._draft;
            check("Without a candidate data folder the X action is absent", !plain._x.IsEnabled && plain.XWindow() is null);
            reel._caption.Text = "Edited X text";
            check("Editing the caption disables the X draft action for the stale copy", !reel._x.IsEnabled && reel.XWindow() is null);
            reelHandler.Format = "yt_short"; reel._format.SelectedIndex = 2; reel._sources.SelectedIndex = 0;
            await reel.RunAsync(reel.PrepareAsync);
            var youtube = reel.YouTubeWindow();
            check("A saved YouTube Short copy enables only the bounded YouTube candidate window", (reel._youtube.Content as string) == "Create YouTube Short draft…" && reel._youtube.IsEnabled && !reel._x.IsEnabled && !reel._tiktok.IsEnabled && !reel._reel.IsEnabled
                && youtube is not null && youtube.Route == "/api/farm/youtube-creations" && youtube.Capability == "youtubeCreation"
                && youtube.BookmarkPath.EndsWith("farm-pending-youtube-creation.json") && youtube.DraftId == reelHandler.CreatedId && !youtube.InspectAvailable
                && reelHandler.Routes.All(p => p.StartsWith("/api/farm/video-drafts")));
            youtube?.Close();
            plain._draft = reel._draft;
            check("Without a candidate data folder the YouTube action is absent", !plain._youtube.IsEnabled && plain.YouTubeWindow() is null);
            reel._caption.Text = "Edited YouTube title";
            check("Editing the title disables the YouTube draft action for the stale copy", !reel._youtube.IsEnabled && reel.YouTubeWindow() is null);
        }
        finally { reel.Close(); plain.Close(); Directory.Delete(folder, recursive: true); }
    }
}
