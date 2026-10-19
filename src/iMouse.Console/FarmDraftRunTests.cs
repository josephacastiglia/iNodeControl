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
        internal bool Inspection, WrongCreationProof, Reel;
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
            workflow = new { source = "candidate_phone_workflow", mode = Inspection ? "inspect_saved_draft" : Reel ? "create_reel_draft" : "create_new_draft", inspectionOnly = Inspection, createdDraftVerified = CreationConfirmed, mediaDelivery = new { stopped = true }, actions = new[] { new { label = Inspection ? "inspect-open-draft" : "prepared-save-once", state = Verified ? "answered" : "outcome_unknown" } },
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
            if (route == "/health") return Response(new { protocolVersion = 2, executionMode = Enabled ? "live" : "simulate", draftWorkflow = new { version = 1, storeId = StoreId, enabled = Enabled }, draftCreation = new { version = 1, storeId = StoreId, enabled = Enabled, device = "C24C", account = "xs.halle.xo", publishing = false, messaging = false }, draftRecovery = new { version = 1, storeId = StoreId, enabled = Enabled, device = "C24C", account = "xs.halle.xo", publishing = false, messaging = false, inspectionOnly = true }, reelCreation = new { version = 1, storeId = StoreId, enabled = Enabled, device = "C24C", account = "xs.halle.xo", publishing = false, messaging = false, format = "ig_reel" } });
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
            if (route is "/api/farm/draft-runs" or "/api/farm/draft-creations" or "/api/farm/draft-recoveries" or "/api/farm/reel-creations") return Response(new { protocolVersion = 2, runs = Id is null ? Array.Empty<object>() : new[] { new { id = Id, revision = 3 } } });
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
