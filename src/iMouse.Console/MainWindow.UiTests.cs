using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace IMouse2;

// The --smoke-test and --ui-test phases. They drive this window's real handlers; --ui-test uses
// TestHandler for every request, so no command reaches a service or a phone.
public partial class MainWindow
{
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
        var qa = Path.Combine(InstallLayout.RunFiles, "qa"); Directory.CreateDirectory(qa);
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
        await off.CloseSafelyAsync();
        File.WriteAllText(trackFile, "{\"address\":\"http://localhost:9923\",\"theme\":\"light\"}");
        var on = new MainWindow(_factory, trackDir);
        Check("Hover tracking stays on by default", on.TrackPointer.IsChecked == true);
        on.SaveSettings();
        Check("A settings file without trackPointer is saved without it",
            File.ReadAllText(trackFile) == "{\"address\":\"http://localhost:9923\",\"theme\":\"light\"}");
        await on.CloseSafelyAsync();
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
        for (int i = 0; _inputActions.IsRunning && i < 200; i++) await Task.Delay(10);
        Check("The drag loop finishes", !_inputActions.IsRunning && !_dragStarted);

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
        for (int i = 0; _inputActions.IsRunning && i < 200; i++) await Task.Delay(10);
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
        for (int i = 0; _inputActions.IsRunning && i < 200; i++) await Task.Delay(10);
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
        for (int i = 0; _pointerMoves.IsRunning && i < 100; i++) await Task.Delay(10);

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
        bool farmReachable = Hits(FarmTabButton);
        Check("Farm button is reachable in the top bar while a drawer is open" + (farmReachable ? "" : hitDetail),
            farmReachable && Equals(FarmTabButton.Content, "Marketing Farm (Test Tab)"));
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
        await WaitFor(() => !_inputActions.IsRunning && _activity.Any(s => s.Contains("Drag: Request timed out")));
        await EndGestureAsync(new Point(dragFrom.X + 60, dragFrom.Y));
        await WaitFor(() => !_inputActions.IsRunning && _activity.Any(s => s.Contains("Held button released after the request timed out")));
        handler.TimeoutFun = null;
        var heldCommands = handler.Commands.Skip(beforeHeld).ToList();
        var heldStroke = heldCommands.Select(c => c.GetProperty("fun").GetString()).ToList();
        var pressTokens = heldCommands.First(c => c.GetProperty("fun").GetString() == "/mouse/down").GetProperty("data").GetProperty("tokens");
        var releases = heldCommands.Where(c => c.GetProperty("fun").GetString() == "/input/release").Select(c => c.GetProperty("data")).ToList();
        Check("A drag whose move timed out sends no /mouse/up", !heldStroke.Contains("/mouse/up") && !_inputActions.IsRunning);
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
