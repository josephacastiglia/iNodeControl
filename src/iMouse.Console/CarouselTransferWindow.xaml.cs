using System.Text.Json;
using System.Windows;
using System.Windows.Threading;

namespace IMouse2;

public partial class CarouselTransferWindow : Window
{
    private readonly FarmApiClient _api;
    private readonly CarouselDraft _draft;
    private string _kind = "carousel", _platform = "Instagram";
    private string? _sessionId;
    private bool _active, _busy, _known, _closing;
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromSeconds(5) };

    internal CarouselTransferWindow(FarmApiClient api, CarouselDraft draft)
    {
        _api = api;
        _draft = draft;
        InitializeComponent();
        DraftText.Text = $"{draft.Title} · saved revision {draft.Revision} · {draft.Slides.Length} slides";
        Loaded += async (_, _) => { await RunAsync(RefreshAsync); _timer.Start(); };
        _timer.Tick += async (_, _) => { if (_active) await RunAsync(RefreshAsync); };
        Closing += async (_, e) =>
        {
            if (_closing) return;
            if (_busy) { e.Cancel = true; StatusText.Text = "Wait for the current request; the transfer also has an expiry timer."; return; }
            _timer.Stop();
            if (!_active && _known) return;
            e.Cancel = true;
            await RunAsync(async () =>
            {
                await RefreshAsync();
                if (_active) await StopAsync();
            });
            // If the backend cannot be reached, expiry still bounds the exposure.
            if (_active || !_known)
                MessageBox.Show(this, "Could not confirm the link closed. It expires at its original deadline (at most 20 minutes after starting). Reopen transfer controls and Check status when the backend is available.", "Transfer status unknown");
            _closing = true;
            Close();
        };
    }

    internal CarouselTransferWindow(FarmApiClient api, JsonElement video) : this(api, new CarouselDraft
    {
        Id = video.GetProperty("id").GetString()!, Revision = video.GetProperty("revision").GetInt32(),
        Title = video.GetProperty("title").GetString()!, Slides = []
    })
    {
        _kind = "video"; _platform = video.GetProperty("platform").GetString()!;
        Title = "Transfer video draft to C24C";
        DraftText.Text = $"{_draft.Title} · {_platform} · H.264 720×1280 · saved revision {_draft.Revision}";
        AccountLabel.Text = _platform + " account";
        AccountBox.ToolTip = "Verify this signed-in account in " + _platform + " before saving a draft.";
        PhoneInstructions.Text = "1. Open the link in Safari. Hold Open video to save → Download Linked File. Open Safari Downloads → imouse-draft → Share → Save Video. Verify it in Photos.\n\n2. Confirm the account in " + _platform + ", select the video and paste the reviewed caption.\n\n3. Check the frame, duration, sound and text. Remove unwanted suggested sounds. Choose Save draft. Do not tap Post, Share or Upload in the app.\n\n4. Reopen and play the draft, verify its caption, then stop this transfer. Permission prompts may require a physical tap.";
        DeliveryText.Text = "Video requests do not confirm a Photos save or an app draft.";
    }

    private void Buttons()
    {
        Setup.IsEnabled = !_busy && _known && !_active;
        StartButton.IsEnabled = !_busy && _known && !_active;
        StopButton.IsEnabled = !_busy && _active;
        CheckButton.IsEnabled = !_busy;
    }

    private async Task RunAsync(Func<Task> action)
    {
        if (_busy) return;
        _busy = true;
        Buttons();
        try { await action(); }
        catch (Exception ex)
        {
            _known = false;
            UrlBox.Text = "";
            StatusText.Text = ex.Message + " Transfer outcome is unknown. Check status before starting again.";
        }
        finally { _busy = false; Buttons(); }
    }

    private void Apply(JsonElement response)
    {
        var item = response.GetProperty("transfer");
        _known = true;
        if (item.ValueKind == JsonValueKind.Null)
        {
            _sessionId = null; _active = false;
            StatusText.Text = "No transfer open. Verify the addresses and intended " + _platform + " account before starting.";
            UrlBox.Text = "";
            return;
        }
        _sessionId = item.GetProperty("id").GetString();
        string state = item.GetProperty("state").GetString()!;
        _active = state is "starting" or "serving" or "stopping";
        bool isVideo = item.TryGetProperty("kind", out var kind) && kind.GetString() == "video";
        bool thisRevision = item.GetProperty("draft_id").GetString() == _draft.Id && item.GetProperty("revision").GetInt32() == _draft.Revision && isVideo == (_kind == "video");
        if (_active)
        {
            BindBox.Text = item.GetProperty("bind").GetString();
            ClientBox.Text = item.GetProperty("client").GetString();
            AccountBox.Text = "@" + item.GetProperty("account").GetString();
        }
        UrlBox.Text = item.TryGetProperty("url", out var url) ? url.GetString() ?? "" : "";
        int remaining = item.GetProperty("secondsRemaining").GetInt32();
        string error = item.TryGetProperty("error", out var err) ? err.GetString() ?? "" : "";
        StatusText.Text = $"Transfer {state} · {remaining / 60}:{remaining % 60:00} remaining. " + error
            + (_active && !thisRevision ? " This is a different saved draft/revision. Stop it before sharing this revision." : "");
        int delivered = item.GetProperty("imagesDelivered").GetArrayLength();
        DeliveryText.Text = isVideo
            ? $"{item.GetProperty("videoRequests").GetInt32()} video requests (may be partial). Photos and app-draft saves are unverified. Nothing is published."
            : $"{delivered} / {item.GetProperty("slideCount").GetInt32()} images delivered over HTTP. Saves in Photos and Instagram are unverified. Nothing is published by this tool.";
        Buttons();
    }

    private async Task RefreshAsync() => Apply(await _api.SendAsync("/api/farm/transfers/current"));

    private async Task StartAsync()
    {
        // Current-session recovery prevents creating another listener after a lost response.
        await RefreshAsync();
        if (_active) return;
        _known = false;
        Apply(await _api.SendAsync("/api/farm/transfers", new
        {
            id = Guid.NewGuid().ToString(), draft_id = _draft.Id, revision = _draft.Revision,
            device_id = "C24C", bind = BindBox.Text.Trim(), client = ClientBox.Text.Trim(),
            account = AccountBox.Text.Trim(), port = 9916, minutes = 20, kind = _kind
        }));
    }

    private async Task StopAsync()
    {
        if (_sessionId is not null)
            Apply(await _api.SendAsync($"/api/farm/transfers/{_sessionId}/stop", new { }));
    }
    private async void Start_Click(object sender, RoutedEventArgs e) => await RunAsync(StartAsync);
    private async void Check_Click(object sender, RoutedEventArgs e) => await RunAsync(RefreshAsync);
    private async void Stop_Click(object sender, RoutedEventArgs e) => await RunAsync(StopAsync);
}
