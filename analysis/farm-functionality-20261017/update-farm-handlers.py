"""One-time UTF-8 rewrite of the native farm handlers, with exact method counts."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
path = root / "src/iMouse.Console/MainWindow.FarmTab.cs"
source = path.read_text(encoding="utf-8-sig")

def method(name, body):
    global source
    pattern = r"^    private async (?:void|Task) " + name + r"\([^\n]*\)\n    \{.*?^    \}"
    source, count = re.subn(pattern, lambda _: body, source, count=1, flags=re.S | re.M)
    assert count == 1, name

method("FarmAutoCreate_Click", '''    private async void FarmAutoCreate_Click(object sender, RoutedEventArgs e)
    {
        if (SelectedFarmInputPhone() is not { } device) return;
        await RunFarmJobAsync("auto-create-and-deploy", new { device_id = device.Id });
    }''')
method("FarmCohortWarmup_Click", '''    private async void FarmCohortWarmup_Click(object sender, RoutedEventArgs e)
    {
        if (SelectedFarmInputPhone() is not { } device) return;
        await RunFarmJobAsync("warmup-wave", new { device_id = device.Id, clips = 2, time_scale = 0.5 });
    }''')
method("FarmSchedulerTick_Click", '''    private async void FarmSchedulerTick_Click(object sender, RoutedEventArgs e)
    {
        await RunFarmJobAsync("scheduler-tick", new { cohort = 1, execute_actions = false });
    }''')
method("FarmFunnel_Click", '''    private async void FarmFunnel_Click(object sender, RoutedEventArgs e)
    {
        if (SelectedFarmInputPhone() is not { } device) return;
        await RunFarmJobAsync("funnel-action", new { device_id = device.Id, action = "comment_to_dm" });
    }''')
method("FarmSpotlightTest_Click", '''    private async void FarmSpotlightTest_Click(object sender, RoutedEventArgs e)
    {
        if (SelectedFarmInputPhone() is not { } device) return;
        try
        {
            AppendFarmLog("Live C24C Spotlight/Notes input starting…");
            await SendFarmInputAsync("/mouse/swipe", new() { ["direction"] = "down", ["len"] = 0.5 });
            await Task.Delay(1000, _controlCancellation.Token);
            await SendFarmInputAsync("/key/sendkey", new() { ["key"] = "Notes" });
            await Task.Delay(500, _controlCancellation.Token);
            await SendFarmInputAsync("/key/sendkey", new() { ["fn_key"] = "ENTER" });
            AppendFarmLog("Commands completed. Check C24C to confirm Notes opened.");
        }
        catch (Exception ex) { AppendFarmLog("Spotlight stopped: " + ex.Message); }
    }''')
method("FarmEmergencyStop_Click", '''    private async void FarmEmergencyStop_Click(object sender, RoutedEventArgs e)
    {
        await RequestFarmCancellationAsync();
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
            await FarmApi.SendAsync("/api/farm/emergency-stop", new { device_id = "C24C" });
            AppendFarmLog("C24C Stop confirmed. Job cleanup may still be finishing.");
            await PollFarmJobAsync();
        }
        catch (Exception ex) { AppendFarmLog("Stop not confirmed: " + ex.Message); }
    }''')
method("TriggerSingleUploadAsync", '''    private async Task TriggerSingleUploadAsync(string deviceId, string platform, string uploadFormat)
    {
        if (!FarmTargetPolicy.IsC24C(deviceId)) { AppendFarmLog("Only C24C is enabled for farm testing."); return; }
        await RunFarmJobAsync("single-upload", new { device_id = deviceId, platform, format = uploadFormat });
    }''')
method("FarmPreview_Down", '''    private async void FarmPreview_Down(object sender, MouseButtonEventArgs e)
    {
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
    }''')
path.write_text(source, encoding="utf-8")

xaml = root / "src/iMouse.Console/MainWindow.xaml"
text = xaml.read_text(encoding="utf-8-sig")
for old, new in {
    'Text="LAST JITTERED TOUCH"': 'Text="LAST CONFIRMED TAP"',
    'Text="Approach: (---, ---)"': 'Text="Exact selected point"',
    'Text="--- ms dwell • unique tap"': 'Text="No tap sent"',
    'Text="Status Bar Safe: 0–60px masked · Gaussian Click Engine"': 'Text="Manual preview controls the real C24C"',
    'ToolTip="Click live phone screen to send humanized jittered tap"': 'ToolTip="Tap the selected C24C at the exact point shown; margins are ignored"',
    'Content="⚡ 1-Click: Auto-Create &amp; Deploy"': 'Content="Create &amp; deploy C24C"',
    'Content="🔥 Run Cohort Warmup"': 'Content="Run C24C warmup"',
    'Content="⏱️ Scheduler Tick"': 'Content="Preview schedule"',
    'Content="💬 Funnel Suite"': 'Content="Check keyword replies"',
    'Text="PHONE RACK WALL &amp; MARKETING COHORTS"': 'Text="MARKETING PROFILES · ONLY C24C ENABLED FOR TESTING"',
    'Text="Gaussian Upload"': 'Text="Scoped input"',
    'Text="LIVE KERNEL 9913 RPC &amp; ACTIVITY STREAM"': 'Text="JOB STATUS &amp; ACTIVITY"',
}.items():
    assert old in text, old
    text = text.replace(old, new)
anchor = '<WrapPanel Grid.Row="0" Margin="0,0,0,10">'
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + '\n              <Button Content="Create content only" Click="FarmCreateContent_Click" MinHeight="30" Padding="10,5"/>\n              <Button Content="Check job" Click="FarmCheckJob_Click" MinHeight="30" Padding="10,5"/>')
anchor = '<TextBox x:Name="FarmKeywordBox" Text="SYSTEM" MinHeight="26" Margin="0,2,0,6" FontSize="12"/>'
assert text.count(anchor) == 1
text = text.replace(anchor, anchor + '\n              <Button Content="Save C24C profile" Click="FarmSavePersona_Click" MinHeight="26" Margin="0,0,0,6"/>')
xaml.write_text(text, encoding="utf-8")
print("Updated native farm handlers and labels using UTF-8.")
