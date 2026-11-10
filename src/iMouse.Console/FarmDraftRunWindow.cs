using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace IMouse2;

internal sealed record DraftRunBookmark(string Id, string StoreId, string DraftId, int Revision, string? ImportedFrom = null);

/// <summary>The draft a creation window makes: an Instagram carousel from a saved carousel revision, or one
/// app draft from one saved video copy.</summary>
internal enum DraftRunKind { Carousel, Reel, TikTok, X, YouTube }

internal sealed partial class FarmDraftRunWindow : Window
{
    // Everything that differs between the five creation windows. Format is the saved copy's format
    // the backend must offer (none for a carousel); BindsAccount means the run binds whichever
    // account is signed in instead of a configured one.
    private sealed record Mode(string Name, string App, string Route, string Capability, string Bookmark, string? Format,
        string Title, string Heading, string Start, string Verified, string Description, bool BindsAccount = false);
    private static readonly Dictionary<DraftRunKind, Mode> Modes = new()
    {
        [DraftRunKind.Carousel] = new("carousel", "Instagram", "/api/farm/draft-creations", "draftCreation", "farm-pending-draft-creation.json", null,
            "Create a verified C24C draft", "Create a new verified phone draft", "Create and verify new draft on C24C", "NEW PHONE DRAFT CREATED AND VERIFIED",
            "C24C · Instagram @xs.halle.xo\nImports this saved revision into Photos, selects each slide in order, copies and pastes the exact caption, saves a draft and checks it after reopening. Start on the account profile. This replaces the phone clipboard. Three slides and a short visible caption are supported. Nothing is published or messaged."),
        [DraftRunKind.Reel] = new("Reel", "Instagram", "/api/farm/reel-creations", "reelCreation", "farm-pending-reel-creation.json", "ig_reel",
            "Create a verified C24C Reel draft", "Create a new verified Reel draft", "Create and verify Reel draft on C24C", "NEW REEL DRAFT CREATED AND VERIFIED",
            "C24C · Instagram @xs.halle.xo\nSafari downloads this saved video and Files saves it to Photos. Instagram then selects that exact video for a new Reel, the one-line caption is pasted and Save draft is pressed once. A separate check reopens the draft, plays it and keeps it in Reels drafts. Start on the account profile. The video stays in Photos and Safari Downloads, and the phone clipboard is replaced. Nothing is shared, published or messaged."),
        [DraftRunKind.TikTok] = new("TikTok", "TikTok", "/api/farm/tiktok-creations", "tiktokCreation", "farm-pending-tiktok-creation.json", "tt_video",
            "Create a verified C24C TikTok draft", "Create a new verified TikTok draft", "Create and verify TikTok draft on C24C", "NEW TIKTOK DRAFT CREATED AND VERIFIED",
            "C24C · TikTok @xs.halle.xo\nSafari downloads this saved video and Files saves it to Photos. TikTok then selects that exact video, removes a suggested sound if one is attached, pastes the one-line description and presses Drafts once. A separate check reopens the draft, requires it silent with the exact description and keeps it in Drafts. Start on the account’s TikTok profile. The video stays in Photos and Safari Downloads, and the phone clipboard is replaced. Nothing is posted, shared or messaged."),
        [DraftRunKind.X] = new("X", "X", "/api/farm/x-creations", "xCreation", "farm-pending-x-creation.json", "x_video",
            "Create a verified C24C X draft", "Create a new verified X draft", "Create and verify X draft on C24C", "NEW X DRAFT CREATED AND VERIFIED",
            "C24C · X · the account signed in first\nBefore any other input the run reads the signed-in handle from the X side menu and binds this draft to it; later screens and the separate check must show the same handle. Safari downloads this saved video and Files saves it to Photos. X then gets the one-line text by paste and the exact video from the photo picker, and Save to drafts is pressed once. A separate check reopens the draft with the exact text, plays it and keeps it in Drafts. Start on the X home timeline. The video stays in Photos and Safari Downloads, and the phone clipboard is replaced. Nothing is posted or messaged.", BindsAccount: true),
        [DraftRunKind.YouTube] = new("YouTube", "YouTube", "/api/farm/youtube-creations", "youtubeCreation", "farm-pending-youtube-creation.json", "yt_short",
            "Create a verified YouTube Short draft", "Create a new verified YouTube Short draft", "Create and verify YouTube draft", "NEW YOUTUBE DRAFT CREATED AND VERIFIED",
            "YouTube · the phone this backend is configured for · the channel signed in on it\nSafari downloads this saved video and Files saves it to Photos. YouTube then selects that exact video from its gallery and keeps its whole length. The run reads the channel shown on Add details and binds this draft to it before the title is entered; the separate check must show the same channel. The one-line title is pasted, checked without the text caret, and Save draft is pressed once. A separate check reopens the draft with the exact title, sees it play, keeps it with Save draft and finds it once in Drafts. Start on the YouTube home feed. A permission prompt stops the run with a one-time request. The video stays in Photos and Safari Downloads, and the phone clipboard is replaced. Nothing is uploaded, posted or messaged.", BindsAccount: true),
    };

    private readonly FarmApiClient _api;
    private readonly DraftRunKind _kind;
    private readonly Mode _mode;
    private readonly string _draftId, _bookmarkPath;
    private readonly string _route, _capability;
    private bool YouTube => _kind == DraftRunKind.YouTube;
    private readonly int _revision;
    private readonly Button _start = new() { Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _recover = new() { Content = "Check saved result", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _stop = new() { Content = "Stop check", Padding = new Thickness(12, 8, 12, 8) };
    private readonly Button _view = new() { Content = "View retained frame", Padding = new Thickness(12, 8, 12, 8) };
    private readonly ComboBox _history = new() { DisplayMemberPath = "Label", MinHeight = 32 };
    private readonly ComboBox _frames = new() { DisplayMemberPath = "Label", MinHeight = 32 };
    private readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 16, 0, 16) };
    private readonly TextBlock _subtitle = new() { Margin = new Thickness(0, 10, 0, 10), TextWrapping = TextWrapping.Wrap };
    private readonly Image _preview = new() { MaxHeight = 450, Stretch = Stretch.Uniform };
    private readonly DispatcherTimer _poll = new() { Interval = TimeSpan.FromSeconds(2) };
    private DraftRunBookmark? _pending;
    private string? _storeId, _shownId, _continueFrom;
    private bool _busy, _eligible, _terminal, _bookmarkBroken, _retryBeforeImport, _continueImported;
    private sealed record Choice(string Id, string Label) { public override string ToString() => Label; }
    // Read-only identity for other windows' headless checks; never a way to start input.
    internal string Route => _route; internal string Capability => _capability; internal string BookmarkPath => _bookmarkPath;
    internal string DraftId => _draftId;

    internal FarmDraftRunWindow(FarmApiClient api, string dataFolder, string draftId, int revision, string title, DraftRunKind kind)
    {
        _api = api; _draftId = draftId; _revision = revision; _kind = kind; _mode = Modes[kind];
        _route = _mode.Route; _capability = _mode.Capability;
        _bookmarkPath = Path.Combine(dataFolder, _mode.Bookmark);
        Title = _mode.Title; _start.Content = _mode.Start; Width = 840; Height = 820; MinWidth = 680; MinHeight = 600;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        SetResourceReference(BackgroundProperty, "SurfaceBrush"); SetResourceReference(ForegroundProperty, "TextBrush");
        var panel = new StackPanel { Margin = new Thickness(24) };
        panel.Children.Add(new TextBlock { Text = _mode.Heading, FontSize = 24, FontWeight = FontWeights.SemiBold });
        _subtitle.Text = $"{title} · saved revision {revision}"; panel.Children.Add(_subtitle);
        panel.Children.Add(new TextBlock { Text = _mode.Description, TextWrapping = TextWrapping.Wrap });
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
        _start.IsEnabled = _eligible && !_busy && (_pending is null || _retryBeforeImport || _continueImported) && !_bookmarkBroken;
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
                if (_pending is { } b && (!Guid.TryParse(b.Id, out _) || !Guid.TryParse(b.StoreId, out _) || !Guid.TryParse(b.DraftId, out _) || b.Revision < 1 || (b.ImportedFrom is not null && !Guid.TryParse(b.ImportedFrom, out _))))
                    throw new InvalidOperationException("Invalid saved draft request.");
            }
            catch { _bookmarkBroken = true; throw new InvalidOperationException("Saved request cannot be read. Preserve this candidate data folder for review; no new check can start."); }
        }
        var health = await _api.SendAsync("/health");
        var capability = health.GetProperty(_capability);
        if (capability.GetProperty("version").GetInt32() != 1) throw new InvalidOperationException("Use the matching draft candidate backend.");
        if (!DesignatedDevice(capability) || !DesignatedAccount(capability) || capability.GetProperty("publishing").GetBoolean() || capability.GetProperty("messaging").GetBoolean()) throw new InvalidOperationException(YouTube ? "Use the draft-only backend designated for the configured YouTube phone; the run binds the signed-in channel." : "Use the designated C24C account and draft-only backend.");
        if (_mode.Format is { } format && capability.GetProperty("format").GetString() != format) throw new InvalidOperationException($"This backend does not offer the {_mode.Name} draft candidate.");
        _storeId = capability.GetProperty("storeId").GetString();
        if (!Guid.TryParse(_storeId, out _)) throw new InvalidOperationException("Candidate storage identity is missing.");
        if (_pending is not null && _pending.StoreId != _storeId) throw new InvalidOperationException("This is a different candidate data store. Reopen the original backend to retrieve the pending result.");
        // A pending request belongs to its retained revision, even if the editor
        // has since changed or deleted that revision. Retrieve it before asking
        // whether today's editor contents are eligible for a new operation.
        if (_pending is not null) { await RecoverAsync(); return; }
        var eligible = (await _api.SendAsync($"{_route}/eligibility?draft_id={_draftId}&revision={_revision}")).GetProperty("eligibility");
        _eligible = capability.GetProperty("enabled").GetBoolean() && eligible.GetProperty("eligible").GetBoolean() && health.GetProperty("executionMode").GetString() == "live" && eligible.GetProperty("storeId").GetString() == _storeId;
        if (_eligible && eligible.TryGetProperty("continueImportedFrom", out var origin))
        {
            _continueFrom = origin.GetString(); _continueImported = Guid.TryParse(_continueFrom, out _);
            if (!_continueImported) throw new InvalidOperationException("Imported-media checkpoint is invalid.");
            _start.Content = "Continue · use imported images";
        }
        await HistoryAsync();
        _status.Text = eligible.GetProperty("reason").GetString() + "\n\n" + eligible.GetProperty("contentReason").GetString() + "\n\nThe interface integration still needs a fresh phone acceptance run. An offline pass is not a saved " + _mode.App + " draft.";
        if (YouTube) _status.Text = "Configured phone: " + PhoneLabel(capability) + "\n\n" + _status.Text;
    }
    // YouTube runs on the phone its backend is configured for (box slot 16 from 20 Oct), never a default; the other routes on C24C.
    private bool DesignatedDevice(JsonElement capability)
    {
        var device = capability.GetProperty("device");
        if (!YouTube) return device.ValueKind == JsonValueKind.String && device.GetString() == "C24C";
        return device.ValueKind == JsonValueKind.String && capability.TryGetProperty("phone", out var phone) && phone.ValueKind == JsonValueKind.Object
            && phone.TryGetProperty("board", out var board) && board.ValueKind == JsonValueKind.String && board.GetString() == device.GetString()
            && phone.TryGetProperty("receiver", out var receiver) && receiver.ValueKind == JsonValueKind.String && !string.IsNullOrEmpty(receiver.GetString());
    }
    private static string PhoneLabel(JsonElement capability)
    {
        var phone = capability.GetProperty("phone");
        string label = phone.GetProperty("receiver").GetString() + " (board " + phone.GetProperty("board").GetString();
        return label + (phone.TryGetProperty("slot", out var slot) && slot.ValueKind == JsonValueKind.Number ? ", box slot " + slot.GetInt32() : "") + ")";
    }
    // X and YouTube have no fixed handle: the backend must bind whichever account or channel is signed in, never a configured one.
    private bool DesignatedAccount(JsonElement capability)
    {
        var account = capability.GetProperty("account");
        if (_mode.BindsAccount) return account.ValueKind == JsonValueKind.Null && capability.TryGetProperty("accountPolicy", out var policy) && policy.GetString() == "first_signed_in";
        return account.ValueKind == JsonValueKind.String && account.GetString() == "xs.halle.xo";
    }
    private async Task HistoryAsync()
    {
        var response = await _api.SendAsync(_route + "?draft_id=" + _draftId);
        _history.ItemsSource = response.GetProperty("runs").EnumerateArray().Select(row => new Choice(row.GetProperty("id").GetString()!, $"Revision {row.GetProperty("revision").GetInt32()} · {row.GetProperty("id").GetString()![..8]}" )).ToArray();
    }
    private async Task StartAsync()
    {
        string? importedFrom = null;
        if (_retryBeforeImport || _continueImported)
        {
            var eligible = (await _api.SendAsync($"{_route}/eligibility?draft_id={_draftId}&revision={_revision}")).GetProperty("eligibility");
            if (!eligible.GetProperty("eligible").GetBoolean() || eligible.GetProperty("storeId").GetString() != _storeId) throw new InvalidOperationException("The earlier attempt cannot be safely replaced. Keep its saved result.");
            if (_continueImported)
            {
                importedFrom = eligible.TryGetProperty("continueImportedFrom", out var origin) ? origin.GetString() : null;
                if (!Guid.TryParse(importedFrom, out _) || importedFrom != (_pending?.Id ?? _continueFrom)) throw new InvalidOperationException("The imported-media checkpoint changed. Keep its saved result.");
            }
            else if (eligible.TryGetProperty("continueImportedFrom", out _)) throw new InvalidOperationException("This attempt now needs an explicit imported-media continuation.");
            Keep(null); _retryBeforeImport = _continueImported = false; _continueFrom = null;
        }
        if (!_eligible || _pending is not null || _bookmarkBroken || _storeId is null) throw new InvalidOperationException("Resolve the existing request first.");
        Keep(new(Guid.NewGuid().ToString(), _storeId, _draftId, _revision, importedFrom));
        _terminal = false; _shownId = null; _preview.Source = null; Buttons(); _poll.Start();
        // Keep every ambiguous response until status is reconciled. A timeout or
        // restart must never turn the same intent into a different request ID.
        var intent = new Dictionary<string, object> { ["id"] = _pending!.Id, ["draft_id"] = _draftId, ["revision"] = _revision, ["store_id"] = _storeId };
        if (importedFrom is not null) intent["continue_imported_from"] = importedFrom;
        var response = await _api.SendAsync(_route, intent);
        Apply(response.GetProperty("run"), _pending.Id); await HistoryAsync();
    }
    private async Task RecoverAsync()
    {
        if (_pending is null || _pending.StoreId != _storeId) return;
        await ShowAsync(_pending.Id); if (!_terminal) _poll.Start();
    }
    private async Task ShowAsync(string id) => Apply((await _api.SendAsync(_route + "/" + id)).GetProperty("run"), id);
    private async Task StopAsync()
    {
        if (_pending is null || _pending.StoreId != _storeId || _terminal) return;
        try
        {
            await _api.SendAsync(_route + "/" + _pending.Id + "/cancel", new { store_id = _storeId });
            _status.Text = "Stop requested. Waiting for the saved result and lease cleanup; no actions will resume automatically.";
        }
        catch (Exception ex) { _status.Text = "Stop is unconfirmed: " + ex.Message + ". The original request is kept for review."; }
    }
    private void Apply(JsonElement value, string expectedId)
    {
        var request = value.GetProperty("request");
        if (value.GetProperty("id").GetString() != expectedId || value.GetProperty("storeId").GetString() != _storeId || value.GetProperty("publishing").GetBoolean() || value.GetProperty("messaging").GetBoolean() || value.GetProperty("automaticResume").GetBoolean()
            || (_pending is { } b && (request.GetProperty("draft_id").GetString() != b.DraftId || request.GetProperty("revision").GetInt32() != b.Revision || (request.TryGetProperty("continue_imported_from", out var origin) ? origin.GetString() : null) != b.ImportedFrom))) throw new InvalidOperationException("Result does not match the saved request and candidate data store.");
        bool terminal = value.GetProperty("terminal").GetBoolean(), verified = value.GetProperty("savedDraftVerified").GetBoolean();
        string state = value.GetProperty("state").GetString()!, cleanup = value.GetProperty("cleanup").GetString()!;
        var workflow = value.GetProperty("workflow");
        if (verified && (!terminal || state != "verified" || cleanup != "confirmed" || workflow.ValueKind != JsonValueKind.Object || workflow.GetProperty("source").GetString() != "candidate_phone_workflow")) throw new InvalidOperationException("The result lacks confirmed phone evidence and cleanup.");
        if (verified && workflow.GetProperty("actions").EnumerateArray().Any(a => a.GetProperty("state").GetString() != "answered")) throw new InvalidOperationException("An uncertain phone action cannot be presented as a verified draft.");
        if (verified && (!workflow.GetProperty("createdDraftVerified").GetBoolean() || !workflow.GetProperty("mediaDelivery").GetProperty("stopped").GetBoolean())) throw new InvalidOperationException("New draft creation lacks confirmed import, reopen verification or media-service cleanup.");
        string? boundAccount = _mode.BindsAccount && workflow.ValueKind == JsonValueKind.Object && workflow.TryGetProperty("account", out var bound) && bound.ValueKind == JsonValueKind.String ? bound.GetString() : null;
        if (verified && _mode.BindsAccount && (string.IsNullOrEmpty(boundAccount) || !workflow.TryGetProperty("verification", out var check) || check.ValueKind != JsonValueKind.Object
            || !check.TryGetProperty("account", out var checkedAccount) || checkedAccount.ValueKind != JsonValueKind.String || checkedAccount.GetString() != boundAccount)) throw new InvalidOperationException(YouTube ? "A verified YouTube draft must be checked on the channel bound by creation." : "A verified X draft must be checked on the account bound by creation.");
        _shownId = expectedId; _terminal = terminal; if (terminal) _poll.Stop();
        _retryBeforeImport = terminal && !verified && value.TryGetProperty("retryBeforeImportAllowed", out var retry) && retry.GetBoolean()
            && request.GetProperty("draft_id").GetString() == _draftId && request.GetProperty("revision").GetInt32() == _revision;
        _continueImported = terminal && !verified && value.TryGetProperty("continueImportedAllowed", out var reuse) && reuse.GetBoolean()
            && request.GetProperty("draft_id").GetString() == _draftId && request.GetProperty("revision").GetInt32() == _revision;
        _continueFrom = _continueImported ? expectedId : null;
        if (_retryBeforeImport || _continueImported) _eligible = true;
        _start.Content = _continueImported ? "Continue · use imported images" : _retryBeforeImport ? "Start new attempt · no media imported" : _mode.Start;
        if (verified && _pending is not null) Keep(null);
        if (verified) _eligible = false;
        var lines = new List<string> { verified ? _mode.Verified : terminal ? "STOPPED · REVIEW REQUIRED" : "CHECK IN PROGRESS", value.GetProperty("reason").GetString()!, "Lease cleanup: " + cleanup.Replace('_', ' '), "Nothing was published or messaged. A saved draft check does not prove app-restart persistence." };
        if (boundAccount is not null) lines.Add((YouTube ? "YouTube channel" : "X account") + " bound by this run: @" + boundAccount + (verified ? " (the separate check saw the same handle)." : "."));
        if (value.GetProperty("draftChangedSinceRun").GetBoolean()) lines.Add("This evidence belongs to an older saved revision.");
        if (workflow.ValueKind == JsonValueKind.Object)
        {
            foreach (var action in workflow.GetProperty("actions").EnumerateArray()) lines.Add(action.GetProperty("label").GetString()!.Replace('-', ' ') + ": " + action.GetProperty("state").GetString()!.Replace('_', ' '));
            _frames.ItemsSource = workflow.GetProperty("observations").EnumerateArray().Where(e => e.GetProperty("state").GetString() == "observed").Select(e => new Choice(e.GetProperty("observationId").GetString()!, e.GetProperty("role").GetString()!.Replace('_', ' '))).ToArray();
        }
        else _frames.ItemsSource = Array.Empty<Choice>();
        if (terminal && !verified) lines.Add("The pending request stays saved for review. Checking status or reopening this window never repeats Save or resumes input.");
        if (_continueImported) lines.Add("A new explicit continuation can reuse the confirmed Photos imports. It rechecks the account and media; it never repeats Photos saves or resumes a prior editor.");
        _status.Text = string.Join("\n\n", lines); _frames.SelectedIndex = _frames.Items.Count > 0 ? 0 : -1; _preview.Source = null;
    }
    private async Task ViewAsync()
    {
        if (_shownId is null || !_terminal || _frames.SelectedItem is not Choice frame) return;
        var response = await _api.SendAsync($"{_route}/{_shownId}/frames/{frame.Id}");
        using var bytes = new MemoryStream(Convert.FromBase64String(response.GetProperty("frame").GetString()!));
        var bitmap = new BitmapImage(); bitmap.BeginInit(); bitmap.CacheOption = BitmapCacheOption.OnLoad; bitmap.StreamSource = bytes; bitmap.EndInit(); bitmap.Freeze(); _preview.Source = bitmap;
    }
}
