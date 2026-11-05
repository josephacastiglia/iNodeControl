// File: src/iMouse.Console/MainWindow.FarmTab.cs
// Partial class for MainWindow implementing the "Marketing Farm (Test Tab)" interface,
// live AirPlay frame synchronization, and 1-Click marketing automation.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Shapes;

namespace IMouse2;

public partial class MainWindow
{
    private static readonly HttpClient FarmHttp = new() { Timeout = TimeSpan.FromSeconds(30) };
    private const string FarmServerUrl = "http://127.0.0.1:9915";
    private string? _farmExecutionMode;
    private bool _farmManualSequence;
    private bool _farmPersonaLoaded;

    private string? FarmAutomationTarget() => _farmExecutionMode == "simulate" ? "C24C" : SelectedFarmInputPhone()?.Id;

    private Brush BrushOr(string key, Brush fallback) => (TryFindResource(key) as Brush) ?? fallback;

    private Device? SelectedFarmInputPhone()
    {
        if (Selected is { } device && FarmTargetPolicy.IsC24C(device.Id)) return device;
        AppendFarmLog("Farm controls are restricted to C24C. Select C24C in Rack View first.");
        return null;
    }

    private bool FarmAutomationModeKnown()
    {
        if (_farmJobRecoveryError is not null) { AppendFarmLog(_farmJobRecoveryError); return false; }
        if (_farmJobId is not null || _farmManualSequence) { AppendFarmLog("Farm work is already pending. Use Check job or Stop."); return false; }
        if (_farmProtocolVersion == 2 && _farmExecutionMode is "simulate" or "live") return true;
        AppendFarmLog("No automation request sent: backend execution mode is unknown. Reopen the tab after starting the updated backend in an explicit mode.");
        return false;
    }

    public void SyncFarmPhoneImage()
    {
        try
        {
            if (FarmPhoneImage is null) return;
            if (FarmViewSurface?.Visibility == Visibility.Visible)
            {
                if (!ReferenceEquals(FarmPhoneImage.Source, PhoneImage?.Source))
                {
                    FarmPhoneImage.Source = PhoneImage?.Source;
                }
            }
        }
        catch { }
    }

    private void RackViewTab_Click(object sender, RoutedEventArgs e)
    {
        if (RackViewSurface is null || FarmViewSurface is null) return;
        RackViewSurface.Visibility = Visibility.Visible;
        FarmViewSurface.Visibility = Visibility.Collapsed;

        RackViewTabButton.Background = BrushOr("AccentBrush", Brushes.Blue);
        RackViewTabButton.Foreground = BrushOr("OnAccentBrush", Brushes.White);
        FarmTabButton.Background = BrushOr("RaisedBrush", Brushes.LightGray);
        FarmTabButton.Foreground = BrushOr("TextBrush", Brushes.Black);
    }

    private async void FarmTab_Click(object sender, RoutedEventArgs e)
    {
        if (RackViewSurface is null || FarmViewSurface is null) return;
        RackViewSurface.Visibility = Visibility.Collapsed;
        FarmViewSurface.Visibility = Visibility.Visible;

        FarmTabButton.Background = BrushOr("AccentBrush", Brushes.Blue);
        FarmTabButton.Foreground = BrushOr("OnAccentBrush", Brushes.White);
        RackViewTabButton.Background = BrushOr("RaisedBrush", Brushes.LightGray);
        RackViewTabButton.Foreground = BrushOr("TextBrush", Brushes.Black);

        // Sync live stream
        SyncFarmPhoneImage();
        UpdateFarmSelectedHeader();

        // Connect & Refresh Farm Backend
        await EnsureFarmBackendRunningAsync();
        await RefreshFarmStateAsync();
    }

    private void UpdateFarmSelectedHeader()
    {
        try
        {
            if (FarmSelectedPhoneText is null || FarmMirrorBadge is null) return;
            if (Selected is { } dev)
            {
                FarmSelectedPhoneText.Text = $"{dev.DisplayName} ({dev.Model})";
                FarmMirrorBadge.Text = dev.Online ? "● Mirroring Live" : "○ Offline";
                FarmMirrorBadge.Foreground = dev.Online ? BrushOr("OkBrush", Brushes.Green) : BrushOr("MutedBrush", Brushes.Gray);
            }
            else
            {
                FarmSelectedPhoneText.Text = "No Phone Selected (select in Rack View)";
                FarmMirrorBadge.Text = "○ Offline";
                FarmMirrorBadge.Foreground = BrushOr("MutedBrush", Brushes.Gray);
            }
        }
        catch { }
    }

    public void AppendFarmLog(string message)
    {
        Dispatcher.Invoke(() =>
        {
            if (FarmLogBox is null) return;
            string entry = $"[{DateTime.Now:HH:mm:ss.fff}] {message}\n";
            FarmLogBox.Text = entry + FarmLogBox.Text;
            if (FarmLogBox.Text.Length > 20000)
            {
                FarmLogBox.Text = FarmLogBox.Text[..20000];
            }
        });
    }

    private async Task EnsureFarmBackendRunningAsync()
    {
        try
        {
            var res = await FarmHttp.GetAsync(FarmServerUrl + "/health");
            if (res.IsSuccessStatusCode)
            {
                AppendFarmLog("Connected to farm backend on " + FarmServerUrl);
                return;
            }
        }
        catch { }

        // Resolve and start if not running
        string? scriptPath = IMouse2.ConsoleApp.FarmAutomationWindow.ResolveFarmServerScriptPath();
        if (scriptPath != null && File.Exists(scriptPath))
        {
            try
            {
                Process.Start(new ProcessStartInfo(InstallLayout.Python, $"\"{scriptPath}\" --no-browser --mode simulate --port 9915")
                {
                    WorkingDirectory = InstallLayout.FarmStateRoot(scriptPath),
                    UseShellExecute = false,
                    CreateNoWindow = true
                });
                await Task.Delay(800);
                AppendFarmLog("Started Farm backend in SIMULATION mode; automation sends no phone input. " + scriptPath);
            }
            catch (Exception ex)
            {
                AppendFarmLog("Could not auto-start farm server: " + ex.Message);
            }
        }
    }

    private async Task RefreshFarmStateAsync()
    {
        try
        {
            string json = await FarmHttp.GetStringAsync(FarmServerUrl + "/api/farm/state");
            using var doc = JsonDocument.Parse(json);
            string mode = doc.RootElement.TryGetProperty("executionMode", out var modeValue) ? modeValue.GetString() ?? "" : "";
            _farmExecutionMode = mode is "simulate" or "live" ? mode : null;
            _farmProtocolVersion = doc.RootElement.TryGetProperty("protocolVersion", out var protocol) ? protocol.GetInt32() : 0;
            _farmLiveAutomationReady = doc.RootElement.TryGetProperty("liveAutomationReady", out var ready) && ready.GetBoolean();
            FarmExecutionModeText.Text = mode switch
            {
                "simulate" => "Automation: SIMULATION · manual preview taps still control C24C",
                "live" => "Live connection · automated app actions await validation",
                _ => "Automation mode unknown · older backend"
            };
            if (!doc.RootElement.TryGetProperty("personas", out var personas)) return;

            FarmPhoneListPanel.Children.Clear();
            foreach (var p in personas.EnumerateArray())
            {
                string id = p.GetProperty("device_id").GetString() ?? "";
                int cohort = p.GetProperty("cohort").GetInt32();
                int day = p.GetProperty("account_day").GetInt32();
                string niche = p.GetProperty("niche").GetString() ?? "";
                string kw = p.GetProperty("cta_keyword").GetString() ?? "";
                if (id == "C24C" && !_farmPersonaLoaded)
                {
                    FarmNicheBox.Text = niche;
                    FarmKeywordBox.Text = kw;
                    _farmPersonaLoaded = true;
                }
                bool paused = p.GetProperty("paused_zero_view").GetInt32() != 0;

                // Match with actual connected device
                Device? matchDev = _devices.Find(d => d.Id.Equals(id, StringComparison.OrdinalIgnoreCase) ||
                                                      (id == "C24C" && FarmTargetPolicy.IsC24C(d.Id)));

                string liveState = matchDev != null ? (matchDev.Online ? "MIRRORING" : "NOT MIRRORING") : "PROFILE ONLY · NO VERIFIED PHONE";

                var card = new Border
                {
                    Background = (Brush)FindResource("RaisedBrush"),
                    BorderBrush = paused ? (Brush)FindResource("BadBrush") : (Brush)FindResource("EdgeBrush"),
                    BorderThickness = new Thickness(1),
                    CornerRadius = new CornerRadius(6),
                    Padding = new Thickness(10, 8, 10, 8),
                    Margin = new Thickness(0, 0, 0, 8)
                };

                var cardGrid = new Grid();
                cardGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
                cardGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(85) });

                var infoStack = new StackPanel();
                var headerLine = new StackPanel { Orientation = Orientation.Horizontal };
                headerLine.Children.Add(new TextBlock { Text = id, FontWeight = FontWeights.Bold, Margin = new Thickness(0, 0, 8, 0) });
                headerLine.Children.Add(new TextBlock
                {
                    Text = $"[Cohort {cohort} · Day {day}]",
                    Foreground = (Brush)FindResource("MutedBrush"),
                    FontSize = 11,
                    VerticalAlignment = VerticalAlignment.Center
                });
                headerLine.Children.Add(new TextBlock
                {
                    Text = $" · {liveState}",
                    Foreground = matchDev?.Online == true ? (Brush)FindResource("OkBrush") : (Brush)FindResource("MutedBrush"),
                    FontSize = 11,
                    FontWeight = FontWeights.SemiBold,
                    VerticalAlignment = VerticalAlignment.Center
                });
                infoStack.Children.Add(headerLine);

                infoStack.Children.Add(new TextBlock
                {
                    Text = $"{niche} | CTA: '{kw}' " + (paused ? "(0-VIEW PAUSED)" : ""),
                    Foreground = (Brush)FindResource("TextBrush"),
                    FontSize = 11.5,
                    Margin = new Thickness(0, 3, 0, 0)
                });
                Grid.SetColumn(infoStack, 0);
                cardGrid.Children.Add(infoStack);

                var deployBtn = new Button
                {
                    Content = mode == "simulate" ? "Simulate" : "Deploy",
                    Padding = new Thickness(6, 4, 6, 4),
                    FontSize = 11,
                    MinHeight = 26,
                    Background = (Brush)FindResource("AccentBrush"),
                    Foreground = (Brush)FindResource("OnAccentBrush"),
                    Tag = id
                };
                deployBtn.IsEnabled = id == "C24C" && (mode == "simulate" || _farmLiveAutomationReady);
                deployBtn.ToolTip = id == "C24C" ? "Run in the displayed automation mode" : "This profile is outside the current C24C test scope";
                deployBtn.Click += async (s, _) =>
                {
                    if (s is Button b && b.Tag is string devId)
                    {
                        await TriggerSingleUploadAsync(devId, "instagram", "ig_reel");
                    }
                };
                Grid.SetColumn(deployBtn, 1);
                cardGrid.Children.Add(deployBtn);

                card.Child = cardGrid;
                card.MouseLeftButtonUp += (_, _) =>
                {
                    if (id != "C24C") { AppendFarmLog("Only the C24C profile is editable in this test build."); return; }
                    if (FarmNicheBox is not null) FarmNicheBox.Text = niche;
                    if (FarmKeywordBox is not null) FarmKeywordBox.Text = kw;
                    AppendFarmLog($"Selected persona profile for {id}: {niche}");
                };
                FarmPhoneListPanel.Children.Add(card);
            }
        }
        catch (Exception ex)
        {
            _farmExecutionMode = null;
            _farmProtocolVersion = 0;
            FarmExecutionModeText.Text = "Automation backend unavailable";
            AppendFarmLog("State refresh note: " + ex.Message);
        }
    }

    private async void FarmAutoCreate_Click(object sender, RoutedEventArgs e)
    {
        if (FarmAutomationTarget() is not { } deviceId) return;
        await RunFarmJobAsync("auto-create-and-deploy", new { device_id = deviceId });
    }

    private async void FarmCohortWarmup_Click(object sender, RoutedEventArgs e)
    {
        if (FarmAutomationTarget() is not { } deviceId) return;
        await RunFarmJobAsync("warmup-wave", new { device_id = deviceId, clips = 2, time_scale = 0.5 });
    }

    private async void FarmSchedulerTick_Click(object sender, RoutedEventArgs e)
    {
        await RunFarmJobAsync("scheduler-tick", new { cohort = 1, execute_actions = false });
    }

    private async void FarmFunnel_Click(object sender, RoutedEventArgs e)
    {
        if (FarmAutomationTarget() is not { } deviceId) return;
        await RunFarmJobAsync("funnel-action", new { device_id = deviceId, action = "comment_to_dm" });
    }

    private async void FarmSpotlightTest_Click(object sender, RoutedEventArgs e)
    {
        if (_farmManualSequence || SelectedFarmInputPhone() is not { } device) return;
        _farmManualSequence = true;
        var sequence = _controlCancellation.Token;
        try
        {
            AppendFarmLog("Live C24C Spotlight/Notes input starting…");
            await SendFarmInputAsync("/mouse/swipe", new() { ["direction"] = "down", ["len"] = 0.5 });
            await Task.Delay(1000, sequence);
            await SendFarmInputAsync("/key/sendkey", new() { ["key"] = "Notes" });
            await Task.Delay(500, sequence);
            await SendFarmInputAsync("/key/sendkey", new() { ["fn_key"] = "ENTER" });
            AppendFarmLog("Commands completed. Check C24C to confirm Notes opened.");
        }
        catch (Exception ex) { AppendFarmLog("Spotlight stopped: " + ex.Message); }
        finally { _farmManualSequence = false; }
    }

    private async void FarmEmergencyStop_Click(object sender, RoutedEventArgs e)
    {
        var cancellation = RequestFarmCancellationAsync();
        try
        {
            // The real preview and simulated automation are different input paths.
            // Stop only C24C on the real console, never its checked followers.
            if (_api is { UsesInputOwnership: true } api)
            {
                CancelLocalInput();
                InputStateText.Text = "Stopping C24C…";
                await api.StopInputAsync(FarmTargetPolicy.DeviceId);
                InputStateText.Text = "C24C stopped · choose Resume input after the job ends";
                RefreshInputOwnershipUi();
            }
            await cancellation;
            await FarmApi.SendAsync("/api/farm/emergency-stop", new { device_id = "C24C" });
            AppendFarmLog("C24C Stop confirmed. Job cleanup may still be finishing.");
            await PollFarmJobAsync();
        }
        catch (Exception ex) { AppendFarmLog("Stop not confirmed: " + ex.Message); }
    }

    private async void FarmDeploySingle_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button btn || btn.Tag is not string tag) return;
        string[] parts = tag.Split('|');
        if (parts.Length != 2) return;
        string platform = parts[0];
        string format = parts[1];

        if (FarmAutomationTarget() is not { } deviceId) return;
        await TriggerSingleUploadAsync(deviceId, platform, format);
    }

    private async Task TriggerSingleUploadAsync(string deviceId, string platform, string uploadFormat)
    {
        if (!FarmTargetPolicy.IsC24C(deviceId)) { AppendFarmLog("Only C24C is enabled for farm testing."); return; }
        await RunFarmJobAsync("single-upload", new { device_id = deviceId, platform, format = uploadFormat });
    }

    private async void FarmPreview_Down(object sender, MouseButtonEventArgs e)
    {
        if (_farmManualSequence) return;
        if (FarmPhoneImage?.Source is not System.Windows.Media.Imaging.BitmapSource image ||
            SelectedFarmInputPhone() is not { Online: true } device || _frameId != device.Id ||
            (DateTime.UtcNow - _frameAt).TotalSeconds > 10) return;
        var pt = e.GetPosition(FarmTapCanvas);
        var size = TargetSize(device, image);
        var mapped = CoordinateMapper.Map(pt.X, pt.Y, FarmTapCanvas.ActualWidth, FarmTapCanvas.ActualHeight,
            image.PixelWidth, image.PixelHeight, size.W, size.H);
        if (mapped is not { } position) return;
        try
        {
            await SendFarmInputAsync("/mouse/click", new() { ["x"] = position.X, ["y"] = position.Y });
            FarmLastCoordText.Text = $"({position.X}, {position.Y})";
            FarmLastApproachText.Text = "Exact selected point";
            FarmLastDwellText.Text = "Tap command confirmed";
            DrawFarmTapMarker((int)pt.X, (int)pt.Y, isCanvasCoords: true);
        }
        catch (Exception ex) { AppendFarmLog("Tap not confirmed: " + ex.Message); }
    }

    private void DrawFarmTapMarker(int x, int y, bool isCanvasCoords = false)
    {
        if (FarmTapCanvas is null) return;
        double cx = x;
        double cy = y;

        if (!isCanvasCoords)
        {
            double canvasW = FarmTapCanvas.ActualWidth > 0 ? FarmTapCanvas.ActualWidth : 250;
            double canvasH = FarmTapCanvas.ActualHeight > 0 ? FarmTapCanvas.ActualHeight : 540;
            cx = (x / 500.0) * canvasW;
            cy = (y / 1080.0) * canvasH;
        }

        var marker = new Ellipse
        {
            Width = 14,
            Height = 14,
            Fill = new SolidColorBrush(Color.FromArgb(180, 244, 63, 94)),
            Stroke = Brushes.White,
            StrokeThickness = 2,
            IsHitTestVisible = false
        };
        Canvas.SetLeft(marker, cx - 7);
        Canvas.SetTop(marker, cy - 7);
        FarmTapCanvas.Children.Add(marker);

        // Fade out
        var anim = new DoubleAnimation(1.0, 0.0, TimeSpan.FromMilliseconds(1200));
        anim.Completed += (_, _) => FarmTapCanvas.Children.Remove(marker);
        marker.BeginAnimation(UIElement.OpacityProperty, anim);
    }
}
