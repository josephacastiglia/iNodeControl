using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;

namespace IMouse2;

internal sealed partial class FarmPreparationWindow : Window
{
    private readonly FarmApiClient _api;
    private readonly string _dataFolder, _mode;
    private readonly TextBox _minutes = new() { Text = "1440" };
    private readonly TextBox _limit = new() { Text = "3" };
    private readonly Button _start = new() { Content = "Start local preparation", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _pause = new() { Content = "Pause future runs", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _check = new() { Content = "Check status", Padding = new Thickness(12, 8, 12, 8) };
    private readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 12) };
    private readonly ComboBox _history = new() { MinWidth = 320, Margin = new Thickness(0, 8, 0, 8) };
    private readonly Button _openDraft = new() { Content = "Open this run’s carousel", Padding = new Thickness(12, 8, 12, 8), IsEnabled = false };
    private readonly Button _openVideo = new() { Content = "Prepare this run’s video…", Padding = new Thickness(12, 8, 12, 8), IsEnabled = false };
    private readonly TextBox _runs = new() { IsReadOnly = true, TextWrapping = TextWrapping.Wrap, Height = 210, VerticalContentAlignment = VerticalAlignment.Top, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
    private sealed record PreparedRun(string Id, string Label, JsonElement Record)
    {
        public override string ToString() => Label;
    }
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromSeconds(5) };
    private object? _pending;
    private string? _pendingId;
    private bool _busy;

    internal FarmPreparationWindow(FarmApiClient api, string dataFolder, string mode)
    {
        _api = api; _dataFolder = dataFolder; _mode = mode;
        Title = "Recurring local preparation"; Width = 720; Height = 820; MinWidth = 500; MinHeight = 500;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        SetResourceReference(BackgroundProperty, "SurfaceBrush"); SetResourceReference(ForegroundProperty, "TextBrush");
        var body = new StackPanel { Margin = new Thickness(24) };
        body.Children.Add(new TextBlock { Text = "Prepare content for review", FontSize = 24, FontWeight = FontWeights.SemiBold });
        body.Children.Add(new TextBlock { Text = "Creates local C24C images and video while the candidate backend runs. It never connects to a phone, starts a transfer, publishes or sends messages. The first run is due immediately; later runs use the interval below.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 10, 0, 12) });
        foreach (var (label, field) in new[] { ("Interval in minutes (60–10,080; 1,440 = daily)", _minutes), ("Run limit (1–30; schedule stops at this limit)", _limit) })
        {
            body.Children.Add(new TextBlock { Text = label, Margin = new Thickness(0, 10, 0, 4), TextWrapping = TextWrapping.Wrap }); body.Children.Add(field);
        }
        var actions = new WrapPanel { Margin = new Thickness(0, 16, 0, 0) };
        actions.Children.Add(_start); actions.Children.Add(_pause); actions.Children.Add(_check); body.Children.Add(actions);
        body.Children.Add(_status);
        body.Children.Add(new TextBlock { Text = "Completed and recent runs", FontWeight = FontWeights.SemiBold });
        body.Children.Add(_history);
        var reviewActions = new WrapPanel(); reviewActions.Children.Add(_openDraft); reviewActions.Children.Add(_openVideo);
        body.Children.Add(reviewActions); body.Children.Add(_runs);
        body.Children.Add(new TextBlock { Text = "Closing this window leaves the configured backend schedule running. Pause stops future runs; an active render can finish. Missed runs are skipped. A failed or interrupted render holds the schedule for review and is never automatically retried. Generated media is retained for review, so check disk space before long runs.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 0) });
        Content = new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Loaded += async (_, _) => { await RunAsync(RefreshAsync); _timer.Start(); };
        _timer.Tick += async (_, _) => { if (_pending is null) await RunAsync(RefreshAsync); };
        Closed += (_, _) => _timer.Stop();
        _start.Click += async (_, _) => await RunAsync(StartAsync);
        _pause.Click += async (_, _) => await RunAsync(PauseAsync);
        _check.Click += async (_, _) => await RunAsync(RefreshAsync);
        _history.SelectionChanged += (_, _) => ShowSelectedRun();
        _openDraft.Click += (_, _) =>
        {
            if (SelectedDraftId() is not { } id) return;
            _timer.Stop();
            try { new CarouselDraftWindow(_api, _dataFolder, _mode, id) { Owner = this }.ShowDialog(); }
            finally { _timer.Start(); }
        };
        _openVideo.Click += (_, _) =>
        {
            if (SelectedVideoBatch() is not { } batch) return;
            _timer.Stop();
            try { new VideoDraftWindow(_api, batch, _dataFolder) { Owner = this }.ShowDialog(); }
            finally { _timer.Start(); }
        };
    }
    private async Task RunAsync(Func<Task> action)
    {
        if (_busy) return;
        _busy = true; Buttons();
        try { await action(); }
        catch (Exception ex) { _status.Text = ex.Message + (_pending is null ? "" : " Configuration outcome is unknown. Finish the same request or pause; no new schedule ID will be sent."); }
        finally { _busy = false; Buttons(); }
    }
    private void Buttons()
    {
        _start.IsEnabled = _pause.IsEnabled = _check.IsEnabled = !_busy;
        _minutes.IsEnabled = _limit.IsEnabled = !_busy && _pending is null;
        _start.Content = _pending is null ? "Start local preparation" : "Finish same request";
        _openDraft.IsEnabled = !_busy && SelectedDraftId() is not null;
        _openVideo.IsEnabled = !_busy && SelectedVideoBatch() is not null;
    }
    private async Task StartAsync()
    {
        if (_pending is null)
        {
            if (!int.TryParse(_minutes.Text, out int minutes) || !int.TryParse(_limit.Text, out int limit)) throw new InvalidOperationException("Use whole numbers for interval and run limit.");
            _pendingId = Guid.NewGuid().ToString();
            _pending = new { id = _pendingId, device_id = "C24C", action = "create-content", interval_minutes = minutes, max_runs = limit };
        }
        try { Apply(await _api.SendAsync("/api/farm/preparation-schedule", _pending)); _pending = null; _pendingId = null; }
        catch (FarmRequestRejectedException ex) when (ex.StatusCode is >= 400 and < 500 && ex.StatusCode != 409)
        { _pending = null; _pendingId = null; throw; }
    }
    private async Task PauseAsync()
    {
        Apply(await _api.SendAsync("/api/farm/preparation-schedule/pause", new { cancel_request_id = _pendingId }));
        _pending = null; _pendingId = null;
    }
    private async Task RefreshAsync() => Apply(await _api.SendAsync("/api/farm/preparation-schedule"));
    private void Apply(JsonElement response)
    {
        var status = response.GetProperty("preparationSchedule"); var config = status.GetProperty("config");
        _status.Text = config.GetProperty("state").GetString() + " · " + config.GetProperty("reason").GetString();
        if (config.TryGetProperty("enabled", out var enabled) && enabled.ValueKind == JsonValueKind.True && config.TryGetProperty("nextDue", out var due))
            _status.Text += "\nNext due (UTC): " + DateTimeOffset.FromUnixTimeSeconds((long)due.GetDouble()).ToString("yyyy-MM-dd HH:mm:ss");
        if (!status.GetProperty("workerRunning").GetBoolean()) _status.Text += "\nBackground worker is not running; no scheduled preparation will start.";
        if (status.TryGetProperty("workerError", out var error) && error.ValueKind == JsonValueKind.String) _status.Text += "\nWorker stopped: " + error.GetString();
        string? selected = (_history.SelectedItem as PreparedRun)?.Id;
        var runs = status.GetProperty("runs").EnumerateArray().Select(run =>
        {
            string id = run.GetProperty("id").GetString()!;
            string when = run.TryGetProperty("startedAt", out var started) ? DateTimeOffset.FromUnixTimeSeconds((long)started.GetDouble()).ToLocalTime().ToString("MMM d HH:mm") : id;
            return new PreparedRun(id, when + " · " + run.GetProperty("state").GetString(), run.Clone());
        }).ToArray();
        _history.ItemsSource = runs;
        _history.SelectedItem = runs.FirstOrDefault(run => run.Id == selected) ?? runs.FirstOrDefault();
        ShowSelectedRun();
    }
    private string? SelectedDraftId()
    {
        if (_history.SelectedItem is not PreparedRun run || run.Record.GetProperty("state").GetString() != "succeeded" ||
            !run.Record.TryGetProperty("contentItems", out var items)) return null;
        var drafts = items.EnumerateArray().Where(item => item.TryGetProperty("localDraft", out _)).ToArray();
        return drafts.Length == 1 && drafts[0].GetProperty("localDraft").TryGetProperty("id", out var id) &&
            Guid.TryParse(id.GetString(), out var parsed) ? parsed.ToString() : null;
    }
    private void ShowSelectedRun()
    {
        _runs.Text = _history.SelectedItem is PreparedRun run ? DescribeRun(run.Record) : "No preparation runs yet.";
        _openDraft.IsEnabled = !_busy && SelectedDraftId() is not null;
        _openVideo.IsEnabled = !_busy && SelectedVideoBatch() is not null;
    }
    private VideoDraftWindow.Batch? SelectedVideoBatch()
    {
        if (_history.SelectedItem is not PreparedRun run || run.Record.GetProperty("state").GetString() != "succeeded" ||
            !run.Record.TryGetProperty("contentItems", out var items)) return null;
        foreach (var item in items.EnumerateArray())
            if (item.TryGetProperty("generation", out var generation) && Guid.TryParseExact(generation.GetString(), "N", out _) &&
                item.TryGetProperty("manifestSha256", out var checksum) && checksum.ValueKind == JsonValueKind.String && checksum.GetString()?.Length == 64 &&
                item.TryGetProperty("stagedFiles", out var files) && files.EnumerateArray().Any(f => f.GetString()?.EndsWith(".mp4", StringComparison.OrdinalIgnoreCase) == true))
                return new(generation.GetString()!, checksum.GetString()!);
        return null;
    }
    private static string DescribeRun(JsonElement run)
    {
        string text = run.GetProperty("state").GetString() + " · " + run.GetProperty("id").GetString();
        if (run.TryGetProperty("error", out var error)) text += "\n" + error.GetString();
        if (run.TryGetProperty("contentItems", out var items))
            foreach (var item in items.EnumerateArray())
            {
                text += "\n" + (item.TryGetProperty("platform", out var platform) ? platform.GetString() : "Content")
                    + (item.TryGetProperty("id", out var id) ? " · item " + id.ToString() : "");
                if (item.TryGetProperty("caption", out var caption)) text += "\n" + caption.GetString();
                if (item.TryGetProperty("stagedFiles", out var files)) text += "\n" + string.Join(", ", files.EnumerateArray().Select(f => f.GetString()));
                if (item.TryGetProperty("localDraft", out var draft)) text += "\nSaved local carousel · original revision " + draft.GetProperty("revision").ToString()
                    + ". Open to review or edit its current saved revision. Not an Instagram draft.";
            }
        return text;
    }
}
