using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace IMouse2;

internal sealed partial class FarmDraftRehearsalWindow : Window
{
    private readonly FarmApiClient _api;
    private readonly string _draftId;
    private readonly int _revision;
    private readonly ComboBox _scenario = new() { DisplayMemberPath = "Label", MinHeight = 32 };
    private readonly ComboBox _history = new() { DisplayMemberPath = "Label", MinHeight = 32 };
    private readonly ComboBox _frames = new() { DisplayMemberPath = "Label", MinHeight = 32 };
    private readonly Button _start = new() { Content = "Run offline check", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _recover = new() { Content = "Check saved result", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _cancel = new() { Content = "Stop rehearsal", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _view = new() { Content = "View simulated frame", Padding = new Thickness(12, 8, 12, 8) };
    private readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 12) };
    private readonly Image _preview = new() { MaxHeight = 400, Stretch = Stretch.Uniform };
    private bool _busy, _ready;
    private string? _pending, _saved;
    private sealed record Choice(string Id, string Label)
    {
        public override string ToString() => Label;
    }

    internal FarmDraftRehearsalWindow(FarmApiClient api, string draftId, int revision, string title)
    {
        _api = api; _draftId = draftId; _revision = revision;
        Title = "Offline draft recovery checks"; Width = 850; Height = 800; MinWidth = 650; MinHeight = 550;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        SetResourceReference(BackgroundProperty, "SurfaceBrush"); SetResourceReference(ForegroundProperty, "TextBrush");
        var panel = new StackPanel { Margin = new Thickness(24) };
        panel.Children.Add(new TextBlock { Text = "Check draft save and recovery", FontSize = 24, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = $"{title} · saved revision {revision}", Margin = new Thickness(0, 8, 0, 8), TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = "Uses your saved slides and caption in a simulated app. Checks save → library → reopen, every slide and account boundaries. No phone connection is used and nothing is saved in Instagram. These checks do not establish live automation readiness.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 16) });
        _scenario.ItemsSource = new Choice[] { new("normal", "Complete save and reopen"), new("save_reply_lost", "Save happens, but its reply is lost"),
            new("reopen_reply_lost", "Reopen happens, but its reply is lost"), new("permission_prompt", "Permission dialog interrupts saving"),
            new("account_changed", "Account changes before the final check"), new("stale_frame", "Save screen is stale"),
            new("wrong_slide", "Reopened slide differs"), new("wrong_caption", "Reopened caption differs"), new("duplicate_cover", "Two library covers match") };
        _scenario.SelectedIndex = 0; panel.Children.Add(_scenario);
        var buttons = new WrapPanel { Margin = new Thickness(0, 12, 0, 12) };
        buttons.Children.Add(_start); buttons.Children.Add(_recover); buttons.Children.Add(_cancel); panel.Children.Add(buttons);
        panel.Children.Add(new TextBlock { Text = "Saved offline checks", FontWeight = FontWeights.SemiBold }); panel.Children.Add(_history);
        panel.Children.Add(_status); panel.Children.Add(_frames); panel.Children.Add(_view); panel.Children.Add(_preview);
        Content = new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Loaded += async (_, _) => await RunAsync(InitializeAsync);
        _start.Click += async (_, _) => await RunAsync(StartAsync);
        _recover.Click += async (_, _) => await RunAsync(RecoverAsync);
        _cancel.Click += async (_, _) => await CancelAsync();
        _view.Click += async (_, _) => await RunAsync(ViewAsync);
        _history.SelectionChanged += async (_, _) => { if (!_busy && _pending is null && _history.SelectedItem is Choice row) await RunAsync(() => ShowAsync(row.Id)); };
        Closing += (_, e) => { if (_busy) { e.Cancel = true; _status.Text = "Stop the rehearsal or wait for its response. No phone is being controlled."; } };
        Buttons();
    }

    private static string Label(string value) => value switch
    {
        "simulation_passed" => "Simulation passed", "review_required" => "Needs review",
        "outcome_unknown" => "Outcome unknown", "answered" => "Acknowledged",
        "not_sent" => "Not sent", "not_needed" => "Not needed",
        _ => value.Length == 0 ? value : char.ToUpperInvariant(value[0]) + value[1..].Replace('_', ' ')
    };
    private string ScenarioLabel(string id) => _scenario.Items.Cast<Choice>().FirstOrDefault(c => c.Id == id)?.Label ?? Label(id);

    private void Buttons()
    {
        _start.IsEnabled = _scenario.IsEnabled = _ready && !_busy && _pending is null;
        _history.IsEnabled = !_busy && _pending is null;
        _recover.IsEnabled = !_busy && _pending is not null;
        _cancel.IsEnabled = _pending is not null;
        _frames.IsEnabled = _view.IsEnabled = !_busy && _saved is not null;
    }
    private async Task RunAsync(Func<Task> action)
    {
        if (_busy) return; _busy = true; Buttons();
        try { await action(); }
        catch (Exception ex) { _status.Text = ex.Message + (_pending is null ? " No phone action was sent." : " Check the saved result. Do not start another attempt while this result is unknown."); }
        finally { _busy = false; Buttons(); }
    }
    private async Task InitializeAsync()
    {
        var health = await _api.SendAsync("/health");
        _ready = health.TryGetProperty("draftRehearsalVersion", out var version) && version.GetInt32() == 1
            && health.TryGetProperty("executionMode", out var mode) && mode.GetString() == "simulate";
        await HistoryAsync();
        _status.Text = _ready ? "Choose a scenario. An interrupted check should stop for review; that is the expected outcome for a fault scenario." : "Start the matching simulation candidate backend to run offline checks. Saved results remain available.";
    }
    private async Task HistoryAsync()
    {
        var response = await _api.SendAsync("/api/farm/draft-rehearsals?draft_id=" + Uri.EscapeDataString(_draftId));
        _history.ItemsSource = response.GetProperty("rehearsals").EnumerateArray().Select(v => new Choice(v.GetProperty("id").GetString()!,
            $"{ScenarioLabel(v.GetProperty("request").GetProperty("scenario").GetString()!)} · {Label(v.GetProperty("state").GetString()!)} · revision {v.GetProperty("request").GetProperty("revision").GetInt32()}" )).ToArray();
    }
    private async Task StartAsync()
    {
        if (!_ready || _pending is not null || _scenario.SelectedItem is not Choice scenario) throw new InvalidOperationException("Check the existing result before starting.");
        _pending = Guid.NewGuid().ToString(); _saved = null; _preview.Source = null; Buttons();
        JsonElement response;
        try { response = await _api.SendAsync("/api/farm/draft-rehearsals", new { id = _pending, draft_id = _draftId, revision = _revision, scenario = scenario.Id }); }
        catch (FarmRequestRejectedException ex) when (ex.StatusCode is >= 400 and < 500 && ex.StatusCode != 409) { _pending = null; throw; }
        Apply(response.GetProperty("rehearsal")); await HistoryAsync();
    }
    private async Task ShowAsync(string id) => Apply((await _api.SendAsync("/api/farm/draft-rehearsals/" + id)).GetProperty("rehearsal"));
    private async Task RecoverAsync()
    {
        if (_pending is null) return;
        // Even a 404 keeps the request ID: absence is not permission to replay a mutating workflow.
        await ShowAsync(_pending); await HistoryAsync();
    }
    private async Task CancelAsync()
    {
        if (_pending is null) return;
        try { await _api.SendAsync("/api/farm/draft-rehearsals/" + _pending + "/cancel", new { }); _status.Text = "Stop requested. Check the saved result for the final state and cleanup."; }
        catch (Exception ex) { _status.Text = "Stop was not confirmed: " + ex.Message + ". Check the saved result."; }
    }
    private void Apply(JsonElement value)
    {
        if (value.GetProperty("source").GetString() != "simulation" || value.GetProperty("savedDraftVerified").GetBoolean()
            || value.GetProperty("automaticInputAllowed").GetBoolean() || value.GetProperty("accountContinuityProven").GetBoolean())
            throw new InvalidOperationException("Unexpected live acceptance claim in an offline result.");
        _saved = value.GetProperty("id").GetString(); string state = value.GetProperty("state").GetString()!;
        if (state != "running") _pending = null;
        var lines = new List<string> { "OFFLINE SIMULATION · " + Label(state), value.GetProperty("reason").GetString()!, "Cleanup: " + Label(value.GetProperty("cleanup").GetString()!),
            "No phone draft was saved or verified. Live publishing and messaging remain disabled." };
        if (value.GetProperty("draftChangedSinceRun").GetBoolean()) lines.Add("This result belongs to an older revision of the local draft.");
        if (value.TryGetProperty("reconciliation", out var reconciliation)) lines.Add("Read-only recovery: " + (reconciliation.GetProperty("status").GetString() == "matching_screen_after_unknown_reply" ? "the expected screen matched after the reply was lost" : "the outcome is still unresolved") + ". The uncertain action was not replayed.");
        foreach (var action in value.GetProperty("actions").EnumerateArray()) lines.Add(Label(action.GetProperty("kind").GetString()!) + ": " + Label(action.GetProperty("state").GetString()!));
        lines.Add(value.GetProperty("recovery").GetString()!);
        _status.Text = string.Join("\n\n", lines);
        _frames.ItemsSource = value.GetProperty("evidenceManifest").EnumerateObject().Select(p => new Choice(p.Name, Label(value.GetProperty("captureRoles").GetProperty(p.Name).GetString()!))).ToArray();
        _frames.SelectedIndex = _frames.Items.Count > 0 ? 0 : -1; _preview.Source = null;
    }
    private async Task ViewAsync()
    {
        if (_saved is null || _frames.SelectedItem is not Choice frame) return;
        _preview.Source = null;
        var response = await _api.SendAsync($"/api/farm/draft-rehearsals/{_saved}/frames/{frame.Id}");
        using var bytes = new MemoryStream(Convert.FromBase64String(response.GetProperty("frame").GetString()!));
        var image = new BitmapImage(); image.BeginInit(); image.CacheOption = BitmapCacheOption.OnLoad; image.StreamSource = bytes; image.EndInit(); image.Freeze(); _preview.Source = image;
    }
}
