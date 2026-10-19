using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace IMouse2;

internal sealed record DraftRunBookmark(string Id, string StoreId, string DraftId, int Revision);

internal sealed partial class FarmDraftRunWindow : Window
{
    private readonly FarmApiClient _api;
    private readonly string _draftId, _bookmarkPath;
    private readonly int _revision;
    private readonly Button _start = new() { Content = "Check save and reopen on C24C", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _recover = new() { Content = "Check saved result", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _stop = new() { Content = "Stop check", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _view = new() { Content = "View retained frame", Padding = new Thickness(12, 8, 12, 8) };
    private readonly ComboBox _history = new() { DisplayMemberPath = "Label", MinHeight = 32 };
    private readonly ComboBox _frames = new() { DisplayMemberPath = "Label", MinHeight = 32 };
    private readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 16, 0, 16) };
    private readonly Image _preview = new() { MaxHeight = 450, Stretch = Stretch.Uniform };
    private readonly DispatcherTimer _poll = new() { Interval = TimeSpan.FromSeconds(2) };
    private DraftRunBookmark? _pending;
    private string? _storeId, _shownId;
    private bool _busy, _eligible, _terminal, _bookmarkBroken;
    private sealed record Choice(string Id, string Label) { public override string ToString() => Label; }

    internal FarmDraftRunWindow(FarmApiClient api, string dataFolder, string draftId, int revision, string title)
    {
        _api = api; _draftId = draftId; _revision = revision;
        _bookmarkPath = Path.Combine(dataFolder, "farm-pending-draft-run.json");
        Title = "C24C draft save and reopen"; Width = 840; Height = 820; MinWidth = 680; MinHeight = 600;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        SetResourceReference(BackgroundProperty, "SurfaceBrush"); SetResourceReference(ForegroundProperty, "TextBrush");
        var panel = new StackPanel { Margin = new Thickness(24) };
        panel.Children.Add(new TextBlock { Text = "Verify the existing phone draft", FontSize = 24, FontWeight = FontWeights.SemiBold });
        panel.Children.Add(new TextBlock { Text = $"{title} · saved revision {revision}", Margin = new Thickness(0, 10, 0, 10), TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = "Candidate check · C24C · Instagram @xs.halle.xo\nChecks the already prepared, labelled three-slide test draft and its exact caption. Start on the account’s profile. The check saves, reopens, checks every slide and returns to the profile. It does not import media, type, publish or message. Other drafts are not supported by this first candidate.", TextWrapping = TextWrapping.Wrap });
        var buttons = new WrapPanel { Margin = new Thickness(0, 16, 0, 16) };
        buttons.Children.Add(_start); buttons.Children.Add(_recover); buttons.Children.Add(_stop); panel.Children.Add(buttons);
        panel.Children.Add(new TextBlock { Text = "Saved checks", FontWeight = FontWeights.SemiBold });
        panel.Children.Add(_history); panel.Children.Add(_status); panel.Children.Add(_frames); panel.Children.Add(_view); panel.Children.Add(_preview);
        Content = new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Loaded += async (_, _) => await RunAsync(InitializeAsync);
        _start.Click += async (_, _) => await RunAsync(StartAsync);
        _recover.Click += async (_, _) => await RunAsync(RecoverAsync);
        _stop.Click += async (_, _) => await StopAsync();
        _view.Click += async (_, _) => await RunAsync(ViewAsync);
        _history.SelectionChanged += async (_, _) =>
        {
            if (!_busy && _pending is null && _history.SelectedItem is Choice row) await RunAsync(() => ShowAsync(row.Id));
        };
        _poll.Tick += async (_, _) => { if (!_busy && _pending is not null && !_terminal) await RunAsync(RecoverAsync); };
        Closing += (_, e) =>
        {
            if (_busy) { e.Cancel = true; _status.Text = "Wait for the current request or use Stop check. The saved request will not be replayed."; return; }
            _poll.Stop();
            if (_pending is not null && !_terminal) _ = StopAsync();
        };
        Buttons();
    }

    private void Buttons()
    {
        bool sameStore = _pending is not null && _pending.StoreId == _storeId;
        _start.IsEnabled = _eligible && !_busy && _pending is null && !_bookmarkBroken;
        _recover.IsEnabled = !_busy && sameStore;
        _stop.IsEnabled = sameStore && !_terminal;
        _history.IsEnabled = !_busy && _pending is null && !_bookmarkBroken;
        _view.IsEnabled = _frames.IsEnabled = !_busy && _shownId is not null && _terminal;
    }
    private async Task RunAsync(Func<Task> action)
    {
        if (_busy) return; _busy = true; Buttons();
        try { await action(); }
        catch (Exception ex) { _status.Text = ex.Message + (_pending is null ? " No new check was confirmed." : " The saved request is retained. Check its result; do not repeat phone actions."); }
        finally { _busy = false; Buttons(); }
    }
    private void Keep(DraftRunBookmark? bookmark)
    {
        SettingsPersistence.WriteAtomic(_bookmarkPath, JsonSerializer.SerializeToUtf8Bytes(bookmark));
        _pending = bookmark;
    }
    private async Task InitializeAsync()
    {
        if (File.Exists(_bookmarkPath))
        {
            try
            {
                _pending = JsonSerializer.Deserialize<DraftRunBookmark?>(File.ReadAllBytes(_bookmarkPath));
                if (_pending is { } b && (!Guid.TryParse(b.Id, out _) || !Guid.TryParse(b.StoreId, out _) || !Guid.TryParse(b.DraftId, out _) || b.Revision < 1)) throw new InvalidOperationException("Invalid saved draft request.");
            }
            catch { _bookmarkBroken = true; throw new InvalidOperationException("Saved request cannot be read. Preserve this candidate data folder for review; no new check can start."); }
        }
        var health = await _api.SendAsync("/health");
        var capability = health.GetProperty("draftWorkflow");
        if (capability.GetProperty("version").GetInt32() != 1) throw new InvalidOperationException("Use the matching draft candidate backend.");
        _storeId = capability.GetProperty("storeId").GetString();
        if (!Guid.TryParse(_storeId, out _)) throw new InvalidOperationException("Candidate storage identity is missing.");
        if (_pending is not null && _pending.StoreId != _storeId) throw new InvalidOperationException("This is a different candidate data store. Reopen the original backend to retrieve the pending result.");
        // A pending request belongs to its retained revision, even if the editor
        // has since changed or deleted that revision. Retrieve it before asking
        // whether today's editor contents are eligible for a new operation.
        if (_pending is not null) { await RecoverAsync(); return; }
        var eligible = (await _api.SendAsync($"/api/farm/draft-runs/eligibility?draft_id={_draftId}&revision={_revision}")).GetProperty("eligibility");
        _eligible = capability.GetProperty("enabled").GetBoolean() && eligible.GetProperty("eligible").GetBoolean() && health.GetProperty("executionMode").GetString() == "live" && eligible.GetProperty("storeId").GetString() == _storeId;
        await HistoryAsync();
        _status.Text = eligible.GetProperty("reason").GetString() + "\n\n" + eligible.GetProperty("contentReason").GetString() + "\n\nThe interface integration still needs a fresh phone acceptance run. An offline pass is not a saved Instagram draft.";
    }
    private async Task HistoryAsync()
    {
        var response = await _api.SendAsync("/api/farm/draft-runs?draft_id=" + _draftId);
        _history.ItemsSource = response.GetProperty("runs").EnumerateArray().Select(row => new Choice(row.GetProperty("id").GetString()!, $"Revision {row.GetProperty("revision").GetInt32()} · {row.GetProperty("id").GetString()![..8]}" )).ToArray();
    }
    private async Task StartAsync()
    {
        if (!_eligible || _pending is not null || _bookmarkBroken || _storeId is null) throw new InvalidOperationException("Resolve the existing request first.");
        Keep(new(Guid.NewGuid().ToString(), _storeId, _draftId, _revision));
        _terminal = false; _shownId = null; _preview.Source = null; Buttons(); _poll.Start();
        // Keep every ambiguous response until status is reconciled. A timeout or
        // restart must never turn the same intent into a different request ID.
        var response = await _api.SendAsync("/api/farm/draft-runs", new { id = _pending!.Id, draft_id = _draftId, revision = _revision, store_id = _storeId });
        Apply(response.GetProperty("run"), _pending.Id); await HistoryAsync();
    }
    private async Task RecoverAsync()
    {
        if (_pending is null || _pending.StoreId != _storeId) return;
        await ShowAsync(_pending.Id); if (!_terminal) _poll.Start();
    }
    private async Task ShowAsync(string id) => Apply((await _api.SendAsync("/api/farm/draft-runs/" + id)).GetProperty("run"), id);
    private async Task StopAsync()
    {
        if (_pending is null || _pending.StoreId != _storeId || _terminal) return;
        try
        {
            await _api.SendAsync("/api/farm/draft-runs/" + _pending.Id + "/cancel", new { store_id = _storeId });
            _status.Text = "Stop requested. Waiting for the saved result and lease cleanup; no actions will resume automatically.";
        }
        catch (Exception ex) { _status.Text = "Stop is unconfirmed: " + ex.Message + ". The original request is kept for review."; }
    }
    private void Apply(JsonElement value, string expectedId)
    {
        var request = value.GetProperty("request");
        if (value.GetProperty("id").GetString() != expectedId || value.GetProperty("storeId").GetString() != _storeId || value.GetProperty("publishing").GetBoolean() || value.GetProperty("messaging").GetBoolean() || value.GetProperty("automaticResume").GetBoolean()
            || (_pending is { } b && (request.GetProperty("draft_id").GetString() != b.DraftId || request.GetProperty("revision").GetInt32() != b.Revision))) throw new InvalidOperationException("Result does not match the saved request and candidate data store.");
        bool terminal = value.GetProperty("terminal").GetBoolean(), verified = value.GetProperty("savedDraftVerified").GetBoolean();
        string state = value.GetProperty("state").GetString()!, cleanup = value.GetProperty("cleanup").GetString()!;
        var workflow = value.GetProperty("workflow");
        if (verified && (!terminal || state != "verified" || cleanup != "confirmed" || workflow.ValueKind != JsonValueKind.Object || workflow.GetProperty("source").GetString() != "candidate_phone_workflow")) throw new InvalidOperationException("The result lacks confirmed phone evidence and cleanup.");
        if (verified && workflow.GetProperty("actions").EnumerateArray().Any(a => a.GetProperty("state").GetString() != "answered")) throw new InvalidOperationException("An uncertain phone action cannot be presented as a verified draft.");
        _shownId = expectedId; _terminal = terminal; if (terminal) _poll.Stop();
        if (verified && _pending is not null) Keep(null);
        var lines = new List<string> { verified ? "PHONE DRAFT VERIFIED" : terminal ? "STOPPED · REVIEW REQUIRED" : "CHECK IN PROGRESS", value.GetProperty("reason").GetString()!, "Lease cleanup: " + cleanup.Replace('_', ' '), "Nothing was published or messaged. A saved draft check does not prove app-restart persistence." };
        if (value.GetProperty("draftChangedSinceRun").GetBoolean()) lines.Add("This evidence belongs to an older saved revision.");
        if (workflow.ValueKind == JsonValueKind.Object)
        {
            foreach (var action in workflow.GetProperty("actions").EnumerateArray()) lines.Add(action.GetProperty("label").GetString()!.Replace('-', ' ') + ": " + action.GetProperty("state").GetString()!.Replace('_', ' '));
            _frames.ItemsSource = workflow.GetProperty("observations").EnumerateArray().Where(e => e.GetProperty("state").GetString() == "observed").Select(e => new Choice(e.GetProperty("observationId").GetString()!, e.GetProperty("role").GetString()!.Replace('_', ' '))).ToArray();
        }
        else _frames.ItemsSource = Array.Empty<Choice>();
        if (terminal && !verified) lines.Add("The pending request stays saved for review. Checking status or reopening this window never repeats Save or resumes input.");
        _status.Text = string.Join("\n\n", lines); _frames.SelectedIndex = _frames.Items.Count > 0 ? 0 : -1; _preview.Source = null;
    }
    private async Task ViewAsync()
    {
        if (_shownId is null || !_terminal || _frames.SelectedItem is not Choice frame) return;
        var response = await _api.SendAsync($"/api/farm/draft-runs/{_shownId}/frames/{frame.Id}");
        using var bytes = new MemoryStream(Convert.FromBase64String(response.GetProperty("frame").GetString()!));
        var bitmap = new BitmapImage(); bitmap.BeginInit(); bitmap.CacheOption = BitmapCacheOption.OnLoad; bitmap.StreamSource = bytes; bitmap.EndInit(); bitmap.Freeze(); _preview.Source = bitmap;
    }
}
