using System.Windows;

namespace IMouse2;

public partial class MainWindow
{
    private CancellationTokenSource _controlCancellation = new();
    private string _controlScope = "";
    private ApiClient? _controlApi;
    private Task _scopeTail = Task.CompletedTask;
    private long _controlRevision;
    private bool _controlReady = true, _stopPending, _resumePending;
    // The control lifetime a pause notice cancelled, when the notice cancelled it first.
    private volatile CancellationTokenSource? _pausedByNotice;

    private string StopTargetIds() => string.Join(',',
        (Selected is { } selected ? new[] { selected.Id } : Array.Empty<string>())
        .Concat(BatchMode.IsChecked == true ? _devices.Where(d => d.IsChecked).Select(d => d.Id) : Array.Empty<string>())
        .Distinct().Order());

    private void CancelLocalInput()
    {
        _controlReady = false;
        _controlCancellation.Cancel();
        ReleaseCurrentGesture();
        _pointerMoves.ClearPending();
    }

    /// <summary>
    /// Whether this console cancelled an input path (Stop, Resume, a selection change, disconnect
    /// or close) rather than HttpClient's timeout. Decided by the path's own lifetimes, because the
    /// exception is a TaskCanceledException either way. The pause notice a timeout raises cancels
    /// local input as well, possibly before the path sees its exception, so a control lifetime that
    /// notice cancelled first does not count as a cancellation.
    /// </summary>
    private bool CancelledHere(CancellationToken lifetime, CancellationTokenSource control) =>
        lifetime.IsCancellationRequested || (control.IsCancellationRequested && control != _pausedByNotice);

    private void RefreshInputOwnershipUi()
    {
        if (StopInputButton is null || ResumeInputButton is null || InputStateText is null) return;
        bool managed = !_closing && _api?.UsesInputOwnership == true;
        var ids = managed ? InputTargetIds() : "";
        if (managed && (_controlApi != _api || ids != _controlScope))
        {
            var oldApi = _controlApi; string previous = _controlScope;
            _controlApi = _api; _controlScope = ids;
            var nextApi = _api!; long revision = ++_controlRevision;
            CancelLocalInput();
            InputStateText.Text = "Changing control selection…";
            var prior = _scopeTail;
            _scopeTail = ChangeInputScopeAsync(prior, oldApi, previous, nextApi, ids, revision);
        }
        string targets = StopTargetIds();
        StopInputButton.IsEnabled = managed && targets.Length > 0 && !_stopPending;
        ResumeInputButton.IsEnabled = managed && targets.Length > 0 && !_stopPending && !_resumePending && !_controlReady;
        string names = string.Join(", ", targets.Split(',').Select(id => _devices.FirstOrDefault(d => d.Id == id)?.DisplayName ?? id));
        StopInputButton.ToolTip = "Stop input: " + names + ". Works even when video is offline.";
        ResumeInputButton.ToolTip = "Resume input: " + names + ". Previous clicks are never replayed.";
    }
    private async Task ChangeInputScopeAsync(Task prior, ApiClient? oldApi, string previous, ApiClient nextApi, string ids, long revision)
    {
        await Task.Yield();
        try
        {
            await prior;
            if (oldApi is not null && previous.Length > 0) await oldApi.ReleaseInputAsync(previous);
            if (_closing || revision != _controlRevision || nextApi != _api) return;
            nextApi.ReadyInputScope(ids);
            _controlCancellation = new(); _controlReady = true;
            InputStateText.Text = ids.Length == 0 ? "Select a phone to control" : "Input ready · ownership checked before sending";
        }
        catch (Exception ex) { if (revision == _controlRevision) InputStateText.Text = "Input paused: " + Friendly(ex); }
        finally { if (!_closing) RefreshInputOwnershipUi(); }
    }
    private async void StopInput_Click(object sender, RoutedEventArgs e)
    {
        var api = _api; string ids = StopTargetIds();
        if (api is null || ids.Length == 0 || _stopPending) return;
        long revision = ++_controlRevision;
        CancelLocalInput(); _stopPending = true;
        InputStateText.Text = "Stopping input and releasing buttons…";
        RefreshInputOwnershipUi();
        try
        {
            await api.StopInputAsync(ids);
            if (revision == _controlRevision) InputStateText.Text = "Input stopped · choose Resume input to continue";
            Log("Input stopped: " + ids);
        }
        catch (Exception ex) { if (!_closing && revision == _controlRevision) { InputStateText.Text = "Stop not confirmed: " + Friendly(ex); Log(InputStateText.Text, true); } }
        finally { _stopPending = false; RefreshInputOwnershipUi(); }
    }
    private async void ResumeInput_Click(object sender, RoutedEventArgs e)
    {
        var api = _api; string ids = StopTargetIds();
        if (api is null || ids.Length == 0 || _stopPending || _resumePending) return;
        long revision = ++_controlRevision;
        CancelLocalInput(); _resumePending = true;
        InputStateText.Text = "Checking input recovery…"; RefreshInputOwnershipUi();
        try
        {
            await _scopeTail;
            await api.ResumeInputAsync(ids);
            if (_closing || revision != _controlRevision || api != _api) return;
            _controlCancellation = new(); _controlReady = true;
            InputStateText.Text = "Input ready · previous actions discarded";
        }
        catch (Exception ex) { if (revision == _controlRevision) InputStateText.Text = "Cannot resume: " + Friendly(ex); }
        finally { _resumePending = false; RefreshInputOwnershipUi(); }
    }
}
