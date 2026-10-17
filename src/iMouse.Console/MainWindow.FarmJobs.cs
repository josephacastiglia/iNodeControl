using System.Windows;

namespace IMouse2;

public partial class MainWindow
{
    private string? _farmJobId;
    private bool _farmOwnsInput, _farmLiveAutomationReady;
    private int _farmProtocolVersion;
    private FarmApiClient FarmApi => new(FarmHttp, FarmServerUrl);

    private async Task RunFarmJobAsync(string action, object payload)
    {
        if (!FarmAutomationModeKnown()) return;
        bool liveInput = _farmExecutionMode == "live" && action is not ("create-content" or "scan-profile-views" or "scheduler-tick");
        if (liveInput && !_farmLiveAutomationReady)
        {
            AppendFarmLog("Live automation is unavailable until app observations and the account workflow are validated. You can create content now.");
            return;
        }
        // Set before the first await; repeated button presses cannot launch a second job.
        _farmJobId = Guid.NewGuid().ToString();
        bool submitted = false;
        try
        {
            if (liveInput)
            {
                if (_api is not { UsesInputOwnership: true } api || !FarmTargetPolicy.IsC24C(InputTargetIds()))
                    throw new InvalidOperationException("Select only C24C and disable followers before starting live automation.");
                await _scopeTail;
                _farmOwnsInput = true;
                ++_controlRevision;
                CancelLocalInput();
                InputStateText.Text = "Releasing C24C to the farm job…";
                RefreshInputOwnershipUi();
                await api.ReleaseInputAsync(FarmTargetPolicy.DeviceId);
                if (_closing || _api != api || !FarmTargetPolicy.IsC24C(InputTargetIds()))
                    throw new InvalidOperationException("Control selection changed during handover; no job sent.");
            }
            AppendFarmLog($"Starting {action} ({_farmExecutionMode})…");
            // If this response is lost, query the same ID. Never resubmit the action.
            submitted = true;
            try { await FarmApi.SendAsync("/api/farm/jobs", new { request_id = _farmJobId, action, payload }); }
            catch (FarmRequestRejectedException) { submitted = false; throw; }
            catch (Exception ex) { AppendFarmLog("Checking submission outcome: " + ex.Message); }
            await PollFarmJobAsync();
        }
        catch (Exception ex)
        {
            AppendFarmLog("Farm job: " + ex.Message);
            if (!submitted) FinishFarmJob();
            else AppendFarmLog("Outcome not confirmed. Use Check job or Stop; this action will not be replayed.");
        }
    }

    private bool _farmPolling;
    private async Task PollFarmJobAsync()
    {
        if (_farmPolling || _farmJobId is not { } jobId) return;
        _farmPolling = true;
        string lastState = "";
        try
        {
            while (!_closing && _farmJobId == jobId)
            {
                var response = await FarmApi.SendAsync("/api/farm/jobs/" + jobId);
                var job = response.GetProperty("job");
                string state = job.GetProperty("status").GetString() ?? "unknown";
                if (state != lastState) { AppendFarmLog("Job " + state); lastState = state; }
                if (job.GetProperty("terminal").GetBoolean())
                {
                    if (job.TryGetProperty("error", out var error) && error.ValueKind == System.Text.Json.JsonValueKind.String)
                        AppendFarmLog(error.GetString() ?? "Job failed");
                    if (job.TryGetProperty("result", out var result) && result.ValueKind != System.Text.Json.JsonValueKind.Null)
                        AppendFarmLog(result.ToString());
                    FinishFarmJob();
                    await RefreshFarmStateAsync();
                    return;
                }
                await Task.Delay(500);
            }
            await RequestFarmCancellationAsync();
        }
        finally { _farmPolling = false; }
    }

    private void FinishFarmJob()
    {
        _farmJobId = null;
        if (_farmOwnsInput)
        {
            _farmOwnsInput = false;
            InputStateText.Text = "Farm job ended · inspect C24C, then choose Resume input";
            RefreshInputOwnershipUi(); // Explicit Resume; no takeover or replay.
        }
    }

    private async Task RequestFarmCancellationAsync()
    {
        if (_farmJobId is not { } jobId) return;
        try { await FarmApi.SendAsync("/api/farm/jobs/" + jobId + "/cancel", new { }); }
        catch (Exception ex) { AppendFarmLog("Cancellation not confirmed: " + ex.Message); }
    }

    private async void FarmCheckJob_Click(object sender, RoutedEventArgs e)
    {
        try { await PollFarmJobAsync(); await RefreshFarmStateAsync(); }
        catch (Exception ex) { AppendFarmLog("Job status unavailable: " + ex.Message); }
    }

    private async void FarmCreateContent_Click(object sender, RoutedEventArgs e) =>
        await RunFarmJobAsync("create-content", new { device_id = "C24C" });

    private async void FarmResumeSimulation_Click(object sender, RoutedEventArgs e)
    {
        if (!FarmAutomationModeKnown()) return;
        try
        {
            await FarmApi.SendAsync("/api/farm/resume-simulation", new { });
            AppendFarmLog("Simulation resumed. Real C24C input is unchanged.");
        }
        catch (Exception ex) { AppendFarmLog(ex.Message); }
    }

    private async void FarmSavePersona_Click(object sender, RoutedEventArgs e)
    {
        if (!FarmAutomationModeKnown()) return;
        try
        {
            await FarmApi.SendAsync("/api/farm/update-persona", new { device_id = "C24C", niche = FarmNicheBox.Text, cta_keyword = FarmKeywordBox.Text });
            _farmPersonaLoaded = false;
            AppendFarmLog("C24C persona saved.");
            await RefreshFarmStateAsync();
        }
        catch (Exception ex) { AppendFarmLog("Persona not saved: " + ex.Message); }
    }

    private void FarmOpenContent_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            if (_farmExecutionMode is not ("simulate" or "live")) throw new InvalidOperationException("Connect to the farm backend first.");
            string? script = IMouse2.ConsoleApp.FarmAutomationWindow.ResolveFarmServerScriptPath();
            if (script is null) throw new InvalidOperationException("The farm workspace was not found.");
            string folder = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(System.IO.Path.GetDirectoryName(script))!, "output", "media-stage", "v2", _farmExecutionMode, "C24C");
            string review = System.IO.Path.Combine(folder, "review.html");
            if (!System.IO.File.Exists(review)) throw new InvalidOperationException("Create content first. There is no draft to review yet.");
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(review) { UseShellExecute = true });
        }
        catch (Exception ex) { AppendFarmLog("Draft review: " + ex.Message); }
    }

    private async Task SendFarmInputAsync(string function, Dictionary<string, object> values)
    {
        if (_farmJobId is not null || !_controlReady || !_connected || _api is not { } api || SelectedFarmInputPhone() is not { } phone)
            throw new InvalidOperationException("Select C24C and make sure input is ready with no farm job running.");
        var payload = new Dictionary<string, object>(values) { ["id"] = phone.Id };
        var context = new InputContext(api, phone.Id, _lifetime.Token, _controlCancellation);
        _pointerMoves.ClearPending();
        // Unlike the general control helper, this never expands to checked followers
        // and propagates failure so a multi-step farm flow stops immediately.
        await _inputActions.Enqueue(context, ct => api.CommandAsync(function, payload, ct));
    }
}
