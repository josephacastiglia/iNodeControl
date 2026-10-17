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
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            var path = request.RequestUri!.AbsolutePath; Routes.Add(path);
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
                var data = JsonDocument.Parse(body).RootElement;
                SavedDraft = new { id = data.GetProperty("id").GetString(), revision = 1, title = "Test video", caption = "DRAFT ONLY", platform = "TikTok", format = "tt_video",
                    video = new { seconds = 2.0, codec = "h264", width = 720, height = 1280, fitted = true, upscaled = true }, published = false, savedInApp = false };
                if (ServerErrorAfterSave)
                    return new(HttpStatusCode.InternalServerError) { Content = new StringContent("{\"error\":\"Response failed after saving\"}", Encoding.UTF8, "application/json") };
                if (LoseResponse) throw new HttpRequestException("Response lost after local save");
            }
            if (request.Method == HttpMethod.Get && path.StartsWith("/api/farm/video-drafts/") && SavedDraft is null)
                return new(HttpStatusCode.NotFound) { Content = new StringContent("{\"error\":\"Video draft not saved yet\"}", Encoding.UTF8, "application/json") };
            object payload = path == "/api/farm/video-drafts" && request.Method == HttpMethod.Get
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
    }
}
