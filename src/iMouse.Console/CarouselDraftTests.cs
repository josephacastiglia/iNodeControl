using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows.Interop;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace IMouse2;

public partial class CarouselDraftWindow
{
    private sealed class DraftHandler : HttpMessageHandler
    {
        internal CarouselDraft Draft = new() { Id = Guid.NewGuid().ToString(), Title = "Saved draft", Revision = 1 };
        internal List<string> Requests = [];
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string path = request.RequestUri!.AbsolutePath;
            Requests.Add(request.Method + " " + path);
            if (request.Method == HttpMethod.Get && path == "/api/farm/drafts")
                return Response(new { protocolVersion = 2, drafts = new[] { new { id = Draft.Id, title = Draft.Title } } });
            if (request.Method == HttpMethod.Post && path.EndsWith("/save"))
            {
                using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(cancellationToken));
                var root = body.RootElement;
                if (root.GetProperty("revision").GetInt32() != Draft.Revision)
                    return Response(new { error = "Revision conflict" }, HttpStatusCode.Conflict);
                if (root.GetProperty("caption").GetString()!.Length > 2200)
                    return Response(new { error = "Caption exceeds 2200 characters" }, HttpStatusCode.BadRequest);
                Draft.Title = root.GetProperty("title").GetString()!;
                Draft.Caption = root.GetProperty("caption").GetString()!;
                Draft.SlideIds = root.GetProperty("slide_ids").EnumerateArray().Select(x => x.GetString()!).ToArray();
                Draft.Slides = Draft.SlideIds.Select(id => Draft.Slides.First(s => s.Id == id)).ToArray();
                Draft.Revision++;
            }
            return Response(new { protocolVersion = 2, draft = Draft });
        }
        private static HttpResponseMessage Response(object value, HttpStatusCode code = HttpStatusCode.OK) =>
            new(code) { Content = new StringContent(JsonSerializer.Serialize(value), Encoding.UTF8, "application/json") };
    }

    internal static async Task CheckHeadlessAsync(Action<string, bool> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "imouse-carousel-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        var handler = new DraftHandler();
        using var http = new HttpClient(handler);
        var api = new FarmApiClient(http, "http://carousel-test.invalid");
        var window = new CarouselDraftWindow(api, folder, "simulate");
        CarouselDraftWindow? reopened = null;
        CarouselDraftWindow? conflict = null;
        try
        {
            // A valid 1x1 PNG makes preview decoding part of the headless check.
            const string preview = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=";
            handler.Draft.Slides = [new() { Id = "one", Name = "First", Preview = preview }, new() { Id = "two", Name = "Second", Preview = preview }];
            handler.Draft.SlideIds = ["one", "two"];
            await window.InitializeAsync();
            window.Apply(CarouselDraft.Read(await api.SendAsync("/api/farm/drafts/" + handler.Draft.Id)));
            window.TitleBox.Text = "Campaign draft";
            window.CaptionBox.Text = "Hi there\nUnicode café 🎉";
            window.SlidesList.SelectedIndex = 1;
            window.Move(-1);
            var edits = new CarouselRecovery(folder).Load()!;
            check("Carousel editing preserves caption and selected slide order for crash recovery",
                edits.Unsaved && edits.Caption == window.CaptionBox.Text && edits.SlideIds.SequenceEqual(new[] { "two", "one" }));
            check("Carousel preview uses the selected slide", window.SlidePreview.Source is not null && window.SlideNumber.Text == "Slide 1 of 2");
            reopened = new CarouselDraftWindow(api, folder, "simulate");
            await reopened.InitializeAsync();
            check("Carousel reopening restores unsaved text and ordering", reopened.CaptionBox.Text == edits.Caption && reopened._slides.Select(s => s.Id).SequenceEqual(edits.SlideIds));
            await reopened.SaveAsync();
            check("Carousel save commits a new revision without claiming Instagram saved it", handler.Draft.Revision == 2 && !handler.Draft.SavedInInstagram && !new CarouselRecovery(folder).Load()!.Unsaved);
            // Render only the unshown content tree; no desktop capture or native window.
            reopened.EditorControls.IsEnabled = true;
            var content = (FrameworkElement)reopened.Content;
            content.Measure(new Size(1000, 700));
            content.Arrange(new Rect(0, 0, 1000, 700));
            content.UpdateLayout();
            var bitmap = new RenderTargetBitmap(1000, 700, 96, 96, PixelFormats.Pbgra32);
            var background = new DrawingVisual();
            using (var drawing = background.RenderOpen()) drawing.DrawRectangle(reopened.Background, null, new Rect(0, 0, 1000, 700));
            bitmap.Render(background);
            bitmap.Render(content);
            var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(bitmap));
            string qa = Path.Combine(AppContext.BaseDirectory, "qa"); Directory.CreateDirectory(qa);
            using (var output = File.Create(Path.Combine(qa, "carousel-editor-headless.png"))) png.Save(output);
            check("Carousel editor renders at desktop size without a window", content.IsMeasureValid && bitmap.PixelWidth == 1000 && new WindowInteropHelper(reopened).Handle == IntPtr.Zero);
            reopened.CaptionBox.Text = new string('x', 2201);
            bool refused = false;
            try { await reopened.SaveAsync(); }
            catch (FarmRequestRejectedException) { refused = true; }
            check("Carousel does not truncate over-budget pasted captions", refused && reopened.CaptionBox.Text.Length == 2201 && handler.Draft.Caption == edits.Caption);
            check("Rejected carousel edits remain recoverable", new CarouselRecovery(folder).Load()!.Caption.Length == 2201);
            handler.Draft.Revision++;
            conflict = new CarouselDraftWindow(api, folder, "simulate");
            await conflict.InitializeAsync();
            string[] archives = Directory.GetFiles(folder, "farm-carousel-edits-*.json");
            check("Conflicting recovery edits are archived before loading the newer draft", archives.Length == 1 && File.ReadAllText(archives[0]).Contains(new string('x', 2201)) && conflict._draft!.Revision == handler.Draft.Revision);
            check("Carousel workflow never calls input, upload, or publication routes", handler.Requests.All(p => p.Contains("/api/farm/drafts")));
            check("Carousel tests never show a window or create a native handle", new[] { window, reopened, conflict }.All(w => !w.IsVisible && new WindowInteropHelper(w).Handle == IntPtr.Zero));
            File.WriteAllText(Path.Combine(folder, "farm-carousel-edits.json"), "{damaged");
            bool damaged = false;
            try { new CarouselRecovery(folder).Load(); } catch (InvalidOperationException) { damaged = true; }
            var preserved = Directory.GetFiles(folder, "farm-carousel-damaged-*.json");
            check("Unreadable carousel edits preserve original bytes before allowing new work", damaged && preserved.Length == 1 && File.ReadAllText(preserved[0]) == "{damaged");
        }
        finally
        {
            window._dirty = false;
            if (reopened is not null) { reopened._dirty = false; reopened.Close(); }
            if (conflict is not null) { conflict._dirty = false; conflict.Close(); }
            window.Close();
            Directory.Delete(folder, true);
        }
    }
}
