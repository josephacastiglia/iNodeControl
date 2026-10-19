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
    private bool _commandBusy, _connected, _closing, _filtering;
    private List<Device> _devices = [];
    private readonly ObservableCollection<string> _activity = [];
    private readonly DispatcherTimer _refreshTimer = new() { Interval = TimeSpan.FromSeconds(5) };
    private FrameBuffer? _frame;
    private string? _frameId;
    private DateTime _frameAt = DateTime.MinValue;
    private readonly LiveFrame _live = new();
    private readonly RateMeter _rate = new();
    private List<Board> _boards = [];
    private bool _autoBinding;
    private (string Id, int Session, int X, int Y, Point View, int W, int H)? _gesture;
    private string _lastPreviewError = "";
    private readonly string _dataPath;
    private readonly bool _mirrorLocal;
    private Device? Selected => DeviceList.SelectedItem as Device;
    /// <summary>The address the data folder's settings.json named, or null when it named none
    /// (the box then shows the built-in default, the vendor service on 9911).</summary>
    internal string? SavedAddress { get; private set; }
    private bool? _savedTrackPointer;

    // dataPath is for test modes and --data-dir: they must never load or overwrite the
    // operator's %APPDATA%\iMouse2, which every console build on this machine shares.
    public MainWindow(Func<string, ApiClient>? factory = null, string? dataPath = null)
    {
        _dataPath = dataPath ?? ResolveDataPath();
        _mirrorLocal = dataPath is null;
        _factory = factory ?? (address => new ApiClient(address));
        _presentNow = () => PresentPending(null, EventArgs.Empty);
        InitializeComponent();
        BuildIdentity.Text = ConsoleBuildInfo.Current.Label + " · Independent AirPlay";
        BuildIdentity.ToolTip = ConsoleBuildInfo.Current.Detail;
        InputTrace.AttachIfRequested(this);
        ActivityList.ItemsSource = _activity;
        PhoneWall.ItemsSource = _wall;
        PhoneWall.DataContext = this;
        GroupFilter.ItemsSource = new[] { "All groups" };
        GroupFilter.SelectedIndex = 0;
        try
        {
            var file = Path.Combine(_dataPath, "settings.json");
            if (File.Exists(file))
            {
                using var d = JsonDocument.Parse(File.ReadAllText(file));
                var saved = JsonValue.Text(d.RootElement, "address");
                if (!string.IsNullOrWhiteSpace(saved)) SavedAddress = saved;
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
        Closed += (_, _) => { _closing = true; _tileStreams.Stop(); _refreshTimer.Stop(); CompositionTarget.Rendering -= PresentPending; _lifetime.Cancel(); _api?.Dispose(); _lifetime.Dispose(); if (_timerRaised) { try { timeEndPeriod(1); } catch { } _timerRaised = false; } };
        UpdateControls();
    }

    public async Task ConnectAsync()
    {
        if (_commandBusy) return;
        ApiClient next;
        try { next = _factory(AddressBox.Text.Trim()); }
        catch (Exception ex) { Log(ex.Message, true); return; }
        _session++; _tileStreams.Stop();
        _lifetime.Cancel(); _lifetime.Dispose(); _lifetime = new();
        _api?.Dispose(); _api = next;
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
        if (_connected)
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
            _mirrorLocal ? Path.Combine(AppContext.BaseDirectory, "data") : null,
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
            : $"iOS {device.Os}   ·   {device.Ip}   ·   {device.VideoStatus}   ·   {device.ControlStatus}";
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
    private void Disconnect_Click(object sender, RoutedEventArgs e)
    {
        if (_commandBusy) return;
        _session++; _tileStreams.Stop(); _lifetime.Cancel(); _api?.Dispose(); _api = null; _connected = false; _castName = "";
        _refreshTimer.Stop();
        ConnectionStatus.Text = "Disconnected";
        _devices.Clear(); DeviceList.ItemsSource = null;
        Totals.Text = "Connect to your iMouse service";
        EmptyList.Text = "Connect to load your iPhones."; EmptyList.Visibility = Visibility.Visible;
        ClearFrame("Disconnected", "Phone mirroring was left unchanged.");
        Log("Console disconnected. Phone mirroring was left unchanged."); UpdateControls();
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
                var group = GroupFilter.SelectedItem as string;
                _filtering = true;
                GroupFilter.ItemsSource = new[] { "All groups" }.Concat(_devices.Select(x => x.Group).Distinct().Order()).ToArray();
                GroupFilter.SelectedItem = (GroupFilter.ItemsSource as string[])!.Contains(group ?? "") ? group : "All groups";
                _filtering = false;
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
    private static string Signature(IEnumerable<Device> items) => JsonSerializer.Serialize(items.Select(x => new { x.Id, x.Name, x.Model, x.Group, x.Ip, x.Os, x.Hardware, x.Online, x.VideoState, x.ReceiverName, x.Width, x.Height, x.Rotation }));

    private void Filter_Changed(object sender, RoutedEventArgs e) { if (IsInitialized && !_filtering) ApplyFilter(Selected?.Id); }
    private void Group_Changed(object sender, SelectionChangedEventArgs e) { if (IsInitialized && !_filtering) ApplyFilter(Selected?.Id); }
    private void ApplyFilter(string? selectedId)
    {
        if (DeviceList is null || SearchBox is null) return;
        var query = SearchBox.Text.Trim(); var group = GroupFilter.SelectedItem as string;
        var visible = _devices.Where(d => (OnlineOnly.IsChecked != true || d.Online) &&
            (group is null or "All groups" || d.Group == group) &&
            (query.Length == 0 || string.Join(" ", d.DisplayName, d.Model, d.Id, d.Ip, d.Group).Contains(query, StringComparison.OrdinalIgnoreCase))).ToList();
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
        ActionPanel.IsEnabled = _connected && !_commandBusy && !_autoBinding && (BatchMode.IsChecked == true ? count > 0 : Selected is not null);
        ConnectButton.IsEnabled = !_commandBusy;
        DisconnectButton.IsEnabled = !_commandBusy && _api is not null;
        RefreshButton.IsEnabled = _api is not null;
        AddressBox.IsEnabled = !_commandBusy;
        SaveFrameButton.IsEnabled = _frame is not null && _frameId == Selected?.Id;
        SyncPumpTarget();
        SyncWall();
        RefreshBindingUi();
        RefreshServiceActionUi();
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
    /// </summary>
    private void ResetJoinedPointers()
    {
        if (!_connected || _api is null || _gesture is not null || _dragLoopRunning) return;
        var ids = BatchMode.IsChecked == true ? InputTargetIds() : "";
        if (ids == _pointersResetFor) return;
        _pointersResetFor = ids;
        if (ids.Length == 0 || !ids.Contains(',')) return;
        _ = SendInputAsync("Pointer reset", "/mouse/reset", new());
    }
    private void ClearFrame(string heading, string message)
    {
        PhoneImage.Source = null; _frame = null; _frameId = null; _frameAt = DateTime.MinValue; _gesture = null;
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
    private async void Preview_Click(object sender, RoutedEventArgs e) => await GrabOneAsync();

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
        _pumpEnabled = AutoPreview?.IsChecked == true && !_autoBinding && _connected && WindowState != WindowState.Minimized;
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
                    await api.ScreenshotIntoAsync(id, false, fetch, _lifetime.Token).ConfigureAwait(false);
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
        if (FrameStatus is null || Selected is not { } device || PhoneImage.Source is not BitmapSource shown) return;
        var target = TargetSize(device, shown);
        // The gap between frames actually reaching the screen, and how many of the last
        // few seconds' intervals ran long. Those are the numbers that move when smoothness
        // moves; an fps average cannot see judder, because 7/60/7/60 averages the same as
        // a steady 33.
        var gaps = _jitter.Summary();
        string pacing = gaps.P50 > 0 ? $" \u00b7 {gaps.P50:0}/{gaps.P95:0} ms p50/p95" + (gaps.Long > 0 ? $" \u00b7 {gaps.Long} slow" : "") : "";
        FrameStatus.Text = $"{_previewFreshness.Status.Text} \u00b7 {_rate.Fps:0.#} updates/s \u00b7 {shown.PixelWidth} \u00d7 {shown.PixelHeight} \u00b7 taps in {(CoordinateSpaceIsImage ? "image pixels" : "iOS points")} {target.W} \u00d7 {target.H}{pacing}";
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
            await api.ScreenshotIntoAsync(device.Id, false, _grabBuffer, _lifetime.Token);
            if (_closing || Selected?.Id != device.Id || epoch != _frameEpoch) return;
            var stamp = _previewFreshness.Observe(epoch, false, _grabBuffer.Metadata, "manual", _grabBuffer.RequestSerial);
            if (stamp is null) return;
            _frame = _grabBuffer; _frameId = device.Id; _frameAt = DateTime.UtcNow;
            var prepared = _live.Prepare(_grabBuffer.Span);
            if (prepared is not null)
            {
                if (_live.Present(prepared) && !ReferenceEquals(PhoneImage.Source, _live.Source)) PhoneImage.Source = _live.Source;
                _live.Recycle(prepared);
            }
            else
            {
                using var stream = new MemoryStream(_grabBuffer.Data, 0, _grabBuffer.Length);
                var decoded = new BitmapImage();
                decoded.BeginInit(); decoded.CacheOption = BitmapCacheOption.OnLoad; decoded.StreamSource = stream; decoded.EndInit(); decoded.Freeze();
                PhoneImage.Source = decoded;
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

    /// <summary>
    /// The service reports two different geometries per phone: the mirror stream
    /// in pixels (imgw/imgh) and the iOS logical screen in points (width/height).
    /// Image search results come back in image pixels, so that is the default for
    /// taps; the selector exists because the documentation does not state which
    /// space /mouse/click expects, and a wrong guess puts taps in the wrong place.
    /// </summary>
    private bool CoordinateSpaceIsImage => (CoordSpace?.SelectedItem as ComboBoxItem)?.Tag as string != "points";
    private (int W, int H) TargetSize(Device d, BitmapSource image)
    {
        if (CoordinateSpaceIsImage) return (image.PixelWidth, image.PixelHeight);
        int w = d.Width, h = d.Height;
        if (w <= 0 || h <= 0) return (image.PixelWidth, image.PixelHeight);
        if ((image.PixelWidth > image.PixelHeight) != (w > h)) (w, h) = (h, w);
        return (w, h);
    }
    /// <summary>MapPreview, but pulls an outside point to the nearest edge. For gestures.</summary>
    private (int X, int Y)? MapPreviewClamped(Point point)
    {
        if (Selected is not { Online: true } d || PhoneImage.Source is not BitmapSource image || _frameId != d.Id) return null;
        var size = TargetSize(d, image);
        return CoordinateMapper.MapClamped(point.X, point.Y, PhoneImage.ActualWidth, PhoneImage.ActualHeight,
                                           image.PixelWidth, image.PixelHeight, size.W, size.H);
    }

    private (int X, int Y)? MapPreview(Point point)
    {
        if (Selected is not { Online: true } d || PhoneImage.Source is not BitmapSource image || _frameId != d.Id || (DateTime.UtcNow - _frameAt).TotalSeconds > 10) return null;
        var size = TargetSize(d, image);
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
    private bool _holdGesture;
    private (int X, int Y)? _dragWanted;
    private bool _dragLoopRunning, _dragRelease, _dragStarted;

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
        var size = TargetSize(Selected, image);
        _gesture = (Selected.Id, _session, mapped.Value.X, mapped.Value.Y, point, size.W, size.H);
        _dragStarted = false; _dragRelease = false; _dragWanted = null; _holdGesture = false;
        // Stop hover tracking. A queued hover move that lands after the button goes down
        // starts the drag from wherever the mouse last rested instead of from the press.
        _wantedPoint = null;
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
        if (seq != _gestureSeq || _gesture is not { } gesture || _dragStarted || _dragLoopRunning) return;
        if (PointerEnabled.IsChecked != true || _api is not { } api || Selected is not { } device
            || device.Id != gesture.Id || _session != gesture.Session) return;
        _holdGesture = true; _dragStarted = true; _dragLoopRunning = true; _dragWanted = null;
        if (PointerReadout is not null) PointerReadout.Text = $"x {gesture.X}, y {gesture.Y} — holding";
        var ids = InputTargetIds();
        _ = Task.Run(() => DragLoopAsync(ids, api, gesture.X, gesture.Y));
    }

    private async void Preview_Up(object sender, MouseButtonEventArgs e) => await EndGestureAsync(e.GetPosition(PhoneImage));

    private async Task EndGestureAsync(Point raw)
    {
        var gesture = _gesture; _gesture = null; PhoneImage.ReleaseMouseCapture();
        if (gesture is null) return;

        if (_dragStarted)
        {
            // Hand the final position to the drag loop and let it release the button. The
            // loop owns ordering, so every queued move lands before /mouse/up and a drag
            // can never finish at a stale coordinate.
            var last = MapPreviewClamped(raw);
            // A long press released where it began must not tack a jittery one-pixel move
            // onto the end of the hold; only a real movement is delivered before release.
            if (last is not null && (raw - gesture.Value.View).Length > DragThreshold) _dragWanted = last;
            _dragRelease = true;
            return;
        }

        if (PointerEnabled.IsChecked != true || Selected?.Id != gesture.Value.Id || _session != gesture.Value.Session) return;
        if (PhoneImage.Source is not BitmapSource image) return;
        if (TargetSize(Selected, image) != (gesture.Value.W, gesture.Value.H)) { Log("Phone orientation changed. Try again.", true); return; }
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
    // What the last drag actually sent, for the mirror test to report. A drag that reaches
    // one phone and not another is invisible from the outside, so record it at the source.
    private string _lastDragIds = "";
    private int _lastDragMoves;
    private int _lastDragX = -1;
    private string _lastDragTrace = "";

    /// <summary>
    /// Runs entirely off the UI thread.
    ///
    /// It did not, and that was the single worst thing about how a drag felt. The loop is
    /// started from a mouse handler, so without ConfigureAwait every await resumed on the
    /// WPF dispatcher - which is simultaneously presenting the live view at thirty frames
    /// a second and painting wall tiles. Each step of the stroke queued behind a render
    /// pass. Measured: a request the service answers in 3.7 ms took 106, 286 and 126 ms,
    /// so a 250 ms swipe reached the phone as two positions and iOS read it as a jump
    /// rather than a swipe. The frame pumps already used ConfigureAwait(false); the input
    /// paths were the ones left behind the paint.
    /// </summary>
    private async Task DragLoopAsync(string ids, ApiClient api, int x, int y)
    {
        var lifetime = _lifetime.Token; var control = _controlCancellation;
        using var inputLifetime = CancellationTokenSource.CreateLinkedTokenSource(lifetime, control.Token);
        var ct = inputLifetime.Token;
        bool pressed = false, hold = _holdGesture, paused = false;
        var held = System.Diagnostics.Stopwatch.StartNew();
        _lastDragIds = ids; _lastDragMoves = 0; _lastDragTrace = ""; _lastDragX = -1;
        try
        {
            // No waiting for the hover pump here. It used to pause up to 100 ms so that an
            // in-flight hover move could not land after the press - but that race is not
            // real: the mouse goes down where it was hovering, so a late hover move carries
            // the same coordinate the press does. Meanwhile the wait sat on the critical
            // path of every drag, and the cost was severe. Measured with it in place, a
            // 250 ms swipe reached the phone as TWO positions - the setup swallowed the
            // first half of the stroke and the newest-wins queue discarded the rest - and
            // iOS read the remainder as a jump rather than a swipe, so the gesture did
            // nothing at all.
            var phase = System.Diagnostics.Stopwatch.StartNew();
            await api.MoveAsync(ids, x, y, ct).ConfigureAwait(false);
            long tMove = phase.ElapsedMilliseconds;
            await api.CommandAsync("/mouse/down", new() { ["id"] = ids, ["button"] = "1" }, ct).ConfigureAwait(false);
            long tDown = phase.ElapsedMilliseconds;
            _lastDragTrace = $"[setup move {tMove} ms, down {tDown - tMove} ms] ";
            pressed = true;
            while (!_dragRelease && !_closing && !ct.IsCancellationRequested)
            {
                var target = _dragWanted; _dragWanted = null;
                if (target is not null)
                {
                    long t0 = phase.ElapsedMilliseconds;
                    await api.MoveAsync(ids, target.Value.X, target.Value.Y, ct).ConfigureAwait(false);
                    _lastDragMoves++; _lastDragX = target.Value.X;
                    if (_lastDragTrace.Length < 400) _lastDragTrace += $"({target.Value.X},{target.Value.Y})+{phase.ElapsedMilliseconds - t0}ms ";
                }
                else await Task.Delay(3, ct).ConfigureAwait(false);
            }
            var final = _dragWanted; _dragWanted = null;
            if (final is not null)
            {
                long tf = phase.ElapsedMilliseconds;
                await api.MoveAsync(ids, final.Value.X, final.Value.Y, ct).ConfigureAwait(false);
                _lastDragMoves++; _lastDragX = final.Value.X;
                if (_lastDragTrace.Length < 400) _lastDragTrace += $"final({final.Value.X},{final.Value.Y})+{phase.ElapsedMilliseconds - tf}ms ";
            }
        }
        catch (OperationCanceledException) when (CancelledHere(lifetime, control)) { }
        catch (Exception ex)
        {
            // A failure or timeout has paused the phones under the lease client, which would
            // only refuse the release below and log that as a second error.
            paused = api.UsesInputOwnership;
            LogAsync("Drag: " + Friendly(ex), true);
        }
        finally
        {
            // The button must come up even if a move failed mid-gesture, or the phone is
            // left with a stuck press and every later tap lands inside a drag.
            // After Stop or cancellation, the kernel has already released all held buttons;
            // sending /mouse/up would be rejected and log a spurious release failure.
            if (pressed && !paused && !ct.IsCancellationRequested && !_controlCancellation.IsCancellationRequested && !_closing)
            {
                try { await api.CommandAsync("/mouse/up", new() { ["id"] = ids, ["button"] = "1" }, ct).ConfigureAwait(false); }
                catch (OperationCanceledException) when (CancelledHere(lifetime, control)) { }
                catch (Exception ex) { LogAsync("Drag release failed: " + Friendly(ex), true); }
                if (hold)
                {
                    // Long presses are deliberate and rare, so say what was held and for how
                    // long; ordinary drags stay quiet, as before, or the log fills with strokes.
                    int count = ids.Count(c => c == ',') + 1;
                    string what = _lastDragMoves > 0 ? "Long press, then drag" : "Long press";
                    LogAsync(count > 1 ? $"{what} ({held.ElapsedMilliseconds} ms) -> {count} phones" : $"{what} ({held.ElapsedMilliseconds} ms)");
                }
            }
            _dragLoopRunning = false; _dragStarted = false; _dragRelease = false; _dragWanted = null;
        }
    }

    private void Preview_LostCapture(object sender, MouseEventArgs e)
    {
        _gesture = null;
        if (_dragStarted) _dragRelease = true;   // losing capture must still lift the button
    }

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
            if (!_dragStarted && !_dragLoopRunning
                && (raw - gesture.View).Length > DragThreshold
                && _api is { } dragApi && Selected is { } dragDevice && dragDevice.Id == gesture.Id)
            {
                _dragStarted = true; _dragLoopRunning = true; _dragWanted = held.Value;
                // The target list must be worked out here, on the UI thread; the loop then
                // runs on the pool so no step of the stroke waits for a render pass.
                var dragIds = InputTargetIds();
                _ = Task.Run(() => DragLoopAsync(dragIds, dragApi, gesture.X, gesture.Y));
            }
            else if (_dragStarted) _dragWanted = held.Value;
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

    // Drives the phone's own pointer so it follows the mouse. A fixed throttle was
    // wrong here twice over: it capped the rate below what the board sustains
    // (measured 44 moves/sec at 10 ms median), and it *discarded* moves that arrived
    // while one was in flight - so the pointer stopped at a stale position whenever
    // the mouse came to rest. This coalesces instead: the newest position always
    // wins, and the last one is always delivered.
    private (int X, int Y)? _wantedPoint;
    private volatile string _wantedIds = "";
    private bool _pumpingPointer;
    private void TrackPointerTo((int X, int Y) point)
    {
        if (!_controlReady) return;
        // While a gesture owns the pointer, the drag loop is the only thing allowed to
        // move it - two writers would fight over the same phone-side cursor.
        if (_gesture is not null || _dragLoopRunning) return;
        // The target list is read here, on the UI thread, because working it out means
        // reading the selection and the tick boxes. The pump itself must never touch them.
        _wantedIds = InputTargetIds();
        _wantedPoint = point;
        if (_pumpingPointer) return;
        _pumpingPointer = true;
        _ = Task.Run(PumpPointerAsync);
    }
    private async Task PumpPointerAsync()
    {
        using var inputLifetime = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token, _controlCancellation.Token);
        var inputToken = inputLifetime.Token;
        // Started on the pool by the caller, for the same reason the drag loop is: a hover
        // move that has to queue behind a render pass arrives after the mouse has moved on.
        try
        {
            while (!_closing && !inputToken.IsCancellationRequested)
            {
                var target = _wantedPoint;
                var api = _api;
                // Address the whole mirror set. Tracking only the master left the followers'
                // pointers wherever they happened to be, so the phones were not in the same
                // state when the click arrived. The list is prepared on the UI thread.
                var ids = _wantedIds;
                if (target is null || api is null || ids.Length == 0) break;
                _wantedPoint = null;
                try { await api.CommandAsync("/mouse/move", new() { ["id"] = ids, ["x"] = target.Value.X, ["y"] = target.Value.Y }, inputToken).ConfigureAwait(false); }
                catch { break; /* Pointer tracking is cosmetic; never interrupt the live view for it. */ }
            }
        }
        finally { _pumpingPointer = false; }
    }

    private void Preview_Leave(object sender, MouseEventArgs e)
    {
        if (PointerReadout is not null) PointerReadout.Text = "Hover the screen to see tap coordinates";
    }

    // ---- control-board binding ----

    private void RefreshServiceActionUi()
    {
        if (StartCastingButton is null || RecoveryRestartButton is null || BoardRestartHelp is null) return;
        void Update(Button button, string function, string normalTip)
        {
            var reason = _api?.UnavailableCommandReason(function);
            button.IsEnabled = _connected && !_commandBusy && reason is null;
            button.ToolTip = reason ?? normalTip;
            ToolTipService.SetShowOnDisabled(button, true);
        }
        Update(CastButton, "/device/airplay/connect", "Ask this phone to start screen mirroring");
        Update(StartCastingButton, "/device/airplay/connect", "Ask the target phones to start screen mirroring");
        Update(DiscButton, "/device/airplay/disconnect", "Stop this phone's screen mirroring");
        Update(StopCastingButton, "/device/airplay/disconnect", "Stop the target phones' screen mirroring");
        Update(RestartButton, "/device/usb/restart", "Restart this phone's control board. Control drops for a few seconds.");
        Update(RecoveryRestartButton, "/device/usb/restart", "Restart the target phones' control boards");
        bool independent = _connected && _api?.UsesInputOwnership == true;
        MirroringActionHelp.Text = ApiClient.MirroringActionUnavailable;
        BoardRestartHelp.Text = ApiClient.BoardRestartUnavailable;
        MirroringActionHelp.Visibility = BoardRestartHelp.Visibility = independent ? Visibility.Visible : Visibility.Collapsed;
    }

    private sealed record BoardOption(Board Board, string Label)
    {
        public override string ToString() => Label;
    }

    /// <summary>A board is a candidate only if no other phone already claims it.</summary>
    private List<Board> FreeBoards(Device? forDevice)
    {
        var claimed = _devices.Where(d => d.Id != forDevice?.Id && d.Hardware.Length > 0).Select(d => d.Hardware).ToHashSet();
        return _boards.Where(b => !claimed.Contains(b.Uid)).OrderByDescending(b => b.PhoneAttached).ThenBy(b => b.Uid).ToList();
    }

    private void RefreshBindingUi()
    {
        if (BoardPicker is null) return;
        var device = Selected;
        if (_api?.LiveBindingEnabled != true || !_connected)
        {
            BoardPicker.IsEnabled = BindButton.IsEnabled = UnbindButton.IsEnabled = AutoBindButton.IsEnabled = false;
            BoardPicker.IsDropDownOpen = false;
            BoardPicker.ItemsSource = null;
            BindStatus.Text = !_connected ? "Connect to view phone and board assignments."
                : (device is null ? "" : device.Hardware.Length == 0 ? "No board assigned. " : $"Bound to {device.Hardware} · {device.ControlStatus}. ")
                    + ApiClient.LiveBindingUnavailable;
            return;
        }
        // Rebuilding an enabled picker while it is open would snap it shut.
        BoardPicker.IsEnabled = !_commandBusy && !_autoBinding;
        if (BoardPicker.IsDropDownOpen) return;
        if (device is null)
        {
            BindStatus.Text = "Select a phone to bind it to a control board.";
            BoardPicker.ItemsSource = null;
            BindButton.IsEnabled = UnbindButton.IsEnabled = false;
            AutoBindButton.IsEnabled = false;
            return;
        }
        var free = FreeBoards(device);
        var options = free.Select(b => new BoardOption(b, b.Uid + (b.PhoneAttached ? "  (phone attached)" : "  (no phone)"))).ToList();
        var keep = (BoardPicker.SelectedItem as BoardOption)?.Board.Uid;
        BoardPicker.ItemsSource = options;
        BoardPicker.SelectedItem = options.FirstOrDefault(o => o.Board.Uid == keep)
            ?? options.FirstOrDefault(o => o.Board.Uid == device.Hardware)
            ?? options.FirstOrDefault(o => o.Board.PhoneAttached);
        BindStatus.Text = device.Hardware.Length == 0
            ? $"Not bound. {options.Count(o => o.Board.PhoneAttached)} board(s) with a phone are free."
            : $"Bound to {device.Hardware} · {device.ControlStatus}";
        bool idle = _connected && !_commandBusy && !_autoBinding;
        BindButton.IsEnabled = idle && BoardPicker.SelectedItem is not null;
        UnbindButton.IsEnabled = idle && device.Hardware.Length > 0;
        AutoBindButton.IsEnabled = idle && _devices.Any(d => d.Online && d.Hardware.Length == 0);
    }

    private async void Bind_Click(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } device || BoardPicker.SelectedItem is not BoardOption option || _api is null) return;
        await ExecuteAsync("Bind board", "/device/set",
            new() { ["vid"] = option.Board.Vid, ["pid"] = option.Board.Pid, ["uid"] = option.Board.Uid }, [device], true);
    }

    private async void Unbind_Click(object sender, RoutedEventArgs e)
    {
        if (Selected is not { } device || _api is null) return;
        await ExecuteAsync("Unbind board", "/device/set",
            new() { ["vid"] = "", ["pid"] = "", ["uid"] = "" }, [device], true);
    }

    /// <summary>
    /// Works out which board drives which phone instead of guessing. With several free
    /// boards there is nothing in the data that links a board to a phone, and a wrong
    /// guess would send that phone's taps to a different handset. So each candidate is
    /// bound in turn, the pointer is moved to a known coordinate, and the phone's own
    /// screen is checked for the pointer appearing there. Only a board that visibly
    /// moves this phone's pointer is kept. Pointer moves are harmless: nothing is tapped.
    /// </summary>
    private async void AutoBind_Click(object sender, RoutedEventArgs e)
    {
        if (_api is null || _autoBinding || _commandBusy) return;
        // Guard the handler as well as its button: stale queued UI actions must
        // not stop video, probe boards or misdiagnose a refused binding as wiring.
        if (!_api.LiveBindingEnabled) { Log(ApiClient.LiveBindingUnavailable, true); RefreshBindingUi(); return; }
        var api = _api; var ct = _lifetime.Token; int session = _session;
        var pending = _devices.Where(d => d.Online && d.Hardware.Length == 0).ToList();
        if (pending.Count == 0) { Log("Every mirroring phone already has a board bound."); return; }

        _autoBinding = true; UpdateControls(); RefreshBindingUi();
        bool wasLive = AutoPreview.IsChecked == true;
        AutoPreview.IsChecked = false;   // the probe needs the frames, not the live loop
        int bound = 0, failed = 0;
        try
        {
            foreach (var device in pending)
            {
                if (ct.IsCancellationRequested || session != _session) break;
                var candidates = FreeBoards(device).Where(b => b.PhoneAttached).ToList();
                Log($"Auto-bind {device.DisplayName}: testing {candidates.Count} board(s)…");
                Board? found = null;
                foreach (var board in candidates)
                {
                    if (ct.IsCancellationRequested || session != _session) break;
                    try
                    {
                        await api.BindAsync(device.Id, board, ct);
                        if (await ReactsToPointerAsync(api, device, ct)) { found = board; break; }
                    }
                    catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
                    catch { /* A board that refuses the probe simply is not this phone's. */ }
                }
                if (found is not null)
                {
                    bound++;
                    Log($"Auto-bind: {device.DisplayName} → board {found.Uid}. Verified by pointer response.");
                }
                else
                {
                    failed++;
                    try { await api.UnbindAsync(device.Id, ct); } catch { }
                    Log($"Auto-bind: no board moved {device.DisplayName}'s pointer. Check its cable, and that AssistiveTouch is on.", true);
                }
            }
            Log($"Auto-bind finished. {bound} bound, {failed} unresolved.", failed > 0);
        }
        finally
        {
            _autoBinding = false;
            AutoPreview.IsChecked = wasLive;
            if (!_closing) { await RefreshDevicesAsync(); UpdateControls(); RefreshBindingUi(); }
        }
    }

    /// <summary>Moves the pointer between two points and reports whether this phone's screen showed it.</summary>
    private static async Task<bool> ReactsToPointerAsync(ApiClient api, Device device, CancellationToken ct)
    {
        int w = device.ImageWidth > 0 ? device.ImageWidth : 500;
        int h = device.ImageHeight > 0 ? device.ImageHeight : 1080;
        int ax = (int)(w * 0.25), ay = (int)(h * 0.30);
        int bx = (int)(w * 0.75), by = (int)(h * 0.70);
        int radius = Math.Max(12, w / 20);

        await api.MoveAsync(device.Id, ax, ay, ct);
        await Task.Delay(450, ct);
        var before = await api.ScreenshotAsync(device.Id, false, ct);
        await api.MoveAsync(device.Id, bx, by, ct);
        await Task.Delay(450, ct);
        var after = await api.ScreenshotAsync(device.Id, false, ct);

        // The pointer must have left A and arrived at B. Requiring both rules out a
        // phone whose screen merely changed on its own while the probe was running.
        double left = FrameRegion.MeanDifference(before, after, ax, ay, radius);
        double arrived = FrameRegion.MeanDifference(before, after, bx, by, radius);
        double control = FrameRegion.MeanDifference(before, after, w / 2, (int)(h * 0.92), radius);
        return left > 1.0 && arrived > 1.0 && Math.Min(left, arrived) > control * 1.6;
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
    private long _tileFrames, _tileFetches, _tileDupes, _tileRestarts;
    private long _tileFetchMs, _tilePrepareMs, _tilePresentMs;
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
                    long t0 = Environment.TickCount64;
                    var result = await _tileFetchScheduler.FetchAsync(
                        ct => api.ScreenshotIntoAsync(stream.Id, false, fetch, ct), stream.Token).ConfigureAwait(false);
                    if (result.Cancelled || !Current()) break;
                    if (!result.Success) throw new IOException("Tile screenshot unavailable.");
                    Interlocked.Increment(ref _tileFetches);
                    Interlocked.Add(ref _tileFetchMs, Environment.TickCount64 - t0);
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
                        long t1 = Environment.TickCount64;
                        var prepared = live.Prepare(previous.Span, Math.Max(48, _tileHeight * 2));
                        Interlocked.Add(ref _tilePrepareMs, Environment.TickCount64 - t1);
                        if (prepared is null)
                        {
                            previous.Length = 0;
                            throw new InvalidDataException("Tile image cannot be decoded.");
                        }
                        long t2 = Environment.TickCount64;
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
                        Interlocked.Add(ref _tilePresentMs, Environment.TickCount64 - t2);
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
        finally { Interlocked.Increment(ref _tileRestarts); _tileStreams.Complete(stream); }
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
    /// Sends one input to the master and every follower in a single request. Kept separate
    /// from ExecuteAsync, which loops per device - that is right for casting (each phone
    /// negotiates its own AirPlay session) but wrong for input, where the whole point is
    /// that every phone receives the same event as close to simultaneously as possible.
    /// </summary>
    private async Task SendInputAsync(string label, string function, Dictionary<string, object> data, bool quiet = false)
    {
        if (!_controlReady) return;
        var lifetime = _lifetime.Token; var control = _controlCancellation;
        using var inputLifetime = CancellationTokenSource.CreateLinkedTokenSource(lifetime, control.Token);
        var api = _api;
        var ids = InputTargetIds();
        if (api is null || !_connected || ids.Length == 0) return;
        int count = ids.Count(c => c == ',') + 1;
        try
        {
            // ConfigureAwait(false): a tap must not wait for the live view to finish
            // painting before it is sent, nor again before it is logged.
            await api.CommandAsync(function, new Dictionary<string, object>(data) { ["id"] = ids }, inputLifetime.Token).ConfigureAwait(false);
            if (!quiet) LogAsync(count > 1 ? $"{label} -> {count} phones" : label);
        }
        catch (OperationCanceledException) when (CancelledHere(lifetime, control)) { }
        catch (InputNotSentException ex) { LogAsync($"{label}: {ex.Message}", true); }
        // A cancellation nobody here asked for is HttpClient's timeout: logged, not swallowed.
        catch (Exception ex) { LogAsync($"{label} failed: {Friendly(ex)}", true); }
    }

    private List<Device> Targets() => BatchMode.IsChecked == true ? _devices.Where(x => x.IsChecked).ToList() : Selected is { } d ? [d] : [];
    private async void Action_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button button || button.Tag is not string tag) return;
        var parts = tag.Split('|'); var targets = Targets();
        var data = new Dictionary<string, object>(); string function;
        switch (parts[0])
        {
            case "cast": function = "/device/airplay/" + parts[1]; break;
            case "swipe": function = "/mouse/swipe"; data["direction"] = parts[1]; data["len"] = 0.75; break;
            case "key": function = "/key/sendkey"; data["fn_key"] = parts[1]; break;
            case "reset": function = "/mouse/reset"; break;
            case "usb": function = "/device/usb/restart"; break;
            default: return;
        }
        if (parts[0] == "cast") { await ExecuteAsync(button.Content.ToString()!, function, data, targets, true); return; }
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
        using var inputLifetime = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token, _controlCancellation.Token);
        int count = ids.Count(c => c == ',') + 1;
        string label = count > 1 ? $"Send text -> {count} phones" : "Send text";
        _sendingText = true;
        try
        {
            var r = await api.SendTextAsync(ids, text, inputLifetime.Token);
            if (r.End == InputEnd.Completed) { Log($"{label}: {r.Total} characters in {r.Chunks} chunk(s)"); return; }
            string progress = $"{r.ConfirmedCharacters} of {r.Total} characters confirmed.";
            string partial = r.Sent > r.Confirmed ? $" Chunk {r.Sent} of {r.Chunks} may be partly typed and was not retried." : "";
            string rest = r.Sent == r.Chunks ? "" : r.Sent == 0 ? " No chunk was sent."
                : r.Sent + 1 == r.Chunks ? $" Chunk {r.Chunks} was not sent." : $" Chunks {r.Sent + 1}–{r.Chunks} were not sent.";
            switch (r.End)
            {
                case InputEnd.Cancelled: Log($"{label} stopped: {progress}{partial}{rest}", true); break;
                // The lease client's pause notice shows Input paused and enables Resume.
                case InputEnd.TimedOut: Log($"{label} timed out: {progress}{partial}{rest} Check the phone before continuing.", true); break;
                default: Log($"{label} failed: {progress}{partial}{rest} {Friendly(r.Failure!)}", true); break;
            }
        }
        finally { _sendingText = false; }
    }
    private async Task ExecuteAsync(string label, string function, Dictionary<string, object> data, List<Device> targets, bool allowOffline)
    {
        if (_commandBusy || !_connected || _api is null || targets.Count == 0) return;
        _commandBusy = true; UpdateControls();
        var api = _api; var ct = _lifetime.Token; int session = _session;
        int success = 0, failed = 0, skipped = 0;
        Log($"{label}: working on {targets.Count} phone(s)…");
        try
        {
            foreach (var device in targets)
            {
                if (ct.IsCancellationRequested || session != _session) break;
                if (!allowOffline && !device.Online) { skipped++; continue; }
                var payload = new Dictionary<string, object>(data) { ["id"] = device.Id };
                try { await api.CommandAsync(function, payload, ct); success++; }
                catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
                catch (Exception ex) { failed++; Log($"{label}, target {success + failed + skipped}/{targets.Count}: {Friendly(ex)}", true); }
            }
            if (!_closing && session == _session) Log($"{label}: {success} succeeded, {failed} failed, {skipped} offline skipped.", failed > 0 || skipped > 0);
        }
        finally { _commandBusy = false; if (!_closing) UpdateControls(); }
        if (!_closing && session == _session) { await RefreshDevicesAsync(); }
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

    /// <summary>
    /// Runs the real live pipeline against the running service for a few seconds and
    /// records the frame rate actually presented to the screen. Smoothness is the whole
    /// point of the render path, so it is measured rather than asserted.
    /// </summary>
    /// <summary>
    /// Drives the real mirroring path against the live service and records what the app
    /// actually addresses. The protocol was already proven to work with an id list, so if
    /// mirroring misbehaves the fault is in this app's own targeting - which is what this
    /// exercises: the same Followers/InputTargetIds/SendInputAsync the mouse handlers use.
    /// </summary>
    public async Task RunMirrorAsync()
    {
        var report = new List<object>();
        void Note(string step, object detail) => report.Add(new { step, detail });

        await ConnectAsync();
        if (!_connected) throw new Exception("mirror test could not reach the service.");
        await Task.Delay(800);
        await RefreshDevicesAsync();

        Note("devices", _devices.Select(d => new
        {
            d.Id, d.DisplayName, d.Online, d.BoardState, d.ControlReady,
            geometry = $"{d.ImageWidth}x{d.ImageHeight}", d.Hardware
        }).ToList());

        var master = Selected;
        Note("master", master?.Id ?? "(none)");
        Note("beforeAnyChecks", new { batch = BatchMode.IsChecked, followers = Followers().Count, ids = InputTargetIds() });

        // exactly what the "Mirror to all" tick box does
        SelectAllBox.IsChecked = true;
        SelectAll_Click(SelectAllBox, new RoutedEventArgs());
        await Task.Delay(300);

        Note("afterMirrorToAll", new
        {
            batch = BatchMode.IsChecked,
            checkedDevices = _devices.Count(d => d.IsChecked),
            followers = Followers().Count,
            followerIds = Followers().Select(d => d.Id).ToList(),
            mismatched = MismatchedFollowers().Select(d => new { d.Id, geometry = $"{d.ImageWidth}x{d.ImageHeight}" }).ToList(),
            ids = InputTargetIds()
        });

        // send a real mirrored input through the same method the handlers use
        int before = _activity.Count;
        await SendInputAsync("MirrorTest Home", "/key/sendkey", new() { ["fn_key"] = "Home" });
        await Task.Delay(600);
        Note("sendInputLog", _activity.Take(Math.Max(1, _activity.Count - before)).ToList());

        // and the drag path: DragLoopAsync is handed the id list up front
        Note("dragWouldAddress", InputTargetIds());

        // --- end to end on the real phones ---
        // Everything above proves the app addresses the right ids. This part drives the
        // actual mouse handlers against the rack and reads the phones back, because the
        // question the id list cannot answer is whether the gesture reached the glass.
        var content = (FrameworkElement)Content;
        content.Measure(new Size(1370, 880)); content.Arrange(new Rect(0, 0, 1370, 880)); content.UpdateLayout();
        await GrabOneAsync();
        content.UpdateLayout();

        // "Did the phone react?" cannot be answered by comparing screenshots byte for byte:
        // a mirrored screen never repeats exactly - the clock, the AirPlay encoder and the
        // wallpaper parallax all move on their own, so an untouched phone fails an equality
        // test just as reliably as a tapped one. Mean pixel difference over the whole frame
        // separates them: idle noise sits near zero, a screen that actually changed does not.
        async Task<Dictionary<string, byte[]>> Shots()
        {
            var map = new Dictionary<string, byte[]>();
            foreach (var d in _devices.Where(x => x.Online))
            {
                try { map[d.Id] = await _api!.ScreenshotAsync(d.Id, false, _lifetime.Token); }
                catch { }
            }
            return map;
        }
        List<object> Reacted(Dictionary<string, byte[]> before, Dictionary<string, byte[]> after) =>
            _devices.Where(d => d.Online).Select(d => (object)new
            {
                d.Id,
                diff = before.TryGetValue(d.Id, out var b) && after.TryGetValue(d.Id, out var a)
                    ? Math.Round(FrameRegion.MeanDifference(b, a, d.ImageWidth / 2, d.ImageHeight / 2, Math.Max(d.ImageWidth, d.ImageHeight)), 2)
                    : -1
            }).ToList();

        // Two Home presses, not one: the first leaves an app, the second returns to the
        // first home page. Without that the phones drift onto different pages and the
        // same coordinate stops meaning the same thing on each of them - which looks
        // exactly like broken mirroring when it is really an unequal starting state.
        async Task NormaliseAsync()
        {
            await SendInputAsync("MirrorTest Home", "/key/sendkey", new() { ["fn_key"] = "Home" }, quiet: true);
            await Task.Delay(900);
            await SendInputAsync("MirrorTest Home", "/key/sendkey", new() { ["fn_key"] = "Home" }, quiet: true);
            await Task.Delay(1600);
        }

        // How long does one input request take from inside this app, with its own frame
        // pumps running and with them stopped? The service itself answers a move in about
        // 1-3 ms even while both phones are being polled flat out, so any difference here
        // is this process's own doing.
        async Task<object> MoveLatency(string label)
        {
            var lat = new List<double>();
            for (int i = 0; i < 25; i++)
            {
                var w = System.Diagnostics.Stopwatch.StartNew();
                try { await _api!.MoveAsync(InputTargetIds(), 100 + i * 4, 500, _lifetime.Token); }
                catch { continue; }
                lat.Add(w.Elapsed.TotalMilliseconds);
                await Task.Delay(18);
            }
            lat.Sort();
            return new { label, p50 = Math.Round(lat[lat.Count / 2], 1), p95 = Math.Round(lat[(int)(lat.Count * .95)], 1), max = Math.Round(lat[^1], 1) };
        }
        Note("inputLatencyWithPumps", await MoveLatency("pumps running"));
        AutoPreview.IsChecked = false;
        SyncPumpTarget();
        await Task.Delay(600);
        Note("inputLatencyPumpsIdle", await MoveLatency("pumps idle"));
        AutoPreview.IsChecked = true;
        SyncPumpTarget();
        await Task.Delay(600);

        double pw = PhoneImage.ActualWidth, ph = PhoneImage.ActualHeight;
        Note("preview", new { frame = _frame is not null, frameId = _frameId, width = pw, height = ph, pointerEnabled = PointerEnabled.IsChecked });

        if (_frame is not null && pw > 0 && ph > 0)
        {
            // 0. a control run. "The screenshot changed" only means "the gesture landed" if
            //    an untouched phone holds still for the same interval - a clock tick or a
            //    stray animation would otherwise read as a reaction on every phone.
            await NormaliseAsync();
            var quiet = await Shots();
            await Task.Delay(2000);
            Note("quietControl", Reacted(quiet, await Shots()));

            // 1. a tap, mirrored. The target is the Clock icon on the stock home screen -
            //    an app with no network or account side effects that repaints the whole
            //    screen when it opens, so "the tap landed" is unmistakable in the numbers.
            //    Note the release point is deliberately a couple of pixels off the press
            //    point: that difference is what used to move the tap.
            await NormaliseAsync();
            var beforeTap = await Shots();
            BeginGesture(new Point(pw * 0.845, ph * 0.232));
            await EndGestureAsync(new Point(pw * 0.845 + 2, ph * 0.232 + 2));
            await Task.Delay(2500);
            Note("mirroredTap", Reacted(beforeTap, await Shots()));

            // 2. the stroke that runs off the edge of the picture - the one that used to
            //    freeze half way, and the reason the clamping mapper exists.
            //
            //    Two things are checked, and neither depends on what the phones happen to
            //    be showing. First, what the app SENDS: the delivered coordinate must be
            //    the clamped edge, addressed to every mirrored phone. Second, whether the
            //    stroke reached the glass: measured as the change in a small box around the
            //    coordinate the stroke ended on, which is where each phone's pointer must
            //    now be sitting.
            //
            //    Earlier versions of this probe watched for a home-page flip or for Control
            //    Centre to open, and both were unreliable for the same reason: a phone
            //    already on its last page, or an edge gesture iOS declined to recognise,
            //    looks exactly like mirroring having dropped that phone. The pointer is the
            //    honest signal - it moves whether or not iOS does anything with the touch.
            await NormaliseAsync();
            var beforeStroke = await Shots();
            BeginGesture(new Point(pw * 0.82, ph * 0.55));
            for (int i = 1; i <= 14; i++)
            {
                // the last points deliberately lie well outside the picture
                TrackGesture(new Point(pw * 0.82 - pw * 0.95 * i / 14.0, ph * 0.55), true);
                await Task.Delay(16);
            }
            await EndGestureAsync(new Point(-40, ph * 0.55));
            for (int i = 0; _dragLoopRunning && i < 300; i++) await Task.Delay(10);
            await Task.Delay(1200);
            var afterStroke = await Shots();

            int endX = Math.Max(0, _lastDragX), endY = (int)(0.55 * (Selected?.ImageHeight ?? 1080));
            Note("strokePastTheEdge", new
            {
                ids = _lastDragIds,
                addressedEveryMirroredPhone = _lastDragIds == InputTargetIds(),
                lastDeliveredX = _lastDragX,
                clampedToTheEdge = _lastDragX == 0,
                trace = _lastDragTrace,
                // A whole-frame diff drowns a pointer dot a few pixels across, so look only
                // where the stroke ended. This is the same measurement auto-bind uses.
                pointerArrived = _devices.Where(d => d.Online).Select(d => (object)new
                {
                    d.Id,
                    boxDiff = beforeStroke.TryGetValue(d.Id, out var b0) && afterStroke.TryGetValue(d.Id, out var a0)
                        ? Math.Round(FrameRegion.MeanDifference(b0, a0, endX, endY, 45), 2) : -1
                }).ToList()
            });

            await NormaliseAsync();

            // Both phones should now be showing the same thing. If they are not, every
            // coordinate-based comparison above was measuring divergent state, so say so.
            var settled = await Shots();
            var master0 = settled.Values.FirstOrDefault();
            Note("phonesAgreeAfterReset", _devices.Where(d => d.Online).Select(d => (object)new
            {
                d.Id,
                vsMaster = master0 is null || !settled.TryGetValue(d.Id, out var mine) ? -1
                    : Math.Round(FrameRegion.MeanDifference(master0, mine, d.ImageWidth / 2, d.ImageHeight / 2, Math.Max(d.ImageWidth, d.ImageHeight)), 2)
            }).ToList());
        }

        var qa = Path.Combine(AppContext.BaseDirectory, "qa"); Directory.CreateDirectory(qa);
        File.WriteAllText(Path.Combine(qa, "mirror.json"),
            JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
    }

    /// <summary>
    /// Measures the master view and the wall tiles together, while the phones are actually
    /// moving. A still home screen is the wrong thing to benchmark: the source emits almost
    /// no new frames, so every rate looks the same and the numbers say nothing about what
    /// swiping feels like. This drives a continuous mirrored swipe throughout.
    /// </summary>
    public async Task RunWallAsync(int tileMs = 0)
    {
        await ConnectAsync();
        if (!_connected) throw new Exception("wall test could not reach the service.");
        await Task.Delay(800);
        await RefreshDevicesAsync();
        if (Selected is null) throw new Exception("wall test found no mirroring phone.");

        SelectAllBox.IsChecked = true;
        SelectAll_Click(SelectAllBox, new RoutedEventArgs());
        AutoPreview.IsChecked = true;
        var content = (FrameworkElement)Content;
        content.Measure(new Size(1370, 880)); content.Arrange(new Rect(0, 0, 1370, 880)); content.UpdateLayout();
        if (tileMs > 0) _tilePeriodMs = tileMs;
        SyncPumpTarget();
        StartPump();
        await Task.Delay(2500);           // let both pumps settle and the tiles appear

        var api = _api!;
        var ids = InputTargetIds();
        int w = Selected.ImageWidth, h = Selected.ImageHeight;
        bool running = true;

        // Continuous motion: swipe between home pages, alternating direction so the phones
        // end where they started.
        async Task Motion()
        {
            bool forward = true;
            while (running && !_closing)
            {
                try
                {
                    int from = forward ? (int)(w * 0.85) : (int)(w * 0.15);
                    int to = forward ? (int)(w * 0.15) : (int)(w * 0.85);
                    await api.MoveAsync(ids, from, h / 2, _lifetime.Token);
                    await api.CommandAsync("/mouse/down", new() { ["id"] = ids, ["button"] = "1" }, _lifetime.Token);
                    for (int i = 1; i <= 12; i++)
                    {
                        await api.MoveAsync(ids, from + (to - from) * i / 12, h / 2, _lifetime.Token);
                        await Task.Delay(12);
                    }
                    await api.CommandAsync("/mouse/up", new() { ["id"] = ids, ["button"] = "1" }, _lifetime.Token);
                    forward = !forward;
                    await Task.Delay(500);
                }
                catch { await Task.Delay(200); }
            }
        }
        var motion = Motion();

        await Task.Delay(1200);
        long masterStart = _live.Frames, tileStart = _tileFrames;
        long fetchStart = _tileFetches, dupeStart = _tileDupes;
        long allocStart = GC.GetTotalAllocatedBytes();
        int g0 = GC.CollectionCount(0), g1 = GC.CollectionCount(1), g2 = GC.CollectionCount(2);
        var pauseStart = GC.GetTotalPauseDuration();
        // Watch the tiles' geometry for the whole run. This is the same measurement that
        // caught the wall jittering - taken from a screen recording then, taken from the
        // live layout now - so a tile that resizes itself again will show up here.
        var widths = new HashSet<double>();
        var lefts = new HashSet<double>();
        bool watching = true;
        async Task WatchGeometry()
        {
            while (watching && !_closing)
            {
                await Dispatcher.InvokeAsync(() =>
                {
                    foreach (var t in _wall)
                        if (PhoneWall.ItemContainerGenerator.ContainerFromItem(t) is FrameworkElement box && box.ActualWidth > 0)
                        {
                            widths.Add(Math.Round(box.ActualWidth, 2));
                            lefts.Add(Math.Round(box.TranslatePoint(new Point(0, 0), PhoneWall).X, 2));
                        }
                });
                await Task.Delay(50);
            }
        }
        var watcher = WatchGeometry();

        var clock = System.Diagnostics.Stopwatch.StartNew();
        await Task.Delay(10000);
        clock.Stop();
        watching = false;
        try { await watcher; } catch { }
        double seconds = clock.Elapsed.TotalSeconds;
        long masterDrawn = _live.Frames - masterStart, tileDrawn = _tileFrames - tileStart;
        int tiles = Math.Max(1, _wall.Count);

        running = false;
        try { await motion; } catch { }
        await SendInputAsync("WallTest Home", "/key/sendkey", new() { ["fn_key"] = "Home" }, quiet: true);

        var gaps = _jitter.Summary();
        var qa = Path.Combine(AppContext.BaseDirectory, "qa"); Directory.CreateDirectory(qa);
        File.WriteAllText(Path.Combine(qa, $"wall-{_tilePeriodMs}.json"), JsonSerializer.Serialize(new
        {
            phonesOnWall = _wall.Count,
            mirroring = Followers().Count,
            seconds = Math.Round(seconds, 2),
            masterFps = Math.Round(masterDrawn / seconds, 1),
            tileFpsEach = Math.Round(tileDrawn / seconds / tiles, 1),
            tileFramesTotal = tileDrawn,
            distinctTileWidths = widths.OrderBy(x => x).ToList(),
            distinctTileLefts = lefts.OrderBy(x => x).ToList(),
            tileFetchesPerSec = Math.Round((_tileFetches - fetchStart) / seconds, 1),
            tileDuplicatesSkipped = _tileDupes - dupeStart,
            tilePumpsAlive = _tileStreams.RunningCount,
            tilePumpExits = _tileRestarts,
            avgFetchMs = _tileFetches > 0 ? Math.Round((double)_tileFetchMs / _tileFetches, 1) : 0,
            avgPrepareMs = tileDrawn > 0 ? Math.Round((double)_tilePrepareMs / tileDrawn, 1) : 0,
            avgPresentMs = tileDrawn > 0 ? Math.Round((double)_tilePresentMs / tileDrawn, 1) : 0,
            masterPresentP50Ms = Math.Round(gaps.P50, 1),
            masterPresentP95Ms = Math.Round(gaps.P95, 1),
            allocatedMbPerSec = Math.Round((GC.GetTotalAllocatedBytes() - allocStart) / seconds / 1e6, 1),
            gen0 = GC.CollectionCount(0) - g0,
            gen1 = GC.CollectionCount(1) - g1,
            gen2 = GC.CollectionCount(2) - g2,
            gcPauseMs = Math.Round((GC.GetTotalPauseDuration() - pauseStart).TotalMilliseconds, 1),
            tilePeriodMs = _tilePeriodMs,
            tileHeight = _tileHeight,
            at = DateTime.Now
        }, new JsonSerializerOptions { WriteIndented = true }));
    }

    public async Task RunFpsAsync()
    {
        await ConnectAsync();
        if (!_connected) throw new Exception("fps test could not reach the service.");
        if (Selected is null) throw new Exception("fps test found no mirroring phone to measure.");
        AutoPreview.IsChecked = true;
        SyncPumpTarget();
        StartPump();

        await Task.Delay(1500);                 // let the pump settle
        _rate.Reset(); _jitter.Reset();
        long start = _live.Frames;
        // Every screenshot is a fresh 1.6 MB array, which is over the 85 KB large-object
        // threshold, so each frame is a Large Object Heap allocation. Record what that
        // costs: gen-2 collections are what turn a steady stream into a stuttering one.
        long allocStart = GC.GetTotalAllocatedBytes();
        int g0 = GC.CollectionCount(0), g1 = GC.CollectionCount(1), g2 = GC.CollectionCount(2);
        var pauseStart = GC.GetTotalPauseDuration();
        var clock = System.Diagnostics.Stopwatch.StartNew();
        var samples = new List<double>();
        for (int i = 0; i < 16; i++) { await Task.Delay(500); samples.Add(_rate.Fps); }
        clock.Stop();

        long drawn = _live.Frames - start;
        double seconds = clock.Elapsed.TotalSeconds;
        double average = seconds > 0 ? drawn / seconds : 0;
        var ordered = samples.Order().ToList(); // Keep zero-update samples; do not hide pauses.
        double worst = ordered.Count > 0 ? ordered[0] : 0;
        double median = ordered.Count > 0 ? ordered[ordered.Count / 2] : 0;

        var qa = Path.Combine(AppContext.BaseDirectory, "qa"); Directory.CreateDirectory(qa);
        File.WriteAllText(Path.Combine(qa, "fps.json"), JsonSerializer.Serialize(new
        {
            device = Selected?.DisplayName,
            framesPresented = drawn,
            allocatedMbPerSec = seconds > 0 ? Math.Round((GC.GetTotalAllocatedBytes() - allocStart) / seconds / 1e6, 1) : 0,
            gen0 = GC.CollectionCount(0) - g0,
            gen1 = GC.CollectionCount(1) - g1,
            gen2 = GC.CollectionCount(2) - g2,
            gcPauseMs = Math.Round((GC.GetTotalPauseDuration() - pauseStart).TotalMilliseconds, 1),
            wallTiles = _wall.Count,
            seconds = Math.Round(seconds, 2),
            averageFps = Math.Round(average, 1),
            medianFps = Math.Round(median, 1),
            worstFps = Math.Round(worst, 1),
            // Pacing, not just throughput. A run with the same averageFps but a larger
            // p95 or a non-zero longIntervals count will look worse on screen, and that
            // is the difference this build set out to remove.
            presentIntervalP50Ms = Math.Round(_jitter.Summary().P50, 1),
            presentIntervalP95Ms = Math.Round(_jitter.Summary().P95, 1),
            presentIntervalMaxMs = Math.Round(_jitter.Summary().Max, 1),
            longIntervals = _jitter.Summary().Long,
            sinceLastPresentationMs = _jitter.SinceLastMs,
            metricScope = "WPF bitmap updates after pixel deduplication; not physical display scans or receiver freshness",
            pollIntervalMs = _pollInterval,
            framePeriodMs = _framePeriod,
            imageSize = $"{_live.Width}x{_live.Height}",
            at = DateTime.Now
        }, new JsonSerializerOptions { WriteIndented = true }));
    }

    public async Task RunSmokeAsync(bool fake, TestHandler? handler = null)
    {
        await ConnectAsync();
        _refreshTimer.Stop();
        if (!_connected) throw new Exception("Smoke test could not connect to the service.");
        if (_devices.Count == 0) throw new Exception("Smoke test received no devices.");
        DeviceList.SelectedItem = _devices.First();
        await GrabOneAsync();
        if (fake && _frame is null) throw new Exception("Preview did not render from a valid image response.");
        var content = (FrameworkElement)Content;
        content.Measure(new Size(1370, 880)); content.Arrange(new Rect(0, 0, 1370, 880)); content.UpdateLayout();
        // Let the wall pumps deliver a frame or two first, so the render shows the app as
        // an operator sees it rather than a half-populated wall.
        await Task.Delay(900);
        content.UpdateLayout();
        var bitmap = new RenderTargetBitmap(1370, 880, 96, 96, PixelFormats.Pbgra32); bitmap.Render(content);
        var qa = Path.Combine(AppContext.BaseDirectory, "qa"); Directory.CreateDirectory(qa);
        using (var stream = File.Create(Path.Combine(qa, fake ? "ui-preview.png" : "live-offline.png"))) { var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap)); encoder.Save(stream); }
        if (fake)
        {
            content.Measure(new Size(1052, 700)); content.Arrange(new Rect(0, 0, 1052, 700)); content.UpdateLayout();
            var small = new RenderTargetBitmap(1052, 700, 96, 96, PixelFormats.Pbgra32); small.Render(content);
            using var stream = File.Create(Path.Combine(qa, "ui-minimum.png")); var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(small)); encoder.Save(stream);
        }
        File.WriteAllText(Path.Combine(qa, fake ? "ui-smoke.json" : "live-smoke.json"), JsonSerializer.Serialize(new { connected = _connected, devices = _devices.Count, online = _devices.Count(x => x.Online), frameDecoded = _frame is not null, inputCommandsSent = 0, at = DateTime.Now }, new JsonSerializerOptions { WriteIndented = true }));
        if (fake && handler is not null) await CheckInteractionsAsync(handler, qa);
    }

    private async Task CheckInteractionsAsync(TestHandler handler, string qa)
    {
        var passed = new List<string>();
        void Check(string name, bool value) { if (!value) throw new Exception("UI check failed: " + name); passed.Add(name); }
        async Task Click(string tag)
        {
            Action_Click(new Button { Tag = tag, Content = tag }, new RoutedEventArgs());
            for (int i = 0; (_commandBusy || _refreshSession >= 0) && i < 100; i++) await Task.Delay(20);
            if (_commandBusy) throw new Exception("Command did not complete during UI test.");
        }
        // The operator's console reads %APPDATA%\iMouse2 on every launch; a test run must not be able to change it.
        var operatorData = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "iMouse2");
        Check("The test run's data folder is not the operator's %APPDATA%\\iMouse2",
            !string.Equals(Path.GetFullPath(_dataPath).TrimEnd('\\'), Path.GetFullPath(operatorData).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase));
        var testSettings = Path.Combine(_dataPath, "settings.json");
        Check("Connecting saves settings into the test's own data folder", File.Exists(testSettings));
        string SavedTheme() { using var d = JsonDocument.Parse(File.ReadAllText(testSettings)); return JsonValue.Text(d.RootElement, "theme"); }
        var mirror = Path.Combine(AppContext.BaseDirectory, "data", "settings.json");
        var mirrorStamp = File.GetLastWriteTimeUtc(mirror);
        Theme_Click(ThemeButton, new RoutedEventArgs());
        Check("A theme change during a test is saved to the test's data folder", SavedTheme() == (Theme.IsNight ? "night" : "light"));
        Theme_Click(ThemeButton, new RoutedEventArgs());
        Check("A test run does not rewrite the settings mirror beside the exe", File.GetLastWriteTimeUtc(mirror) == mirrorStamp);
        // Hover tracking: on unless a settings file turns it off, and a file without the key is
        // written back exactly as before, so the operator's file never gains it.
        var trackDir = Path.Combine(_dataPath, "track-pointer-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(trackDir);
        var trackFile = Path.Combine(trackDir, "settings.json");
        File.WriteAllText(trackFile, "{\"address\":\"http://localhost:9923\",\"theme\":\"light\",\"trackPointer\":false}");
        var off = new MainWindow(_factory, trackDir);
        Check("A settings file can turn hover tracking off before connecting", off.TrackPointer.IsChecked == false);
        off.SaveSettings();
        Check("A saved trackPointer setting is kept when settings are saved",
            File.ReadAllText(trackFile) == "{\"address\":\"http://localhost:9923\",\"theme\":\"light\",\"trackPointer\":false}");
        off.Close();
        File.WriteAllText(trackFile, "{\"address\":\"http://localhost:9923\",\"theme\":\"light\"}");
        var on = new MainWindow(_factory, trackDir);
        Check("Hover tracking stays on by default", on.TrackPointer.IsChecked == true);
        on.SaveSettings();
        Check("A settings file without trackPointer is saved without it",
            File.ReadAllText(trackFile) == "{\"address\":\"http://localhost:9923\",\"theme\":\"light\"}");
        on.Close();
        Directory.Delete(trackDir, true);
        AutoPreview.IsChecked = false;
        Check("Footer uses live receiver names, not a stale imserver name",
            StatusInfo.Text.Contains("iMouse2-C24C") && StatusInfo.Text.Contains("iMouse2-C241") && !StatusInfo.Text.Contains("C214"));
        DeviceList.SelectedItem = _devices[1];
        UpdateControls();
        Check("Footer keeps live names after selection change",
            StatusInfo.Text.Contains("iMouse2-C24C") && StatusInfo.Text.Contains("iMouse2-C241") && !StatusInfo.Text.Contains("C214"));
        DeviceList.SelectedItem = _devices[0];
        Check("Default control scope is single phone", BatchMode.IsChecked != true);
        _devices[1].IsChecked = true;
        await Click("key|Home");
        Check("Checked phone does not change single target", handler.Commands.Count == 1 && handler.Commands[0].GetProperty("data").GetProperty("id").GetString() == "TEST:01");
        Check("Home button uses documented hotkey", handler.Commands[0].GetProperty("fun").GetString() == "/key/sendkey" && handler.Commands[0].GetProperty("data").GetProperty("fn_key").GetString() == "Home");
        BatchMode.IsChecked = true;
        await Click("swipe|up");
        // Mirroring is master-plus-followers, so the master is always addressed; the
        // invariant worth asserting is that an offline follower never is. Checking the id
        // list beats checking a log line, which is what the previous version did.
        Check("Offline follower is not addressed by a mirrored input",
            handler.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01");
        // --- master / mirror ---
        // TEST:04 is online, same 500x1080 mirror geometry, board attached: a valid follower.
        // TEST:05 is online with a board but 375x812: excluded, because an identical
        // coordinate on a different-sized screen is not the same place.
        foreach (var d in _devices) d.IsChecked = false;
        DeviceList.SelectedItem = _devices.First(d => d.Id == "TEST:01");
        _devices.First(d => d.Id == "TEST:04").IsChecked = true;
        BatchMode.IsChecked = true;
        UpdateControls();
        int beforeMirror = handler.Commands.Count;
        await Click("key|Home");
        var mirrored = handler.Commands[^1].GetProperty("data").GetProperty("id").GetString()!;
        Check("Mirrored input is a single request, not one per phone", handler.Commands.Count == beforeMirror + 1);
        Check("Mirrored input addresses master and follower", mirrored == "TEST:01,TEST:04");
        Check("Master is named first in the mirror target list", mirrored.StartsWith("TEST:01"));

        _devices.First(d => d.Id == "TEST:05").IsChecked = true;
        UpdateControls();
        await Click("key|Home");
        var withOdd = handler.Commands[^1].GetProperty("data").GetProperty("id").GetString()!;
        Check("A differently sized phone is excluded from mirroring", !withOdd.Contains("TEST:05"));
        Check("Excluded followers are reported, not dropped silently",
            MirrorWarning.Visibility == Visibility.Visible && MirrorWarning.Text.Contains("different screen size"));

        _devices.First(d => d.Id == "TEST:02").IsChecked = true;   // offline
        UpdateControls();
        await Click("key|Home");
        Check("An offline follower never joins the mirror set",
            !handler.Commands[^1].GetProperty("data").GetProperty("id").GetString()!.Contains("TEST:02"));

        BatchMode.IsChecked = false;
        UpdateControls();
        await Click("key|Home");
        Check("Mirroring off sends to the master alone",
            handler.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01");

        foreach (var d in _devices) d.IsChecked = false;
        UpdateControls();

        // --- the action strip follows the mirror set ---
        // Reset and Home sit next to the master, so it would be easy to assume they are
        // "master only". They are not: they go through the same mirrored path as a tap, and
        // with Mirror to all on, one click is a rack-wide action.
        foreach (var d in _devices) d.IsChecked = false;
        DeviceList.SelectedItem = _devices.First(d => d.Id == "TEST:01");
        BatchMode.IsChecked = false;
        UpdateControls();
        await Click("reset|mouse");
        Check("Strip Reset alone targets only the master",
            handler.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01" &&
            handler.Commands[^1].GetProperty("fun").GetString() == "/mouse/reset");
        Check("Strip target caption is hidden with no followers", StripTarget.Visibility != Visibility.Visible);

        _devices.First(d => d.Id == "TEST:04").IsChecked = true;
        BatchMode.IsChecked = true;
        UpdateControls();
        await Click("reset|mouse");
        Check("Strip Reset reaches every mirrored phone",
            handler.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04");
        await Click("key|Home");
        Check("Strip Home reaches every mirrored phone",
            handler.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04" &&
            handler.Commands[^1].GetProperty("data").GetProperty("fn_key").GetString() == "Home");
        Check("Strip says how many phones it will hit", StripTarget.Visibility == Visibility.Visible && StripTarget.Text.Contains("2 phones"));

        Check("Strip Restart is wired to a board restart", RestartButton.Tag as string == "usb|restart");
        Check("Strip Lock is wired to the lock hotkey", LockButton.Tag as string == "key|TAB+l");
        Check("Strip Ctrl Bar is wired to Control Centre", CtrlBarButton.Tag as string == "key|ControlBar");
        Check("Strip KB is wired to the on-screen keyboard", KeyboardButton.Tag as string == "key|OPENKeyboard");
        Check("Strip Cast is wired to airplay connect", CastButton.Tag as string == "cast|connect");
        Check("Strip App is wired to the app switcher", AppButton.Tag as string == "key|AppSwitch");
        Check("Strip IME is wired to the input-method switch", ImeButton.Tag as string == "key|SwitchIme");
        Check("Strip Disc is wired to airplay disconnect", DiscButton.Tag as string == "cast|disconnect");

        await Click("usb|restart");
        Check("Strip Restart restarts the board on every mirrored phone",
            handler.Commands[^1].GetProperty("fun").GetString() == "/device/usb/restart" &&
            handler.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04");
        foreach (var (tag, fn, key) in new (string Tag, string Fun, string Key)[]
        {
            ("key|TAB+l", "/key/sendkey", "TAB+l"),
            ("key|ControlBar", "/key/sendkey", "ControlBar"),
            ("key|OPENKeyboard", "/key/sendkey", "OPENKeyboard"),
            ("key|AppSwitch", "/key/sendkey", "AppSwitch"),
            ("key|SwitchIme", "/key/sendkey", "SwitchIme"),
        })
        {
            await Click(tag);
            Check($"Strip {key} reaches every mirrored phone",
                handler.Commands[^1].GetProperty("fun").GetString() == fn &&
                handler.Commands[^1].GetProperty("data").GetProperty("fn_key").GetString() == key &&
                handler.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04");
        }

        // Cast and Disc cannot use the input id list: starting a mirror has to reach a
        // phone that is not mirroring yet, and each AirPlay session is its own handshake.
        int beforeStripCast = handler.Commands.Count;
        await Click("cast|connect");
        var stripCast = handler.Commands.Skip(beforeStripCast).ToList();
        Check("Strip Cast uses documented airplay connect",
            stripCast.Count > 0 && stripCast.All(c => c.GetProperty("fun").GetString() == "/device/airplay/connect"));
        Check("Strip Cast is one request per phone, not a comma list",
            stripCast.All(c => !c.GetProperty("data").GetProperty("id").GetString()!.Contains(',')));
        int beforeStripDisc = handler.Commands.Count;
        await Click("cast|disconnect");
        var stripDisc = handler.Commands.Skip(beforeStripDisc).ToList();
        Check("Strip Disc uses documented airplay disconnect",
            stripDisc.Count > 0 && stripDisc.All(c => c.GetProperty("fun").GetString() == "/device/airplay/disconnect"));

        foreach (var d in _devices) d.IsChecked = false;
        BatchMode.IsChecked = false;
        UpdateControls();

        // --- select all ---
        // This one switch arms mirroring at every phone at once, so it has to be exact in
        // both directions: on means all selected AND mirroring live, off means nothing is
        // following. A half state would look armed while doing nothing, or the reverse.
        foreach (var d in _devices) d.IsChecked = false;
        BatchMode.IsChecked = false;
        UpdateControls();
        Check("Select-all starts clear", SelectAllBox.IsChecked == false);

        SelectAllBox.IsChecked = true; SelectAll_Click(SelectAllBox, new RoutedEventArgs());
        Check("Select-all checks every phone", _devices.All(d => d.IsChecked));
        Check("Select-all arms mirroring", BatchMode.IsChecked == true);

        SelectAllBox.IsChecked = false; SelectAll_Click(SelectAllBox, new RoutedEventArgs());
        Check("Unchecking releases every phone", _devices.All(d => !d.IsChecked));
        Check("Unchecking disarms mirroring", BatchMode.IsChecked != true);
        Check("Released phones follow nothing", Followers().Count == 0);

        _devices[0].IsChecked = true;
        UpdateControls();
        Check("A partial selection shows as indeterminate", SelectAllBox.IsChecked is null);
        Check("Partial selection is spelled out", SelectAllLabel.Text.Contains("1 of"));
        foreach (var d in _devices) d.IsChecked = false;
        UpdateControls();

        // --- a tile's size never depends on what is inside it ---
        // The wall used to reflow every time a phone's rate readout changed width, which
        // read as the tiles jittering. Measured from a recording of the running app: the
        // tile swung between 131 and 178 pixels wide, fourteen times in thirteen seconds.
        foreach (var d in _devices) d.IsChecked = false;
        SearchBox.Text = "";
        DeviceList.SelectedItem = _devices.First(d => d.Id == "TEST:01");
        UpdateControls();
        var content2 = (FrameworkElement)Content;
        content2.UpdateLayout();
        var probe = _wall.FirstOrDefault();
        Check("The wall has a tile to measure", probe is not null);

        double MeasureTile()
        {
            content2.UpdateLayout();
            return PhoneWall.ItemContainerGenerator.ContainerFromItem(probe) is FrameworkElement box
                ? Math.Round(box.ActualWidth, 2) : -1;
        }

        probe!.Fps = 0;
        double quiet = MeasureTile();
        Check("A tile has a real measured width", quiet > 0);
        probe.Fps = 21;
        Check("Showing a rate does not resize the tile", MeasureTile() == quiet);
        probe.Fps = 7;
        Check("A one-digit rate is the same width as a two-digit one", MeasureTile() == quiet);
        probe.Fps = 120;
        Check("A three-digit rate does not resize the tile either", MeasureTile() == quiet);
        probe.Name = "A very much longer phone name than any tile can show";
        Check("A long name trims instead of widening the tile", MeasureTile() == quiet);
        // The default name for an unnamed phone ends in the only part that distinguishes
        // it, so the caption keeps the tail rather than trimming it away.
        probe.Name = "iPhone XR · 35:8D";
        Check("An unnamed phone's caption keeps the part that identifies it", probe.ShortName == "35:8D");
        probe.Status = "following";
        Check("The tooltip still carries the full name and state",
            probe.Detail.Contains("iPhone XR") && probe.Detail.Contains("following"));
        probe.Name = "Farm-07";
        Check("A phone the operator has named keeps that name", probe.ShortName == "Farm-07");
        Check("Naming a phone does not resize its tile", MeasureTile() == quiet);
        probe.Fps = 0;
        Check("Going quiet does not resize the tile", MeasureTile() == quiet);
        Check("The rate is hidden when a phone is not delivering frames", probe.RateVisibility == Visibility.Collapsed);
        probe.Fps = 12;
        Check("The rate reads as a whole number of frames a second", probe.RateText == "12/s");
        probe.Fps = 12.4;
        Check("Sub-frame drift does not rewrite the rate", probe.RateText == "12/s");
        probe.Fps = 17;
        Check("A real change does update the rate", probe.RateText == "17/s");

        // The width must follow the size slider, and only the size slider.
        double before = TileWidth;
        SmallSize.Value = SmallSize.Value + 40;
        Check("The size slider does change the tile width", TileWidth > before);
        SmallSize.Value = SmallSize.Value - 40;
        Check("The tile width returns when the slider does", Math.Abs(TileWidth - before) < 0.01);
        probe.Fps = 0;
        UpdateControls();

        // --- a phone joining the mirror set gets its pointer reset ---
        // Measured on the rack: a follower accepted pointer moves but ignored every click,
        // mirrored or not, until it was sent /mouse/reset. To the operator that looks like
        // mirroring silently skipping a phone, so joining the set now clears it.
        foreach (var d in _devices) d.IsChecked = false;
        SearchBox.Text = "";
        DeviceList.SelectedItem = _devices.First(d => d.Id == "TEST:01");
        BatchMode.IsChecked = false;
        UpdateControls();
        int beforeJoin = handler.Commands.Count;
        _devices.First(d => d.Id == "TEST:04").IsChecked = true;
        BatchMode.IsChecked = true;
        UpdateControls();
        for (int i = 0; handler.Commands.Count == beforeJoin && i < 100; i++) await Task.Delay(10);
        Check("A phone joining the mirror set has its pointer reset",
            handler.Commands[^1].GetProperty("fun").GetString() == "/mouse/reset" &&
            handler.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04");

        int afterJoin = handler.Commands.Count;
        UpdateControls(); UpdateControls();
        await Task.Delay(60);
        Check("An unchanged mirror set is not reset again", handler.Commands.Count == afterJoin);

        _devices.First(d => d.Id == "TEST:05").IsChecked = true;   // wrong screen size: excluded
        UpdateControls();
        await Task.Delay(60);
        Check("Ticking a phone that cannot mirror does not trigger a reset", handler.Commands.Count == afterJoin);
        _devices.First(d => d.Id == "TEST:05").IsChecked = false;

        BatchMode.IsChecked = false;
        UpdateControls();
        await Task.Delay(60);
        Check("Turning mirroring off does not reset anything", handler.Commands.Count == afterJoin);
        foreach (var d in _devices) d.IsChecked = false;
        UpdateControls();

        // --- taps and drags, through the real gesture path ---
        // This is the part that was broken. A tap used to be sent at the point where the
        // button came UP, and a drag that travelled past the edge of the picture stopped
        // dead - the stricter mapper returned "no coordinate" the moment the cursor left
        // the image, so a fast swipe out of the phone could send nothing at all. With
        // mirroring on, both faults hit every follower at once.
        foreach (var d in _devices) d.IsChecked = false;
        SearchBox.Text = "";
        DeviceList.SelectedItem = _devices.First(d => d.Id == "TEST:01");
        _devices.First(d => d.Id == "TEST:04").IsChecked = true;
        BatchMode.IsChecked = true;
        UpdateControls();
        await GrabOneAsync();
        ((FrameworkElement)Content).UpdateLayout();
        Check("Gesture test has a frame and a laid-out picture",
            _frame is not null && _frameId == "TEST:01" && PhoneImage.ActualWidth > 0 && PhoneImage.ActualHeight > 0);

        double pw = PhoneImage.ActualWidth, ph = PhoneImage.ActualHeight;
        var pressPoint = new Point(pw * 0.30, ph * 0.30);
        var liftPoint = new Point(pw * 0.32, ph * 0.33);
        var pressed = MapPreview(pressPoint)!.Value;
        Check("A press inside the picture maps to a coordinate", MapPreview(pressPoint) is not null);

        int beforeTap = handler.Commands.Count;
        BeginGesture(pressPoint);
        Check("Press opens a gesture", _gesture is not null);
        await EndGestureAsync(liftPoint);
        for (int i = 0; handler.Commands.Count == beforeTap && i < 100; i++) await Task.Delay(10);
        var tap = handler.Commands[^1];
        Check("A tap is one mirrored click, not one request per phone", handler.Commands.Count == beforeTap + 1);
        Check("A tap reaches master and follower together",
            tap.GetProperty("fun").GetString() == "/mouse/click" &&
            tap.GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04");
        Check("A tap lands where the button went down, not where it came up",
            tap.GetProperty("data").GetProperty("x").GetInt32() == pressed.X &&
            tap.GetProperty("data").GetProperty("y").GetInt32() == pressed.Y);

        // A swipe that runs off the right-hand edge. The cursor genuinely leaves the
        // picture during a flick, so this is the ordinary case, not a corner case.
        var outside = new Point(pw + 60, ph * 0.30);
        Check("The stroke really does leave the picture", MapPreview(outside) is null);
        var edge = MapPreviewClamped(outside)!.Value;
        int beforeDrag = handler.Commands.Count;
        BeginGesture(pressPoint);
        TrackGesture(new Point(pw * 0.30 + 30, ph * 0.30), true);
        for (int i = 0; !_dragStarted && i < 100; i++) await Task.Delay(10);
        Check("Moving past the threshold starts a drag", _dragStarted);
        TrackGesture(outside, true);
        for (int i = 0; !handler.Commands.Skip(beforeDrag).Any(c => c.GetProperty("fun").GetString() == "/mouse/down") && i < 100; i++) await Task.Delay(10);
        await EndGestureAsync(outside);
        for (int i = 0; _dragLoopRunning && i < 200; i++) await Task.Delay(10);
        Check("The drag loop finishes", !_dragLoopRunning && !_dragStarted);

        var stroke = handler.Commands.Skip(beforeDrag).ToList();
        var down = stroke.Where(c => c.GetProperty("fun").GetString() == "/mouse/down").ToList();
        var up = stroke.Where(c => c.GetProperty("fun").GetString() == "/mouse/up").ToList();
        var moves = stroke.Where(c => c.GetProperty("fun").GetString() == "/mouse/move").ToList();
        Check("A drag presses once and releases once", down.Count == 1 && up.Count == 1);
        Check("The button goes down before it comes up",
            stroke.IndexOf(down[0]) < stroke.IndexOf(up[0]));
        Check("Every part of the stroke addresses master and follower",
            stroke.All(c => c.GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04"));
        Check("The stroke starts at the press point",
            moves.Count > 0 && moves[0].GetProperty("data").GetProperty("x").GetInt32() == pressed.X
                            && moves[0].GetProperty("data").GetProperty("y").GetInt32() == pressed.Y);
        // The decisive one: a stroke leaving the picture used to freeze at the last inside
        // point. It must now carry to the edge instead.
        Check("A stroke that leaves the picture carries to the edge",
            moves[^1].GetProperty("data").GetProperty("x").GetInt32() == edge.X);
        Check("The last move is delivered before the button is released",
            stroke.IndexOf(moves[^1]) < stroke.IndexOf(up[0]));

        // A stationary press held past the hold threshold is a long press. The button must
        // go down on the phone WHILE the mouse is still held - that is what lets iOS run
        // its own long-press timer and show the icon context menu - and come up only on
        // release, with no click ever sent. Compare the tap above: same press point, but
        // released at once, and that one must stay an atomic click.
        int beforeHold = handler.Commands.Count;
        BeginGesture(pressPoint);
        Check("A hold starts as an ordinary press", _gesture is not null && !_dragStarted);
        for (int i = 0; !_dragStarted && i < 100; i++) await Task.Delay(10);
        Check("Holding still past the threshold presses the button", _dragStarted && _holdGesture);
        for (int i = 0; !handler.Commands.Skip(beforeHold).Any(c => c.GetProperty("fun").GetString() == "/mouse/down") && i < 100; i++) await Task.Delay(10);
        Check("The button is down before the mouse is released",
            handler.Commands.Skip(beforeHold).Any(c => c.GetProperty("fun").GetString() == "/mouse/down") &&
            !handler.Commands.Skip(beforeHold).Any(c => c.GetProperty("fun").GetString() == "/mouse/up"));
        await Task.Delay(300);
        await EndGestureAsync(new Point(pressPoint.X + 1, pressPoint.Y + 1));
        for (int i = 0; _dragLoopRunning && i < 200; i++) await Task.Delay(10);
        var holdCmds = handler.Commands.Skip(beforeHold).ToList();
        Check("A long press is one press and one release and never a click",
            holdCmds.Count(c => c.GetProperty("fun").GetString() == "/mouse/down") == 1 &&
            holdCmds.Count(c => c.GetProperty("fun").GetString() == "/mouse/up") == 1 &&
            !holdCmds.Any(c => c.GetProperty("fun").GetString() == "/mouse/click"));
        Check("A long press stays where it was pressed",
            holdCmds.Where(c => c.GetProperty("fun").GetString() == "/mouse/move")
                    .All(c => c.GetProperty("data").GetProperty("x").GetInt32() == pressed.X
                           && c.GetProperty("data").GetProperty("y").GetInt32() == pressed.Y));
        Check("A long press addresses master and follower",
            holdCmds.All(c => c.GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04"));
        for (int i = 0; !_activity.Any(s => s.Contains("Long press")) && i < 100; i++) await Task.Delay(10);
        Check("A long press is logged with its duration", _activity.Any(s => s.Contains("Long press (")));

        // A flick so quick that it leaves the picture before the drag threshold is crossed
        // used to send nothing whatsoever: no drag started, and the tap path then rejected
        // the outside release point.
        int beforeFlick = handler.Commands.Count;
        BeginGesture(pressPoint);
        TrackGesture(outside, true);
        for (int i = 0; !_dragStarted && i < 100; i++) await Task.Delay(10);
        await EndGestureAsync(outside);
        for (int i = 0; _dragLoopRunning && i < 200; i++) await Task.Delay(10);
        Check("A flick straight out of the picture still sends a gesture", handler.Commands.Count > beforeFlick);

        // Hover tracking moves the phone's own pointer. It has to move every mirrored
        // phone's pointer, or the followers are in a different state when the click lands.
        int beforeHover = handler.Commands.Count;
        TrackPointer.IsChecked = true;
        TrackGesture(new Point(pw * 0.6, ph * 0.6), false);
        for (int i = 0; handler.Commands.Count == beforeHover && i < 100; i++) await Task.Delay(10);
        Check("Hover tracking moves the pointer on every mirrored phone",
            handler.Commands[^1].GetProperty("fun").GetString() == "/mouse/move" &&
            handler.Commands[^1].GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04");
        for (int i = 0; _pumpingPointer && i < 100; i++) await Task.Delay(10);

        // And it must stay out of the way once a gesture owns the pointer.
        BeginGesture(pressPoint);
        int beforeGuard = handler.Commands.Count;
        TrackPointerTo((7, 9));
        await Task.Delay(60);
        Check("Hover tracking yields to a gesture in progress", handler.Commands.Count == beforeGuard);
        await EndGestureAsync(pressPoint);
        for (int i = 0; _commandBusy && i < 100; i++) await Task.Delay(10);

        foreach (var d in _devices) d.IsChecked = false;
        BatchMode.IsChecked = false;
        UpdateControls();

        BatchMode.IsChecked = true;
        _devices[0].IsChecked = true; _devices[1].IsChecked = true; _devices[2].IsChecked = true;
        int beforeCast = handler.Commands.Count;
        await Click("cast|connect");
        var castCommands = handler.Commands.Skip(beforeCast).ToList();
        // Casting stays one request per phone even though input is now mirrored in a single
        // request: each phone negotiates its own AirPlay session, so the two are not the
        // same kind of operation and must not be collapsed into an id list.
        Check("Explicit batch casting uses each checked device",
            castCommands.Select(c => c.GetProperty("data").GetProperty("id").GetString()).SequenceEqual(new[] { "TEST:01", "TEST:02", "TEST:03" }));
        Check("Casting uses documented function", castCommands.All(c => c.GetProperty("fun").GetString() == "/device/airplay/connect"));
        BatchMode.IsChecked = false;
        int beforeText = handler.Commands.Count;
        SendTextBox.Text = "not ASCII: é"; SendText_Click(this, new RoutedEventArgs());
        Check("Unsupported text is blocked before transmission", handler.Commands.Count == beforeText);
        SendTextBox.Text = "hello"; SendText_Click(this, new RoutedEventArgs());
        for (int i = 0; (_commandBusy || _sendingText) && i < 100; i++) await Task.Delay(20);
        Check("Send text transmits explicit field", handler.Commands.Count == beforeText + 1 && handler.Commands[^1].GetProperty("data").GetProperty("key").GetString() == "hello");
        SearchBox.Text = "does-not-match";
        int beforeNone = handler.Commands.Count;
        await Click("key|Home");
        Check("No selected phone means no command", Selected is null && handler.Commands.Count == beforeNone);
        Check("Empty search has explanatory state", EmptyList.Visibility == Visibility.Visible);
        SearchBox.Text = "";
        DeviceList.SelectedItem = _devices[1];
        Check("Switching to offline phone clears previous image", _frame is null && PhoneImage.Source is null);
        DeviceList.SelectedItem = _devices[0];
        handler.ErrorCode = 25; int attempts = handler.PostAttempts;
        await Click("key|Home");
        Check("Failed commands are attempted once without retries", handler.PostAttempts == attempts + 1);
        // Input no longer re-reads the whole device list after every command - a tap is far
        // too frequent to pay for that. The five-second poll is what notices an outage, so
        // drive it here rather than asserting an immediate reaction to one failed tap.
        await RefreshDevicesAsync();
        Check("Service errors disable controls", !_connected && !ActionPanel.IsEnabled);
        handler.ErrorCode = 0; await RefreshDevicesAsync();
        Check("Connection recovers after service responds", _connected);
        handler.DelayMs = 150; AutoPreview.IsChecked = true;
        DeviceList.SelectedItem = _devices[1]; DeviceList.SelectedItem = _devices[0]; DeviceList.SelectedItem = _devices[1];
        await Task.Delay(350);
        Check("Delayed image cannot appear on a different phone", (_frame is null || _frameId == Selected?.Id) && Selected?.Id == "TEST:02");
        handler.DelayMs = 0; AutoPreview.IsChecked = false;
        handler.EmptyList = true; await RefreshDevicesAsync();
        Check("Empty service list clears selection and actions", _devices.Count == 0 && Selected is null && !ActionPanel.IsEnabled);
        Disconnect_Click(this, new RoutedEventArgs());
        Check("Disconnect clears images and control state", !_connected && _frame is null && !ActionPanel.IsEnabled);

        // --- Ownership UI checks with ownership enabled ---
        handler.OwnershipSupported = true;
        handler.ErrorCode = 0;
        handler.EmptyList = false;
        _factory = address => new ApiClient(address, handler, ownership: true, renewalInterval: TimeSpan.FromMilliseconds(50));
        await ConnectAsync();
        UpdateControls();
        DeviceList.SelectedItem = _devices.First(d => d.Id == "TEST:01");
        _devices.First(d => d.Id == "TEST:04").IsChecked = true;
        _devices.First(d => d.Id == "TEST:05").IsChecked = true;
        BatchMode.IsChecked = true;
        UpdateControls();

        Check("Stop button enabled under ownership", StopInputButton.IsEnabled);
        Check("Ownership connection disables every live binding control", !BindButton.IsEnabled
            && !UnbindButton.IsEnabled && !AutoBindButton.IsEnabled && !BoardPicker.IsEnabled);
        Check("Read-only assignment still identifies the selected board and maintenance requirement",
            BindStatus.Text.Contains("TEST-BOARD-01") && BindStatus.Text.Contains(ApiClient.LiveBindingUnavailable));
        int beforeUnsupportedBinding = handler.PostAttempts;
        bool? previewBeforeBinding = AutoPreview.IsChecked;
        AutoBind_Click(this, new RoutedEventArgs());
        Check("Queued Auto-bind cannot send commands or interrupt preview under ownership",
            handler.PostAttempts == beforeUnsupportedBinding && !_autoBinding && AutoPreview.IsChecked == previewBeforeBinding
            && _activity[0].Contains(ApiClient.LiveBindingUnavailable));
        Check("Unsupported remote mirroring and board restart controls are disabled in both locations",
            !CastButton.IsEnabled && !DiscButton.IsEnabled && !RestartButton.IsEnabled
            && !StartCastingButton.IsEnabled && !StopCastingButton.IsEnabled && !RecoveryRestartButton.IsEnabled);
        Check("Unsupported service actions show actionable help", MirroringActionHelp.Visibility == Visibility.Visible
            && BoardRestartHelp.Visibility == Visibility.Visible && MirroringActionHelp.Text == ApiClient.MirroringActionUnavailable
            && BoardRestartHelp.Text == ApiClient.BoardRestartUnavailable);
        // Send text runs from the Controls drawer, so Stop must take the first click while it
        // is open. On the rack the drawer's scrim swallowed that click and typing carried on.
        // Geometric hit test: the test window is never shown, and InputHitTest skips
        // elements that are not on screen.
        string hitDetail = "";
        bool Hits(Button button)
        {
            var root = (UIElement)Content; root.UpdateLayout();
            var centre = button.TranslatePoint(new Point(button.ActualWidth / 2, button.ActualHeight / 2), root);
            var hit = VisualTreeHelper.HitTest(root, centre)?.VisualHit;
            hitDetail = $" (hit {hit?.GetType().Name ?? "nothing"} at {centre})";
            for (DependencyObject? d = hit; d is not null; d = VisualTreeHelper.GetParent(d))
                if (ReferenceEquals(d, button)) return true;
            return false;
        }
        ShowDrawer("Controls", ControlsPane);
        bool stopReachable = Hits(StopInputButton);
        Check("Stop input takes the first click while the Send text drawer is open" + (stopReachable ? "" : hitDetail), stopReachable);
        CloseDrawer_Click(this, new RoutedEventArgs());
        Check("Stop button tooltip lists master and all checked phones",
            StopInputButton.ToolTip.ToString()!.Contains("Test phone 01") &&
            StopInputButton.ToolTip.ToString()!.Contains("Test phone 04") &&
            StopInputButton.ToolTip.ToString()!.Contains("Test phone 05"));

        // Click Stop Input button in UI
        StopInput_Click(StopInputButton, new RoutedEventArgs());
        for (int i = 0; _stopPending && i < 100; i++) await Task.Delay(10);
        Check("Stop button click sends /input/stop for all targets",
            handler.Commands.Any(c => c.GetProperty("fun").GetString() == "/input/stop" &&
                                      c.GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04,TEST:05"));
        Check("Input state shows stopped", InputStateText.Text.Contains("stopped") || InputStateText.Text.Contains("Resume"));
        Check("Resume button enabled after Stop", ResumeInputButton.IsEnabled);

        // Click Resume Input button in UI
        ResumeInput_Click(ResumeInputButton, new RoutedEventArgs());
        for (int i = 0; _resumePending && i < 100; i++) await Task.Delay(10);
        Check("Resume button click sends /input/resume",
            handler.Commands.Any(c => c.GetProperty("fun").GetString() == "/input/resume"));
        Check("Input state recovers to ready", InputStateText.Text.Contains("ready"));

        // --- long text goes out in ApiClient.TextChunk-character chunks, through the real button ---
        const int C = ApiClient.TextChunk; int n = (200 + C - 1) / C;
        // One 200-character sendkey used to outlive the kernel's 8 s command deadline, which
        // cancelled it partway and latched Stop. Master TEST:01 plus follower TEST:04 here.
        async Task SendTextAndWait(string value)
        {
            SendTextBox.Text = value; SendText_Click(this, new RoutedEventArgs());
            for (int i = 0; _sendingText && i < 500; i++) await Task.Delay(10);
            if (_sendingText) throw new Exception("Send text did not finish during UI test.");
        }
        JsonElement[] KeysSince(int index) => handler.Commands.ToArray().Skip(index).Where(c => c.GetProperty("fun").GetString() == "/key/sendkey").ToArray();
        string text = SelfTests.LongText;
        Check("Send text cap is the documented 200 characters", MaxSendText == 200);
        Check("The text box never truncates, so paste cannot shorten text silently", SendTextBox.MaxLength == 0);

        int beforeLong = handler.Commands.Count;
        await SendTextAndWait(text);
        var chunks = KeysSince(beforeLong);
        Check($"A 200-character Send text is {n} /key/sendkey requests", chunks.Length == n);
        Check($"Every Send text chunk is at most {C} characters", chunks.All(c => c.GetProperty("data").GetProperty("key").GetString()!.Length <= ApiClient.TextChunk));
        Check("Send text chunks arrive in order and rebuild the text", string.Concat(chunks.Select(c => c.GetProperty("data").GetProperty("key").GetString())) == text);
        Check("Every Send text chunk addresses the mirrored phones",
            chunks.All(c => c.GetProperty("data").GetProperty("id").GetString() == "TEST:01,TEST:04"));
        string chunkToken = chunks[0].GetProperty("data").GetProperty("tokens").GetProperty("TEST:01").GetString()!;
        Check("Every Send text chunk carries the same lease",
            chunks.All(c => c.GetProperty("data").GetProperty("tokens").GetProperty("TEST:01").GetString() == chunkToken));
        Check("A complete Send text is logged as such", _activity.Any(s => s.Contains($"Send text -> 2 phones: 200 characters in {n} chunk(s)")));
        Check("Long text leaves input ready, not stopped", _controlReady && InputStateText.Text.Contains("ready"));

        Check("The counter shows a full box as within the cap", SendTextCount.Text == "200 / 200");
        int beforeOver = handler.Commands.Count;
        await SendTextAndWait(new string('a', MaxSendText + 1));
        Check("Over-limit text stays whole in the box", SendTextBox.Text.Length == MaxSendText + 1);
        Check("The counter flags over-limit text before sending", SendTextCount.Text.Contains("201 / 200") && SendTextCount.Text.Contains("too long"));
        // Count keys only: the 50 ms renewal heartbeat adds /input/renew while this runs.
        Check("Text over the limit is refused before transmission, not truncated and sent",
            KeysSince(beforeOver).Length == 0 && _activity.Any(s => s.Contains($"at most {MaxSendText} characters at a time; this is 201. Nothing was sent.")));

        int beforeFail = handler.Commands.Count;
        handler.FailSendKeyNumber = handler.SendKeyCount + 3;
        await SendTextAndWait(text);
        var failedChunks = KeysSince(beforeFail);
        Check("A failure on chunk 3 sends no chunk after it", failedChunks.Length == 3);
        Check("The failure reports confirmed characters and the chunk with an unknown outcome",
            _activity.Any(s => s.Contains($"{2 * C} of 200 characters confirmed. Chunk 3 of {n} may be partly typed and was not retried. Chunks 4–{n} were not sent.")));
        // The failed send posts "Input paused: …". A lease renewal already in flight when the kernel revoked
        // the lease can post "Ownership renewal failed: …" just after it and replace that text (seen in about
        // 1 run in 5 with the 50 ms test heartbeat). Either way input is paused, which is what this checks.
        for (int i = 0; _controlReady && i < 100; i++) await Task.Delay(10);
        Check("A failed chunk leaves input paused and offers Resume",
            !_controlReady && ResumeInputButton.IsEnabled && !InputStateText.Text.Contains("ready"));

        // --- a key with no answer is visible and recoverable ---
        // The lease client pauses the phones on HttpClient's timeout. It used to raise no notice
        // for one and the key path swallowed the exception, so the panel still read ready, Resume
        // stayed disabled and the next input was refused as paused.
        async Task ResumeAndWait()
        {
            ResumeInput_Click(ResumeInputButton, new RoutedEventArgs());
            for (int i = 0; _resumePending && i < 100; i++) await Task.Delay(10);
        }
        async Task WaitFor(Func<bool> condition) { for (int i = 0; !condition() && i < 100; i++) await Task.Delay(10); }
        await ResumeAndWait();
        Check("Resume after the failed chunk leaves input ready", _controlReady && InputStateText.Text.Contains("ready"));
        int beforeTimeout = handler.Commands.Count;
        handler.TimeoutSendKeyNumber = handler.SendKeyCount + 1;
        await Click("key|Home");
        await WaitFor(() => InputStateText.Text.StartsWith("Input paused") && _activity.Any(s => s.Contains("key|Home failed")));
        Check("A timed-out key was sent once and not retried", KeysSince(beforeTimeout).Length == 1);
        Check("A timed-out key shows input paused and offers Resume",
            InputStateText.Text == InputLeaseClient.TimedOutNotice && !_controlReady && ResumeInputButton.IsEnabled);
        Check("A timed-out key is logged once as a timeout", _activity.Count(s => s.Contains("key|Home failed: Request timed out")) == 1);

        await ResumeAndWait();
        int beforeRecovered = handler.Commands.Count;
        await Click("key|Home");
        await WaitFor(() => KeysSince(beforeRecovered).Length > 0);
        Check("Resume after a timed-out key restores input", _controlReady && InputStateText.Text.Contains("ready") && KeysSince(beforeRecovered).Length == 1);

        // Send text relies on the same notice now rather than pausing the panel itself.
        int beforeTextTimeout = handler.Commands.Count;
        handler.TimeoutSendKeyNumber = handler.SendKeyCount + 2;
        await SendTextAndWait(text);
        await WaitFor(() => InputStateText.Text.StartsWith("Input paused"));
        Check("A Send text timeout sends nothing after the chunk with no answer", KeysSince(beforeTextTimeout).Length == 2);
        Check("A Send text timeout reports how far it got",
            _activity.Any(s => s.Contains($"Send text -> 2 phones timed out: {C} of 200 characters confirmed. Chunk 2 of {n} may be partly typed and was not retried. Chunks 3–{n} were not sent.")));
        Check("A Send text timeout shows input paused and offers Resume",
            InputStateText.Text == InputLeaseClient.TimedOutNotice && ResumeInputButton.IsEnabled);

        // --- a key queued behind one that times out never goes out, and is reported so ---
        await ResumeAndWait();
        int beforeQueue = handler.Commands.Count;
        int KeyTimeouts() => _activity.Count(s => s.Contains("key|Home failed: Request timed out"));
        int timeoutsBefore = KeyTimeouts();
        var hung = handler.HangNext("/key/sendkey");
        await Click("key|Home");
        await hung.WaitAsync(TimeSpan.FromSeconds(5));
        await Click("key|Home");
        handler.EndHang();
        await WaitFor(() => _activity.Any(s => s.Contains("key|Home: Not sent")) && KeyTimeouts() > timeoutsBefore);
        Check("A key queued behind a timed-out key never reaches the service", KeysSince(beforeQueue).Length == 1);
        Check("The queued key is reported as not sent, once", _activity.Count(s => s.Contains("key|Home: Not sent")) == 1);
        Check("Only the key that went out is reported as timed out", KeyTimeouts() == timeoutsBefore + 1);
        Check("The queued key leaves the timeout's pause showing", InputStateText.Text == InputLeaseClient.TimedOutNotice && ResumeInputButton.IsEnabled);

        // --- a drag whose move times out: logged once, no /mouse/up, released at once, input paused ---
        // The lease client has paused the phones, so /mouse/up would only be refused locally. It
        // releases each phone's own lease instead, which lifts the button on the kernel.
        await ResumeAndWait();
        await GrabOneAsync();
        ((FrameworkElement)Content).UpdateLayout();
        var dragFrom = new Point(PhoneImage.ActualWidth * 0.30, PhoneImage.ActualHeight * 0.30);
        int beforeHeld = handler.Commands.Count;
        BeginGesture(dragFrom);
        TrackGesture(new Point(dragFrom.X + 30, dragFrom.Y), true);
        await WaitFor(() => handler.Commands.Skip(beforeHeld).Any(c => c.GetProperty("fun").GetString() == "/mouse/down"));
        Check("The drag presses the button before its move times out",
            handler.Commands.Skip(beforeHeld).Any(c => c.GetProperty("fun").GetString() == "/mouse/down"));
        handler.TimeoutFun = "/mouse/move";
        TrackGesture(new Point(dragFrom.X + 60, dragFrom.Y), true);
        await WaitFor(() => !_dragLoopRunning && _activity.Any(s => s.Contains("Drag: Request timed out")));
        await EndGestureAsync(new Point(dragFrom.X + 60, dragFrom.Y));
        await WaitFor(() => !_dragLoopRunning && _activity.Any(s => s.Contains("Held button released after the request timed out")));
        handler.TimeoutFun = null;
        var heldCommands = handler.Commands.Skip(beforeHeld).ToList();
        var heldStroke = heldCommands.Select(c => c.GetProperty("fun").GetString()).ToList();
        var pressTokens = heldCommands.First(c => c.GetProperty("fun").GetString() == "/mouse/down").GetProperty("data").GetProperty("tokens");
        var releases = heldCommands.Where(c => c.GetProperty("fun").GetString() == "/input/release").Select(c => c.GetProperty("data")).ToList();
        Check("A drag whose move timed out sends no /mouse/up", !heldStroke.Contains("/mouse/up") && !_dragLoopRunning);
        Check("A drag timeout is logged once, with no refused release after it",
            _activity.Count(s => s.Contains("Drag: Request timed out")) == 1 && !_activity.Any(s => s.Contains("Drag release failed")));
        Check("A drag timeout releases each mirrored phone's own lease at once",
            releases.Count == 2 && releases.All(r => r.GetProperty("token").GetString() == pressTokens.GetProperty(r.GetProperty("id").GetString()!).GetString()));
        Check("The confirmed release is logged and the panel stays paused with Resume offered",
            _activity.Count(s => s.Contains("Held button released after the request timed out on TEST:01, TEST:04")) == 1 &&
            InputStateText.Text == "Input paused: request timed out; held button released (confirmed). Check the phone, then choose Resume input." &&
            !_controlReady && ResumeInputButton.IsEnabled && !heldStroke.Contains("/input/resume"));

        Disconnect_Click(this, new RoutedEventArgs());

        File.WriteAllText(Path.Combine(qa, "ui-interactions.json"), JsonSerializer.Serialize(new { passed = passed.Count, tests = passed, mockPostAttempts = handler.PostAttempts, realPhoneInputCommands = 0, dataPath = _dataPath }, new JsonSerializerOptions { WriteIndented = true }));
    }
}
