using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Diagnostics;
using System.Windows.Threading;

namespace IMouse2;

internal sealed partial class FarmObservationWindow : Window
{
    private readonly FarmApiClient _api;
    private readonly ComboBox _platform = new() { ItemsSource = new[] { "instagram", "tiktok", "x", "youtube" }, SelectedIndex = 0, MinHeight = 30 };
    private readonly TextBox _account = new();
    private readonly TextBox _caption = new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 65 };
    private readonly ComboBox _history = new() { DisplayMemberPath = "Label", MinHeight = 30 };
    private readonly Button _read = new() { Content = "Read C24C screen", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _recover = new() { Content = "Check saved result", Padding = new Thickness(12, 8, 12, 8), IsEnabled = false };
    private readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 0) };
    private readonly TextBlock _freshnessNotice = new() { TextWrapping = TextWrapping.Wrap, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 12, 0, 0) };
    private readonly DispatcherTimer _ageTimer = new() { Interval = TimeSpan.FromMilliseconds(250) };
    private readonly Stopwatch _viewClock = new();
    private double _ageBudgetMs;
    private readonly Image _frame = new() { Stretch = Stretch.Uniform, MaxHeight = 560, Margin = new Thickness(18, 0, 0, 0) };
    private string? _pending;
    private bool _busy;
    private sealed record Saved(string Label, string Id);

    internal FarmObservationWindow(FarmApiClient api)
    {
        _api = api; Title = "Read-only C24C screen review"; Width = 860; Height = 780; MinWidth = 700; MinHeight = 560;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        SetResourceReference(BackgroundProperty, "SurfaceBrush"); SetResourceReference(ForegroundProperty, "TextBrush");
        var root = new StackPanel { Margin = new Thickness(24) };
        root.Children.Add(new TextBlock { Text = "Check the phone before continuing", FontSize = 23, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        root.Children.Add(new TextBlock { Text = "Reads the real C24C mirror using local text recognition, even when jobs use simulation. No clicks, typing, lease takeover or app navigation. The saved image is evidence for review, not permission to run automation.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 10, 0, 18) });
        var columns = new Grid(); columns.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) }); columns.ColumnDefinitions.Add(new() { Width = new GridLength(280) });
        var form = new StackPanel(); columns.Children.Add(form); Grid.SetColumn(_frame, 1); columns.Children.Add(_frame);
        foreach (var (label, field) in new (string, FrameworkElement)[] { ("Expected app", _platform), ("Expected signed-in handle", _account), ("Expected caption (optional; exact OCR text only)", _caption), ("Previous observations", _history) })
        {
            form.Children.Add(new TextBlock { Text = label, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 8, 0, 4) }); form.Children.Add(field);
        }
        var actions = new WrapPanel { Margin = new Thickness(0, 12, 0, 0) }; actions.Children.Add(_read); actions.Children.Add(_recover); form.Children.Add(actions); form.Children.Add(_freshnessNotice); form.Children.Add(_status);
        root.Children.Add(columns); Content = new ScrollViewer { Content = root, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Loaded += async (_, _) => await RunAsync(RefreshHistoryAsync);
        _read.Click += async (_, _) => await RunAsync(CaptureAsync);
        _recover.Click += async (_, _) => await RunAsync(RecoverAsync);
        _history.SelectionChanged += async (_, _) => { if (!_busy && _pending is null && _history.SelectedItem is Saved saved) await RunAsync(() => ShowAsync(saved.Id)); };
        Closing += (_, e) => { if (_busy) { e.Cancel = true; _status.Text = "Wait for the read-only request. No input is being sent."; } };
        _ageTimer.Tick += (_, _) => UpdateFreshnessNotice(_viewClock.Elapsed.TotalMilliseconds);
        Closed += (_, _) => _ageTimer.Stop();
    }

    private async Task RunAsync(Func<Task> action)
    {
        if (_busy) return;
        _busy = true; Buttons(); _ageTimer.Stop(); _freshnessNotice.Text = "Saved evidence only; checking status…";
        try { await action(); }
        catch (Exception ex) { _frame.Source = null; _status.Text = ex.Message + (_pending is null ? "" : " Check the saved result; the capture will not be replayed."); }
        finally { _busy = false; Buttons(); }
    }
    private void Buttons()
    {
        _read.IsEnabled = _platform.IsEnabled = _account.IsEnabled = _caption.IsEnabled = _history.IsEnabled = !_busy && _pending is null;
        _recover.IsEnabled = !_busy && _pending is not null;
    }
    private async Task CaptureAsync()
    {
        if (_pending is not null) throw new InvalidOperationException("Check the pending result first.");
        if (string.IsNullOrWhiteSpace(_account.Text)) throw new InvalidOperationException("Enter the account handle you expect to see.");
        _frame.Source = null; _pending = Guid.NewGuid().ToString(); _status.Text = "Reading C24C without sending input…";
        JsonElement response;
        var elapsed = Stopwatch.StartNew();
        try { response = await _api.SendAsync("/api/farm/observations", new { id = _pending, device_id = "C24C", platform = _platform.SelectedItem, account = _account.Text.Trim(), caption = _caption.Text, source = "phone", read_only = true }); }
        catch (FarmRequestRejectedException ex) when (ex.StatusCode is >= 400 and < 500 && ex.StatusCode != 409)
        { _pending = null; throw; }
        await ApplyAsync(response.GetProperty("observation"), elapsed.Elapsed.TotalMilliseconds);
        _pending = null; await RefreshHistoryAsync();
    }
    private async Task RecoverAsync()
    {
        if (_pending is null) return;
        try { await ShowAsync(_pending); _pending = null; await RefreshHistoryAsync(); }
        catch (FarmRequestRejectedException ex) when (ex.StatusCode == 404)
        { _pending = null; _status.Text = "No saved observation. Choose Read C24C screen for a new explicit capture. Nothing was replayed."; }
    }
    private async Task ShowAsync(string id)
    {
        var elapsed = Stopwatch.StartNew();
        var response = await _api.SendAsync("/api/farm/observations/" + id);
        await ApplyAsync(response.GetProperty("observation"), elapsed.Elapsed.TotalMilliseconds);
    }
    private async Task ApplyAsync(JsonElement observation, double requestElapsedMs = 0)
    {
        _frame.Source = null;
        _viewClock.Restart(); _ageBudgetMs = 0;
        UpdateFreshnessNotice(0);
        string state = observation.GetProperty("state").GetString()!;
        bool expired = observation.GetProperty("expired").GetBoolean();
        var expected = observation.GetProperty("expected");
        _status.Text = $"Expected {expected.GetProperty("platform").GetString()} / @{expected.GetProperty("account").GetString()}.\n"
            + (expired ? "Saved observation is expired. " : "Saved observation. ") + observation.GetProperty("reason").GetString();
        if (state != "observed") { _status.Text += "\nNo screen state was verified. A new read requires an explicit click."; return; }
        var result = observation.GetProperty("result");
        _status.Text += $"\n\nScreen pattern: {result.GetProperty("screen").GetString()}\nAccount text: {result.GetProperty("accountStatus").GetString()}\nCaption: {result.GetProperty("captionStatus").GetString()}\nEvidence when retrieved: {observation.GetProperty("freshness").GetString()}\nStable capture: {observation.GetProperty("stable").GetBoolean()}";
        if (observation.TryGetProperty("frameEvidence", out var evidence))
        {
            _status.Text += "\n" + evidence.GetProperty("reason").GetString();
            _status.Text += "\n" + evidence.GetProperty("meaning").GetString();
            if (!expired && observation.GetProperty("freshness").GetString() == "recent"
                && evidence.TryGetProperty("currentAgeUpperBoundMs", out var age) && age.ValueKind == JsonValueKind.Number)
                _ageBudgetMs = Math.Max(0, 1500 - age.GetDouble() - requestElapsedMs);
        }
        if (observation.TryGetProperty("workflowReview", out var review))
            _status.Text += "\n\nDraft review: " + review.GetProperty("status").GetString()
                + "\n" + string.Join("\n", review.GetProperty("blockers").EnumerateArray().Select(b => "• " + b.GetString()));
        _status.Text += "\n\nOCR can confuse characters. No saved-draft, metric or automation success is inferred.";
        var response = await _api.SendAsync("/api/farm/observations/" + observation.GetProperty("id").GetString() + "/frame");
        using var bytes = new MemoryStream(Convert.FromBase64String(response.GetProperty("frame").GetString()!));
        var image = new BitmapImage(); image.BeginInit(); image.CacheOption = BitmapCacheOption.OnLoad; image.StreamSource = bytes; image.EndInit(); image.Freeze(); _frame.Source = image;
        UpdateFreshnessNotice(_viewClock.Elapsed.TotalMilliseconds); _ageTimer.Start();
    }
    private void UpdateFreshnessNotice(double elapsedMs)
    {
        _freshnessNotice.Text = _ageBudgetMs > elapsedMs
            ? "Recent receiver delivery only. This snapshot does not authorize an action."
            : "Snapshot is old or its age is unverified. Read C24C again before continuing.";
    }
    private async Task RefreshHistoryAsync()
    {
        var response = await _api.SendAsync("/api/farm/observations");
        _history.ItemsSource = response.GetProperty("observations").EnumerateArray().Select(o =>
        {
            string id = o.GetProperty("id").GetString()!;
            return new Saved(o.GetProperty("state").GetString() + " · " + id[..8], id);
        }).ToArray();
    }
}
