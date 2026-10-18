using System.Text.Json;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace IMouse2;

internal sealed partial class FarmDraftVerificationWindow : Window
{
    private readonly FarmApiClient _api;
    private readonly string _draftId;
    private readonly int _revision;
    private readonly TextBox _account = new();
    private readonly Dictionary<string, ListBox> _stages = [];
    private readonly Button _compare = new() { Content = "Compare saved evidence", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _recover = new() { Content = "Check saved result", Padding = new Thickness(12, 8, 12, 8), IsEnabled = false };
    private readonly Button _refresh = new() { Content = "Refresh saved screens", Padding = new Thickness(12, 8, 12, 8) };
    private readonly ComboBox _history = new() { MinHeight = 30, DisplayMemberPath = "Label" };
    private readonly ComboBox _frames = new() { MinHeight = 30, MinWidth = 250, DisplayMemberPath = "Label" };
    private readonly Button _view = new() { Content = "View retained image", Padding = new Thickness(12, 8, 12, 8), IsEnabled = false };
    private readonly Image _preview = new() { MaxHeight = 450, Stretch = Stretch.Uniform };
    private readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 0) };
    private bool _busy;
    private string? _pending;
    private string? _savedId;
    private sealed record Screen(string Id, double Time, string Label)
    {
        public override string ToString() => Label;
    }
    private sealed record Review(string Id, string Label)
    {
        public override string ToString() => Label;
    }

    internal FarmDraftVerificationWindow(FarmApiClient api, string draftId, int revision, string title)
    {
        _api = api; _draftId = draftId; _revision = revision;
        Title = "Review carousel evidence"; Width = 1000; Height = 860; MinWidth = 780; MinHeight = 600;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        SetResourceReference(BackgroundProperty, "SurfaceBrush"); SetResourceReference(ForegroundProperty, "TextBrush");
        var panel = new StackPanel { Margin = new Thickness(24) };
        panel.Children.Add(new TextBlock { Text = "Compare the saved and reopened draft", FontSize = 23, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = $"{title} · saved revision {revision}", Margin = new Thickness(0, 8, 0, 8), TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = "Uses saved C24C screens. Select each full-size editor slide in order, with its page dots visible, plus the caption details screen before saving and after reopening. Use Ctrl for multiple screens. Every stored observation between the account screens is audited, including unselected screens. No phone action is sent.", TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = "Expected Instagram handle", Margin = new Thickness(0, 12, 0, 4) }); panel.Children.Add(_account);
        var grid = new Grid { Margin = new Thickness(0, 12, 0, 0) };
        grid.ColumnDefinitions.Add(new()); grid.ColumnDefinitions.Add(new());
        string[] roles = ["account_before", "prepared", "library", "reopened", "account_after"];
        string[] labels = ["1. Account before", "2. Prepared slides + caption", "3. Draft library after save", "4. Reopened slides + caption", "5. Account after"];
        for (int i = 0; i < roles.Length; i++)
        {
            if (i % 2 == 0) grid.RowDefinitions.Add(new() { Height = GridLength.Auto });
            var group = new StackPanel { Margin = new Thickness(0, 0, 12, 12) };
            group.Children.Add(new TextBlock { Text = labels[i], FontWeight = FontWeights.SemiBold });
            var list = new ListBox { Height = 92, DisplayMemberPath = "Label", SelectionMode = i is 1 or 3 ? SelectionMode.Extended : SelectionMode.Single };
            _stages.Add(roles[i], list); group.Children.Add(list); Grid.SetColumn(group, i % 2); Grid.SetRow(group, i / 2); grid.Children.Add(group);
        }
        panel.Children.Add(grid);
        var buttons = new WrapPanel(); buttons.Children.Add(_refresh); buttons.Children.Add(_compare); buttons.Children.Add(_recover); panel.Children.Add(buttons);
        panel.Children.Add(new TextBlock { Text = "Saved reviews for this draft", Margin = new Thickness(0, 12, 0, 4) }); panel.Children.Add(_history);
        var images = new WrapPanel { Margin = new Thickness(0, 8, 0, 0) }; images.Children.Add(_frames); images.Children.Add(_view);
        panel.Children.Add(images); panel.Children.Add(_preview); panel.Children.Add(_status);
        Content = new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Loaded += async (_, _) => await RunAsync(RefreshAsync);
        _refresh.Click += async (_, _) => await RunAsync(RefreshAsync);
        _compare.Click += async (_, _) => await RunAsync(CompareAsync);
        _recover.Click += async (_, _) => await RunAsync(RecoverAsync);
        _view.Click += async (_, _) => await RunAsync(ViewAsync);
        _history.SelectionChanged += async (_, _) => { if (!_busy && _pending is null && _history.SelectedItem is Review row) await RunAsync(() => ShowAsync(row.Id)); };
        Closing += (_, e) => { if (_busy) { e.Cancel = true; _status.Text = "Wait for the local comparison to finish. No phone action is running."; } };
    }

    private void Buttons()
    {
        bool edit = !_busy && _pending is null;
        _account.IsEnabled = _compare.IsEnabled = _refresh.IsEnabled = _history.IsEnabled = edit;
        foreach (var list in _stages.Values) list.IsEnabled = edit;
        _recover.IsEnabled = !_busy && _pending is not null;
        _frames.IsEnabled = _view.IsEnabled = !_busy && _pending is null && _savedId is not null;
    }
    private async Task RunAsync(Func<Task> action)
    {
        if (_busy) return; _busy = true; Buttons();
        try { await action(); }
        catch (Exception ex) { _status.Text = ex.Message + (_pending is null ? " No phone action was sent." : " Check the saved result; no capture or comparison will be replayed."); }
        finally { _busy = false; Buttons(); }
    }
    private async Task RefreshAsync()
    {
        _savedId = null; _preview.Source = null; _frames.ItemsSource = null;
        var health = await _api.SendAsync("/health");
        if (!health.TryGetProperty("draftVerificationVersion", out var version) || version.GetInt32() != 2)
            throw new InvalidOperationException("Start the updated candidate backend for draft evidence review.");
        var response = await _api.SendAsync("/api/farm/observations");
        var screens = response.GetProperty("observations").EnumerateArray()
            .Where(o => o.GetProperty("state").GetString() == "observed" && o.GetProperty("expected").GetProperty("platform").GetString() == "instagram")
            .Select(o => new Screen(o.GetProperty("id").GetString()!, o.GetProperty("requestedAt").GetDouble(),
                DateTimeOffset.FromUnixTimeSeconds((long)o.GetProperty("requestedAt").GetDouble()).ToLocalTime().ToString("MMM d HH:mm:ss") + " · "
                + o.GetProperty("result").GetProperty("screen").GetString() + " · @" + o.GetProperty("expected").GetProperty("account").GetString()
                + (o.GetProperty("source").GetString() == "phone" ? "" : " · simulated"))).OrderBy(o => o.Time).ToArray();
        foreach (var list in _stages.Values) list.ItemsSource = screens;
        await HistoryAsync();
        _status.Text = screens.Length == 0 ? "No saved Instagram observations. Use Read C24C screen to collect evidence explicitly, then refresh here." : "Select recorded stages. A matching picture or account name alone does not prove the draft was saved.";
    }
    private async Task HistoryAsync()
    {
        var response = await _api.SendAsync("/api/farm/draft-verifications?draft_id=" + Uri.EscapeDataString(_draftId));
        _history.ItemsSource = response.GetProperty("verifications").EnumerateArray().Select(r => new Review(r.GetProperty("id").GetString()!,
            "Revision " + r.GetProperty("revision").GetInt32() + " · " + r.GetProperty("status").GetString() + " · "
            + DateTimeOffset.FromUnixTimeSeconds((long)r.GetProperty("createdAt").GetDouble()).ToLocalTime().ToString("MMM d HH:mm:ss"))).ToArray();
    }
    private async Task CompareAsync()
    {
        if (_pending is not null) throw new InvalidOperationException("Check the pending review first.");
        if (string.IsNullOrWhiteSpace(_account.Text)) throw new InvalidOperationException("Enter the Instagram handle you expect.");
        var selected = _stages.ToDictionary(p => p.Key, p => p.Value.SelectedItems.Cast<Screen>().OrderBy(s => s.Time).Select(s => s.Id).ToArray());
        _pending = Guid.NewGuid().ToString();
        JsonElement response;
        try { response = await _api.SendAsync("/api/farm/draft-verifications", new { id = _pending, draft_id = _draftId, revision = _revision, device_id = "C24C", platform = "instagram", account = _account.Text.Trim(), observations = selected }); }
        catch (FarmRequestRejectedException ex) when (ex.StatusCode is >= 400 and < 500 && ex.StatusCode != 409) { _pending = null; throw; }
        Apply(response.GetProperty("verification")); _pending = null; await HistoryAsync();
    }
    private async Task ShowAsync(string id) => Apply((await _api.SendAsync("/api/farm/draft-verifications/" + id)).GetProperty("verification"));
    private async Task RecoverAsync()
    {
        if (_pending is null) return;
        try { await ShowAsync(_pending); _pending = null; await HistoryAsync(); }
        catch (FarmRequestRejectedException ex) when (ex.StatusCode == 404) { _pending = null; _status.Text = "No saved review. You may request a new comparison. No phone action was replayed."; }
    }
    private void Apply(JsonElement value)
    {
        _savedId = value.GetProperty("id").GetString(); _preview.Source = null;
        var report = value.GetProperty("assessment");
        var images = new List<Review>();
        var lines = new List<string> { "Historical evidence review · " + report.GetProperty("status").GetString(),
            "Source: " + report.GetProperty("source").GetString(), "App save and uninterrupted account continuity are NOT verified. Automatic phone actions remain disabled." };
        if (value.GetProperty("draftChangedSinceReview").GetBoolean()) lines.Add("The local draft changed after this review. These results belong to its older revision.");
        if (report.TryGetProperty("slideCoverage", out var coverage))
            foreach (var stage in coverage.EnumerateObject())
                lines.Add(stage.Name + ": full-size slides and positions " + (stage.Value.GetProperty("fullSizeAndPositionMatch").GetBoolean() ? "match" : "incomplete")
                    + "; expected " + stage.Value.GetProperty("expectedCount") + "; observed " + stage.Value.GetProperty("observedIndices"));
        if (report.TryGetProperty("accountHistory", out var history))
        {
            lines.Add("Account history: " + history.GetProperty("status").GetString() + ". Sampled screens do not prove activity between captures.");
            foreach (var row in history.GetProperty("observations").EnumerateArray())
                images.Add(new Review(row.GetProperty("id").GetString()!, "Account history · " + row.GetProperty("screen").GetString()));
        }
        lines.AddRange(report.GetProperty("blockers").EnumerateArray().Select(b => "• " + b.GetString()));
        foreach (var stage in report.GetProperty("stages").EnumerateObject())
        {
            foreach (var row in stage.Value.EnumerateArray())
            {
                images.Add(new Review(row.GetProperty("id").GetString()!, stage.Name.Replace('_', ' ') + " · " + row.GetProperty("screen").GetString()));
                string detail = stage.Name.Replace('_', ' ') + ": " + row.GetProperty("screen").GetString() + "; account " + row.GetProperty("account").GetString();
                if (row.TryGetProperty("media", out var media)) detail += "; media " + media.GetProperty("status").GetString() + " (slide " + media.GetProperty("matchedIndex").ToString() + ")";
                if (row.TryGetProperty("caption", out var caption)) detail += "; caption " + caption.GetProperty("status").GetString();
                lines.Add(detail);
            }
        }
        lines.AddRange(report.GetProperty("limits").EnumerateArray().Select(l => l.GetString()!));
        _frames.ItemsSource = images.DistinctBy(r => r.Id).ToList(); _frames.SelectedIndex = images.Count > 0 ? 0 : -1;
        _status.Text = string.Join("\n\n", lines);
    }
    private async Task ViewAsync()
    {
        if (_savedId is null || _frames.SelectedItem is not Review row) throw new InvalidOperationException("Choose an image from a saved review first.");
        _preview.Source = null;
        var result = await _api.SendAsync($"/api/farm/draft-verifications/{_savedId}/frames/{row.Id}");
        using var bytes = new MemoryStream(Convert.FromBase64String(result.GetProperty("frame").GetString()!));
        var image = new BitmapImage(); image.BeginInit(); image.CacheOption = BitmapCacheOption.OnLoad; image.StreamSource = bytes; image.EndInit(); image.Freeze(); _preview.Source = image;
    }
}
