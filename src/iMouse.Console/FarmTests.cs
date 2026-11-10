using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Windows.Interop;

namespace IMouse2;

internal static class FarmApiTests
{
    private sealed class Handler(HttpStatusCode code, string body) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            Task.FromResult(new HttpResponseMessage(code) { Content = new StringContent(body, Encoding.UTF8, "application/json") });
    }

    internal static async Task RunAsync(Action<string, bool> check)
    {
        using var good = new HttpClient(new Handler(HttpStatusCode.OK, "{\"protocolVersion\":2,\"status\":\"ok\"}"));
        var response = await new FarmApiClient(good, "http://localhost:9915").SendAsync("/health");
        check("Farm API accepts the matching protocol", response.GetProperty("status").GetString() == "ok");
        foreach (var scenario in new[] {
            (HttpStatusCode.BadRequest, "{\"error\":\"Invalid device\"}", "Farm API surfaces HTTP failure instead of logging completion"),
            (HttpStatusCode.OK, "{\"error\":\"No action performed\"}", "Farm API surfaces application failure even on HTTP 200"),
            (HttpStatusCode.OK, "{\"status\":\"ok\"}", "Farm API refuses an old backend without protocol metadata") })
        {
            using var client = new HttpClient(new Handler(scenario.Item1, scenario.Item2));
            bool refused = false;
            try { await new FarmApiClient(client, "http://localhost:9915").SendAsync("/test", new { }); }
            catch (InvalidOperationException) { refused = true; }
            check(scenario.Item3, refused);
        }
        foreach (var code in new[] { HttpStatusCode.InternalServerError, HttpStatusCode.BadGateway, HttpStatusCode.Conflict, HttpStatusCode.OK, HttpStatusCode.BadRequest })
        {
            using var client = new HttpClient(new Handler(code, "{\"error\":\"Submission response lost after acceptance\"}"));
            bool preserve = false;
            try { await new FarmApiClient(client, "http://job-test.invalid").SendAsync("/api/farm/jobs", new { request_id = Guid.NewGuid().ToString() }); }
            catch (FarmRequestRejectedException ex) when (ex.DefinitelyNotAccepted) { }
            catch (Exception) { preserve = true; }
            check("Job submission " + (int)code + " preserves uncertain outcomes and only clears definite rejection", preserve == (code != HttpStatusCode.BadRequest));
        }
    }
}

public partial class MainWindow
{
    internal static async Task CheckFarmHeadlessAsync(Action<string, bool> check)
    {
        string folder = Path.Combine(Path.GetTempPath(), "imouse-farm-ui-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        File.WriteAllText(Path.Combine(folder, "settings.json"), "{\"address\":\"http://localhost:9923\",\"trackPointer\":false}");
        var handler = new TestHandler();
        var window = new MainWindow(address => new ApiClient(address, handler), folder);
        try
        {
            window.AutoPreview.IsChecked = false;
            window._api = new ApiClient("http://localhost:9923", handler);
            window._connected = true;
            var c24c = new Device { Id = FarmTargetPolicy.DeviceId, Name = "Mock C24C", Online = true, IsChecked = true };
            var other = new Device { Id = "TEST:04", Name = "Other mock phone", Online = true, IsChecked = true };
            window._devices = [c24c, other];
            window.DeviceList.ItemsSource = window._devices;
            window.DeviceList.SelectedItem = c24c;
            window._farmExecutionMode = "simulate";
            window.DeviceList.SelectedItem = null;
            check("Farm simulation targets its C24C profile without selecting a real phone", window.FarmAutomationTarget() == "C24C");
            window._farmExecutionMode = "live";
            check("Farm live actions require a selected C24C", window.FarmAutomationTarget() is null);
            window.DeviceList.SelectedItem = c24c;
            window.BatchMode.IsChecked = true;
            window._controlReady = true;
            window._controlCancellation = new();
            await window.SendFarmInputAsync("/mouse/click", new() { ["x"] = 250, ["y"] = 500 });
            var click = handler.Commands.Last(c => c.GetProperty("fun").GetString() == "/mouse/click");
            check("Farm manual input never includes checked follower phones", click.GetProperty("data").GetProperty("id").GetString() == FarmTargetPolicy.DeviceId);
            int before = handler.Commands.Count;
            window._farmJobId = Guid.NewGuid().ToString();
            bool rejected = false;
            try { await window.SendFarmInputAsync("/mouse/click", new()); }
            catch (InvalidOperationException) { rejected = true; }
            check("Farm job blocks competing manual farm input", rejected && handler.Commands.Count == before);
            window._farmJobId = null;
            window.DeviceList.SelectedItem = other;
            rejected = false;
            try { await window.SendFarmInputAsync("/mouse/click", new()); }
            catch (InvalidOperationException) { rejected = true; }
            check("Farm manual input refuses a non-C24C selection", rejected && handler.Commands.Count == before);
            window.DeviceList.SelectedItem = c24c;
            window._controlReady = true;
            window._controlCancellation = new();
            handler.FailFun = "/mouse/click";
            Exception? failure = null;
            try { await window.SendFarmInputAsync("/mouse/click", new()); }
            catch (Exception ex) { failure = ex; }
            check("Farm manual command failures propagate to stop multi-step work", failure is not null);
            check("Farm checks use no desktop window or native handle", !window.IsVisible && new WindowInteropHelper(window).Handle == IntPtr.Zero);
            var recovery = new FarmJobRecovery(folder);
            var bookmark = new FarmJobBookmark(Guid.NewGuid().ToString(), "simulate", "create-content", false);
            recovery.Save(bookmark);
            int beforeRestore = handler.PostAttempts;
            var resumed = new MainWindow(address => new ApiClient(address, handler), folder);
            try
            {
                check("Pending farm job survives reopening the console", resumed._farmJobId == bookmark.Id && resumed._farmJobMode == "simulate");
                check("Restoring a farm job never resubmits phone input", handler.PostAttempts == beforeRestore && new WindowInteropHelper(resumed).Handle == IntPtr.Zero);
                resumed._farmExecutionMode = "simulate";
                resumed._farmProtocolVersion = 2;
                check("Recovered pending job blocks duplicate automation", !resumed.FarmAutomationModeKnown());
                resumed._farmExecutionMode = "live";
                bool wrongMode = false;
                try { await resumed.PollFarmJobAsync(); } catch (InvalidOperationException) { wrongMode = true; }
                check("Recovered simulation job cannot be queried against a live backend", wrongMode);
                resumed.FinishFarmJob();
                check("Completed job clears its recovery record durably", recovery.Load() is null && resumed._farmJobId is null);
                File.WriteAllText(Path.Combine(folder, "farm-pending-job.json"), "{broken");
                resumed.RestoreFarmJob();
                check("Damaged farm recovery record refuses new work without losing evidence", !resumed.FarmAutomationModeKnown() && File.ReadAllText(Path.Combine(folder, "farm-pending-job.json")) == "{broken");
            }
            finally { resumed._farmJobId = null; await resumed.CloseSafelyAsync(); }
            recovery.Save(bookmark with { Mode = "live", OwnsInput = true });
            var livePending = new MainWindow(address => new ApiClient(address, handler), folder);
            try
            {
                check("Recovered live job leaves manual input paused", livePending._farmOwnsInput && !livePending._controlReady);
                livePending._api = new ApiClient("http://localhost:9923", handler);
                livePending._connected = true;
                livePending._devices = [c24c];
                livePending.DeviceList.ItemsSource = livePending._devices;
                livePending.DeviceList.SelectedItem = c24c;
                livePending.FinishFarmJob();
                await livePending._scopeTail;
                check("Recovered job completion requires explicit Resume", !livePending._controlReady && livePending.ResumeInputButton.IsEnabled);
            }
            finally { livePending._farmJobId = null; await livePending.CloseSafelyAsync(); }
        }
        finally
        {
            window._farmJobId = null;
            await window.CloseSafelyAsync();
            Directory.Delete(folder, true);
        }
    }
}
