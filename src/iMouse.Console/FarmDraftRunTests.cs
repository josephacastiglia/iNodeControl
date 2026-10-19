using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace IMouse2;

internal sealed partial class FarmDraftRunWindow
{
    private sealed class TestHandler : HttpMessageHandler
    {
        internal string StoreId = Guid.NewGuid().ToString(), DraftId = Guid.NewGuid().ToString();
        internal string? Id, BookmarkPath;
        internal int Starts, Cancels, EligibilityCalls;
        internal bool Missing, Terminal, Verified, Enabled = true, WrongResult, BookmarkBeforePost;
        internal readonly List<string> Routes = [];
        private object Result() => new
        {
            id = WrongResult ? Guid.NewGuid().ToString() : Id, storeId = StoreId,
            request = new { draft_id = DraftId, revision = 3 }, state = Verified ? "verified" : Terminal ? "review_required" : "running",
            terminal = Terminal, savedDraftVerified = Verified, cleanup = Terminal ? "confirmed" : "unconfirmed",
            reason = Verified ? "The matching draft was saved, reopened and checked." : "Save reply lost; no replay.", draftChangedSinceRun = true, publishing = false, messaging = false, automaticResume = false,
            workflow = new { source = "candidate_phone_workflow", actions = new[] { new { label = "prepared-save-once", state = Verified ? "answered" : "outcome_unknown" } },
                observations = new[] { new { observationId = "frame1", role = "library", state = "observed" } } }
        };
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            string route = request.RequestUri!.AbsolutePath; Routes.Add(route);
            if (request.Method == HttpMethod.Post)
            {
                if (route.EndsWith("/cancel")) { Cancels++; return Response(new { protocolVersion = 2, job = new { } }); }
                Starts++; Id = JsonSerializer.Deserialize<JsonElement>(await request.Content!.ReadAsStringAsync(token)).GetProperty("id").GetString();
                BookmarkBeforePost = BookmarkPath is not null && System.IO.File.ReadAllText(BookmarkPath).Contains(Id!);
                throw new HttpRequestException("Response lost after admission");
            }
            if (route == "/health") return Response(new { protocolVersion = 2, executionMode = Enabled ? "live" : "simulate", draftWorkflow = new { version = 1, storeId = StoreId, enabled = Enabled } });
            if (route.EndsWith("/eligibility")) { EligibilityCalls++; return Response(new { protocolVersion = 2, eligibility = new { storeId = StoreId, eligible = Enabled, reason = "Prepared candidate only.", contentReason = "Saved content matches." } }); }
            if (route == "/api/farm/draft-runs") return Response(new { protocolVersion = 2, runs = Id is null ? Array.Empty<object>() : new[] { new { id = Id, revision = 3 } } });
            if (route.Contains("/frames/")) return Response(new { protocolVersion = 2, frame = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=" });
            return Missing ? Response(new { error = "Saved result missing" }, HttpStatusCode.NotFound) : Response(new { protocolVersion = 2, run = Result() });
        }
        private static HttpResponseMessage Response(object body, HttpStatusCode status = HttpStatusCode.OK) => new(status) { Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json") };
    }

    internal static async Task CheckHeadlessAsync(Action<string, bool> check)
    {
        string folder = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "farm-draft-window-" + Guid.NewGuid());
        System.IO.Directory.CreateDirectory(folder);
        var handler = new TestHandler(); using var http = new HttpClient(handler);
        var api = new FarmApiClient(http, "http://draft-run-test.invalid");
        var windows = new List<FarmDraftRunWindow>();
        FarmDraftRunWindow New(int revision = 3)
        {
            var next = new FarmDraftRunWindow(api, folder, handler.DraftId, revision, "Labelled three-slide test"); windows.Add(next); return next;
        }
        try
        {
            var window = New(); handler.BookmarkPath = window._bookmarkPath;
            await window.RunAsync(window.InitializeAsync);
            check("Phone draft window opens read-only and requires explicit Start", handler.Starts == 0 && window._start.IsEnabled && window._status.Text.Contains("acceptance"));
            await window.RunAsync(window.StartAsync); window._poll.Stop();
            check("Phone draft request is saved before POST and retained after a lost response", handler.BookmarkBeforePost && handler.Starts == 1 && window._pending?.Id == handler.Id && !window._start.IsEnabled);
            handler.Missing = true; await window.RunAsync(window.RecoverAsync);
            check("Missing phone draft status never enables a duplicate start", window._pending?.Id == handler.Id && !window._start.IsEnabled && handler.Starts == 1);
            handler.Missing = false; handler.WrongResult = true; await window.RunAsync(window.RecoverAsync);
            check("Mismatched phone draft response does not clear its saved request", window._pending?.Id == handler.Id && window._status.Text.Contains("does not match"));
            handler.WrongResult = false;
            window._busy = true; window.Buttons(); await window.StopAsync(); window._busy = false;
            check("Stop phone draft remains available during a pending HTTP request", handler.Cancels == 1 && window._stop.IsEnabled);
            int eligibleCalls = handler.EligibilityCalls;
            var restarted = New(4); await restarted.RunAsync(restarted.InitializeAsync); restarted._poll.Stop();
            check("Reopened window retrieves the pending original revision without a new eligibility check or POST", restarted._pending?.Revision == 3 && handler.Starts == 1 && handler.EligibilityCalls == eligibleCalls);
            handler.Terminal = true; await restarted.RunAsync(restarted.RecoverAsync);
            check("Interrupted phone draft retains its bookmark and displays cleanup and uncertainty", restarted._pending is not null && !restarted._start.IsEnabled && restarted._status.Text.Contains("outcome unknown") && restarted._status.Text.Contains("confirmed") && restarted._status.Text.Contains("older saved revision"));
            await restarted.RunAsync(restarted.ViewAsync);
            check("Phone draft evidence preview retrieves a retained frame without input", restarted._preview.Source is not null && handler.Starts == 1);
            string savedStore = handler.StoreId; handler.StoreId = Guid.NewGuid().ToString();
            var wrongBackend = New(); await wrongBackend.RunAsync(wrongBackend.InitializeAsync);
            check("Different backend data store cannot recover cancel or replace a pending phone draft", !wrongBackend._start.IsEnabled && !wrongBackend._stop.IsEnabled && !wrongBackend._recover.IsEnabled && wrongBackend._status.Text.Contains("different candidate"));
            handler.StoreId = savedStore;
            handler.Verified = true; await restarted.RunAsync(restarted.RecoverAsync);
            check("Confirmed saved phone result clears only the matching pending bookmark", restarted._pending is null && restarted._status.Text.Contains("PHONE DRAFT VERIFIED") && handler.Starts == 1);
            handler.Enabled = false; var offline = New(); await offline.RunAsync(offline.InitializeAsync);
            check("Simulation backend cannot enable live draft input", !offline._start.IsEnabled);
            check("Phone draft interface calls only health and its scoped run API", handler.Routes.All(r => r == "/health" || r.StartsWith("/api/farm/draft-runs")));
            System.IO.File.WriteAllText(window._bookmarkPath, "broken bookmark");
            var damaged = New(); await damaged.RunAsync(damaged.InitializeAsync);
            check("Damaged phone draft bookmark blocks a new request", !damaged._start.IsEnabled && damaged._bookmarkBroken);
            var content = (FrameworkElement)restarted.Content; content.Measure(new Size(840, 820)); content.Arrange(new Rect(0, 0, 840, 820)); content.UpdateLayout();
            var image = new RenderTargetBitmap(840, 820, 96, 96, PixelFormats.Pbgra32);
            var background = new DrawingVisual(); using (var drawing = background.RenderOpen()) drawing.DrawRectangle(restarted.Background, null, new Rect(0, 0, 840, 820));
            image.Render(background); image.Render(content); var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(image));
            using (var file = System.IO.File.Create(System.IO.Path.Combine(AppContext.BaseDirectory, "qa", "farm-draft-run-headless.png"))) png.Save(file);
            check("Phone draft review renders without creating a desktop window", content.IsArrangeValid && new WindowInteropHelper(restarted).Handle == IntPtr.Zero);
        }
        finally
        {
            foreach (var window in windows) { window._poll.Stop(); window._terminal = true; window.Close(); }
            System.IO.Directory.Delete(folder, recursive: true);
        }
    }
}
