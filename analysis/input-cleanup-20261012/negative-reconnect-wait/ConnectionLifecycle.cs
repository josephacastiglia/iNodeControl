using System.Windows.Media;
using System.Windows;

namespace IMouse2;

public partial class MainWindow
{
    private readonly ConnectionCleanup _connectionCleanup = new();
    private ApiClient? _pendingConnection;
    private Task? _windowClose;
    private bool _closeAllowed;
    internal string? CleanupWarning { get; private set; }

    // UI-thread transition: stop accepting work before waiting for any network response.
    // Retired clients remain tracked even if another Connect or Disconnect overtakes us.
    private void DetachConnection()
    {
        ++_session; ++_controlRevision;
        CancelLocalInput();
        _lifetime.Cancel();
        _tileStreams.Stop(); _refreshTimer.Stop();
        _connectionCleanup.Retire(_api);
        _connectionCleanup.Retire(_pendingConnection);
        _api = _pendingConnection = _controlApi = null;
        _scopeTail = Task.CompletedTask;
        _controlScope = ""; _connected = false; _castName = "";
        _devices.Clear(); DeviceList.ItemsSource = null;
        ClearFrame("Disconnected", "Phone mirroring was left unchanged.");
    }

    private async Task<IReadOnlyList<ConnectionCleanupRecord>> FinishConnectionCleanupAsync()
    {
        var records = await _connectionCleanup.DrainAsync();
        foreach (var record in records.Where(r => !r.Result.Confirmed)) Log(record.Result.Summary, true);
        string? saveWarning = ConnectionCleanup.Save(_dataPath, records);
        CleanupWarning = string.Join(Environment.NewLine, records.Where(r => !r.Result.Confirmed).Select(r => r.Result.Summary)
            .Concat(saveWarning is null ? [] : new[] { saveWarning }));
        if (saveWarning is not null) Log(saveWarning, true);
        return records;
    }

    // Normal window close and test-mode exit both await this. Each client has a
    // bounded cleanup budget; a missing answer is recorded, never reported as success.
    internal Task CloseSafelyAsync(bool showWarning = false) => _windowClose ??= CloseWindowAsync(showWarning);
    private async Task CloseWindowAsync(bool showWarning)
    {
        _closing = true;
        DetachConnection();
        _pointerMoves.Close();
        CompositionTarget.Rendering -= PresentPending;
        ConnectionStatus.Text = "Closing · releasing input…";
        IsEnabled = false;
        // Let the original WPF Closing event finish before calling Close again.
        await Task.Yield();
        await FinishConnectionCleanupAsync();
        if (showWarning && !string.IsNullOrEmpty(CleanupWarning))
            MessageBox.Show(this, CleanupWarning, "Input cleanup needs attention", MessageBoxButton.OK, MessageBoxImage.Warning);
        _closeAllowed = true;
        Close();
    }
}
