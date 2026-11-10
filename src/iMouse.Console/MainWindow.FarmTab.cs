// File: src/iMouse.Console/MainWindow.FarmTab.cs
// Partial class for MainWindow implementing the "Marketing Farm (Test Tab)" interface:
// the farm backend connection, content creation and the draft windows, and manual C24C input.

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
        string? scriptPath = InstallLayout.ResolveFarmServerScriptPath();
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
            FarmExecutionModeText.Text = mode switch
            {
                "simulate" => "Farm backend: simulation mode · manual preview taps still control C24C",
                "live" => "Farm backend: live mode",
                _ => "Farm backend mode unknown · older backend"
            };
        }
        catch (Exception ex)
        {
            _farmExecutionMode = null;
            _farmProtocolVersion = 0;
            FarmExecutionModeText.Text = "Farm backend unavailable";
            AppendFarmLog("State refresh note: " + ex.Message);
        }
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
            // Stop only C24C on the console, never its checked followers.
            if (_api is { } api)
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

    private async void FarmPreview_Down(object sender, MouseButtonEventArgs e)
    {
        if (_farmManualSequence) return;
        if (FarmPhoneImage?.Source is not System.Windows.Media.Imaging.BitmapSource image ||
            SelectedFarmInputPhone() is not { Online: true } device || _frameId != device.Id ||
            (DateTime.UtcNow - _frameAt).TotalSeconds > 10) return;
        var pt = e.GetPosition(FarmTapCanvas);
        var size = TargetSize(image);
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
