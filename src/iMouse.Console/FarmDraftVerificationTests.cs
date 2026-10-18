using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace IMouse2;

internal sealed partial class FarmDraftVerificationWindow
{
    private sealed class Handler : HttpMessageHandler
    {
        internal int Comparisons;
        internal string? Id;
        internal List<string> Routes = [];
        internal object Document() => new { id = Id, draftChangedSinceReview = true, assessment = new {
            status = "incomplete", source = "simulation_or_mixed", blockers = new[] { "Missing reopened slide 3.", "Account text is ambiguous." },
            slideCoverage = new { reopened = new { expectedCount = 3, observedIndices = new[] { 1, 3 }, fullSizeAndPositionMatch = false } },
            accountHistory = new { status = "incomplete", observations = new[] { new { id = "intervening-screen", screen = "permission_prompt", account = "not_visible" } } },
            stages = new { reopened = new[] { new { id = "saved-observation", screen = "draft_details", account = "not_visible", media = new { status = "visual_match", matchedIndex = 1 }, caption = new { status = "exact_visible_lines" } } } },
            limits = new[] { "Similar pixels are not byte identity.", "Account observations do not establish uninterrupted continuity." } } };
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            string path = request.RequestUri!.AbsolutePath; Routes.Add(path);
            if (request.Method == HttpMethod.Post)
            {
                Comparisons++; var body = JsonSerializer.Deserialize<JsonElement>(await request.Content!.ReadAsStringAsync(token));
                Id = body.GetProperty("id").GetString(); throw new HttpRequestException("Lost review response");
            }
            const string png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=";
            object response = path.Contains("/frames/") ? new { protocolVersion = 2, frame = png } : path switch {
                "/health" => new { protocolVersion = 2, draftVerificationVersion = 2 },
                "/api/farm/observations" => new { protocolVersion = 2, observations = Array.Empty<object>() },
                "/api/farm/draft-verifications" => new { protocolVersion = 2, verifications = Array.Empty<object>() },
                _ => new { protocolVersion = 2, verification = Document() }
            };
            return new(HttpStatusCode.OK) { Content = new StringContent(JsonSerializer.Serialize(response), Encoding.UTF8, "application/json") };
        }
    }
    internal static async Task CheckHeadlessAsync(Action<string, bool> check)
    {
        var handler = new Handler(); using var http = new HttpClient(handler);
        var window = new FarmDraftVerificationWindow(new FarmApiClient(http, "http://verification-test.invalid"), Guid.NewGuid().ToString(), 5, "Test carousel");
        try
        {
            await window.RunAsync(window.RefreshAsync);
            check("Opening draft verification reads saved history without a phone capture", handler.Comparisons == 0 && !handler.Routes.Any(r => r.EndsWith("/frame")) && window._status.Text.Contains("No saved"));
            window._account.Text = "test.account";
            await window.RunAsync(window.CompareAsync);
            check("Lost draft review response freezes evidence selections and retains request ID", window._pending == handler.Id && !window._compare.IsEnabled && !window._account.IsEnabled && window._recover.IsEnabled);
            await window.RunAsync(window.RecoverAsync);
            check("Draft verification recovery retrieves the same result without another comparison", handler.Comparisons == 1 && window._pending is null && window._compare.IsEnabled);
            check("Draft verification shows changed revision, missing media and uncertain account", window._status.Text.Contains("older revision") && window._status.Text.Contains("Missing reopened slide 3") && window._status.Text.Contains("ambiguous"));
            check("Draft evidence shows slide count and position coverage", window._status.Text.Contains("expected 3") && window._status.Text.Contains("positions incomplete"));
            check("Draft evidence includes unselected account-history images", window._frames.Items.Cast<Review>().Any(r => r.Id == "intervening-screen"));
            check("Account history is presented as sampled evidence", window._status.Text.Contains("Account history: incomplete") && window._status.Text.Contains("between captures"));
            check("Draft review never labels a visual match as an app save or input permission", window._status.Text.Contains("NOT verified") && window._status.Text.Contains("remain disabled") && window._status.Text.Contains("visual_match"));
            await window.RunAsync(window.ViewAsync);
            check("Draft review retrieves its retained image without a phone capture", window._preview.Source is not null && handler.Comparisons == 1);
            window._preview.Source = null;
            check("Draft review requests only local evidence and health routes", handler.Routes.All(r => r == "/health" || r == "/api/farm/observations" || r.StartsWith("/api/farm/draft-verifications")));
            var content = (FrameworkElement)window.Content; content.Measure(new Size(1000, 860)); content.Arrange(new Rect(0, 0, 1000, 860)); content.UpdateLayout();
            var image = new RenderTargetBitmap(1000, 860, 96, 96, PixelFormats.Pbgra32);
            var background = new DrawingVisual(); using (var drawing = background.RenderOpen()) drawing.DrawRectangle(window.Background, null, new Rect(0, 0, 1000, 860));
            image.Render(background); image.Render(content); var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(image));
            using (var file = File.Create(Path.Combine(AppContext.BaseDirectory, "qa", "farm-draft-verification-headless.png"))) png.Save(file);
            check("Draft evidence review renders without creating a desktop window", content.IsArrangeValid && new WindowInteropHelper(window).Handle == IntPtr.Zero);
        }
        finally { window.Close(); }
    }
}
