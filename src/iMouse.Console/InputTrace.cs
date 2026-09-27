using System.IO;
using System.Windows;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;

namespace IMouse2;

/// <summary>
/// Opt-in diagnostic trace of mouse routing, for finding where a click that does nothing stops.
/// Off unless the IMOUSE_INPUT_TRACE environment variable names a file. It logs, in order:
/// the window's raw mouse messages; every input WPF stages (with Mouse.Captured and
/// Mouse.DirectlyOver); each element that receives a button event and whether it was handled;
/// capture changes; button clicks; and the hit-test chain at each press. It only observes.
/// </summary>
static class InputTrace
{
    private static StreamWriter? _out;
    private static readonly object Gate = new();

    public static void AttachIfRequested(Window window)
    {
        string? path = Environment.GetEnvironmentVariable("IMOUSE_INPUT_TRACE");
        if (string.IsNullOrWhiteSpace(path) || _out is not null) return;
        _out = new StreamWriter(path, append: true) { AutoFlush = true };
        Write($"trace start pid {Environment.ProcessId}");

        window.SourceInitialized += (_, _) =>
        {
            if (PresentationSource.FromVisual(window) is HwndSource source)
                source.AddHook((IntPtr hwnd, int msg, IntPtr w, IntPtr l, ref bool handled) =>
                {
                    string? name = msg switch
                    {
                        0x0021 => "WM_MOUSEACTIVATE", 0x0201 => "WM_LBUTTONDOWN", 0x0202 => "WM_LBUTTONUP",
                        0x0215 => "WM_CAPTURECHANGED", 0x0006 => "WM_ACTIVATE", 0x0246 => "WM_POINTERDOWN",
                        0x0247 => "WM_POINTERUP", 0x0245 => "WM_POINTERUPDATE", 0x02A3 => "WM_MOUSELEAVE", _ => null,
                    };
                    if (name is not null && msg != 0x0245)
                        Write($"msg {name} w=0x{w.ToInt64():X} x={(short)(l.ToInt64() & 0xFFFF)} y={(short)((l.ToInt64() >> 16) & 0xFFFF)}");
                    return IntPtr.Zero;
                });
        };
        window.Activated += (_, _) => Write("window Activated");
        window.Deactivated += (_, _) => Write("window Deactivated");

        InputManager.Current.PreProcessInput += (_, e) =>
        {
            if (e.StagingItem.Input is MouseButtonEventArgs b)
                Write($"stage {b.RoutedEvent.Name} {b.ChangedButton} {b.ButtonState} source={Describe(b.Source)} captured={Describe(Mouse.Captured)} over={Describe(Mouse.DirectlyOver)}");
            else if (e.StagingItem.Input.GetType().Name == "InputReportEventArgs")
            {
                // The report types are internal; read the report and its Actions flags by reflection.
                const System.Reflection.BindingFlags any = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic;
                object? report = e.StagingItem.Input.GetType().GetProperty("Report", any)?.GetValue(e.StagingItem.Input);
                string kind = report?.GetType().Name ?? "?";
                string actions = report?.GetType().GetProperty("Actions", any)?.GetValue(report)?.ToString() ?? "";
                if (kind != "RawMouseInputReport" || actions.Contains("Button1") || actions.Contains("Activate") || actions.Contains("Capture"))
                    Write($"stage report {kind} actions={actions} canceled={e.Canceled}");
            }
        };
        InputManager.Current.PostProcessInput += (_, e) =>
        {
            if (e.StagingItem.Input is MouseButtonEventArgs b)
                Write($"done  {b.RoutedEvent.Name} handled={b.Handled} captured={Describe(Mouse.Captured)}");
        };

        void Routed(RoutedEvent ev) => EventManager.RegisterClassHandler(typeof(UIElement), ev,
            new MouseButtonEventHandler((s, e) =>
            {
                if (e.ChangedButton == MouseButton.Left)
                    Write($"route {ev.Name} at {Describe(s)} handled={e.Handled} original={Describe(e.OriginalSource)} enabled={(s as UIElement)?.IsEnabled}");
            }), handledEventsToo: true);
        Routed(UIElement.PreviewMouseLeftButtonDownEvent);
        Routed(UIElement.MouseLeftButtonDownEvent);
        Routed(UIElement.MouseLeftButtonUpEvent);
        EventManager.RegisterClassHandler(typeof(UIElement), Mouse.GotMouseCaptureEvent,
            new MouseEventHandler((s, e) => { if (ReferenceEquals(s, e.OriginalSource)) Write($"capture got  {Describe(s)}"); }), true);
        EventManager.RegisterClassHandler(typeof(UIElement), Mouse.LostMouseCaptureEvent,
            new MouseEventHandler((s, e) => { if (ReferenceEquals(s, e.OriginalSource)) Write($"capture lost {Describe(s)}"); }), true);
        EventManager.RegisterClassHandler(typeof(ButtonBase), ButtonBase.ClickEvent,
            new RoutedEventHandler((s, e) => { if (ReferenceEquals(s, e.OriginalSource)) Write($"click {Describe(s)}"); }), true);
        EventManager.RegisterClassHandler(typeof(UIElement), UIElement.PreviewMouseLeftButtonDownEvent,
            new MouseButtonEventHandler((s, e) =>
            {
                if (!ReferenceEquals(s, window)) return;
                var chain = new List<string>();
                var hit = window.InputHitTest(e.GetPosition(window)) as DependencyObject;
                for (var d = hit; d is not null && chain.Count < 12; d = VisualTreeHelper.GetParent(d)) chain.Add(Describe(d));
                Write($"hit  {string.Join(" < ", chain)} focus={Describe(Keyboard.FocusedElement)}");
            }), true);
    }

    private static string Describe(object? o) => o switch
    {
        null => "null",
        FrameworkElement f when f.Name.Length > 0 => $"{f.GetType().Name}#{f.Name}",
        System.Windows.Controls.ContentControl c when c.Content is string s => $"{c.GetType().Name}'{s}'",
        _ => o.GetType().Name,
    };

    private static void Write(string line)
    {
        lock (Gate) _out?.WriteLine($"{DateTime.Now:HH:mm:ss.fff} {line}");
    }
}
