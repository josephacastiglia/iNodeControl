using System.Text.Json;
using System.Windows;
using System.Windows.Controls;

namespace IMouse2;

internal sealed class FarmReadinessWindow : Window
{
    internal FarmReadinessWindow(JsonElement report)
    {
        Title = "Marketing feature readiness";
        Width = 760; Height = 700; MinWidth = 560; MinHeight = 420;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        SetResourceReference(BackgroundProperty, "SurfaceBrush");
        SetResourceReference(ForegroundProperty, "TextBrush");
        var body = new StackPanel { Margin = new Thickness(24) };
        body.Children.Add(new TextBlock { Text = "What you can use", FontSize = 24, FontWeight = FontWeights.SemiBold });
        body.Children.Add(new TextBlock { Text = "Local editing and media transfer are available in the candidate. Automated live workflows require further acceptance.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 8, 0, 18) });
        foreach (var feature in report.GetProperty("features").EnumerateArray())
        {
            body.Children.Add(new TextBlock { Text = feature.GetProperty("name").GetString() + " · " + feature.GetProperty("availability").GetString(), FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 12, 0, 4) });
            body.Children.Add(new TextBlock { Text = feature.GetProperty("detail").GetString(), TextWrapping = TextWrapping.Wrap });
        }
        Content = new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
    }
}
