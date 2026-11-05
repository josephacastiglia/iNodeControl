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

internal sealed partial class FarmScheduleQueueWindow
{
    // A fake farm server with the Scheduler lane's queue routes and their replies (imouse_farm_server.py,
    // farm_schedule_queue.py): GET the view, POST approve or reject. Nothing else answers.
    private sealed class FakeQueue : HttpMessageHandler
    {
        internal readonly List<(string Method, string Path, string Body)> Requests = [];
        internal readonly List<Dictionary<string, object?>> Pending =
        [
            new() { ["id"] = "reel18-aaaaaa", ["platform"] = "instagram", ["format"] = "ig_reel", ["account"] = "acct-a18", ["caption"] = "Fresh reel acceptance",
                    ["source"] = new Dictionary<string, object?> { ["slot"] = 18, ["manifestSha256"] = new string('a', 64) }, ["state"] = "pending", ["submittedAt"] = 1_762_300_000.0 },
            new() { ["id"] = 7, ["platform"] = "tiktok", ["format"] = "tt_photo", ["account"] = null, ["caption"] = "Prepared copy",
                    ["source"] = new Dictionary<string, object?> { ["stagedFiles"] = new[] { @"C:\staged\s1.jpg", @"C:\staged\s2.jpg" } }, ["state"] = "pending", ["submittedAt"] = 1_762_300_060.0 },
        ];
        internal readonly List<string> Approved = [], Rejected = [];
        internal bool LoseNextAnswer, Unsafe;

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            string path = request.RequestUri!.AbsolutePath;
            string body = request.Content is null ? "" : await request.Content.ReadAsStringAsync(token);
            Requests.Add((request.Method.Method, path, body));
            if (request.Method == HttpMethod.Get && path == QueueRoute) return Reply(200, View());
            if (request.Method != HttpMethod.Post || path is not (QueueRoute + "/approve" or QueueRoute + "/reject"))
                return Reply(404, new { error = "Not a review queue route." });
            var data = JsonSerializer.Deserialize<JsonElement>(body);
            string id = PackageId(data.GetProperty("id"));
            var package = Pending.FirstOrDefault(p => PackageId(JsonSerializer.SerializeToElement(p["id"])) == id);
            if (package is null) return Reply(400, new { error = $"No package {id} in the queue." });
            if (path.EndsWith("/approve"))
            {
                if (data.EnumerateObject().Any(p => p.Name is not ("id" or "account"))) return Reply(400, new { error = "Approve takes only id and account." });
                if (data.TryGetProperty("account", out var account)) package["account"] = account.GetString();
                if (package["account"] is null) return Reply(400, new { error = $"Package {id} has no account; approve it with an account label." });
                package["state"] = "approved"; Approved.Add(id);
            }
            else
            {
                if (data.EnumerateObject().Any(p => p.Name is not ("id" or "reason"))) return Reply(400, new { error = "Reject takes only id and reason." });
                package["state"] = "rejected"; package["reason"] = data.GetProperty("reason").GetString(); Rejected.Add(id);
            }
            Pending.Remove(package);
            if (LoseNextAnswer) { LoseNextAnswer = false; throw new HttpRequestException("Lost queue answer"); }
            return Reply(200, new { package, startsRuns = false, phoneInput = false });
        }

        private object View()
        {
            var safety = new { startsRuns = Unsafe, phoneInput = false, publishing = false };
            return new
            {
                scheduleQueue = new
                {
                    schedule = new
                    {
                        slots = new[] { new { id = "reel17-bbbbbb", platform = "instagram", format = "ig_reel", account = "acct-a17", at = 1_762_340_400.0, day = "2026-11-05" } },
                        pending = Pending.Select(p => p["id"]).ToArray(), approved = Approved.ToArray(), rejected = Rejected.ToArray(),
                        running = Array.Empty<object>(), done = Array.Empty<object>(), stopped = Array.Empty<object>(), runs = Array.Empty<object>(),
                    },
                    plan = new
                    {
                        dryRun = true, lapsing = new object[] { 5 },
                        proposed = Approved.Select(id => new { id, slot = 1_762_344_000.0 }).ToArray(),
                        unplaced = new[] { new { id = "x-cccccc", account = "acct-x1", platform = "x", reason = "account daily cap through 2026-11-11" } },
                    },
                    pending = Pending,
                },
                safety.startsRuns, safety.phoneInput, safety.publishing,
            };
        }

        private static HttpResponseMessage Reply(int status, object payload)
        {
            var json = JsonSerializer.SerializeToNode(payload)!.AsObject();
            json["protocolVersion"] = 2; json["executionMode"] = "simulate";
            return new((HttpStatusCode)status) { Content = new StringContent(json.ToJsonString(), Encoding.UTF8, "application/json") };
        }
    }

    private void SelectPackage(string id) => _pending.SelectedItem = _pending.Items.Cast<Item>().First(i => i.Id == id);

    internal static async Task CheckHeadlessAsync(Action<string, bool> check)
    {
        var fake = new FakeQueue(); using var http = new HttpClient(fake);
        var window = new FarmScheduleQueueWindow(new FarmApiClient(http, "http://schedule-queue-test.invalid"));
        try
        {
            await window.RunAsync(() => window.RefreshAsync());
            var rows = window._pending.Items.Cast<Item>().Select(i => i.ToString()).ToArray();
            check("Review queue lists each waiting package with package, platform, phone and account label",
                rows.Length == 2 && rows[0] == "pkg reel18-aaaaaa · instagram/ig_reel · phone 18 · acct-a18" && rows[1] == "pkg 7 · tiktok/tt_photo · no phone yet · account set at approve");
            check("Review queue opens with a read of the queue only", fake.Requests.Count == 1 && fake.Requests[0] == ("GET", QueueRoute, ""));
            check("Planned slots and the dry-run plan are read-only text",
                window._slots.IsReadOnly && window._plan.IsReadOnly && window._slots.Text.Contains("acct-a17") && window._slots.Text.Contains("pkg reel17-bbbbbb")
                && window._plan.Text.StartsWith("Dry run") && window._plan.Text.Contains("No slot for pkg x-cccccc") && window._plan.Text.Contains("Lapsing") && window._plan.Text.Contains("5"));
            check("Selected package shows its caption and file names, not their folders",
                window._detail.Text.Contains("Fresh reel acceptance") && window._detail.Text.Contains("Manifest aaaaaaaaaaaa") && !window._detail.Text.Contains(@"C:\staged"));

            window.SelectPackage("7");
            await window.RunAsync(window.ApproveAsync);
            check("A package without an account is not approved until a label is typed", fake.Requests.Count == 1 && window._status.Text.Contains("no account yet"));
            window._account.Text = "some.handle";
            await window.RunAsync(window.ApproveAsync);
            window._account.Text = "0f12ab";
            await window.RunAsync(window.ApproveAsync);
            check("A handle or device ID is refused as an account before anything is sent", fake.Requests.Count == 1 && window._status.Text.Contains("opaque label"));
            window._account.Text = "acct-2";
            await window.RunAsync(window.ApproveAsync);
            var approve = fake.Requests[^2];
            check("Approve sends only the package ID and the typed label, then reads the queue again",
                approve.Method == "POST" && approve.Path == QueueRoute + "/approve" && approve.Body == "{\"id\":\"7\",\"account\":\"acct-2\"}" && fake.Requests[^1].Method == "GET"
                && fake.Approved.SequenceEqual(["7"]) && window._status.Text.StartsWith("Package 7 is approved."));
            check("The approved package leaves the review list and appears in the dry-run plan",
                window._pending.Items.Cast<Item>().Select(i => i.Id).SequenceEqual(["reel18-aaaaaa"]) && window._plan.Text.Contains("Would plan pkg 7 at"));

            int before = fake.Requests.Count;
            await window.RunAsync(window.RejectAsync);
            check("Reject needs a reason before anything is sent", fake.Requests.Count == before && window._status.Text.Contains("Say why"));
            window._reason.Text = "caption off";
            fake.LoseNextAnswer = true;
            await window.RunAsync(window.RejectAsync);
            check("A lost reject answer reads the queue again instead of resending",
                fake.Requests.Count(r => r.Path == QueueRoute + "/reject") == 1 && fake.Requests[^1].Method == "GET" && fake.Rejected.SequenceEqual(["reel18-aaaaaa"])
                && window._status.Text.Contains("answer was lost") && window._pending.Items.Count == 0 && !window._approve.IsEnabled && !window._reject.IsEnabled);
            check("Reject sends only the package ID and the reason",
                fake.Requests.Single(r => r.Path == QueueRoute + "/reject").Body == "{\"id\":\"reel18-aaaaaa\",\"reason\":\"caption off\"}");

            fake.Pending.Add(new() { ["id"] = 9, ["platform"] = "x", ["format"] = "x_image", ["account"] = "acct-x1", ["caption"] = "", ["source"] = new Dictionary<string, object?>(), ["state"] = "pending", ["submittedAt"] = 1_762_300_120.0 });
            fake.Unsafe = true;
            await window.RunAsync(() => window.RefreshAsync());
            check("A view that does not confirm review-only keeps approve and reject off",
                window._pending.Items.Count == 1 && !window._approve.IsEnabled && !window._reject.IsEnabled && window._status.Text.Contains("stay off"));
            fake.Unsafe = false;
            await window.RunAsync(() => window.RefreshAsync());
            check("Approve and reject come back once the view is review-only", window._approve.IsEnabled && window._reject.IsEnabled);

            check("Review queue uses only the queue view, approve and reject routes",
                fake.Requests.All(r => (r.Method, r.Path) is ("GET", QueueRoute) or ("POST", QueueRoute + "/approve") or ("POST", QueueRoute + "/reject")));
            check("Review queue never asks to commit a plan, run a slot or send phone input",
                fake.Requests.All(r => !r.Body.Contains("commit") && !r.Body.Contains("run") && !r.Body.Contains("slot") && !r.Path.Contains("input")));

            var content = (FrameworkElement)window.Content; content.Measure(new Size(760, 860)); content.Arrange(new Rect(0, 0, 760, 860)); content.UpdateLayout();
            var image = new RenderTargetBitmap(760, 860, 96, 96, PixelFormats.Pbgra32);
            var background = new DrawingVisual(); using (var drawing = background.RenderOpen()) drawing.DrawRectangle(window.Background, null, new Rect(0, 0, 760, 860));
            image.Render(background); image.Render(content); var png = new PngBitmapEncoder(); png.Frames.Add(BitmapFrame.Create(image));
            using (var file = File.Create(Path.Combine(InstallLayout.RunFiles, "qa", "farm-schedule-queue-headless.png"))) png.Save(file);
            check("Review queue renders without creating a desktop window", content.IsArrangeValid && new WindowInteropHelper(window).Handle == IntPtr.Zero);
        }
        finally { window.Close(); }
    }
}
