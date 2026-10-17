// File: src/iMouse.Console/FarmAutomationWindow.cs
// Drop-in C# / .NET 8 WPF Marketing Farm & Automation Window for iMouse 2.0 Console.
// Connects directly to `tools/imouse_farm_server.py` (http://127.0.0.1:9914) and
// `src/iMouse.Kernel/ApiServer.cs` (http://127.0.0.1:9913/api).

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
using System.Windows.Media;
using System.Windows.Shapes;

namespace IMouse2.ConsoleApp;

public sealed class FarmAutomationWindow : Window
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(30) };
    private readonly string _farmServerUrl;
    private readonly string _kernelApiUrl;
    private Process? _managedServerProcess;

    private readonly StackPanel _phoneCardsPanel = new() { Orientation = Orientation.Vertical };
    private readonly TextBox _logBox = new()
    {
        IsReadOnly = true,
        VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        Background = new SolidColorBrush(Color.FromRgb(7, 11, 18)),
        Foreground = new SolidColorBrush(Color.FromRgb(167, 243, 208)),
        FontFamily = new FontFamily("Consolas"),
        FontSize = 11.5,
        TextWrapping = TextWrapping.Wrap,
        Height = 220,
        Margin = new Thickness(0, 8, 0, 0)
    };
    private readonly Canvas _jitterCanvas = new()
    {
        Width = 250,
        Height = 510,
        Background = new SolidColorBrush(Color.FromRgb(5, 8, 17))
    };
    private readonly ComboBox _cohortSelector = new() { Width = 140, Margin = new Thickness(6, 0, 6, 0) };
    private readonly TextBox _selectedDeviceBox = new() { Width = 90, Text = "C24C" };
    private readonly TextBox _nicheEditBox = new() { Width = 220, Text = "AI Workflow & SaaS Clipping" };
    private readonly TextBox _keywordEditBox = new() { Width = 90, Text = "SYSTEM" };

    public string FarmServerUrl => _farmServerUrl;
    public string KernelApiUrl => _kernelApiUrl;

    public static string NormalizeKernelApiUrl(string? rawAddress)
    {
        if (string.IsNullOrWhiteSpace(rawAddress))
            return "http://127.0.0.1:9913/api";

        var trimmed = rawAddress.Trim().TrimEnd('/');
        if (trimmed.Contains(":9911", StringComparison.Ordinal))
            throw new InvalidOperationException("Refusing vendor port 9911; use independent kernel port 9913.");

        if (!trimmed.StartsWith("http://", StringComparison.OrdinalIgnoreCase) &&
            !trimmed.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
        {
            trimmed = "http://" + trimmed;
        }

        if (!trimmed.EndsWith("/api", StringComparison.OrdinalIgnoreCase))
            trimmed += "/api";

        return trimmed;
    }

    public static string? ResolveFarmServerScriptPath(string? startDirectory = null)
    {
        var roots = new List<string>();
        if (!string.IsNullOrWhiteSpace(startDirectory))
            roots.Add(startDirectory!);
        if (!string.IsNullOrWhiteSpace(AppContext.BaseDirectory))
            roots.Add(AppContext.BaseDirectory);
        if (!string.IsNullOrWhiteSpace(Environment.CurrentDirectory))
            roots.Add(Environment.CurrentDirectory);

        foreach (var root in roots)
        {
            var dir = new DirectoryInfo(root);
            while (dir != null)
            {
                var candidate = System.IO.Path.Combine(dir.FullName, "tools", "imouse_farm_server.py");
                if (File.Exists(candidate))
                    return candidate;
                dir = dir.Parent;
            }
        }
        return null;
    }

    public FarmAutomationWindow(
        string farmServerUrl = "http://127.0.0.1:9914",
        string kernelApiUrl = "http://127.0.0.1:9913/api")
    {
        _farmServerUrl = (string.IsNullOrWhiteSpace(farmServerUrl) ? "http://127.0.0.1:9914" : farmServerUrl).Trim().TrimEnd('/');
        _kernelApiUrl = NormalizeKernelApiUrl(kernelApiUrl);

        Title = "iMouse 2.0 — 19-iPhone Marketing Farm & Social Automation Command Center";
        Width = 1280;
        Height = 820;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Background = new SolidColorBrush(Color.FromRgb(11, 15, 23));
        Foreground = Brushes.WhiteSmoke;

        BuildLayout();
        Loaded += async (_, _) =>
        {
            await EnsureFarmBackendRunningAsync();
            await RefreshFarmStateAsync();
        };
        Closed += (_, _) => StopManagedServer();
    }

    private void BuildLayout()
    {
        var root = new DockPanel { LastChildFill = true, Margin = new Thickness(12) };

        // 1. Top Command Bar (1-Click Content Factory, Cohort Warmup, Scheduler, Clone Winners, Funnel, 0-View Scan, Stop)
        var topBar = new WrapPanel
        {
            Margin = new Thickness(0, 0, 0, 12),
            VerticalAlignment = VerticalAlignment.Center
        };

        _cohortSelector.Items.Add("all");
        for (int c = 1; c <= 5; c++) _cohortSelector.Items.Add(c.ToString());
        _cohortSelector.SelectedIndex = 0;

        var btnAutoCreate = MakeButton("⚡ 1-Click: Auto-Create & Deploy Today's Content", Color.FromRgb(37, 99, 235));
        btnAutoCreate.Click += async (_, _) => await TriggerAutoCreateAndDeployAsync();

        var btnWarmup = MakeButton("🔥 Run Cohort Warmup Wave", Color.FromRgb(124, 58, 237));
        btnWarmup.Click += async (_, _) => await TriggerCohortWarmupAsync();

        var btnScheduler = MakeButton("⏱️ Cohort Scheduler Tick", Color.FromRgb(79, 70, 229));
        btnScheduler.Click += async (_, _) => await TriggerCohortSchedulerTickAsync();

        var btnCloneWinners = MakeButton("🏆 Clone Winning Hooks", Color.FromRgb(217, 119, 6));
        btnCloneWinners.Click += async (_, _) => await TriggerCloneWinningHooksAsync();

        var btnFunnel = MakeButton("💬 Pin CTA + Comment-to-DM + Swarm", Color.FromRgb(16, 185, 129));
        btnFunnel.Click += async (_, _) => await TriggerFunnelSuiteAsync();

        var btnScanViews = MakeButton("🔍 Scan 0-View Grid", Color.FromRgb(14, 116, 144));
        btnScanViews.Click += async (_, _) => await TriggerScanProfileViewsAsync(_selectedDeviceBox.Text);

        var btnWebUi = MakeButton("🌐 Open Full Web Dashboard (:9914)", Color.FromRgb(30, 41, 59));
        btnWebUi.Click += (_, _) => Process.Start(new ProcessStartInfo(_farmServerUrl) { UseShellExecute = true });

        var btnStopAll = MakeButton("🛑 Emergency Stop (/input/stop)", Color.FromRgb(225, 29, 72));
        btnStopAll.Click += async (_, _) => await EmergencyStopDeviceAsync(_selectedDeviceBox.Text);

        topBar.Children.Add(_cohortSelector);
        topBar.Children.Add(btnAutoCreate);
        topBar.Children.Add(btnWarmup);
        topBar.Children.Add(btnScheduler);
        topBar.Children.Add(btnCloneWinners);
        topBar.Children.Add(btnFunnel);
        topBar.Children.Add(btnScanViews);
        topBar.Children.Add(btnWebUi);
        topBar.Children.Add(btnStopAll);
        DockPanel.SetDock(topBar, Dock.Top);
        root.Children.Add(topBar);

        // 2. Main 3-Column Split Grid matching iMouse.Console
        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(280) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(360) });

        // Left Column: 500x1080 Gaussian Click Visualizer
        var leftPanel = new Border
        {
            Background = new SolidColorBrush(Color.FromRgb(17, 24, 39)),
            BorderBrush = new SolidColorBrush(Color.FromRgb(38, 51, 77)),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(10),
            Padding = new Thickness(10),
            Margin = new Thickness(0, 0, 10, 0)
        };
        var leftStack = new StackPanel();
        leftStack.Children.Add(new TextBlock
        {
            Text = "📱 500×1080 Gaussian Tap Visualizer",
            FontWeight = FontWeights.Bold,
            Margin = new Thickness(0, 0, 0, 8)
        });
        leftStack.Children.Add(_jitterCanvas);
        leftPanel.Child = leftStack;
        Grid.SetColumn(leftPanel, 0);
        grid.Children.Add(leftPanel);

        // Center Column: 19-Phone Marketing Persona & Status Cards
        var centerPanel = new Border
        {
            Background = new SolidColorBrush(Color.FromRgb(17, 24, 39)),
            BorderBrush = new SolidColorBrush(Color.FromRgb(38, 51, 77)),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(10),
            Padding = new Thickness(10),
            Margin = new Thickness(0, 0, 10, 0)
        };
        var scroll = new ScrollViewer
        {
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            Content = _phoneCardsPanel
        };
        centerPanel.Child = scroll;
        Grid.SetColumn(centerPanel, 1);
        grid.Children.Add(centerPanel);

        // Right Column: Single-Phone Upload Controls, Persona Editor & Live Log
        var rightPanel = new Border
        {
            Background = new SolidColorBrush(Color.FromRgb(17, 24, 39)),
            BorderBrush = new SolidColorBrush(Color.FromRgb(38, 51, 77)),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(10),
            Padding = new Thickness(10)
        };
        var rightStack = new StackPanel();
        rightStack.Children.Add(new TextBlock
        {
            Text = "🎯 Selected Phone Persona & Upload Actions",
            FontWeight = FontWeights.Bold,
            Margin = new Thickness(0, 0, 0, 8)
        });

        var editorWrap = new WrapPanel { Margin = new Thickness(0, 0, 0, 8) };
        editorWrap.Children.Add(_selectedDeviceBox);
        editorWrap.Children.Add(_nicheEditBox);
        editorWrap.Children.Add(_keywordEditBox);
        var btnSavePersona = MakeButton("💾 Save Persona", Color.FromRgb(59, 130, 246));
        btnSavePersona.Click += async (_, _) => await SavePersonaAsync();
        editorWrap.Children.Add(btnSavePersona);
        rightStack.Children.Add(editorWrap);

        var uploadButtonsWrap = new WrapPanel { Margin = new Thickness(0, 0, 0, 10) };
        foreach (var (label, plat, fmt) in new[]
        {
            ("📸 IG Reel", "instagram", "ig_reel"),
            ("🖼️ IG Carousel", "instagram", "ig_carousel"),
            ("🎵 TikTok Video", "tiktok", "tt_video"),
            ("📑 TT Photo Mode", "tiktok", "tt_photo_carousel"),
            ("𝕏 Video (45s Guard)", "x", "x_video"),
            ("▶️ YT Short", "youtube", "yt_short")
        })
        {
            var b = MakeButton(label, Color.FromRgb(30, 41, 59));
            b.Click += async (_, _) => await TriggerSingleUploadAsync(_selectedDeviceBox.Text, plat, fmt);
            uploadButtonsWrap.Children.Add(b);
        }
        rightStack.Children.Add(uploadButtonsWrap);

        rightStack.Children.Add(new TextBlock
        {
            Text = "📡 7-Layer Execution & Kernel 9913 Log",
            FontWeight = FontWeights.Bold
        });
        rightStack.Children.Add(_logBox);
        rightPanel.Child = rightStack;
        Grid.SetColumn(rightPanel, 2);
        grid.Children.Add(rightPanel);

        root.Children.Add(grid);
        Content = root;
    }

    private static Button MakeButton(string text, Color bg) => new()
    {
        Content = text,
        Background = new SolidColorBrush(bg),
        Foreground = Brushes.White,
        Padding = new Thickness(10, 6, 10, 6),
        Margin = new Thickness(0, 0, 6, 6),
        BorderThickness = new Thickness(0),
        Cursor = System.Windows.Input.Cursors.Hand
    };

    private void AppendLog(string message)
    {
        Dispatcher.Invoke(() =>
        {
            _logBox.Text = $"[{DateTime.Now:HH:mm:ss.fff}] {message}\n" + _logBox.Text;
        });
    }

    private async Task EnsureFarmBackendRunningAsync()
    {
        try
        {
            var res = await Http.GetAsync(_farmServerUrl + "/health");
            if (res.IsSuccessStatusCode)
            {
                AppendLog("Connected to running 7-Layer Farm Server on " + _farmServerUrl);
                return;
            }
        }
        catch { }

        string? scriptPath = ResolveFarmServerScriptPath();
        if (scriptPath != null && File.Exists(scriptPath))
        {
            _managedServerProcess = Process.Start(new ProcessStartInfo("python", $"\"{scriptPath}\" --no-browser")
            {
                WorkingDirectory = System.IO.Path.GetDirectoryName(System.IO.Path.GetDirectoryName(scriptPath)) ?? AppContext.BaseDirectory,
                UseShellExecute = false,
                CreateNoWindow = true
            });
            await Task.Delay(800);
            AppendLog("Started managed background process: " + scriptPath);
        }
    }

    public async Task RefreshFarmStateAsync()
    {
        try
        {
            string json = await Http.GetStringAsync(_farmServerUrl + "/api/farm/state");
            using var doc = JsonDocument.Parse(json);
            if (!doc.RootElement.TryGetProperty("personas", out var personas)) return;

            _phoneCardsPanel.Children.Clear();
            foreach (var p in personas.EnumerateArray())
            {
                string id = p.GetProperty("device_id").GetString() ?? "";
                int cohort = p.GetProperty("cohort").GetInt32();
                int day = p.GetProperty("account_day").GetInt32();
                string niche = p.GetProperty("niche").GetString() ?? "";
                string kw = p.GetProperty("cta_keyword").GetString() ?? "";
                bool paused = p.GetProperty("paused_zero_view").GetInt32() != 0;

                var card = new Border
                {
                    Background = new SolidColorBrush(Color.FromRgb(22, 31, 51)),
                    BorderBrush = new SolidColorBrush(paused ? Color.FromRgb(244, 63, 94) : Color.FromRgb(38, 51, 77)),
                    BorderThickness = new Thickness(1),
                    CornerRadius = new CornerRadius(6),
                    Padding = new Thickness(8),
                    Margin = new Thickness(0, 0, 0, 6)
                };
                card.Child = new TextBlock
                {
                    Text = $"{id} (Cohort {cohort} • Day {day}) — {niche} | CTA: '{kw}' " + (paused ? "[0-VIEW PAUSED]" : "[ACTIVE]"),
                    Foreground = Brushes.WhiteSmoke
                };
                card.MouseLeftButtonUp += (_, _) =>
                {
                    _selectedDeviceBox.Text = id;
                    _nicheEditBox.Text = niche;
                    _keywordEditBox.Text = kw;
                };
                _phoneCardsPanel.Children.Add(card);
            }
        }
        catch (Exception ex)
        {
            AppendLog("State refresh warning: " + ex.Message);
        }
    }

    private async Task TriggerAutoCreateAndDeployAsync()
    {
        string cohort = _cohortSelector.SelectedItem?.ToString() ?? "all";
        AppendLog($"Starting 5-Stage Auto-Create & Deploy for Cohort={cohort}...");
        var payload = JsonSerializer.Serialize(new { cohort });
        var resp = await Http.PostAsync(_farmServerUrl + "/api/farm/auto-create-and-deploy",
            new StringContent(payload, Encoding.UTF8, "application/json"));
        string body = await resp.Content.ReadAsStringAsync();
        AppendLog("Auto-Create & Deploy finished: " + body);
        await RefreshFarmStateAsync();
    }

    private async Task TriggerSingleUploadAsync(string deviceId, string platform, string uploadFormat)
    {
        var payload = JsonSerializer.Serialize(new { device_id = deviceId, platform, upload_format = uploadFormat });
        var resp = await Http.PostAsync(_farmServerUrl + "/api/farm/upload-single",
            new StringContent(payload, Encoding.UTF8, "application/json"));
        string body = await resp.Content.ReadAsStringAsync();
        AppendLog($"Uploaded {uploadFormat} on {deviceId}");

        using var doc = JsonDocument.Parse(body);
        if (doc.RootElement.TryGetProperty("result", out var res) &&
            res.TryGetProperty("clickCoordinates", out var coords))
        {
            foreach (var pt in coords.EnumerateArray())
            {
                int x = pt[1].GetInt32();
                int y = pt[2].GetInt32();
                DrawTapDot(x, y);
            }
        }
    }

    private async Task TriggerCohortWarmupAsync()
    {
        string cohort = _cohortSelector.SelectedItem?.ToString() ?? "all";
        var payload = JsonSerializer.Serialize(new { cohort });
        var resp = await Http.PostAsync(_farmServerUrl + "/api/farm/warmup-wave",
            new StringContent(payload, Encoding.UTF8, "application/json"));
        AppendLog("Cohort Warmup Wave completed: " + await resp.Content.ReadAsStringAsync());
    }

    private async Task TriggerCohortSchedulerTickAsync()
    {
        string selected = _cohortSelector.SelectedItem?.ToString() ?? "1";
        int cohort = int.TryParse(selected, out int parsed) ? parsed : 1;
        var payload = JsonSerializer.Serialize(new { cohort, execute_actions = true });
        var resp = await Http.PostAsync(_farmServerUrl + "/api/farm/scheduler-tick",
            new StringContent(payload, Encoding.UTF8, "application/json"));
        AppendLog($"Cohort {cohort} Scheduler Tick completed: " + await resp.Content.ReadAsStringAsync());
        await RefreshFarmStateAsync();
    }

    private async Task TriggerCloneWinningHooksAsync()
    {
        var payload = JsonSerializer.Serialize(new { });
        var resp = await Http.PostAsync(_farmServerUrl + "/api/farm/clone-winners",
            new StringContent(payload, Encoding.UTF8, "application/json"));
        AppendLog("Cloned winning hooks across sibling personas: " + await resp.Content.ReadAsStringAsync());
        await RefreshFarmStateAsync();
    }

    private async Task TriggerScanProfileViewsAsync(string deviceId)
    {
        var payload = JsonSerializer.Serialize(new { device_id = deviceId });
        var resp = await Http.PostAsync(_farmServerUrl + "/api/farm/scan-profile-views",
            new StringContent(payload, Encoding.UTF8, "application/json"));
        AppendLog($"Scanned profile grid views for {deviceId}: " + await resp.Content.ReadAsStringAsync());
        await RefreshFarmStateAsync();
    }

    private async Task TriggerFunnelSuiteAsync()
    {
        string devId = _selectedDeviceBox.Text;
        foreach (string act in new[] { "pin_cta", "comment_to_dm", "micro_swarm" })
        {
            var payload = JsonSerializer.Serialize(new { device_id = devId, action = act });
            await Http.PostAsync(_farmServerUrl + "/api/farm/funnel-action",
                new StringContent(payload, Encoding.UTF8, "application/json"));
            AppendLog($"Executed Funnel step '{act}' for {devId}");
        }
    }

    private async Task SavePersonaAsync()
    {
        var payload = JsonSerializer.Serialize(new
        {
            device_id = _selectedDeviceBox.Text,
            niche = _nicheEditBox.Text,
            cta_keyword = _keywordEditBox.Text
        });
        await Http.PostAsync(_farmServerUrl + "/api/farm/update-persona",
            new StringContent(payload, Encoding.UTF8, "application/json"));
        AppendLog($"Updated SQLite persona for {_selectedDeviceBox.Text}");
        await RefreshFarmStateAsync();
    }

    private async Task EmergencyStopDeviceAsync(string deviceId)
    {
        var payload = JsonSerializer.Serialize(new { fun = "/input/stop", data = new { id = deviceId } });
        await Http.PostAsync(_kernelApiUrl + "/", new StringContent(payload, Encoding.UTF8, "application/json"));
        AppendLog($"Sent first-click /input/stop for {deviceId}");
    }

    private void DrawTapDot(int x500, int y1080)
    {
        double cx = x500 * 0.5;
        double cy = Math.Max(0, (y1080 - 60) * 0.5);
        var dot = new Ellipse
        {
            Width = 6,
            Height = 6,
            Fill = new SolidColorBrush(Color.FromRgb(244, 63, 94))
        };
        Canvas.SetLeft(dot, cx - 3);
        Canvas.SetTop(dot, cy - 3);
        _jitterCanvas.Children.Add(dot);
    }

    private void StopManagedServer()
    {
        try
        {
            if (_managedServerProcess is { HasExited: false })
                _managedServerProcess.Kill(entireProcessTree: true);
        }
        catch { }
    }
}
