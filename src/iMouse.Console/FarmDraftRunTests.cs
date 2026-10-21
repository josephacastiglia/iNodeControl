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
        internal string? Id, BookmarkPath, ImportedFrom, EligibleImportedFrom;
        internal string? CreationId, CreationStoreId, CreationRecordSha256, EligibleCreationId;
        internal bool Inspection, WrongCreationProof, Reel, TikTok, X, XFixedAccount, WrongXCheckAccount, YouTube, YouTubeFixedAccount, YouTubeNoPhone;
        internal int Starts, Cancels, EligibilityCalls;
        internal bool Missing, Terminal, Verified, Enabled = true, WrongResult, BookmarkBeforePost;
        internal bool CreationConfirmed = true, RetryBeforeImport, ContinueImported;
        internal readonly List<string> Routes = [];
        private object Result() => new
        {
            id = WrongResult ? Guid.NewGuid().ToString() : Id, storeId = StoreId,
            request = new { draft_id = DraftId, revision = 3, continue_imported_from = ImportedFrom, creation_id = CreationId, creation_store_id = CreationStoreId, creation_record_sha256 = WrongCreationProof ? new string('b', 64) : CreationRecordSha256 }, state = Verified ? "verified" : Terminal ? "review_required" : "running",
            terminal = Terminal, savedDraftVerified = Verified, retryBeforeImportAllowed = RetryBeforeImport, continueImportedAllowed = ContinueImported, cleanup = Terminal ? "confirmed" : "unconfirmed",
            reason = Verified ? "The matching draft was saved, reopened and checked." : "Save reply lost; no replay.", draftChangedSinceRun = true, publishing = false, messaging = false, automaticResume = false,
            inspectionOnly = Inspection, originalOutcomeChanged = false, appRestartVerified = false,
            workflow = new { source = "candidate_phone_workflow", mode = Inspection ? "inspect_saved_draft" : Reel ? "create_reel_draft" : TikTok ? "create_tiktok_draft" : X ? "create_x_draft" : YouTube ? "create_youtube_draft" : "create_new_draft", inspectionOnly = Inspection, account = X || YouTube ? "fixture_handle" : null, verification = new { account = WrongXCheckAccount ? "other_handle" : "fixture_handle" }, createdDraftVerified = CreationConfirmed, mediaDelivery = new { stopped = true }, actions = new[] { new { label = Inspection ? "inspect-open-draft" : "prepared-save-once", state = Verified ? "answered" : "outcome_unknown" } },
                observations = new[] { new { observationId = "frame1", role = "library", state = "observed" } } }
        };
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            string route = request.RequestUri!.AbsolutePath; Routes.Add(route);
            if (request.Method == HttpMethod.Post)
            {
                if (route.EndsWith("/cancel")) { Cancels++; return Response(new { protocolVersion = 2, job = new { } }); }
                var intent = JsonSerializer.Deserialize<JsonElement>(await request.Content!.ReadAsStringAsync(token));
                Starts++; Id = intent.GetProperty("id").GetString();
                ImportedFrom = intent.TryGetProperty("continue_imported_from", out var imported) ? imported.GetString() : null;
                CreationId = intent.TryGetProperty("creation_id", out var source) ? source.GetString() : null;
                CreationStoreId = intent.TryGetProperty("creation_store_id", out var sourceStore) ? sourceStore.GetString() : null;
                CreationRecordSha256 = intent.TryGetProperty("creation_record_sha256", out var sourceHash) ? sourceHash.GetString() : null;
                BookmarkBeforePost = BookmarkPath is not null && System.IO.File.ReadAllText(BookmarkPath).Contains(Id!);
                throw new HttpRequestException("Response lost after admission");
            }
            if (route == "/health") return Response(new { protocolVersion = 2, executionMode = Enabled ? "live" : "simulate", draftWorkflow = new { version = 1, storeId = StoreId, enabled = Enabled }, draftCreation = new { version = 1, storeId = StoreId, enabled = Enabled, device = "C24C", account = "xs.halle.xo", publishing = false, messaging = false }, draftRecovery = new { version = 1, storeId = StoreId, enabled = Enabled, device = "C24C", account = "xs.halle.xo", publishing = false, messaging = false, inspectionOnly = true }, reelCreation = new { version = 1, storeId = StoreId, enabled = Enabled, device = "C24C", account = "xs.halle.xo", publishing = false, messaging = false, format = "ig_reel" }, tiktokCreation = new { version = 1, storeId = StoreId, enabled = Enabled, device = "C24C", account = "xs.halle.xo", publishing = false, messaging = false, format = "tt_video" }, xCreation = new { version = 1, storeId = StoreId, enabled = Enabled, device = "C24C", account = XFixedAccount ? "xs.halle.xo" : null, accountPolicy = XFixedAccount ? "fixed" : "first_signed_in", publishing = false, messaging = false, format = "x_video" }, youtubeCreation = new { version = 1, storeId = StoreId, enabled = Enabled, device = YouTubeNoPhone ? null : "F215", phone = YouTubeNoPhone ? null : new { board = "F215", receiver = "iMouse2-16", slot = 16 }, account = YouTubeFixedAccount ? "xs.halle.xo" : null, accountPolicy = YouTubeFixedAccount ? "fixed" : "first_signed_in", publishing = false, messaging = false, format = "yt_short" } });
            if (route.EndsWith("/eligibility"))
            {
                EligibilityCalls++;
                var eligible = new Dictionary<string, object> { ["storeId"] = StoreId, ["eligible"] = Enabled, ["reason"] = "Prepared candidate only.", ["contentReason"] = "Saved content matches." };
                if (EligibleImportedFrom is not null) eligible["continueImportedFrom"] = EligibleImportedFrom;
                if (route.StartsWith("/api/farm/draft-recoveries"))
                {
                    eligible["draftId"] = DraftId; eligible["revision"] = 3;
                    eligible["sourceProof"] = new { creationId = EligibleCreationId, creationStoreId = StoreId, creationRecordSha256 = new string('a', 64) };
                }
                return Response(new { protocolVersion = 2, eligibility = eligible });
            }
            if (route is "/api/farm/draft-runs" or "/api/farm/draft-creations" or "/api/farm/draft-recoveries" or "/api/farm/reel-creations" or "/api/farm/tiktok-creations" or "/api/farm/x-creations" or "/api/farm/youtube-creations") return Response(new { protocolVersion = 2, runs = Id is null ? Array.Empty<object>() : new[] { new { id = Id, revision = 3 } } });
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

            handler.Id = null; handler.Terminal = handler.Verified = false; handler.Enabled = true;
            var creation = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "Fresh carousel", createNew: true); windows.Add(creation);
            handler.BookmarkPath = creation._bookmarkPath;
            await creation.RunAsync(creation.InitializeAsync);
            check("New draft creation uses its own capability, route and pending bookmark", creation._start.IsEnabled && creation._bookmarkPath != restarted._bookmarkPath && creation._route == "/api/farm/draft-creations");
            int starts = handler.Starts;
            await creation.RunAsync(creation.StartAsync); creation._poll.Stop();
            check("New draft creation journals admission before POST and preserves a lost reply", handler.Starts == starts + 1 && handler.BookmarkBeforePost && creation._pending?.Id == handler.Id && !creation._start.IsEnabled);
            await creation.StopAsync();
            check("New draft creation Stop uses the original creation route", handler.Routes.Last() == "/api/farm/draft-creations/" + handler.Id + "/cancel");
            handler.Terminal = handler.Verified = true; handler.CreationConfirmed = false;
            await creation.RunAsync(creation.RecoverAsync);
            check("A verified existing draft result cannot masquerade as new draft creation", creation._pending is not null && !creation._start.IsEnabled);
            handler.CreationConfirmed = true; await creation.RunAsync(creation.RecoverAsync);
            check("New draft completion needs confirmed creation and stopped media delivery", creation._pending is null && creation._status.Text.Contains("NEW PHONE DRAFT CREATED AND VERIFIED"));
            check("Stopped creation with a started Save offers a separate inspection without replay", creation._inspect.IsEnabled && creation._shownId == handler.Id);
            string originalCreation = handler.Id!; handler.EligibleCreationId = originalCreation;
            var inspection = await creation.InspectionWindowAsync(); windows.Add(inspection);
            handler.Inspection = true; handler.Terminal = handler.Verified = false;
            await inspection.RunAsync(inspection.InitializeAsync);
            check("Saved draft inspection has its own route and bookmark and opens without input", inspection._inspection && inspection._route == "/api/farm/draft-recoveries" && inspection._bookmarkPath != creation._bookmarkPath && inspection._start.IsEnabled && handler.Starts == starts + 1);
            handler.BookmarkPath = inspection._bookmarkPath; int inspectionStarts = handler.Starts;
            await inspection.RunAsync(inspection.StartAsync); inspection._poll.Stop();
            check("Inspection retains the source creation hash before its first POST", handler.Starts == inspectionStarts + 1 && handler.BookmarkBeforePost && handler.CreationId == originalCreation && inspection._pending?.CreationRecordSha256 == new string('a', 64));
            handler.WrongCreationProof = true; await inspection.RunAsync(inspection.RecoverAsync);
            check("Inspection rejects a result from changed creation evidence and keeps its pending request", inspection._pending is not null && inspection._status.Text.Contains("immutable source") && !inspection._start.IsEnabled);
            handler.WrongCreationProof = false;
            var inspectionReopened = new FarmDraftRunWindow(api, folder, handler.DraftId, 4, "Edited local revision", inspectCreationId: originalCreation); windows.Add(inspectionReopened);
            int sourceEligibilityCalls = handler.EligibilityCalls;
            await inspectionReopened.RunAsync(inspectionReopened.InitializeAsync); inspectionReopened._poll.Stop();
            check("Reopening inspection after a lost reply only retrieves its original revision and source", inspectionReopened._pending?.CreationId == originalCreation && inspectionReopened._pending?.Revision == 3 && handler.Starts == inspectionStarts + 1 && handler.EligibilityCalls == sourceEligibilityCalls);
            await inspectionReopened.StopAsync();
            check("Inspection cancellation uses its own original request and store", handler.Routes.Last() == "/api/farm/draft-recoveries/" + handler.Id + "/cancel");
            handler.Terminal = handler.Verified = true; await inspectionReopened.RunAsync(inspectionReopened.RecoverAsync);
            check("Completed inspection is presented as an observation without changing original creation", inspectionReopened._pending is null && inspectionReopened._status.Text.Contains("MATCHING SAVED DRAFT OBSERVED") && inspectionReopened._status.Text.Contains("does not change the original") && creation._shownId == originalCreation && handler.Starts == inspectionStarts + 1);
            var inspectionContent = (FrameworkElement)inspectionReopened.Content;
            inspectionContent.Measure(new Size(840, 820)); inspectionContent.Arrange(new Rect(0, 0, 840, 820)); inspectionContent.UpdateLayout();
            var inspectionImage = new RenderTargetBitmap(840, 820, 96, 96, PixelFormats.Pbgra32);
            var inspectionBackground = new DrawingVisual(); using (var drawing = inspectionBackground.RenderOpen()) drawing.DrawRectangle(inspectionReopened.Background, null, new Rect(0, 0, 840, 820));
            inspectionImage.Render(inspectionBackground);
            inspectionImage.Render(inspectionContent); var inspectionPng = new PngBitmapEncoder(); inspectionPng.Frames.Add(BitmapFrame.Create(inspectionImage));
            using (var file = System.IO.File.Create(System.IO.Path.Combine(AppContext.BaseDirectory, "qa", "farm-draft-recovery-headless.png"))) inspectionPng.Save(file);
            check("Saved draft inspection renders without desktop control or a native window", inspectionContent.IsArrangeValid && new WindowInteropHelper(inspectionReopened).Handle == IntPtr.Zero);
            handler.Inspection = false; handler.EligibleCreationId = null;
            handler.Id = null; handler.Terminal = handler.Verified = false;
            var retryWindow = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "Fresh carousel", createNew: true); windows.Add(retryWindow);
            handler.BookmarkPath = retryWindow._bookmarkPath; await retryWindow.RunAsync(retryWindow.InitializeAsync);
            await retryWindow.RunAsync(retryWindow.StartAsync); retryWindow._poll.Stop();
            string previousId = handler.Id!;
            handler.Terminal = handler.RetryBeforeImport = true; await retryWindow.RunAsync(retryWindow.RecoverAsync);
            check("Only a confirmed preimport hold offers an explicit new creation attempt", retryWindow._retryBeforeImport && retryWindow._start.IsEnabled && retryWindow._pending is not null);
            await retryWindow.RunAsync(retryWindow.StartAsync); retryWindow._poll.Stop();
            check("Explicit preimport retry rechecks eligibility and uses a new durable request", handler.Id != previousId && retryWindow._pending?.Id == handler.Id && !retryWindow._retryBeforeImport);
            previousId = handler.Id!; handler.RetryBeforeImport = false; handler.ContinueImported = true; handler.EligibleImportedFrom = previousId;
            await retryWindow.RunAsync(retryWindow.RecoverAsync);
            check("Confirmed imported-media hold offers continuation without reimport", retryWindow._continueImported && retryWindow._start.IsEnabled && retryWindow._start.Content.ToString()!.Contains("imported images"));
            await retryWindow.RunAsync(retryWindow.StartAsync); retryWindow._poll.Stop();
            check("Continuation origin is durable before admission and included in the request", handler.Id != previousId && handler.ImportedFrom == previousId && retryWindow._pending?.ImportedFrom == previousId && handler.BookmarkBeforePost);
            int continuationStarts = handler.Starts; handler.ContinueImported = false;
            var recoveredCreation = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "Fresh carousel", createNew: true); windows.Add(recoveredCreation);
            await recoveredCreation.RunAsync(recoveredCreation.InitializeAsync); recoveredCreation._poll.Stop();
            check("A lost continuation reply recovers the same request and import provenance", recoveredCreation._pending?.Id == handler.Id && recoveredCreation._pending?.ImportedFrom == previousId && handler.Starts == continuationStarts && !recoveredCreation._start.IsEnabled);

            handler.Id = null; handler.Terminal = handler.Verified = handler.RetryBeforeImport = false; handler.EligibleImportedFrom = null; handler.Reel = true;
            int routesBefore = handler.Routes.Count;
            var reel = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "Reel acceptance", createNew: true, reel: true); windows.Add(reel);
            handler.BookmarkPath = reel._bookmarkPath; await reel.RunAsync(reel.InitializeAsync);
            check("Reel creation opens with its own capability, route and bookmark and sends nothing", reel._start.IsEnabled && reel._route == "/api/farm/reel-creations"
                && reel._bookmarkPath.EndsWith("farm-pending-reel-creation.json") && reel._bookmarkPath != creation._bookmarkPath && handler.Starts == continuationStarts && reel._status.Text.Contains("acceptance"));
            await reel.RunAsync(reel.StartAsync); reel._poll.Stop();
            check("Reel creation journals admission before POST and keeps a lost reply", handler.Starts == continuationStarts + 1 && handler.BookmarkBeforePost && reel._pending?.Id == handler.Id && !reel._start.IsEnabled);
            await reel.StopAsync();
            check("Reel Stop uses the original Reel request route", handler.Routes.Last() == "/api/farm/reel-creations/" + handler.Id + "/cancel");
            handler.Terminal = handler.Verified = true; handler.CreationConfirmed = false; await reel.RunAsync(reel.RecoverAsync);
            check("A Reel result without confirmed creation cannot be shown as a new draft", reel._pending is not null && !reel._start.IsEnabled);
            handler.CreationConfirmed = true; await reel.RunAsync(reel.RecoverAsync);
            check("A verified Reel needs confirmed creation and stopped media delivery", reel._pending is null && reel._status.Text.Contains("NEW REEL DRAFT CREATED AND VERIFIED") && !reel._inspect.IsEnabled);
            check("The Reel window calls only health and its own scoped route", handler.Routes.Skip(routesBefore).All(r => r == "/health" || r.StartsWith("/api/farm/reel-creations")));
            var reelContent = (FrameworkElement)reel.Content; reelContent.Measure(new Size(840, 820)); reelContent.Arrange(new Rect(0, 0, 840, 820)); reelContent.UpdateLayout();
            var reelImage = new RenderTargetBitmap(840, 820, 96, 96, PixelFormats.Pbgra32);
            var reelBackground = new DrawingVisual(); using (var drawing = reelBackground.RenderOpen()) drawing.DrawRectangle(reel.Background, null, new Rect(0, 0, 840, 820));
            reelImage.Render(reelBackground); reelImage.Render(reelContent); var reelPng = new PngBitmapEncoder(); reelPng.Frames.Add(BitmapFrame.Create(reelImage));
            using (var file = System.IO.File.Create(System.IO.Path.Combine(AppContext.BaseDirectory, "qa", "farm-reel-draft-headless.png"))) reelPng.Save(file);
            check("Reel creation renders without desktop control or a native window", reelContent.IsArrangeValid && new WindowInteropHelper(reel).Handle == IntPtr.Zero);
            handler.Reel = false;

            handler.Id = null; handler.Terminal = handler.Verified = false; handler.TikTok = true;
            int tiktokStarts = handler.Starts, tiktokRoutes = handler.Routes.Count;
            var tiktok = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "TikTok acceptance", createNew: true, tiktok: true); windows.Add(tiktok);
            handler.BookmarkPath = tiktok._bookmarkPath; await tiktok.RunAsync(tiktok.InitializeAsync);
            check("TikTok creation opens with its own capability, route and bookmark and sends nothing", tiktok._start.IsEnabled && tiktok._route == "/api/farm/tiktok-creations"
                && tiktok._bookmarkPath.EndsWith("farm-pending-tiktok-creation.json") && tiktok._bookmarkPath != reel._bookmarkPath && handler.Starts == tiktokStarts
                && tiktok._start.Content as string == "Create and verify TikTok draft on C24C");
            await tiktok.RunAsync(tiktok.StartAsync); tiktok._poll.Stop();
            check("TikTok creation journals admission before POST and keeps a lost reply", handler.Starts == tiktokStarts + 1 && handler.BookmarkBeforePost && tiktok._pending?.Id == handler.Id && !tiktok._start.IsEnabled);
            await tiktok.StopAsync();
            check("TikTok Stop uses the original TikTok request route", handler.Routes.Last() == "/api/farm/tiktok-creations/" + handler.Id + "/cancel");
            handler.Terminal = handler.Verified = true; handler.CreationConfirmed = false; await tiktok.RunAsync(tiktok.RecoverAsync);
            check("A TikTok result without confirmed creation cannot be shown as a new draft", tiktok._pending is not null && !tiktok._start.IsEnabled);
            handler.CreationConfirmed = true; await tiktok.RunAsync(tiktok.RecoverAsync);
            check("A verified TikTok draft needs confirmed creation", tiktok._pending is null && tiktok._status.Text.Contains("NEW TIKTOK DRAFT CREATED AND VERIFIED") && !tiktok._inspect.IsEnabled);
            check("The TikTok window calls only health and its own scoped route", handler.Routes.Skip(tiktokRoutes).All(r => r == "/health" || r.StartsWith("/api/farm/tiktok-creations")));
            bool refused;
            try { _ = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "Both", createNew: true, reel: true, tiktok: true); refused = false; }
            catch (ArgumentException) { refused = true; }
            check("One window never drives both the Reel and TikTok routes", refused);
            handler.TikTok = false;

            handler.Id = null; handler.Terminal = handler.Verified = false; handler.X = true; handler.XFixedAccount = true;
            int xStarts = handler.Starts, xRoutes = handler.Routes.Count;
            var pinnedX = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "X acceptance", createNew: true, x: true); windows.Add(pinnedX);
            await pinnedX.RunAsync(pinnedX.InitializeAsync);
            check("An X backend with a fixed account is refused; X binds the account signed in first", !pinnedX._start.IsEnabled && pinnedX._status.Text.Contains("designated") && handler.Starts == xStarts);
            handler.XFixedAccount = false;
            var xWindow = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "X acceptance", createNew: true, x: true); windows.Add(xWindow);
            handler.BookmarkPath = xWindow._bookmarkPath; await xWindow.RunAsync(xWindow.InitializeAsync);
            check("X creation opens with its own capability, route and bookmark and sends nothing", xWindow._start.IsEnabled && xWindow._route == "/api/farm/x-creations" && xWindow._capability == "xCreation"
                && xWindow._bookmarkPath.EndsWith("farm-pending-x-creation.json") && xWindow._bookmarkPath != tiktok._bookmarkPath && handler.Starts == xStarts
                && xWindow._start.Content as string == "Create and verify X draft on C24C" && xWindow._status.Text.Contains("not a saved X draft"));
            await xWindow.RunAsync(xWindow.StartAsync); xWindow._poll.Stop();
            check("X creation journals admission before POST and keeps a lost reply", handler.Starts == xStarts + 1 && handler.BookmarkBeforePost && xWindow._pending?.Id == handler.Id && !xWindow._start.IsEnabled);
            await xWindow.StopAsync();
            check("X Stop uses the original X request route", handler.Routes.Last() == "/api/farm/x-creations/" + handler.Id + "/cancel");
            handler.Terminal = handler.Verified = true; handler.WrongXCheckAccount = true; await xWindow.RunAsync(xWindow.RecoverAsync);
            check("A verified X result checked on another account is refused and kept", xWindow._pending is not null && !xWindow._status.Text.Contains("NEW X DRAFT CREATED AND VERIFIED"));
            handler.WrongXCheckAccount = false; await xWindow.RunAsync(xWindow.RecoverAsync);
            check("A verified X draft names the bound account and its matching check", xWindow._pending is null && xWindow._status.Text.Contains("NEW X DRAFT CREATED AND VERIFIED")
                && xWindow._status.Text.Contains("X account bound by this run: @fixture_handle (the separate check saw the same handle).") && !xWindow._inspect.IsEnabled);
            check("The X window calls only health and its own scoped route", handler.Routes.Skip(xRoutes).All(r => r == "/health" || r.StartsWith("/api/farm/x-creations")));
            foreach (var (reelFlag, tiktokFlag) in new[] { (true, false), (false, true) })
            {
                try { _ = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "Both", createNew: true, reel: reelFlag, tiktok: tiktokFlag, x: true); refused = false; }
                catch (ArgumentException) { refused = true; }
                check("One window never drives X together with " + (reelFlag ? "Reel" : "TikTok"), refused);
            }
            handler.X = false;

            handler.Id = null; handler.Terminal = handler.Verified = false; handler.YouTube = true; handler.YouTubeFixedAccount = true;
            int ytStarts = handler.Starts, ytRoutes = handler.Routes.Count;
            var pinnedYouTube = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "YouTube acceptance", createNew: true, youtube: true); windows.Add(pinnedYouTube);
            await pinnedYouTube.RunAsync(pinnedYouTube.InitializeAsync);
            check("A YouTube backend with a fixed account is refused; YouTube binds the signed-in channel", !pinnedYouTube._start.IsEnabled && pinnedYouTube._status.Text.Contains("designated") && handler.Starts == ytStarts);
            handler.YouTubeFixedAccount = false; handler.YouTubeNoPhone = true;
            var phoneless = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "YouTube acceptance", createNew: true, youtube: true); windows.Add(phoneless);
            await phoneless.RunAsync(phoneless.InitializeAsync);
            check("A YouTube backend that names no phone is refused; there is no default phone", !phoneless._start.IsEnabled && phoneless._status.Text.Contains("designated") && handler.Starts == ytStarts);
            handler.YouTubeNoPhone = false;
            var ytWindow = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "YouTube acceptance", createNew: true, youtube: true); windows.Add(ytWindow);
            handler.BookmarkPath = ytWindow._bookmarkPath; await ytWindow.RunAsync(ytWindow.InitializeAsync);
            check("YouTube creation opens with its own capability, route and bookmark and sends nothing", ytWindow._start.IsEnabled && ytWindow._route == "/api/farm/youtube-creations" && ytWindow._capability == "youtubeCreation"
                && ytWindow._bookmarkPath.EndsWith("farm-pending-youtube-creation.json") && ytWindow._bookmarkPath != xWindow._bookmarkPath && handler.Starts == ytStarts
                && ytWindow._start.Content as string == "Create and verify YouTube draft" && ytWindow._status.Text.Contains("not a saved YouTube draft"));
            check("The YouTube window names the phone its backend is configured for", ytWindow._status.Text.StartsWith("Configured phone: iMouse2-16 (board F215, box slot 16)")
                && !ytWindow.Title.Contains("C24C"));
            await ytWindow.RunAsync(ytWindow.StartAsync); ytWindow._poll.Stop();
            check("YouTube creation journals admission before POST and keeps a lost reply", handler.Starts == ytStarts + 1 && handler.BookmarkBeforePost && ytWindow._pending?.Id == handler.Id && !ytWindow._start.IsEnabled);
            await ytWindow.StopAsync();
            check("YouTube Stop uses the original YouTube request route", handler.Routes.Last() == "/api/farm/youtube-creations/" + handler.Id + "/cancel");
            handler.Terminal = handler.Verified = true; handler.WrongXCheckAccount = true; await ytWindow.RunAsync(ytWindow.RecoverAsync);
            check("A verified YouTube result checked on another channel is refused and kept", ytWindow._pending is not null && !ytWindow._status.Text.Contains("NEW YOUTUBE DRAFT CREATED AND VERIFIED")
                && ytWindow._status.Text.Contains("checked on the channel bound by creation"));
            handler.WrongXCheckAccount = false; await ytWindow.RunAsync(ytWindow.RecoverAsync);
            check("A verified YouTube draft names the bound channel and its matching check", ytWindow._pending is null && ytWindow._status.Text.Contains("NEW YOUTUBE DRAFT CREATED AND VERIFIED")
                && ytWindow._status.Text.Contains("YouTube channel bound by this run: @fixture_handle (the separate check saw the same handle).") && !ytWindow._inspect.IsEnabled);
            check("The YouTube window calls only health and its own scoped route", handler.Routes.Skip(ytRoutes).All(r => r == "/health" || r.StartsWith("/api/farm/youtube-creations")));
            foreach (var (reelFlag, tiktokFlag, xFlag) in new[] { (true, false, false), (false, true, false), (false, false, true) })
            {
                try { _ = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "Both", createNew: true, reel: reelFlag, tiktok: tiktokFlag, x: xFlag, youtube: true); refused = false; }
                catch (ArgumentException) { refused = true; }
                check("One window never drives YouTube together with " + (reelFlag ? "Reel" : tiktokFlag ? "TikTok" : "X"), refused);
            }
            try { _ = new FarmDraftRunWindow(api, folder, handler.DraftId, 3, "Run", youtube: true); refused = false; }
            catch (ArgumentException) { refused = true; }
            check("A YouTube window only creates a new draft from a saved copy", refused);
            handler.YouTube = false;
            var report = JsonSerializer.Deserialize<JsonElement>("{\"features\":[{\"name\":\"Jobs\",\"availability\":\"Simulation tested\",\"detail\":\"Durable IDs.\"}],"
                + "\"formats\":[{\"name\":\"Instagram Reel\",\"level\":\"integrated_offline\",\"remaining\":\"Fresh C24C acceptance.\"},"
                + "{\"name\":\"Instagram story\",\"level\":\"unsupported_draft\",\"remaining\":\"No draft mechanism.\"}]}");
            var readiness = new FarmReadinessWindow(report); var readinessContent = (FrameworkElement)readiness.Content;
            readinessContent.Measure(new Size(760, 700)); readinessContent.Arrange(new Rect(0, 0, 760, 700)); readinessContent.UpdateLayout();
            var readinessText = string.Join(" | ", ((System.Windows.Controls.StackPanel)((System.Windows.Controls.ScrollViewer)readiness.Content).Content).Children.OfType<System.Windows.Controls.TextBlock>().Select(t => t.Text));
            check("Readiness lists draft formats with honest evidence levels", readinessText.Contains("Draft formats") && readinessText.Contains("Instagram Reel · Offline candidate · live acceptance pending")
                && readinessText.Contains("Instagram story · Unsupported · no verified draft mechanism") && FarmReadinessWindow.Level("integrated_live") == "Scoped live acceptance"
                && FarmReadinessWindow.Level("other") == "Unknown evidence level" && new WindowInteropHelper(readiness).Handle == IntPtr.Zero);
            readiness.Close();
        }
        finally
        {
            foreach (var window in windows) { window._poll.Stop(); window._terminal = true; window.Close(); }
            System.IO.Directory.Delete(folder, recursive: true);
        }
    }
}
