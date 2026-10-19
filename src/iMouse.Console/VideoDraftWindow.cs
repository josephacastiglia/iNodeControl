using System.Text.Json;
using System.Windows;
using System.Windows.Controls;

namespace IMouse2;

internal sealed partial class VideoDraftWindow : Window
{
    private readonly FarmApiClient _api;
    internal sealed record Batch(string Generation, string ManifestSha256);
    private readonly Batch? _batch;
    private readonly ComboBox _sources = new() { DisplayMemberPath = "Name", MinHeight = 32 };
    private readonly ComboBox _saved = new() { DisplayMemberPath = "Name", MinHeight = 32 };
    private readonly ComboBox _format = new() { MinHeight = 32, ItemsSource = new[] { "TikTok video", "X video", "YouTube Short", "Instagram Reel" }, SelectedIndex = 0 };
    private readonly TextBox _title = new() { Text = "Reviewed video draft" };
    private readonly TextBox _caption = new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 95 };
    private readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 8) };
    private readonly Button _prepare = new() { Content = "Prepare video draft", Padding = new Thickness(14, 8, 14, 8) };
    private readonly Button _transfer = new() { Content = "Transfer to C24C…", Padding = new Thickness(14, 8, 14, 8), IsEnabled = false };
    private readonly Button _reel = new() { Content = "Create Reel draft on C24C…", Padding = new Thickness(14, 8, 14, 8), IsEnabled = false };
    private readonly string? _dataFolder;
    private JsonElement? _draft;
    private string? _pending;
    private object? _pendingRequest;
    private bool _busy, _loadingSaved;
    private sealed record Source(string Name, string Sha256, string? Generation = null, string? ManifestSha256 = null) { public override string ToString() => Name; }
    private sealed record Saved(string Name, JsonElement Draft) { public override string ToString() => Name; }

    internal VideoDraftWindow(FarmApiClient api, Batch? batch = null, string? dataFolder = null)
    {
        _api = api; _batch = batch; _dataFolder = dataFolder; Title = "Video drafts for C24C"; Width = 650; Height = 740; MinWidth = 540; MinHeight = 600;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        SetResourceReference(BackgroundProperty, "SurfaceBrush"); SetResourceReference(ForegroundProperty, "TextBrush");
        var panel = new StackPanel { Margin = new Thickness(24) };
        panel.Children.Add(new TextBlock { Text = "Prepare a video draft", FontSize = 24, FontWeight = FontWeights.SemiBold });
        panel.Children.Add(new TextBlock { Text = "Use a generated C24C video. Preparation creates a separate H.264 copy and preserves the entire frame. Nothing is sent to the phone until you explicitly start a media transfer.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 10, 0, 8) });
        foreach (var (label, control) in new (string, FrameworkElement)[] { ("Saved copies (select to transfer)", _saved), ("Generated video", _sources), ("Destination", _format), ("Draft name", _title), ("Caption / title (280 characters; YouTube 100)", _caption) })
        {
            panel.Children.Add(new TextBlock { Text = label, Margin = new Thickness(0, 12, 0, 4) });
            panel.Children.Add(control);
        }
        panel.Children.Add(new TextBlock { Text = "Candidate limits: 64 MiB source, at most 45 seconds, 720×1280 output. No trimming; nonvertical media receives margins. Small sources may look soft. Review video and sound in Safari and the app.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 8) });
        var buttons = new WrapPanel(); buttons.Children.Add(_prepare); buttons.Children.Add(_transfer);
        if (_dataFolder is not null) buttons.Children.Add(_reel);
        panel.Children.Add(buttons);
        panel.Children.Add(_status); Content = new ScrollViewer { Content = panel, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Loaded += async (_, _) => await RunAsync(InitializeAsync);
        _prepare.Click += async (_, _) => await RunAsync(PrepareAsync);
        _saved.SelectionChanged += (_, _) =>
        {
            if (_busy || _pending is not null || _saved.SelectedItem is not Saved saved) return;
            _loadingSaved = true;
            try
            {
                _sources.SelectedIndex = -1;
                _title.Text = saved.Draft.GetProperty("title").GetString()!;
                _caption.Text = saved.Draft.GetProperty("caption").GetString()!;
                _format.SelectedIndex = Array.IndexOf(new[] { "tt_video", "x_video", "yt_short", "ig_reel" }, saved.Draft.GetProperty("format").GetString());
            }
            finally { _loadingSaved = false; }
            _draft = saved.Draft;
            _status.Text = "Selected saved copy: " + saved.Name + ". Its saved caption and destination are shown above. Choose a generated source to prepare another copy.";
            _transfer.IsEnabled = true; _reel.IsEnabled = IsReel(_draft);
        };
        _title.TextChanged += (_, _) => InvalidatePrepared();
        _caption.TextChanged += (_, _) => InvalidatePrepared();
        _format.SelectionChanged += (_, _) => InvalidatePrepared();
        _sources.SelectionChanged += (_, _) => InvalidatePrepared();
        _transfer.Click += (_, _) => { if (_draft is { } draft) new CarouselTransferWindow(_api, draft) { Owner = this }.ShowDialog(); };
        // Opens the bounded candidate window. Its own capability and eligibility
        // checks decide whether Start is available; opening it sends no input.
        _reel.Click += (_, _) => { if (ReelWindow() is { } window) { window.Owner = this; window.ShowDialog(); } };
        Closing += (_, e) => { if (_busy) { e.Cancel = true; _status.Text = "Wait for the current preparation to finish; no phone input is being sent."; } };
    }

    private async Task InitializeAsync()
    {
        await RefreshSavedAsync();
        string path = "/api/farm/video-sources" + (_batch is null ? "" : "?generation=" + Uri.EscapeDataString(_batch.Generation) + "&manifest_sha256=" + Uri.EscapeDataString(_batch.ManifestSha256));
        var response = await _api.SendAsync(path);
        var rows = response.GetProperty("sources").EnumerateArray().ToArray();
        var sources = rows.Select(s => new Source(s.GetProperty("name").GetString()!, s.GetProperty("sha256").GetString()!,
            s.TryGetProperty("sourceGeneration", out var generation) && generation.ValueKind == JsonValueKind.String ? generation.GetString() : null,
            s.TryGetProperty("manifestSha256", out var checksum) ? checksum.GetString() : null)).ToArray();
        if (_batch is not null && sources.Any(s => s.Generation != _batch.Generation || s.ManifestSha256 != _batch.ManifestSha256))
            throw new InvalidOperationException("The backend returned another batch. No video was selected.");
        _sources.ItemsSource = sources; _sources.SelectedIndex = sources.Length > 0 ? 0 : -1;
        if (_batch is not null && rows.Length > 0 && rows[0].TryGetProperty("caption", out var caption)) _caption.Text = caption.GetString() ?? "";
        _status.Text = sources.Length == 0 ? "No staged C24C video in this batch. No newer batch was substituted."
            : (_batch is null ? "" : "Opened this preparation’s original video and caption. ") + "Choose the destination, review the full caption, then prepare a saved copy.";
    }

    private async Task RunAsync(Func<Task> action)
    {
        if (_busy) return;
        _busy = true; _prepare.IsEnabled = _transfer.IsEnabled = false;
        _saved.IsEnabled = _sources.IsEnabled = _format.IsEnabled = _title.IsEnabled = _caption.IsEnabled = false;
        try { await action(); }
        catch (Exception ex) { _status.Text = ex.Message + (_pending is null ? "" : " Use Check saved draft to recover it. If absent, preparation retries with the same ID and original content; no transfer has started."); }
        finally
        {
            _busy = false; _prepare.IsEnabled = true; _transfer.IsEnabled = _draft is not null; _reel.IsEnabled = IsReel(_draft);
            _sources.IsEnabled = _format.IsEnabled = _title.IsEnabled = _caption.IsEnabled = _pending is null;
            _saved.IsEnabled = _pending is null;
            _prepare.Content = _pending is null ? "Prepare video draft" : "Check saved draft";
        }
    }

    private async Task PrepareAsync()
    {
        JsonElement response;
        if (_pending is not null)
        {
            try { response = await _api.SendAsync("/api/farm/video-drafts/" + _pending); }
            catch (FarmRequestRejectedException ex) when (ex.StatusCode == 404 && _pendingRequest is not null)
            {
                // The request may never have arrived. The server serializes creation and
                // deduplicates the original ID, including when a first request is still running.
                response = await SubmitPendingAsync();
            }
        }
        else
        {
            if (_sources.SelectedItem is not Source source) throw new InvalidOperationException("Create and select a C24C video first.");
            _draft = null; _pending = Guid.NewGuid().ToString();
            _status.Text = "Preparing and decoding the complete video. This can take a moment…";
            _pendingRequest = new { id = _pending, device_id = "C24C", name = source.Name, sha256 = source.Sha256,
                format = new[] { "tt_video", "x_video", "yt_short", "ig_reel" }[_format.SelectedIndex], title = _title.Text, caption = _caption.Text,
                source_generation = source.Generation, manifest_sha256 = source.Generation is null ? null : source.ManifestSha256 };
            response = await SubmitPendingAsync();
        }
        _draft = response.GetProperty("draft").Clone(); _pending = null; _pendingRequest = null;
        await RefreshSavedAsync();
        var info = _draft.Value.GetProperty("video");
        _status.Text = $"Saved on this PC: {info.GetProperty("seconds").GetDouble():0.0}s, H.264, 720×1280. "
            + (info.GetProperty("fitted").GetBoolean() ? "Margins preserve the whole source frame. " : "")
            + (info.GetProperty("upscaled").GetBoolean() ? "Source was enlarged; check sharpness. " : "")
            + "Transfer uses this saved copy. An app draft has not yet been verified.";
    }

    private async Task<JsonElement> SubmitPendingAsync()
    {
        try { return await _api.SendAsync("/api/farm/video-drafts", _pendingRequest); }
        catch (FarmRequestRejectedException ex) when (ex.StatusCode is >= 400 and < 500 && ex.StatusCode != 409)
        { _pending = null; _pendingRequest = null; throw; }
    }

    private void InvalidatePrepared()
    {
        if (_busy || _loadingSaved || _pending is not null) return;
        _draft = null; _transfer.IsEnabled = _reel.IsEnabled = false; _saved.SelectedIndex = -1;
    }

    private bool IsReel(JsonElement? draft) => _dataFolder is not null && draft is { } value && !_busy
        && value.TryGetProperty("format", out var format) && format.GetString() == "ig_reel"
        && value.TryGetProperty("id", out var id) && Guid.TryParse(id.GetString(), out _)
        && value.TryGetProperty("revision", out var revision) && revision.ValueKind == JsonValueKind.Number;

    private FarmDraftRunWindow? ReelWindow()
    {
        if (!IsReel(_draft) || _draft is not { } draft) return null;
        return new FarmDraftRunWindow(_api, _dataFolder!, draft.GetProperty("id").GetString()!, draft.GetProperty("revision").GetInt32(),
            draft.GetProperty("title").GetString() ?? "Reel draft", createNew: true, reel: true);
    }

    private async Task RefreshSavedAsync()
    {
        var response = await _api.SendAsync("/api/farm/video-drafts");
        _saved.ItemsSource = response.GetProperty("drafts").EnumerateArray()
            .Select(d => new Saved(d.GetProperty("title").GetString() + " · " + d.GetProperty("platform").GetString(), d.Clone())).ToArray();
    }
}
