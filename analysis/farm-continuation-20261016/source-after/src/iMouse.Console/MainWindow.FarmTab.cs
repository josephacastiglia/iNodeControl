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
    private const string FarmServerUrl = "http://127.0.0.1:9914";
    private readonly Random _jitterRng = new();
    private string? _farmExecutionMode;

    private Brush BrushOr(string key, Brush fallback) => (TryFindResource(key) as Brush) ?? fallback;

    private Device? SelectedFarmInputPhone()
    {
        if (Selected is { } device && FarmTargetPolicy.IsC24C(device.Id)) return device;
        AppendFarmLog("Farm controls are restricted to C24C. Select C24C in Rack View first.");
        return null;
    }

    private bool FarmAutomationModeKnown()
    {
        if (_farmExecutionMode is "simulate" or "live") return true;
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
                AppendFarmLog("Connected to running 7-Layer Farm Server on " + FarmServerUrl);
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
                Process.Start(new ProcessStartInfo("python", $"\"{scriptPath}\" --no-browser --mode simulate")
                {
                    WorkingDirectory = System.IO.Path.GetDirectoryName(System.IO.Path.GetDirectoryName(scriptPath)) ?? AppContext.BaseDirectory,
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
            FarmExecutionModeText.Text = mode switch
            {
                "simulate" => "Automation: SIMULATION · manual preview taps still control C24C",
                "live" => "Automation: LIVE · C24C only",
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
                bool paused = p.GetProperty("paused_zero_view").GetInt32() != 0;

                // Match with actual connected device
                Device? matchDev = _devices.Find(d => d.Id.Equals(id, StringComparison.OrdinalIgnoreCase) ||
                                                      d.Name.Contains(id, StringComparison.OrdinalIgnoreCase) ||
                                                      (id == "C24C" && d.Name.Contains("C24C", StringComparison.OrdinalIgnoreCase)));

                string liveState = matchDev != null ? (matchDev.Online ? "LIVE ONLINE" : "OFFLINE") : "REGISTERED";

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
                    Content = "⚡ Deploy",
                    Padding = new Thickness(6, 4, 6, 4),
                    FontSize = 11,
                    MinHeight = 26,
                    Background = (Brush)FindResource("AccentBrush"),
                    Foreground = (Brush)FindResource("OnAccentBrush"),
                    Tag = id
                };
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
            FarmExecutionModeText.Text = "Automation backend unavailable";
            AppendFarmLog("State refresh note: " + ex.Message);
        }
    }

    private async void FarmAutoCreate_Click(object sender, RoutedEventArgs e)
    {
        if (!FarmAutomationModeKnown()) return;
        AppendFarmLog("Starting 5-Stage 1-Click Auto-Create & Deploy across all cohorts...");
        try
        {
            var payload = JsonSerializer.Serialize(new { cohort = "all" });
            var resp = await FarmHttp.PostAsync(FarmServerUrl + "/api/farm/auto-create-and-deploy",
                new StringContent(payload, Encoding.UTF8, "application/json"));
            string body = await resp.Content.ReadAsStringAsync();
            AppendFarmLog("Auto-Create & Deploy finished: " + body);
            await RefreshFarmStateAsync();
        }
        catch (Exception ex)
        {
            AppendFarmLog("Auto-Create error: " + ex.Message);
        }
    }

    private async void FarmCohortWarmup_Click(object sender, RoutedEventArgs e)
    {
        if (!FarmAutomationModeKnown()) return;
        if (SelectedFarmInputPhone() is not { } device) return;
        string targetDev = device.Id;
        AppendFarmLog($"Triggering Warmup session for {targetDev} (TikTok 2 clips)...");
        try
        {
            var payload = JsonSerializer.Serialize(new
            {
                device_id = targetDev,
                clips = 2,
                time_scale = 0.5
            });
            var resp = await FarmHttp.PostAsync(FarmServerUrl + "/api/farm/warmup-wave",
                new StringContent(payload, Encoding.UTF8, "application/json"));
            string body = await resp.Content.ReadAsStringAsync();
            AppendFarmLog("Warmup finished: " + body);
            await RefreshFarmStateAsync();
        }
        catch (Exception ex)
        {
            AppendFarmLog("Warmup error: " + ex.Message);
        }
    }

    private async void FarmSchedulerTick_Click(object sender, RoutedEventArgs e)
    {
        if (!FarmAutomationModeKnown()) return;
        AppendFarmLog("Ticking Background Cohort Scheduler...");
        try
        {
            var resp = await FarmHttp.PostAsync(FarmServerUrl + "/api/farm/scheduler-tick", new StringContent("{}", Encoding.UTF8, "application/json"));
            string body = await resp.Content.ReadAsStringAsync();
            AppendFarmLog("Scheduler tick completed: " + body);
            await RefreshFarmStateAsync();
        }
        catch (Exception ex)
        {
            AppendFarmLog("Scheduler tick error: " + ex.Message);
        }
    }

    private async void FarmFunnel_Click(object sender, RoutedEventArgs e)
    {
        if (!FarmAutomationModeKnown() || SelectedFarmInputPhone() is not { } device) return;
        AppendFarmLog("Running Conversion Funnel Suite (Comment to DM + Swarm)...");
        try
        {
            var payload = JsonSerializer.Serialize(new { device_id = device.Id, keyword = FarmKeywordBox?.Text ?? "SYSTEM" });
            var resp = await FarmHttp.PostAsync(FarmServerUrl + "/api/farm/funnel-suite",
                new StringContent(payload, Encoding.UTF8, "application/json"));
            string body = await resp.Content.ReadAsStringAsync();
            AppendFarmLog("Funnel Suite finished: " + body);
        }
        catch (Exception ex)
        {
            AppendFarmLog("Funnel Suite error: " + ex.Message);
        }
    }

    private async void FarmSpotlightTest_Click(object sender, RoutedEventArgs e)
    {
        if (SelectedFarmInputPhone() is not { } dev) return;

        AppendFarmLog($"Running live C24C Spotlight & Notes test on {dev.DisplayName} ({dev.Id})...");
        try
        {
            // 1. Pull down Spotlight search via proven iOS swipe down gesture
            AppendFarmLog("Opening Spotlight Search via native Swipe Down...");
            await SendInputAsync("Spotlight Swipe", "/mouse/swipe", new() { ["id"] = dev.Id, ["direction"] = "down", ["len"] = 0.5 });
            await Task.Delay(1000);

            // 2. Type "Notes"
            AppendFarmLog("Typing 'Notes' via keyboard sendkey...");
            await SendInputAsync("Type Notes", "/key/sendkey", new() { ["id"] = dev.Id, ["key"] = "Notes" });
            await Task.Delay(500);

            // 3. Press Enter to launch Notes
            AppendFarmLog("Sending Enter to launch Notes...");
            await SendInputAsync("Enter", "/key/sendkey", new() { ["id"] = dev.Id, ["fn_key"] = "ENTER" });

            AppendFarmLog("Spotlight Search & Notes launch flow completed.");
        }
        catch (Exception ex)
        {
            AppendFarmLog("Spotlight test error: " + ex.Message);
        }
    }

    private async void FarmEmergencyStop_Click(object sender, RoutedEventArgs e)
    {
        AppendFarmLog("Stopping C24C input...");
        try
        {
            // Trigger Console's native Stop Input flow (pauses UI and releases buttons)
            if (string.Equals(StopTargetIds(), FarmTargetPolicy.DeviceId, StringComparison.OrdinalIgnoreCase))
                StopInput_Click(StopInputButton, new RoutedEventArgs());

            // Notify Farm Server
            var resp = await FarmHttp.PostAsync(FarmServerUrl + "/api/farm/emergency-stop",
                new StringContent(JsonSerializer.Serialize(new { device_id = FarmTargetPolicy.DeviceId }), Encoding.UTF8, "application/json"));
            string body = await resp.Content.ReadAsStringAsync();
            AppendFarmLog("Stop signal delivered: " + body);
        }
        catch (Exception ex)
        {
            AppendFarmLog("Emergency Stop error: " + ex.Message);
        }
    }

    private async void FarmDeploySingle_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button btn || btn.Tag is not string tag) return;
        string[] parts = tag.Split('|');
        if (parts.Length != 2) return;
        string platform = parts[0];
        string format = parts[1];

        if (SelectedFarmInputPhone() is not { } device) return;
        await TriggerSingleUploadAsync(device.Id, platform, format);
    }

    private async Task TriggerSingleUploadAsync(string deviceId, string platform, string uploadFormat)
    {
        if (!FarmAutomationModeKnown()) return;
        if (!FarmTargetPolicy.IsC24C(deviceId))
        {
            AppendFarmLog("Farm deployment is restricted to C24C; no request sent.");
            return;
        }
        AppendFarmLog($"Deploying {platform.ToUpper()} format '{uploadFormat}' to {deviceId}...");
        try
        {
            var payload = JsonSerializer.Serialize(new
            {
                device_id = deviceId,
                platform = platform,
                format = uploadFormat,
                niche = FarmNicheBox?.Text ?? "AI Workflow & SaaS Clips",
                cta_keyword = FarmKeywordBox?.Text ?? "SYSTEM"
            });
            var resp = await FarmHttp.PostAsync(FarmServerUrl + "/api/farm/single-upload",
                new StringContent(payload, Encoding.UTF8, "application/json"));
            string body = await resp.Content.ReadAsStringAsync();
            AppendFarmLog($"Deploy result: {body}");
        }
        catch (Exception ex)
        {
            AppendFarmLog($"Deploy error: {ex.Message}");
        }
    }

    private async void FarmPreview_Down(object sender, MouseButtonEventArgs e)
    {
        if (FarmPhoneImage?.Source is null || SelectedFarmInputPhone() is not { } dev) return;
        var pt = e.GetPosition(FarmTapCanvas);

        // Normalize to 500x1080 coordinate space
        double canvasW = FarmTapCanvas.ActualWidth;
        double canvasH = FarmTapCanvas.ActualHeight;
        if (canvasW <= 0 || canvasH <= 0) return;

        int normX = (int)Math.Clamp(pt.X / canvasW * 500.0, 0, 500);
        int normY = (int)Math.Clamp(pt.Y / canvasH * 1080.0, 0, 1080);

        // Calculate approach jitter
        int jx = normX + _jitterRng.Next(-4, 5);
        int jy = normY + _jitterRng.Next(-4, 5);
        int dwell = _jitterRng.Next(95, 145);

        FarmLastCoordText.Text = $"({normX}, {normY})";
        FarmLastApproachText.Text = $"Approach: ({jx}, {jy})";
        FarmLastDwellText.Text = $"{dwell} ms • unique tap";

        DrawFarmTapMarker((int)pt.X, (int)pt.Y, isCanvasCoords: true);

        AppendFarmLog($"Interactive Tap -> ({normX}, {normY}) on {dev.DisplayName}");
        try
        {
            await SendInputAsync("Farm Tap", "/mouse/click", new()
            {
                ["id"] = dev.Id,
                ["x"] = normX,
                ["y"] = normY
            });
        }
        catch (Exception ex)
        {
            AppendFarmLog("Tap delivery warning: " + ex.Message);
        }
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
