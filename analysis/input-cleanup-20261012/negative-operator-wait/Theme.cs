using System.Windows;
using System.Windows.Media;

namespace IMouse2;

/// <summary>
/// Swaps the whole palette at runtime.
///
/// Every themed colour is a keyed brush in App.xaml and every reference to one is a
/// DynamicResource, so replacing the brush object in the application's resource dictionary
/// repaints everything that uses it. That is the reason the styles in App.xaml use
/// DynamicResource rather than StaticResource: a static reference is resolved once at load
/// and would leave half the window stuck in the old palette.
///
/// Light is the default and is deliberately plain - white surfaces, hairline rules, one
/// restrained accent. Night is not the light palette inverted; dark surfaces need a dimmer
/// accent and a lower-contrast muted tone or the whole window glares.
/// </summary>
public static class Theme
{
    public static bool IsNight { get; private set; }

    private static readonly (string Key, string Light, string Night)[] Palette =
    [
        ("CanvasBrush",      "#FFFFFF", "#0F1115"),
        ("SurfaceBrush",     "#FFFFFF", "#171A20"),
        ("RaisedBrush",      "#F5F6F8", "#1F242C"),
        ("EdgeBrush",        "#E2E5E9", "#2C333D"),
        ("TextBrush",        "#14171A", "#ECEFF3"),
        ("MutedBrush",       "#6B7280", "#98A2B0"),
        ("AccentBrush",      "#2F6FED", "#4C8DFF"),
        ("OnAccentBrush",    "#FFFFFF", "#0A1220"),
        ("OkBrush",          "#0E9F6E", "#34D399"),
        ("WarnBrush",        "#B45309", "#F59E0B"),
        ("BadBrush",         "#DC2626", "#F87171"),
        // The stage sits behind a letterboxed phone. Light grey rather than white so the
        // phone's own white screens still read as a distinct object.
        ("StageBrush",       "#EDEFF2", "#06080B"),
        ("WallBrush",        "#FAFBFC", "#12151A"),
        ("TileBrush",        "#FFFFFF", "#1A1E25"),
        ("ItemBrush",        "#FFFFFF", "#1A1E25"),
        ("ItemHoverBrush",   "#F2F5FA", "#232932"),
        // Tinted toward the accent, not toward the OK green - this chip carries accent-
        // coloured text, and a green ground under blue text read as a mismatch in night mode.
        ("TargetBrush",      "#EAF2FE", "#16233A"),
        ("LogBrush",         "#FAFBFC", "#0C0E12"),
        ("ScrollThumbBrush", "#C7CCD3", "#3A424E"),
    ];

    public static void Apply(bool night)
    {
        var app = Application.Current;
        if (app is null) return;
        IsNight = night;
        foreach (var (key, light, dark) in Palette)
        {
            var brush = new SolidColorBrush((Color)ColorConverter.ConvertFromString(night ? dark : light));
            brush.Freeze();
            app.Resources[key] = brush;
        }
    }
}
