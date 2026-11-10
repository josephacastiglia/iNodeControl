using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using System.Runtime.InteropServices;
using Microsoft.Win32;

namespace IMouse2;

public partial class MainWindow : Window
{
    private Func<string, ApiClient> _factory;
    private ApiClient? _api;
    private CancellationTokenSource _lifetime = new();
    private int _session;
    private int _refreshSession = -1;
    private bool _connected, _closing;
    private List<Device> _devices = [];
    private readonly ObservableCollection<string> _activity = [];
    private readonly DispatcherTimer _refreshTimer = new() { Interval = TimeSpan.FromSeconds(5) };
    private FrameBuffer? _frame;
    private string? _frameId;
    private DateTime _frameAt = DateTime.MinValue;
    private readonly LiveFrame _live = new();
    private readonly RateMeter _rate = new();
    private List<Board> _boards = [];
    private (string Id, int Session, int X, int Y, Point View, int W, int H)? _gesture;
    private string _lastPreviewError = "";
    private readonly string _dataPath;
    private readonly bool _mirrorLocal;
    private Device? Selected => DeviceList.SelectedItem as Device;
    private bool? _savedTrackPointer;

    // dataPath is for test modes and --data-dir: they must never load or overwrite the
    // operator's %APPDATA%\iMouse2, which every console build on this machine shares.
    public MainWindow(Func<string, ApiClient>? factory = null, string? dataPath = null)
    {
        _inputActions = new(context => CancelledHere(context.Connection, context.Control));
        _dataPath = dataPath ?? ResolveDataPath();
        _mirrorLocal = dataPath is null;
        _factory = factory ?? (address => new ApiClient(address));
        _presentNow = () => PresentPending(null, EventArgs.Empty);
        InitializeComponent();
        BuildIdentity.Text = ConsoleBuildInfo.Current.Label + " · Independent AirPlay";
        BuildIdentity.ToolTip = ConsoleBuildInfo.Current.Detail;
        RestoreFarmJob();
        ActivityList.ItemsSource = _activity;
        PhoneWall.ItemsSource = _wall;
        PhoneWall.DataContext = this;
        try
        {
            var file = Path.Combine(_dataPath, "settings.json");
            if (File.Exists(file))
            {
                using var d = JsonDocument.Parse(File.ReadAllText(file));
                AddressBox.Text = JsonValue.Text(d.RootElement, "address", AddressBox.Text);
                if (JsonValue.Text(d.RootElement, "theme") == "night") ApplyTheme(true);
                // Optional and absent by default, so hover tracking stays on unless a settings file
                // turns it off. A test data folder sets it false, so connecting sends no incidental
                // pointer moves and does not take control before the test starts.
                if (d.RootElement.TryGetProperty("trackPointer", out var track) && track.ValueKind is JsonValueKind.True or JsonValueKind.False)
                    TrackPointer.IsChecked = _savedTrackPointer = track.GetBoolean();
            }
        }
        catch { /* A damaged optional preferences file must not prevent startup. */ }
        // The mirror is 500x1080 and gets drawn into roughly a fifth of that area, so WPF
        // resamples every single frame. Its default filter is the expensive high-quality
        // one, which runs on the render thread and is a prime suspect for frames being
        // written but never composited. Bilinear is visually indistinguishable at this
        // scale and far cheaper.
        RenderOptions.SetBitmapScalingMode(PhoneImage, BitmapScalingMode.LowQuality);
        RenderOptions.SetEdgeMode(PhoneImage, EdgeMode.Aliased);
        _refreshTimer.Tick += async (_, _) =>
        {
            UpdatePreviewFreshness();
            UpdateWallFreshness();
            if (AutoPreview.IsChecked == true) UpdateFrameStatus();
            await RefreshDevicesAsync();
        };
        StateChanged += (_, _) => { SyncPumpTarget(); if (WindowState != WindowState.Minimized) StartPump(); };
        // Fit once the first real layout pass has happened; before that the viewport is zero.
        ContentRendered += (_, _) => { FitMaster(); UpdateWallWidth(); };
        Closing += (_, e) => { if (!_closeAllowed) { e.Cancel = true; _ = CloseSafelyAsync(showWarning: true); } };
        Closed += (_, _) => { _lifetime.Dispose(); if (_timerRaised) { try { timeEndPeriod(1); } catch { } _timerRaised = false; } };
        UpdateControls();
    }

    public async Task ConnectAsync()
    {
        if (_closing) return;
        ApiClient next;
        try { next = _factory(AddressBox.Text.Trim()); }
        catch (Exception ex) { Log(ex.Message, true); return; }
        DetachConnection();
        int session = _session;
        _pendingConnection = next;
        ConnectionStatus.Text = "Releasing previous input…";
        UpdateControls();
        await FinishConnectionCleanupAsync();
        if (_closing || session != _session || _pendingConnection != next) return;
        _pendingConnection = null;
        _lifetime.Dispose(); _lifetime = new();
        _api = next;
        next.InputNotice += message => Dispatcher.BeginInvoke(() =>
        {
            if (_closing || _api != next) return;
            if (!_controlCancellation.IsCancellationRequested) _pausedByNotice = _controlCancellation;
            CancelLocalInput(); InputStateText.Text = message; RefreshInputOwnershipUi();
        });
        // The release after a failure never resumes anything: the panel stays paused and only says
        // whether the kernel confirmed the button came up. A result overtaken by Stop, Resume or a
        // selection change is logged but leaves the panel to that newer state.
        next.InputCleaned += cleanup => Dispatcher.BeginInvoke(() =>
        {
            if (_closing || _api != next) return;
            Log(cleanup.Summary, !cleanup.Confirmed);
            if (cleanup.Current && !_controlReady) { InputStateText.Text = cleanup.PanelText; RefreshInputOwnershipUi(); }
        });
        _connected = false;
        ClearFrame("Connecting", "Loading devices from the iMouse service.");
        _devices.Clear(); DeviceList.ItemsSource = null;
        ConnectionStatus.Text = "Connecting…";
        _refreshTimer.Start(); StartPump();
        UpdateControls();
        await RefreshDevicesAsync(true);
        if (_connected && !_closing && session == _session && _api == next)
        {
            AddressBox.Text = next.Endpoint.GetLeftPart(UriPartial.Authority);
            try { SaveSettings(); }
            catch (Exception ex) { Log("Connected. Preferences could not be saved: " + ex.Message, true); }
        }
    }
    // %APPDATA%\iMouse2 survives a new build folder or a rollback. Local data/ is a mirror for launcher scripts.
    internal static string ResolveDataPath()
    {
        var local = Path.Combine(AppContext.BaseDirectory, "data");
        var root = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        if (root.Length == 0) return local;
        var appData = Path.Combine(root, "iMouse2");
        try
        {
            var persisted = Path.Combine(appData, "settings.json");
            if (!File.Exists(persisted))
            {
                var seed = Path.Combine(local, "settings.json");
                if (File.Exists(seed))
                {
                    Directory.CreateDirectory(appData);
                    try { File.Copy(seed, persisted); }
                    catch (IOException) when (File.Exists(persisted)) { }
                }
            }
            Directory.CreateDirectory(appData);
            return appData;
        }
        catch { return local; }
    }

    private void SaveSettings()
    {
        // trackPointer is written back only when the file named it, so a file without it is
        // rewritten exactly as before.
        var warning = SettingsPersistence.Save(_dataPath,
            _mirrorLocal && !InstallLayout.Installed ? Path.Combine(AppContext.BaseDirectory, "data") : null,
            AddressBox.Text, Theme.IsNight, _savedTrackPointer is null ? null : TrackPointer.IsChecked == true);
        if (warning is not null) Log(warning, true);
    }

    private void ApplyTheme(bool night)
    {
        Theme.Apply(night);
        if (ThemeButton is not null) ThemeButton.Content = night ? "Light" : "Night";
    }

    private void Theme_Click(object sender, RoutedEventArgs e)
    {
        ApplyTheme(!Theme.IsNight);
        try { SaveSettings(); }
        catch (Exception ex) { Log("Theme changed for this session. Preferences could not be saved: " + ex.Message, true); }
    }

    // ---- shell: drawer, size sliders, status line ----
    //
    // The main surface shows phones only. Everything else opens in a drawer, so the
    // controls are one click away rather than permanently occupying a third of the window.
    private void ShowDrawer(string title, FrameworkElement pane)
    {
        DrawerTitle.Text = title;
        ControlsPane.Visibility = ReferenceEquals(pane, ControlsPane) ? Visibility.Visible : Visibility.Collapsed;
        SettingsPane.Visibility = ReferenceEquals(pane, SettingsPane) ? Visibility.Visible : Visibility.Collapsed;
        ActivityPane.Visibility = ReferenceEquals(pane, ActivityPane) ? Visibility.Visible : Visibility.Collapsed;
        // Start below the top bar. Covering it made the first click on Stop input only close
        // the drawer, and Send text lives in a drawer, so a long send could not be stopped
        // with one click.
        DrawerHost.Margin = new Thickness(0, TopBar.ActualHeight, 0, 0);
        DrawerHost.Visibility = Visibility.Visible;
    }
    private void OpenControls_Click(object sender, RoutedEventArgs e) { ShowDrawer("Controls", ControlsPane); UpdateControls(); }
    private void OpenSettings_Click(object sender, RoutedEventArgs e) { ShowDrawer("Settings", SettingsPane); UpdateControls(); }
    private void OpenActivity_Click(object sender, RoutedEventArgs e) => ShowDrawer("Activity", ActivityPane);
    private void CloseDrawer_Click(object sender, RoutedEventArgs e) => DrawerHost.Visibility = Visibility.Collapsed;
    private void CloseDrawer_Click(object sender, MouseButtonEventArgs e) => DrawerHost.Visibility = Visibility.Collapsed;

    // The master image is given an explicit height and sits in a ScrollViewer, so the
    // slider can take it past the window and the view scrolls - the same behaviour as the
    // original console's large-screen slider. Tap mapping is unaffected: it is derived
    // from the image's actual rendered size, which is what the slider changes.
    private void LargeSize_Changed(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (PhoneImage is null) return;
        PhoneImage.Height = e.NewValue;
        PhoneImage.Width = double.NaN;
        Dispatcher.BeginInvoke(new Action(UpdateWallWidth), System.Windows.Threading.DispatcherPriority.Loaded);
    }

    /// <summary>Sizes the master to the space available, which is what most people want most of the time.</summary>
    private void Fit_Click(object sender, RoutedEventArgs e) => FitMaster();

    private void FitMaster()
    {
        if (MasterScroll is null || LargeSize is null) return;
        double available = MasterScroll.ViewportHeight > 20 ? MasterScroll.ViewportHeight : MasterScroll.ActualHeight;
        if (available <= 20) return;
        LargeSize.Value = Math.Clamp(available - 24, LargeSize.Minimum, LargeSize.Maximum);
        Dispatcher.BeginInvoke(new Action(UpdateWallWidth), System.Windows.Threading.DispatcherPriority.Loaded);
    }

    private void MasterScroll_SizeChanged(object sender, SizeChangedEventArgs e) => UpdateWallWidth();

    /// <summary>
    /// Caps the wall's width to the space left beside the master. Inside a horizontally
    /// scrolling surface a WrapPanel is offered infinite width, so without this the tiles
    /// would lay out in one endless row instead of filling the area to the right.
    /// </summary>
    private void UpdateWallWidth()
    {
        if (MasterScroll is null || PhoneWall is null) return;
        double viewport = MasterScroll.ViewportWidth > 0 ? MasterScroll.ViewportWidth : MasterScroll.ActualWidth;
        if (viewport <= 0) return;
        double master = PhoneImage?.ActualWidth ?? 0;
        double strip = ActionStrip?.ActualWidth ?? 0;
        PhoneWall.MaxWidth = Math.Max(120, viewport - master - strip - 52);
    }

    private void SmallSize_Changed(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        _tileHeight = (int)e.NewValue;
        // The template binds tile height through the ItemsControl's DataContext, so it has
        // to be re-read for the change to reach every tile.
        if (PhoneWall is not null) { PhoneWall.DataContext = null; PhoneWall.DataContext = this; }
        UpdateWallWidth();
    }

    private void WallRate_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (WallRate?.SelectedItem is ComboBoxItem item && int.TryParse(item.Tag?.ToString(), out int ms)) _tilePeriodMs = Math.Max(1, ms);
    }

    // One switch that puts every phone under the master, and takes them back out again.
    // Checking it also turns mirroring on, and unchecking turns it off, so the tick box and
    // the actual behaviour can never disagree - a half state where phones are selected but
    // mirroring is off looks armed when it is not.
    private bool _bulkChecking;

    private void SelectAll_Click(object sender, RoutedEventArgs e)
    {
        bool target = SelectAllBox.IsChecked == true;
        _bulkChecking = true;
        try { foreach (var d in _devices) d.IsChecked = target; }
        finally { _bulkChecking = false; }
        BatchMode.IsChecked = target && _devices.Count > 1;
        Log(target
            ? $"Mirroring to every phone: {Followers().Count} will follow {Selected?.DisplayName ?? "the master"}."
            : "Released every phone. Nothing is following the master now.");
        UpdateControls();
    }

    private void SyncSelectAll()
    {
        if (SelectAllBox is null || _bulkChecking) return;
        int checkedCount = _devices.Count(d => d.IsChecked);
        // Null renders as the indeterminate box, which is honest when only some are picked.
        SelectAllBox.IsChecked = _devices.Count == 0 || checkedCount == 0 ? false
            : checkedCount == _devices.Count ? true : null;
        SelectAllLabel.Text = checkedCount == 0 ? "Mirror to all" : $"Mirror to all  ({checkedCount} of {_devices.Count})";
    }

    /// <summary>Shows on the strip how many phones its buttons will reach.</summary>
    private void UpdateStripTarget()
    {
        if (StripTarget is null) return;
        int followers = Followers().Count;
        StripTarget.Text = followers > 0 ? $"→ {followers + 1} phones" : "";
        StripTarget.Visibility = followers > 0 ? Visibility.Visible : Visibility.Collapsed;
    }

    private void UpdateSelectedHeader()
    {
        if (SelectedTitle is null) return;
        var device = Selected;
        SelectedTitle.Text = device?.DisplayName ?? "Select an iPhone";
        // One compact line beside the title. The full identity - device id, board uid - is
        // a support detail, not something to keep on screen while driving the phone; it
        // lives in Settings, where binding is done.
        SelectedDetails.Text = device is null ? ""
            : $"iOS {device.Os}   ·   {device.VideoStatus}   ·   {device.ControlStatus}";
        UpdateFarmSelectedHeader();
    }

    private void UpdateStatusBar()
    {
        if (StatusInfo is null) return;
        if (!_connected) { StatusInfo.Text = "Not connected"; return; }
        int online = _devices.Count(d => d.Online);
        int ready = _devices.Count(d => d.ControlReady);
        int attached = _boards.Count(b => b.PhoneAttached);
        var parts = new List<string>
        {
            $"Hardware {_boards.Count} ({attached} with a phone)",
            $"Online {online}",
            $"Controllable {ready}",
        };
        string cast = CastLabel(_devices, _castName);
        if (cast.Length > 0) parts.Add("Cast " + cast);
        StatusInfo.Text = string.Join("   \u00b7   ", parts);
    }

    private static string CastLabel(IEnumerable<Device> devices, string fallback)
    {
        var names = devices.Select(d => d.ReceiverName).Where(n => n.Length > 0).Distinct().ToArray();
        return names.Length > 0 ? string.Join(" / ", names) : fallback;
    }

    private async void Connect_Click(object sender, RoutedEventArgs e) => await ConnectAsync();
    private async void Disconnect_Click(object sender, RoutedEventArgs e)
    {
        if (_closing) return;
        DetachConnection();
        int session = _session;
        ConnectionStatus.Text = "Disconnecting · releasing input…";
        Totals.Text = "Connect to your iMouse service";
        EmptyList.Text = "Connect to load your iPhones."; EmptyList.Visibility = Visibility.Visible;
        ClearFrame("Disconnected", "Phone mirroring was left unchanged.");
        UpdateControls();
        var records = await FinishConnectionCleanupAsync();
        if (_closing || session != _session) return;
        bool confirmed = records.All(r => r.Result.Confirmed);
        ConnectionStatus.Text = confirmed ? "Disconnected" : "Disconnected · input release unconfirmed";
        InputStateText.Text = confirmed ? "Input released" : "Input release not confirmed. Check the affected phones.";
        Log("Console disconnected. Phone mirroring was left unchanged.");
    }
    private async void Refresh_Click(object sender, RoutedEventArgs e) => await RefreshDevicesAsync(true);

    private async Task RefreshDevicesAsync(bool report = false)
    {
        if (_api is null || _refreshSession == _session || _closing) return;
        var session = _session; var api = _api; var ct = _lifetime.Token;
        _refreshSession = session;
        try
        {
            var fresh = await api.DevicesAsync(ct);
            if (session != _session || _closing) return;
            var oldId = Selected?.Id;
            var checkedIds = _devices.Where(x => x.IsChecked).Select(x => x.Id).ToHashSet();
            bool changed = Signature(_devices) != Signature(fresh);
            bool reconnect = !_connected;
            _connected = true;
            if (changed || reconnect)
            {
                foreach (var item in fresh) { item.IsChecked = checkedIds.Contains(item.Id); item.PropertyChanged += (_, _) => UpdateControls(); }
                _devices = fresh;
                ApplyFilter(oldId);
            }
            // Control and video are separate channels. A phone can be attached to a
            // working board with no mirroring, or mirroring with no board attached,
            // so the board list is read alongside the device list rather than inferred.
            try
            {
                var boards = await api.BoardsAsync(ct);
                if (session != _session || _closing) return;
                _boards = boards;
                var states = boards.Where(b => b.Uid.Length > 0).GroupBy(b => b.Uid).ToDictionary(g => g.Key, g => g.Max(b => b.State));
                foreach (var item in _devices) item.BoardState = item.Hardware.Length > 0 && states.TryGetValue(item.Hardware, out var state) ? state : 0;
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { return; }
            catch { /* Supplementary: the device list stays usable if the board list is unavailable. */ }

            _castName = CastLabel(fresh, "");
            if (_castName.Length == 0)
            {
                try
                {
                    var config = await api.GetAsync("/config/imserver/get", ct);
                    _castName = JsonValue.Text(config, "air_play_name");
                }
                catch { /* cosmetic only - the status line simply omits it */ }
            }
            ConnectionStatus.Text = "Connected to iMouse";
            ConnectionStatus.Foreground = (Brush)FindResource("OkBrush");
            Totals.Text = $"{_devices.Count} phones  ·  {_devices.Count(x => x.Online)} mirroring  ·  {_devices.Count(x => x.ControlReady)} controllable  ·  {_boards.Count} boards ({_boards.Count(b => b.PhoneAttached)} with a phone)";
            if (report || reconnect) Log($"Service connected. {_devices.Count} devices, {_devices.Count(x => x.Online)} online.");
            UpdateControls();
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { }
        catch (Exception ex)
        {
            if (session != _session || _closing) return;
            bool wasConnected = _connected; _connected = false;
            ConnectionStatus.Text = "Service unavailable · retrying";
            ConnectionStatus.Foreground = (Brush)FindResource("BadBrush");
            Totals.Text = "Check the address and existing iMouse service";
            ClearFrame("Service unavailable", "Keep iMouse running. This console will retry every 5 seconds.");
            if (wasConnected || report) Log("Connection failed: " + Friendly(ex), true);
            UpdateControls();
        }
        finally { if (_refreshSession == session) _refreshSession = -1; }
    }
    private static string Signature(IEnumerable<Device> items) => JsonSerializer.Serialize(items.Select(x => new { x.Id, x.Name, x.Model, x.Group, x.Os, x.Hardware, x.Online, x.VideoState, x.ReceiverName, x.Width, x.Height }));

    private void Filter_Changed(object sender, RoutedEventArgs e) { if (IsInitialized) ApplyFilter(Selected?.Id); }
    private void ApplyFilter(string? selectedId)
    {
        if (DeviceList is null || SearchBox is null) return;
        var query = SearchBox.Text.Trim();
        var visible = _devices.Where(d => (OnlineOnly.IsChecked != true || d.Online) &&
            (query.Length == 0 || string.Join(" ", d.DisplayName, d.Model, d.Id, d.Group).Contains(query, StringComparison.OrdinalIgnoreCase))).ToList();
        DeviceList.ItemsSource = visible;
        // Keep the caller's selection if it survived the filter; otherwise fall to the
        // first mirroring phone so the console shows a live screen on open rather than
        // an empty stage that has to be clicked before anything happens.
        DeviceList.SelectedItem = visible.FirstOrDefault(x => x.Id == selectedId)
            ?? visible.FirstOrDefault(x => x.Online);
        EmptyList.Visibility = visible.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        EmptyList.Text = _devices.Count == 0 ? "No phones returned. Check your phone setup and service address." : "No devices match these filters.";
        UpdateControls();
    }
    private void Device_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (SelectedTitle is null) return;
        ClearFrame("Your phone, here.", "Select an online iPhone to start its screen preview.");
        var device = Selected;
        UpdateSelectedHeader();
        if (device is { Online: false })
        {
            string receiver = device.ReceiverName.Length>0 ? device.ReceiverName : _castName.Length > 0 ? _castName : "iMouse2-C24C";
            if (device.VideoState == "restarting")
                ClearFrame("Receiver restarting", "The AirPlay helper is coming back. If the picture does not return, open Control Centre and pick " + receiver + " under Screen Mirroring.");
            else if (device.VideoState == "failed")
                ClearFrame("Receiver failed", "Restart the independent kernel, then recast this phone to " + receiver + ".");
            else
                ClearFrame("Not mirroring", "On the iPhone open Control Centre and pick " + receiver + " under Screen Mirroring. Control over the board is separate and may already be working.");
        }
        UpdateControls();
        if (AutoPreview.IsChecked == true) StartPump();
    }
    private void CheckVisible_Click(object sender, RoutedEventArgs e) { foreach (var d in DeviceList.Items.OfType<Device>()) d.IsChecked = true; UpdateControls(); }
    private void ClearChecks_Click(object sender, RoutedEventArgs e) { foreach (var d in _devices) d.IsChecked = false; UpdateControls(); }
    private void Batch_Changed(object sender, RoutedEventArgs e) { if (IsInitialized) UpdateControls(); }
    private void UpdateControls()
    {
        if (ActionPanel is null || _bulkChecking) return;
        UpdateConnectionHint();
        RefreshInputOwnershipUi();
        int count = _devices.Count(x => x.IsChecked);
        CheckedCount.Text = $"{count} checked across all groups";
        var followers = Followers();
        var mismatched = MismatchedFollowers();
        TargetText.Text = Selected is null
            ? "Target: select an iPhone"
            : BatchMode.IsChecked == true && followers.Count > 0
                ? $"Master: {Selected.DisplayName}  \u2192  mirroring to {followers.Count} phone(s)"
                : "Target: " + Selected.DisplayName;
        if (MirrorWarning is not null)
        {
            // Name anything the user ticked that will NOT receive the actions, and why.
            // Silently dropping a follower is the worst outcome here: the operator believes
            // ten phones are in lockstep when only nine are.
            var reasons = new List<string>();
            if (mismatched.Count > 0) reasons.Add($"{mismatched.Count} checked phone(s) have a different screen size and are excluded");
            if (BatchMode.IsChecked == true && Selected is not null)
            {
                int unusable = _devices.Count(d => d.IsChecked && d.Id != Selected.Id && (!d.Online || !d.ControlReady))
                               - mismatched.Count(d => !d.Online || !d.ControlReady);
                if (unusable > 0) reasons.Add($"{unusable} checked phone(s) are not mirroring or have no working board");
            }
            MirrorWarning.Text = string.Join("; ", reasons);
            MirrorWarning.Foreground = (Brush)FindResource("WarnBrush");
            MirrorWarning.Visibility = reasons.Count > 0 ? Visibility.Visible : Visibility.Collapsed;
        }
        ActionPanel.IsEnabled = _connected && (BatchMode.IsChecked == true ? count > 0 : Selected is not null);
        DisconnectButton.IsEnabled = _api is not null || _pendingConnection is not null;
        RefreshButton.IsEnabled = _api is not null;
        SaveFrameButton.IsEnabled = _frame is not null && _frameId == Selected?.Id;
        SyncPumpTarget();
        SyncWall();
        RefreshBindingUi();
        SyncSelectAll();
        UpdateStripTarget();
        UpdateSelectedHeader();
        UpdateStatusBar();
        ResetJoinedPointers();
    }

    private string _pointersResetFor = "";
    /// <summary>
    /// Resets the phone-side pointer whenever the mirror set changes.
    ///
    /// A phone can end up ignoring taps entirely - measured on the rack: a follower took
    /// pointer moves but every click did nothing at all, on its own and mirrored alike,
    /// until it was sent /mouse/reset, after which it responded to every mirrored click.
    /// Sending /mouse/up first did not fix it, so this is the pointer's own state, not a
    /// button left down. It reads to the operator as "mirroring is broken": the master
    /// obeys and one phone in the rack quietly does nothing.
    ///
    /// The set only changes when a phone is ticked, unticked or made master, so this
    /// costs one request at those moments and nothing at all while working.
    ///
    /// Known gap (audit, 9 Nov 2026): under the lease protocol this reset is normally NOT sent.
    /// The same change of mirror set starts a change of input scope first, which marks input not
    /// ready, and SendInputAsync drops the reset while it is not ready; the set is still recorded
    /// as reset. It is sent only when the change is noticed later, after an input action or
    /// gesture that was in progress. Left as it is until the reset can be checked on a rack.
    /// </summary>
    private void ResetJoinedPointers()
    {
        if (!_connected || _api is null || _gesture is not null || _inputActions.IsRunning) return;
        var ids = BatchMode.IsChecked == true ? InputTargetIds() : "";
        if (ids == _pointersResetFor) return;
        _pointersResetFor = ids;
        if (ids.Length == 0 || !ids.Contains(',')) return;
        _ = SendInputAsync("Pointer reset", "/mouse/reset", new());
    }
    private void ClearFrame(string heading, string message)
    {
        ReleaseCurrentGesture();
        PhoneImage.Source = null; _frame = null; _frameId = null; _frameAt = DateTime.MinValue;
        if (FarmPhoneImage is not null) FarmPhoneImage.Source = null;
        _live.Reset(); _rate.Reset(); _jitter.Reset(); _frameEpoch++; _lastFrameAt = DateTime.MinValue; _lastDelivered = DateTime.MinValue; _idleStreak = 0; _errorStreak = 0;
        _previewFreshness.Reset(_frameEpoch);
        PreparedFrame? obsolete;
        lock (_pendingLock) { obsolete = _pending; _pending = null; }
        _live.Recycle(obsolete);
        if (PointerReadout is not null) PointerReadout.Text = "Hover the screen to see tap coordinates";
        PreviewHeading.Text = heading; PreviewMessage.Text = message; PreviewPlaceholder.Visibility = Visibility.Visible;
        FrameStatus.Text = "Live view idle";
        UpdatePreviewFreshness();
    }
    /// <summary>
    /// The dropdown's Tag is a target FRAME PERIOD, not a poll spacing, and the two are
    /// deliberately different quantities. Assigning one to the other made the shipped
    /// default poll every 33 ms - the exact beat against the source's own 33 ms clock
    /// that the pump below exists to avoid. Oversample the period instead, and gate how
    /// often a frame is *delivered* separately from how often one is *looked for*.
    ///
    /// This handler runs during InitializeComponent, before the constructor body: WPF
    /// defers an index-based ComboBox selection until the items exist and then raises
    /// SelectionChanged with the handler already attached. That is why both values are
    /// derived here rather than trusted to the field initializers.
    /// </summary>
    private void Rate_Changed(object sender, SelectionChangedEventArgs e)
    {
        if (PreviewRate?.SelectedItem is ComboBoxItem item && int.TryParse(item.Tag?.ToString(), out int ms))
        {
            _framePeriod = Math.Max(1, ms);
            _pollInterval = Math.Clamp(ms / 6, 2, 40);
        }
    }
    private void Live_Changed(object sender, RoutedEventArgs e)
    {
        if (!IsInitialized) return;
        SyncPumpTarget();
        if (AutoPreview.IsChecked != true) { _rate.Reset(); _jitter.Reset(); FrameStatus.Text = "Live view paused"; } else StartPump();
        UpdatePreviewFreshness();
        UpdateWallFreshness();
    }

    // ---- live view ----
    //
    // The mirror produces a new frame roughly every 33 ms. Sampling that on a 33 ms
    // timer is the worst possible choice: the two clocks drift against each other, so
    // some ticks fetch a frame that has not changed and others miss one entirely. That
    // beat is what reads as stutter even when both ends are running at 30 fps.
    //
    // So the pump polls faster than the source, discards repeats, and only wakes the UI
    // when the picture actually advanced. Decoding happens on the worker thread; the UI
    // thread does one WritePixels per genuinely new frame, timed to the compositor.
    private PreparedFrame? _pending;
    private readonly FrameBuffer _grabBuffer = new();
    // Bumped whenever the displayed phone changes, so the frame pump knows to forget what
    // it last saw rather than mistaking the new phone's first frame for a repeat.
    private volatile int _frameEpoch;
    private readonly object _pendingLock = new();
    private bool _pumpRunning, _presenterHooked;
    // Written on the UI thread by Rate_Changed, read on the pump thread, so volatile for
    // the same reason _activeDeviceId below is.
    private volatile int _pollInterval = 5;   // how often to LOOK for a new frame
    private volatile int _framePeriod = 33;   // how often to DELIVER one, from the rate dropdown
    private DateTime _lastFrameAt = DateTime.MinValue;
    private DateTime _lastDelivered = DateTime.MinValue;
    private int _idleStreak;
    private int _errorStreak;
    private readonly JitterMeter _jitter = new();
    private readonly PreviewFreshness _previewFreshness = new();
    // Cached so the per-frame present request does not allocate a delegate 30 times a second.
    private readonly Action _presentNow;

    // The pump runs on the thread pool, and WPF forbids touching Selected,
    // AutoPreview or WindowState from there. These plain fields mirror that state and
    // are written only on the UI thread, so the worker never touches an element.
    private volatile string? _activeDeviceId;
    private volatile bool _pumpEnabled;

    private void SyncPumpTarget()
    {
        var device = Selected;
        _activeDeviceId = device is { Online: true } ? device.Id : null;
        _pumpEnabled = AutoPreview?.IsChecked == true && _connected && WindowState != WindowState.Minimized;
    }

    // Windows' default timer granularity is about 15.6 ms, so a Task.Delay(6) really
    // sleeps ~15 ms. That alone caps the live view near 20 fps against a 30 fps source.
    // Asking for 1 ms resolution while the console is running is what media players do;
    // it is released again on close.
    [DllImport("winmm.dll", ExactSpelling = true)] private static extern uint timeBeginPeriod(uint period);
    [DllImport("winmm.dll", ExactSpelling = true)] private static extern uint timeEndPeriod(uint period);
    private bool _timerRaised;

    private void StartPump()
    {
        if (_pumpRunning || _api is null || _closing) return;
        if (!_timerRaised) { try { timeBeginPeriod(1); _timerRaised = true; } catch { } }
        _pumpRunning = true;
        if (!_presenterHooked) { CompositionTarget.Rendering += PresentPending; _presenterHooked = true; }
        _ = PumpAsync(_session);
    }

    private async Task PumpAsync(int session)
    {
        // Two buffers, filled alternately, instead of a fresh 1.6 MB array per poll. See
        // FrameBuffer for the measurement that motivated this: the pump polls far more
        // often than the source produces frames, so nearly every allocation was a
        // large-object allocation thrown away microseconds later.
        var fetch = new FrameBuffer();
        var previous = new FrameBuffer();
        int epoch = _frameEpoch;
        try
        {
            while (!_closing && session == _session)
            {
                var api = _api;
                var id = _activeDeviceId;
                if (api is null || id is null || !_pumpEnabled)
                {
                    await Task.Delay(120).ConfigureAwait(false);
                    continue;
                }
                if (epoch != _frameEpoch) { epoch = _frameEpoch; previous.Length = 0; }
                try
                {
                    await api.ScreenshotIntoAsync(id, fetch, _lifetime.Token).ConfigureAwait(false);
                    if (session != _session || _closing) break;
                    if (epoch != _frameEpoch || _activeDeviceId != id) continue;
                    _errorStreak = 0;
                    bool samePixels = LiveFrame.SameAsPrevious(previous.Span, fetch.Span);
                    var stamp = _previewFreshness.Observe(epoch, samePixels, fetch.Metadata, requestSerial: fetch.RequestSerial);
                    if (stamp is null) continue;
                    if (samePixels)
                    {
                        // Preserve legacy input availability for a still image. Delivery
                        // freshness is reported separately, not inferred from this fetch.
                        if (_activeDeviceId == id && _frameId == id) _frameAt = DateTime.UtcNow;
                        // Nothing changed yet. Poll again after a small fixed pause - fixed,
                        // never derived from measured frame gaps, because such a scheme feeds
                        // back on itself: one missed frame widens the gap, which lengthens the
                        // sleep, which misses more frames (measured: 23 fps decaying to 16.5).
                        // Flat-out polling is not better either; it pushed the service's error
                        // rate from ~1% to ~2.7%. A few ms keeps ~60 polls/s, well above the
                        // 30 fps source, at the lowest error rate. Ease off further only once
                        // the screen has genuinely been still for a while.
                        if (_idleStreak < 400) _idleStreak++;
                        await Task.Delay(_idleStreak > 40 ? Math.Min(40, _pollInterval + _idleStreak / 6) : _pollInterval).ConfigureAwait(false);
                        continue;
                    }
                    _idleStreak = 0;
                    if (_activeDeviceId != id) continue;   // selection moved while this frame was in flight

                    var now = DateTime.UtcNow;
                    // The slow presets ("2 / 5 / 15 frames/s") mean what they say: keep looking
                    // often enough to see the picture change promptly, but hand on at most one
                    // frame per selected period. 30 fps and Maximum are never gated - the source
                    // itself is the limit there.
                    if (_framePeriod >= 60 && _lastDelivered != DateTime.MinValue
                        && (now - _lastDelivered).TotalMilliseconds < _framePeriod - _pollInterval)
                    {
                        (fetch, previous) = (previous, fetch);
                        continue;
                    }
                    _lastFrameAt = now;
                    _lastDelivered = now;
                    (fetch, previous) = (previous, fetch);   // previous now holds this frame
                    var prepared = _live.Prepare(previous.Span);
                    if (prepared is null)
                    {
                        _previewFreshness.Failed(epoch, fetch.RequestSerial);
                        await Task.Delay(60).ConfigureAwait(false); continue;
                    }
                    prepared.PreviewStamp = stamp;
                    PreparedFrame? replaced;
                    lock (_pendingLock) { replaced = _pending; _pending = prepared; }
                    _live.Recycle(replaced);   // a frame the compositor never drew is dead weight
                    _frame = previous; _frameId = id; _frameAt = now;
                    _lastPreviewError = ""; _errorStreak = 0;
                    // Ask for the frame to be drawn NOW rather than waiting for the compositor
                    // to come and ask. CompositionTarget.Rendering fires on WPF's own schedule
                    // (measured here: ~83/s, gaps of 7/14/28 ms), so a frame that arrives just
                    // after a tick waits up to 28 ms, which turns an even 33 ms arrival stream
                    // into a 31/47 ms limp. Posting at Render priority schedules a render pass
                    // at the moment the frame exists. Measured on this machine, against a
                    // metronomic 33.4 ms source: present-interval sd 9.5 ms -> 0.5 ms, and the
                    // count of intervals over 45 ms across 8 s went from 58 to 0. The Rendering
                    // hook stays attached as a backstop; whichever runs first takes the frame
                    // and the other finds the slot empty.
                    if (!_closing) _ = Dispatcher.BeginInvoke(DispatcherPriority.Render, _presentNow);
                }
                catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { break; }
                catch (Exception ex)
                {
                    // Roughly 1-3% of screenshot requests fail transiently even on a healthy
                    // phone. Treating each one as an outage and sleeping 700 ms was on its own
                    // enough to drag the live view from ~30 fps down to ~11. Retry straight
                    // away through a short run of failures, and only slow down and report once
                    // they persist - which is what a genuinely disconnected phone looks like.
                    _previewFreshness.Failed(epoch, fetch.RequestSerial);
                    _errorStreak++;
                    if (_errorStreak > 12)
                    {
                        var message = Friendly(ex);
                        if (message != _lastPreviewError)
                        {
                            _lastPreviewError = message;
                            await Dispatcher.InvokeAsync(() => { if (!_closing) Log("Live view: " + message, true); });
                        }
                        await Task.Delay(500).ConfigureAwait(false);
                    }
                    else await Task.Delay(8).ConfigureAwait(false);
                }
            }
        }
        finally { _pumpRunning = false; }
    }

    private void PresentPending(object? sender, EventArgs e)
    {
        if (_closing) return;
        PreparedFrame? frame;
        lock (_pendingLock) { frame = _pending; _pending = null; }
        if (frame is null) return;
        if (frame.PreviewStamp is { } pendingStamp && !_previewFreshness.IsCurrent(pendingStamp))
        {
            _live.Recycle(frame); return;
        }
        if (_live.Present(frame))
        {
            if (!ReferenceEquals(PhoneImage.Source, _live.Source)) PhoneImage.Source = _live.Source;
            SyncFarmPhoneImage();
            PreviewPlaceholder.Visibility = Visibility.Collapsed;
            if (frame.PreviewStamp is { } shownStamp) _previewFreshness.Presented(shownStamp);
            _rate.Mark(); _jitter.Mark();
            if (_live.Frames % 8 == 0 || _live.Frames == 1) UpdateFrameStatus();
        }
        _live.Recycle(frame);
    }

    private void UpdatePreviewFreshness()
    {
        if (PreviewFreshnessText is null) return;
        if (PhoneImage.Source is null)
        {
            PreviewFreshnessText.Text = "";
            PreviewFreshnessText.Visibility = Visibility.Collapsed;
            return;
        }
        var status = _previewFreshness.Status;
        PreviewFreshnessText.Text = AutoPreview.IsChecked == true ? status.Text : "Preview paused — image is not updating";
        PreviewFreshnessText.Foreground = (Brush)FindResource(status.FetchFailed || status.State == "quiet" ? "WarnBrush" : "MutedBrush");
        PreviewFreshnessText.Visibility = Visibility.Visible;
    }

    private void UpdateFrameStatus()
    {
        UpdatePreviewFreshness();
        if (FrameStatus is null || Selected is null || PhoneImage.Source is not BitmapSource shown) return;
        // The gap between frames actually reaching the screen, and how many of the last
        // few seconds' intervals ran long. Those are the numbers that move when smoothness
        // moves; an fps average cannot see judder, because 7/60/7/60 averages the same as
        // a steady 33.
        var gaps = _jitter.Summary();
        string pacing = gaps.P50 > 0 ? $" \u00b7 {gaps.P50:0}/{gaps.P95:0} ms p50/p95" + (gaps.Long > 0 ? $" \u00b7 {gaps.Long} slow" : "") : "";
        FrameStatus.Text = $"{_previewFreshness.Status.Text} \u00b7 {_rate.Fps:0.#} updates/s \u00b7 {shown.PixelWidth} \u00d7 {shown.PixelHeight} \u00b7 taps in image pixels{pacing}";
    }

    /// <summary>Single frame on demand, for the Refresh button and for the smoke test.</summary>
    private async Task GrabOneAsync()
    {
        var api = _api;
        var device = Selected;
        if (api is null || device is null || !device.Online || _closing) return;
        int epoch = _frameEpoch;
        try
        {
            await api.ScreenshotIntoAsync(device.Id, _grabBuffer, _lifetime.Token);
            if (_closing || Selected?.Id != device.Id || epoch != _frameEpoch) return;
            var stamp = _previewFreshness.Observe(epoch, false, _grabBuffer.Metadata, "manual", _grabBuffer.RequestSerial);
            if (stamp is null) return;
            _frame = _grabBuffer; _frameId = device.Id; _frameAt = DateTime.UtcNow;
            var prepared = _live.Prepare(_grabBuffer.Span);
            if (prepared is not null)
            {
                if (_live.Present(prepared))
                {
                    if (!ReferenceEquals(PhoneImage.Source, _live.Source)) PhoneImage.Source = _live.Source;
                    SyncFarmPhoneImage();
                }
                _live.Recycle(prepared);
            }
            else
            {
                using var stream = new MemoryStream(_grabBuffer.Data, 0, _grabBuffer.Length);
                var decoded = new BitmapImage();
                decoded.BeginInit(); decoded.CacheOption = BitmapCacheOption.OnLoad; decoded.StreamSource = stream; decoded.EndInit(); decoded.Freeze();
                PhoneImage.Source = decoded;
                SyncFarmPhoneImage();
            }
            _previewFreshness.Presented(stamp);
            PreviewPlaceholder.Visibility = Visibility.Collapsed;
            _rate.Mark(); UpdateFrameStatus(); UpdateControls();
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
        catch (Exception ex)
        {
            _previewFreshness.Failed(epoch, _grabBuffer.RequestSerial);
            UpdateFrameStatus();
            Log("Preview: " + Friendly(ex), true);
        }
    }

    // Taps and gestures are sent in mirror-image pixels, the space the kernel's calibration uses.
    private static (int W, int H) TargetSize(BitmapSource image) => (image.PixelWidth, image.PixelHeight);

    /// <summary>MapPreview, but pulls an outside point to the nearest edge. For gestures.</summary>
    private (int X, int Y)? MapPreviewClamped(Point point)
    {
        if (Selected is not { Online: true } d || PhoneImage.Source is not BitmapSource image || _frameId != d.Id) return null;
        var size = TargetSize(image);
        return CoordinateMapper.MapClamped(point.X, point.Y, PhoneImage.ActualWidth, PhoneImage.ActualHeight,
                                           image.PixelWidth, image.PixelHeight, size.W, size.H);
    }

    private (int X, int Y)? MapPreview(Point point)
    {
        if (Selected is not { Online: true } d || PhoneImage.Source is not BitmapSource image || _frameId != d.Id || (DateTime.UtcNow - _frameAt).TotalSeconds > 10) return null;
        var size = TargetSize(image);
        return CoordinateMapper.Map(point.X, point.Y, PhoneImage.ActualWidth, PhoneImage.ActualHeight, image.PixelWidth, image.PixelHeight, size.W, size.H);
    }
    // ---- pointer input ----
    //
    // A drag has to happen *while* the mouse is down, not be replayed afterwards. The
    // previous version recorded the start, sent nothing during the gesture, and fired a
    // single canned /mouse/swipe on release - so the phone sat still under the cursor and
    // then jumped at the end. That reads as the picture being stuck, even when the video
    // itself is running at full rate.
    //
    // The service exposes the primitives to do it properly: /mouse/move (absolute, in
    // image pixels), /mouse/down and /mouse/up. The press is held on the phone for the
    // whole gesture while the pointer is streamed to follow the mouse, so content tracks
    // the cursor the way it does under a finger.
    //
    // A stationary press is still sent as /mouse/click, which is atomic and already proven
    // on this hardware; the drag path engages only once the mouse has actually moved.
    private const double DragThreshold = 4;
    // A stationary press held this long becomes a long press: the button goes down on the
    // phone while the mouse is still held, and comes up on release. That is what lets iOS
    // run its own long-press timer - the icon context menu, jiggle mode, text selection -
    // and it is how the vendor console behaves. Below the threshold a press is still the
    // atomic /mouse/click on release, which is proven on this hardware; a human click is
    // well under 150 ms, so the two never collide. Holding then moving carries straight on
    // into the drag path, which is exactly how a finger moves an icon.
    private const int HoldThresholdMs = 250;
    private int _gestureSeq;
    private readonly InputActionQueue _inputActions;
    private DragGesture? _drag;
    private bool _dragStarted => _drag is not null;
    private bool _holdGesture => _drag?.Hold == true;

    private void Preview_Down(object sender, MouseButtonEventArgs e)
    {
        BeginGesture(e.GetPosition(PhoneImage));
        if (_gesture is null) return;
        PhoneImage.CaptureMouse(); e.Handled = true;
    }

    // The three gesture stages take a plain point rather than a mouse event, so the exact
    // path a real press follows can be exercised by the test suite. Synthesising WPF mouse
    // events is not practical, and this path is where the mirroring bugs lived.
    private void BeginGesture(Point point)
    {
        if (!_controlReady) return;
        if (PointerEnabled.IsChecked != true || !_connected || Selected is null || PhoneImage.Source is not BitmapSource image) return;
        var mapped = MapPreview(point);
        if (mapped is null) { Log("Refresh the preview before controlling the phone.", true); return; }
        var size = TargetSize(image);
        ReleaseCurrentGesture();
        _gesture = (Selected.Id, _session, mapped.Value.X, mapped.Value.Y, point, size.W, size.H);
        // Stop hover tracking. A queued hover move that lands after the button goes down
        // starts the drag from wherever the mouse last rested instead of from the press.
        _pointerMoves.ClearPending();
        _ = HoldWatchAsync(++_gestureSeq);
    }

    /// <summary>
    /// Turns a press that is still stationary after HoldThresholdMs into a long press by
    /// starting the drag loop with no movement: it sends /mouse/down and simply waits for
    /// the release. The sequence number guards against a stale timer: a quick tap ends the
    /// gesture long before the delay elapses, and a new press at the same spot gets its
    /// own number, so a timer can only ever promote the press that started it.
    /// </summary>
    private async Task HoldWatchAsync(int seq)
    {
        await Task.Delay(HoldThresholdMs);   // resumes on the UI thread, which owns the gesture state
        if (seq != _gestureSeq || _gesture is not { } gesture || _dragStarted || !_controlReady) return;
        if (PointerEnabled.IsChecked != true || _api is not { } api || Selected is not { } device
            || device.Id != gesture.Id || _session != gesture.Session) return;
        StartDrag(api, gesture.X, gesture.Y, hold: true);
        if (PointerReadout is not null) PointerReadout.Text = $"x {gesture.X}, y {gesture.Y} — holding";
    }

    private async void Preview_Up(object sender, MouseButtonEventArgs e) => await EndGestureAsync(e.GetPosition(PhoneImage));

    private async Task EndGestureAsync(Point raw)
    {
        var gesture = _gesture;
        var drag = _drag;
        _gesture = null; _drag = null; _gestureSeq++;
        if (gesture is null) { PhoneImage.ReleaseMouseCapture(); return; }

        if (drag is not null)
        {
            // Hand the final position to the drag loop and let it release the button. The
            // loop owns ordering, so every queued move lands before /mouse/up and a drag
            // can never finish at a stale coordinate.
            var last = MapPreviewClamped(raw);
            // A long press released where it began must not tack a jittery one-pixel move
            // onto the end of the hold; only a real movement is delivered before release.
            drag.Release((raw - gesture.Value.View).Length > DragThreshold ? last : null);
            // Publish final coordinates before releasing capture; LostCapture may run
            // synchronously and must not release this drag before its final move.
            PhoneImage.ReleaseMouseCapture();
            return;
        }

        PhoneImage.ReleaseMouseCapture();
        if (PointerEnabled.IsChecked != true || Selected?.Id != gesture.Value.Id || _session != gesture.Value.Session) return;
        if (PhoneImage.Source is not BitmapSource image) return;
        if (TargetSize(image) != (gesture.Value.W, gesture.Value.H)) { Log("Phone orientation changed. Try again.", true); return; }
        // A tap lands where the button went DOWN, not where it came up. Using the release
        // point meant a few pixels of drift moved the tap, and a release a hair outside the
        // picture rejected the coordinate and sent nothing.
        await SendInputAsync("Tap", "/mouse/click", new() { ["x"] = gesture.Value.X, ["y"] = gesture.Value.Y });
    }

    /// <summary>
    /// Holds the button down on the phone and streams pointer moves for the life of the
    /// gesture. One sequential task, so press - moves - release is ordered; the newest
    /// pending position always wins and the last one is always delivered before release.
    /// </summary>
    private void StartDrag(ApiClient api, int x, int y, bool hold, (int X, int Y)? point = null)
    {
        var context = new InputContext(api, InputTargetIds(), _lifetime.Token, _controlCancellation);
        var drag = new DragGesture(context, x, y, hold);
        if (point is { } target) drag.Move(target);
        _drag = drag;
        _ = RunDragAsync(drag);
    }

    private async Task RunDragAsync(DragGesture drag)
    {
        var context = drag.Context;
        DragResult? result = null;
        try
        {
            await _inputActions.Enqueue(context, async ct =>
            {
                result = await DragInput.RunAsync(drag, ct).ConfigureAwait(false);
                if (result.Failure is not null) System.Runtime.ExceptionServices.ExceptionDispatchInfo.Throw(result.Failure);
                if (result.ReleaseFailure is not null) System.Runtime.ExceptionServices.ExceptionDispatchInfo.Throw(result.ReleaseFailure);
                if (drag.Hold && result.Released)
                {
                    int count = context.Ids.Count(c => c == ',') + 1;
                    string what = result.Moves > 0 ? "Long press, then drag" : "Long press";
                    LogAsync(count > 1 ? $"{what} ({result.DurationMs} ms) -> {count} phones" : $"{what} ({result.DurationMs} ms)");
                }
            }).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (CancelledHere(context.Connection, context.Control)) { }
        catch (InputNotSentException ex) { LogAsync("Drag: " + ex.Message, true); }
        catch (ApiException ex) when (ex.IsRefusal && result is { Released: true })
        { LogAsync("Drag refused: " + ex.Message + " The button was released; nothing else was sent.", true); }
        catch (Exception ex)
        {
            bool releaseOnly = result is { Failure: null, ReleaseFailure: not null };
            LogAsync((releaseOnly ? "Drag release failed: " : "Drag: ") + Friendly(ex), true);
            if (result is { Failure: not null, ReleaseFailure: not null })
                LogAsync("Drag release failed: " + Friendly(result.ReleaseFailure), true);
        }
    }

    private void ReleaseCurrentGesture()
    {
        _gestureSeq++;
        var drag = _drag;
        _gesture = null; _drag = null;
        drag?.Release();
        if (PhoneImage.IsMouseCaptured) PhoneImage.ReleaseMouseCapture();
    }

    private void Preview_LostCapture(object sender, MouseEventArgs e) => ReleaseCurrentGesture();

    /// <summary>
    /// Reports the coordinate a click would send, and drives the phone's own pointer
    /// so it follows the mouse. No overlay is drawn: the phone's pointer is visible in
    /// the mirror itself, so a second marker was redundant.
    /// </summary>
    private void Preview_Move(object sender, MouseEventArgs e)
        => TrackGesture(e.GetPosition(PhoneImage), e.LeftButton == MouseButtonState.Pressed);

    private void TrackGesture(Point raw, bool buttonDown)
    {
        if (PointerReadout is null) return;

        // A gesture already in progress keeps tracking even once the cursor leaves the
        // picture. This used to sit behind a "point is inside the phone" test, which broke
        // swiping badly: a stroke that ran past the edge froze at the last inside point,
        // and a quick flick that left the picture before passing the movement threshold
        // started no drag and then fell through to a tap that also rejected the point - so
        // the whole gesture sent nothing at all.
        if (_gesture is { } gesture && buttonDown && PointerEnabled.IsChecked == true)
        {
            var held = MapPreviewClamped(raw);
            if (held is null) return;
            if (!_dragStarted && _controlReady
                && (raw - gesture.View).Length > DragThreshold
                && _api is { } dragApi && Selected is { } dragDevice && dragDevice.Id == gesture.Id)
            {
                StartDrag(dragApi, gesture.X, gesture.Y, hold: false, held.Value);
            }
            else _drag?.Move(held.Value);
            PointerReadout.Text = $"x {held.Value.X}, y {held.Value.Y}";
            return;
        }

        var mapped = MapPreview(raw);
        if (mapped is null || PointerEnabled.IsChecked != true)
        {
            PointerReadout.Text = mapped is null && PhoneImage.Source is not null
                ? "Outside the phone screen" : "Hover the screen to see tap coordinates";
            return;
        }
        PointerReadout.Text = $"x {mapped.Value.X}, y {mapped.Value.Y} \u2014 click to tap here";
        if (TrackPointer.IsChecked == true) TrackPointerTo(mapped.Value);
    }

    // Capture the complete request on the UI thread; the worker coalesces positions
    // without mixing selection, connection or cancellation state between requests.
    private readonly PointerMovePump _pointerMoves = new();
    private void TrackPointerTo((int X, int Y) point)
    {
        if (_closing || !_controlReady || !_connected || _api is not { } api) return;
        if (_gesture is not null || _inputActions.IsRunning) return;
        _pointerMoves.Post(new(api, InputTargetIds(), point.X, point.Y,
            _lifetime.Token, _controlCancellation.Token));
    }

    private void PointerTrackingDisabled(object sender, RoutedEventArgs e)
    {
        _pointerMoves.ClearPending();
        if (PointerEnabled.IsChecked != true) ReleaseCurrentGesture();
    }

    private void Preview_Leave(object sender, MouseEventArgs e)
    {
        if (PointerReadout is not null) PointerReadout.Text = "Hover the screen to see tap coordinates";
    }


    // ---- control-board assignment (read-only) ----

    private void RefreshBindingUi()
    {
        if (BindStatus is null) return;
        var device = Selected;
        BindStatus.Text = !_connected ? "Connect to view phone and board assignments."
            : (device is null ? "" : device.Hardware.Length == 0 ? "No board assigned. " : $"Bound to {device.Hardware} · {device.ControlStatus}. ")
                + ApiClient.AssignmentsViewOnly;
    }

    // ---- master / mirror ----
    //
    // The selected phone is the master: it is the one on screen and the one the mouse acts
    // on. With mirroring on, every input is addressed to the master *and* the checked
    // followers in a single request - the service accepts a comma-separated id list on all
    // the input endpoints, so ten phones cost one round trip rather than ten.
    //
    // Only followers with the same mirror geometry are included. Identical screens make the
    // coordinates identical, which is what makes the mimicry exact. A follower with a
    // different screen size would need its coordinates rescaled, and on a different layout
    // a rescaled tap lands on whatever happens to sit at that fraction of the screen - so
    // those are excluded and named in the UI rather than silently mis-tapped.
    // ---- the wall of other phones ----
    //
    // Beside the master sits a live tile per other phone. With a rack of ten this is how an
    // operator confirms a mirrored action actually landed everywhere, so the tiles have to
    // keep updating - a frozen tile has to be distinguishable from a still screen.
    //
    // Each tile has an independent raw-frame pump and a cancellable lifetime. A shared
    // fetch limiter caps concurrent requests at three; backoff and display work do not
    // occupy a fetch slot. Delivery status is separate from pixel changes and input readiness.
    private readonly System.Collections.ObjectModel.ObservableCollection<Thumb> _wall = [];
    private volatile string[] _wallTargets = [];
    private readonly TileStreams _tileStreams = new();
    // Bounds how many tile fetches are in flight at once. Each tile now runs its own pump,
    // so without this a large rack would open one request per phone simultaneously.
    private readonly TileFetchScheduler _tileFetchScheduler = new(3);
    private int _tileHeight = 118;
    private int _tilePeriodMs = 33;    // per tile, not per pass over the whole wall
    private long _tileFrames, _tileFetches, _tileDupes;
    private string _castName = "";

    public double TileHeight => _tileHeight;

    /// <summary>
    /// A tile's width, fixed rather than measured from what is inside it.
    ///
    /// Letting a tile size itself to its contents made the wall visibly jitter. The rate
    /// readout under each phone is text of changing width ("", "21 fps", "20.7 fps"), so
    /// every time the number changed the tile grew or shrank and the whole wall reflowed
    /// around it. Measured from a screen recording of the running app: the tile swung
    /// between 131 and 178 pixels wide - a 47-pixel jump - fourteen times in thirteen
    /// seconds. Nothing about a tile's geometry may depend on its own content.
    /// </summary>
    public double TileWidth => Math.Round(_tileHeight * TileAspect);

    private double _tileAspect = 500.0 / 1080.0;
    private double TileAspect
    {
        get
        {
            // Use a real phone's shape when one is known, so tiles are not letterboxed for
            // no reason; otherwise the iPhone XR mirror geometry this rack reports.
            var sample = _devices.FirstOrDefault(d => d.Online && d.ImageWidth > 0 && d.ImageHeight > 0);
            if (sample is not null) _tileAspect = Math.Clamp((double)sample.ImageWidth / sample.ImageHeight, 0.2, 3.0);
            return _tileAspect;
        }
    }

    private void Thumb_Click(object sender, MouseButtonEventArgs e)
    {
        if (sender is not FrameworkElement fe || fe.Tag is not string id) return;
        var device = _devices.FirstOrDefault(d => d.Id == id);
        if (device is null) return;
        // Promote the clicked phone to master. Its tile disappears from the wall and the
        // previous master takes its place, which is the quickest way to inspect one phone
        // that looks out of step without hunting for it in the device list.
        SearchBox.Text = "";
        DeviceList.SelectedItem = _devices.FirstOrDefault(d => d.Id == id) is { } d2 && DeviceList.Items.Contains(d2) ? d2 : DeviceList.SelectedItem;
        if (!ReferenceEquals(DeviceList.SelectedItem, device))
        {
            ApplyFilter(device.Id);
            DeviceList.SelectedItem = DeviceList.Items.OfType<Device>().FirstOrDefault(x => x.Id == device.Id);
        }
        e.Handled = true;
    }

    /// <summary>Rebuilds the wall to match the current devices. Runs on the UI thread.</summary>
    private void SyncWall()
    {
        if (PhoneWall is null) return;
        var master = Selected;
        var others = _devices.Where(d => d.Id != master?.Id).ToList();
        var followers = Followers().Select(d => d.Id).ToHashSet();

        for (int i = _wall.Count - 1; i >= 0; i--)
            if (others.All(d => d.Id != _wall[i].Id)) _wall.RemoveAt(i);

        foreach (var d in others)
        {
            var tile = _wall.FirstOrDefault(t => t.Id == d.Id);
            if (tile is null) { tile = new Thumb { Id = d.Id }; _wall.Add(tile); }
            tile.Name = d.DisplayName;
            tile.Ready = d.Online && d.ControlReady;
            tile.Following = followers.Contains(d.Id);
            tile.Status = d.Online ? (followers.Contains(d.Id) ? "following" : d.ControlReady ? "ready" : d.ControlStatus) : "not mirroring";
            if (!d.Online) tile.Image = null;
        }

        WallEmpty.Visibility = _wall.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        UpdateWallWidth();
        WallHeading.Text = _wall.Count == 0 ? "Others"
            : $"Others · {_wall.Count(t => t.Following)}/{_wall.Count} following";
        _wallTargets = _devices.Where(d => _connected && d.Online && d.Id != master?.Id).Select(d => d.Id).ToArray();
        // TileWidth is a plain property, read when the template binds. Re-read it if the
        // phones' shape has changed - on the first device list, or a rack of a different
        // model - but never otherwise, because rebinding resets every tile.
        double aspect = _tileAspect;
        if (Math.Abs(TileAspect - aspect) > 0.001 && PhoneWall is not null)
        {
            PhoneWall.DataContext = null; PhoneWall.DataContext = this;
        }
        StartTilePumps();
        UpdateWallFreshness();
    }

    private void UpdateWallFreshness()
    {
        if (_wall is null) return;
        foreach (var tile in _wall)
        {
            var stream = _tileStreams.Find(tile.Id);
            bool online = Array.IndexOf(_wallTargets, tile.Id) >= 0;
            tile.SetDelivery(TileStatusView.From(stream?.Freshness.Status, online, !_pumpEnabled));
            tile.Fps = online && _pumpEnabled && stream is not null ? stream.Rate.Fps : 0;
        }
    }

    /// <summary>Gives every phone on the wall its own pump, and lets removed ones finish.</summary>
    private void StartTilePumps()
    {
        foreach (var stream in _tileStreams.Reconcile(_wallTargets, _session, _lifetime.Token))
        {
            var tile = _wall.FirstOrDefault(t => t.Id == stream.Id);
            if (tile is not null) { tile.Image = null; tile.Fps = 0; }
            _ = TilePumpAsync(stream);
        }
    }

    /// <summary>
    /// One pump per phone on the wall.
    ///
    /// This used to be a single loop walking the phones in turn, one JPEG each, spreading
    /// a full pass over about a second. Two things made that far slower than it needed to
    /// be. The kernel re-encodes for JPEG - measured at roughly 40 ms per request against
    /// 2 ms to serve the raw frame, and it caps a stream at about 21 requests a second -
    /// so the wall was paying twenty times the latency for pictures it then shrank to
    /// thumbnails anyway. And walking the phones in turn means the last tile in a rack of
    /// ten waits for the other nine before it is looked at even once.
    ///
    /// So: raw frames, one independent pump per phone, and a shared gate bounding how many
    /// are in flight. Measured beforehand, polling both phones' raw frames concurrently and
    /// flat out did not slow either of them, and streaming input at the same time did not
    /// slow frame polling - so the phones really are independent and there is no reason to
    /// serialise them.
    /// </summary>
    private async Task TilePumpAsync(TileStream stream)
    {
        var fetch = new FrameBuffer();
        var previous = new FrameBuffer();
        var live = new LiveFrame();
        int idle = 0;
        bool Current() => !_closing && stream.Connection == _session && _tileStreams.IsCurrent(stream);
        void UpdateTile()
        {
            if (!Current()) return;
            var tile = _wall.FirstOrDefault(t => t.Id == stream.Id);
            if (tile is null) return;
            tile.Fps = _pumpEnabled ? stream.Rate.Fps : 0;
            tile.SetDelivery(TileStatusView.From(stream.Freshness.Status, true, !_pumpEnabled));
        }
        try
        {
            while (Current())
            {
                var api = _api;
                if (api is null || !_pumpEnabled)
                { await Task.Delay(250, stream.Token).ConfigureAwait(false); continue; }
                int period = Math.Max(_tilePeriodMs, Math.Max(1, _wallTargets.Length) * 12);
                long started = Environment.TickCount64;
                try
                {
                    var result = await _tileFetchScheduler.FetchAsync(
                        ct => api.ScreenshotIntoAsync(stream.Id, fetch, ct), stream.Token).ConfigureAwait(false);
                    if (result.Cancelled || !Current()) break;
                    if (!result.Success) throw new IOException("Tile screenshot unavailable.");
                    Interlocked.Increment(ref _tileFetches);
                    bool same = LiveFrame.SameAsPrevious(previous.Span, fetch.Span);
                    var stamp = stream.Freshness.Observe(0, same, fetch.Metadata, requestSerial: fetch.RequestSerial);
                    if (stamp is null) continue;
                    if (same)
                    {
                        Interlocked.Increment(ref _tileDupes);
                        if (idle < 200) idle++;
                    }
                    else
                    {
                        idle = 0;
                        (fetch, previous) = (previous, fetch);
                        var prepared = live.Prepare(previous.Span, Math.Max(48, _tileHeight * 2));
                        if (prepared is null)
                        {
                            previous.Length = 0;
                            throw new InvalidDataException("Tile image cannot be decoded.");
                        }
                        try
                        {
                            await Dispatcher.InvokeAsync(() =>
                            {
                                if (!Current() || !_pumpEnabled) { previous.Length = 0; return; }
                                var tile = _wall.FirstOrDefault(t => t.Id == stream.Id);
                                if (tile is null || !live.Present(prepared)) { previous.Length = 0; return; }
                                if (!ReferenceEquals(tile.Image, live.Source)) tile.Image = live.Source;
                                stream.Freshness.Presented(stamp);
                                stream.Rate.Mark(); _tileFrames++;
                            });
                        }
                        finally { live.Recycle(prepared); }
                    }
                    if (Current()) await Dispatcher.InvokeAsync(UpdateTile);
                }
                catch (OperationCanceledException) when (stream.Token.IsCancellationRequested) { break; }
                catch (Exception)
                {
                    if (!Current()) break;
                    stream.Freshness.Failed(0);
                    await Dispatcher.InvokeAsync(UpdateTile);
                    await Task.Delay(400, stream.Token).ConfigureAwait(false);
                }
                int wait = period + Math.Min(220, idle * 4) - (int)(Environment.TickCount64 - started);
                if (wait > 0) await Task.Delay(wait, stream.Token).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (stream.Token.IsCancellationRequested) { }
        finally { _tileStreams.Complete(stream); }
    }

    private List<Device> Followers()
    {
        if (BatchMode.IsChecked != true || Selected is not { } master) return [];
        return _devices.Where(d => d.IsChecked && d.Id != master.Id && d.Online && d.ControlReady
                                   && d.ImageWidth == master.ImageWidth && d.ImageHeight == master.ImageHeight)
                       .ToList();
    }

    private List<Device> MismatchedFollowers()
    {
        if (BatchMode.IsChecked != true || Selected is not { } master) return [];
        return _devices.Where(d => d.IsChecked && d.Id != master.Id
                                   && (d.ImageWidth != master.ImageWidth || d.ImageHeight != master.ImageHeight))
                       .ToList();
    }

    /// <summary>Comma-separated id list for one input request: master first, then followers.</summary>
    private string InputTargetIds()
    {
        if (Selected is not { } master) return "";
        var ids = new List<string> { master.Id };
        ids.AddRange(Followers().Select(d => d.Id));
        return string.Join(",", ids);
    }

    private void FollowSameModel_Click(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } master) { Log("Select the master phone first.", true); return; }
        int n = 0;
        foreach (var d in _devices)
        {
            bool match = d.Id != master.Id && d.Online && d.ControlReady
                         && d.ImageWidth == master.ImageWidth && d.ImageHeight == master.ImageHeight;
            d.IsChecked = match;
            if (match) n++;
        }
        BatchMode.IsChecked = n > 0;
        Log(n == 0
            ? "No other phone is mirroring, controllable and the same screen size as this one."
            : $"{n} phone(s) will now follow {master.DisplayName}.");
        UpdateControls();
    }

    /// <summary>
    /// Sends one input to the master and every follower in a single request, so every phone
    /// receives the same event as close to simultaneously as possible.
    /// </summary>
    private async Task SendInputAsync(string label, string function, Dictionary<string, object> data, bool quiet = false)
    {
        // Capture the targets before the queue/HTTP round trip.
        var ids = InputTargetIds();
        if (!_controlReady) return;
        var lifetime = _lifetime.Token; var control = _controlCancellation;
        var api = _api;
        if (api is null || !_connected || ids.Length == 0) return;
        int count = ids.Count(c => c == ',') + 1;
        try
        {
            // ConfigureAwait(false): a tap must not wait for the live view to finish
            // painting before it is sent, nor again before it is logged.
            var context = new InputContext(api, ids, lifetime, control);
            var payload = new Dictionary<string, object>(data) { ["id"] = ids };
            _pointerMoves.ClearPending();
            await _inputActions.Enqueue(context, ct => api.CommandAsync(function, payload, ct)).ConfigureAwait(false);
            if (!quiet) LogAsync(count > 1 ? $"{label} -> {count} phones" : label);
        }
        catch (OperationCanceledException) when (CancelledHere(lifetime, control)) { }
        catch (InputNotSentException ex) { LogAsync($"{label}: {ex.Message}", true); }
        // The kernel declined it before sending anything; input stays ready and nothing needs Resume.
        catch (ApiException ex) when (ex.IsRefusal) { LogAsync($"{label} refused: {ex.Message} Nothing was sent.", true); }
        // A cancellation nobody here asked for is HttpClient's timeout: logged, not swallowed.
        catch (Exception ex) { LogAsync($"{label} failed: {Friendly(ex)}", true); }
    }

    private async void Action_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button button || button.Tag is not string tag) return;
        var parts = tag.Split('|');
        var data = new Dictionary<string, object>(); string function;
        switch (parts[0])
        {
            case "swipe": function = "/mouse/swipe"; data["direction"] = parts[1]; data["len"] = 0.75; break;
            case "key": function = "/key/sendkey"; data["fn_key"] = parts[1]; break;
            case "reset": function = "/mouse/reset"; break;
            default: return;
        }
        await SendInputAsync(button.Content.ToString()!, function, data);
    }
    /// <summary>
    /// Temporary cap on one Send text, not a chunking requirement: chunks bound the work per command,
    /// but deadlines can still expire under load. The cap bounds how long one send holds the phones
    /// (200 characters is 17 chunks of 12, roughly 35 s idle). The box has no MaxLength, because WPF
    /// truncates pasted text to it silently; over-limit text stays visible and is refused.
    /// </summary>
    internal const int MaxSendText = 200;
    private bool _sendingText;
    private void SendTextBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (SendTextCount is null) return;
        int length = SendTextBox.Text.Length;
        SendTextCount.Text = length > MaxSendText ? $"{length} / {MaxSendText} · too long to send" : $"{length} / {MaxSendText}";
        SendTextCount.SetResourceReference(TextBlock.ForegroundProperty, length > MaxSendText ? "BadBrush" : "MutedBrush");
    }
    private async void SendText_Click(object sender, RoutedEventArgs e)
    {
        string text = SendTextBox.Text;
        if (string.IsNullOrEmpty(text)) { Log("Enter text to send first.", true); return; }
        if (text.Any(c => c < 32 || c > 126)) { Log("This version types English letters, numbers and punctuation only. Unsupported text was not sent.", true); return; }
        if (text.Length > MaxSendText) { Log($"Send text takes at most {MaxSendText} characters at a time; this is {text.Length}. Nothing was sent.", true); return; }
        if (_sendingText) { Log("Still typing the previous text. Wait for it to finish, or use Stop input.", true); return; }
        if (!_controlReady) return;
        var api = _api; var ids = InputTargetIds();
        if (api is null || !_connected || ids.Length == 0) return;
        var context = new InputContext(api, ids, _lifetime.Token, _controlCancellation);
        int count = ids.Count(c => c == ',') + 1;
        string label = count > 1 ? $"Send text -> {count} phones" : "Send text";
        _sendingText = true;
        try
        {
            TextDelivery? r = null;
            _pointerMoves.ClearPending();
            try
            {
                await _inputActions.Enqueue(context, async ct =>
                {
                    r = await api.SendTextAsync(ids, text, ct).ConfigureAwait(false);
                    if (r.Failure is not null) System.Runtime.ExceptionServices.ExceptionDispatchInfo.Throw(r.Failure);
                });
            }
            catch (Exception) when (r is not null) { /* Accepted text reports its own complete outcome below. */ }
            if (r is null) throw new InvalidOperationException("Text operation did not report an outcome.");
            if (r.End == InputEnd.Completed) { Log($"{label}: {r.Total} characters in {r.Chunks} chunk(s)"); return; }
            string progress = $"{r.ConfirmedCharacters} of {r.Total} characters confirmed.";
            string partial = r.Sent > r.Confirmed ? $" Chunk {r.Sent} of {r.Chunks} may be partly typed and was not retried." : "";
            string rest = r.Sent == r.Chunks ? "" : r.Sent == 0 ? " No chunk was sent."
                : r.Sent + 1 == r.Chunks ? $" Chunk {r.Chunks} was not sent." : $" Chunks {r.Sent + 1}–{r.Chunks} were not sent.";
            switch (r.End)
            {
                case InputEnd.Cancelled: Log($"{label} stopped: {progress}{partial}{rest}", true); break;
                // The kernel declined the chunk before typing any of it; input stays ready.
                case InputEnd.Refused: Log($"{label} refused: {progress} Chunk {r.Sent} of {r.Chunks} was not typed.{rest} {Friendly(r.Failure!)}", true); break;
                // The lease client's pause notice shows Input paused and enables Resume.
                case InputEnd.TimedOut: Log($"{label} timed out: {progress}{partial}{rest} Check the phone before continuing.", true); break;
                default: Log($"{label} failed: {progress}{partial}{rest} {Friendly(r.Failure!)}", true); break;
            }
        }
        catch (OperationCanceledException) when (CancelledHere(context.Connection, context.Control)) { Log($"{label} stopped before sending."); }
        catch (InputNotSentException ex) { Log($"{label}: {ex.Message}", true); }
        catch (Exception ex) { Log($"{label} failed: {Friendly(ex)}", true); }
        finally { _sendingText = false; }
    }
    private void SaveImage_Click(object sender, RoutedEventArgs e)
    {
        if (_frame is null || _frameId != Selected?.Id || PhoneImage.Source is not BitmapSource source) return;
        var dialog = new SaveFileDialog { FileName = "iPhone-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + ".png", Filter = "PNG image|*.png" };
        if (dialog.ShowDialog(this) != true) return;
        try { using var file = File.Create(dialog.FileName); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(source)); encoder.Save(file); Log("Screen image saved."); }
        catch (Exception ex) { Log("Save failed: " + ex.Message, true); }
    }
    /// <summary>Log from any thread. The input pumps run off the UI thread now.</summary>
    private void LogAsync(string message, bool error = false)
    {
        if (_closing) return;
        if (Dispatcher.CheckAccess()) Log(message, error);
        else _ = Dispatcher.BeginInvoke(new Action(() => Log(message, error)));
    }

    private void Log(string message, bool error = false)
    {
        if (_closing) return;
        message = message.Replace('\r', ' ').Replace('\n', ' ');
        if (message.Length > 400) message = message[..400];
        LastEvent.Text = message; LastEvent.Foreground = (Brush)FindResource(error ? "BadBrush" : "TextBrush");
        _activity.Insert(0, $"{DateTime.Now:HH:mm:ss}  {message}");
        while (_activity.Count > 100) _activity.RemoveAt(_activity.Count - 1);
    }
    private static string Friendly(Exception ex) => ex is TaskCanceledException ? "Request timed out. The outcome may be unknown; check the phone before repeating the action." : ex.Message;
}
