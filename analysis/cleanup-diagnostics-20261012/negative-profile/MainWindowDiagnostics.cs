using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Win32;

namespace IMouse2;

public partial class MainWindow
{
    private bool _exporting;

    private async void Export_Click(object sender, RoutedEventArgs e)
    {
        if (_exporting) return;
        var dialog = new SaveFileDialog { FileName = "iMouse2-diagnostics-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".json", Filter = "JSON report|*.json" };
        if (dialog.ShowDialog(this) != true) return;
        _exporting = true;
        if (sender is Button button) button.IsEnabled = false;
        try
        {
            // Snapshot UI-owned values before awaiting; never enumerate a changing wall or
            // activity collection on a worker, or read a phone screen for this export.
            Log("Collecting diagnostics…");
            var report = await CollectDiagnosticReportAsync();
            if (_closing) return;
            await ConsoleDiagnostics.SaveAsync(dialog.FileName, report);
            Log(report.Partial
                ? "Diagnostics saved with unavailable sections marked. Review before sharing."
                : "Diagnostics saved with phone, video and recovery details. Review before sharing.");
        }
        catch (Exception ex) { Log("Export failed: " + ex.Message, true); }
        finally
        {
            _exporting = false;
            if (!_closing && sender is Button completed) completed.IsEnabled = true;
        }
    }

    internal Task<DiagnosticReport> CollectDiagnosticReportAsync()
    {
        var snapshot = DiagnosticSnapshot();
        var api = _connected ? _api : null;
        return ConsoleDiagnostics.CollectAsync(snapshot,
            api is null ? null : api.GetAsync, api is null ? CancellationToken.None : _lifetime.Token, dataPath: null);
    }

    private JsonElement DiagnosticSnapshot()
    {
        var gaps = _jitter.Summary();
        return JsonSerializer.SerializeToElement(new
        {
            observed_utc = DateTimeOffset.UtcNow,
            build_identity = ConsoleBuildInfo.Current,
            process = ConsoleDiagnostics.ProcessSnapshot(),
            connected = _connected, connection_session = _session,
            service_address = _api?.Endpoint.AbsoluteUri,
            settings = new { isolated_data_directory = !_mirrorLocal, theme = Theme.IsNight ? "night" : "light",
                track_pointer = TrackPointer.IsChecked == true, pointer_enabled = PointerEnabled.IsChecked == true,
                live_view = AutoPreview.IsChecked == true, mirror_checked_phones = BatchMode.IsChecked == true,
                preview_period_ms = _framePeriod, tile_period_ms = _tilePeriodMs },
            selected_device = Selected?.Id,
            checked_devices = _devices.Where(d => d.IsChecked).Select(d => d.Id).ToArray(),
            input = new { locally_ready = _controlReady, state_text = InputStateText.Text, sending_text = _sendingText },
            // These are cached UI observations; fresh service lists are timestamped separately.
            cached_devices = _devices.Select(d => new { d.Id, d.Name, d.Model, d.Group, board_uid = d.Hardware,
                d.BoardState, d.Online, d.VideoState, d.ReceiverName, d.ImageWidth, d.ImageHeight }).ToArray(),
            cached_boards = _boards.ToArray(),
            video = new
            {
                metric_scope = "Bitmap updates after pixel deduplication; not source FPS or display scans. A still screen may need no updates.",
                preview_device = _frameId, freshness = _previewFreshness.Status,
                bitmap_updates_per_second = _rate.Fps, bitmap_updates = _live.Frames,
                since_last_bitmap_update_ms = _jitter.SinceLastMs,
                completed_gap_p50_ms = gaps.P50, completed_gap_p95_ms = gaps.P95, completed_gap_max_ms = gaps.Max,
                wall_bitmap_updates = Interlocked.Read(ref _tileFrames), wall_fetches = Interlocked.Read(ref _tileFetches),
                wall_duplicates_skipped = Interlocked.Read(ref _tileDupes), wall_streams_running = _tileStreams.RunningCount,
                tiles = _wall.Select(t => new { t.Id, t.Name, t.Status, bitmap_updates_per_second = t.Fps,
                    t.DeliveryLabel, t.DeliveryWarning, t.Following }).ToArray()
            },
            activity = _activity.ToArray()
        }, ConsoleDiagnostics.JsonOptions);
    }
}
