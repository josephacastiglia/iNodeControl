using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;

namespace IMouse2;

/// <summary>
/// The operator's review queue. It lists prepared packages waiting for review and records one
/// decision at a time: approve or reject. Planned slots and the dry-run plan are shown read-only.
/// Nothing here plans, commits or runs a slot, and nothing touches a phone: slots are planned with
/// `farm_schedule_cli.py plan --commit` and run with `farm_schedule_cli.py run`, both by the operator.
/// </summary>
internal sealed partial class FarmScheduleQueueWindow : Window
{
    internal const string QueueRoute = "/api/farm/schedule-queue";
    private static readonly Regex Label = new("^[a-z][a-z0-9-]{0,31}$");
    private static readonly Regex Hexish = new("^[0-9a-f-]{4,}$");
    private readonly FarmApiClient _api;
    private readonly ListBox _pending = new() { MinHeight = 140, MaxHeight = 240, Margin = new Thickness(0, 6, 0, 8) };
    private readonly TextBox _detail = ReadOnlyBox(110);
    private readonly TextBox _account = new() { MinWidth = 180, Margin = new Thickness(0, 0, 12, 0) };
    private readonly TextBox _reason = new() { MinWidth = 280 };
    private readonly Button _approve = ActionButton("Approve");
    private readonly Button _reject = ActionButton("Reject");
    private readonly Button _refresh = ActionButton("Refresh");
    private readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 10, 0, 10) };
    private readonly TextBox _slots = ReadOnlyBox(110);
    private readonly TextBox _plan = ReadOnlyBox(130);
    private bool _busy, _reviewOnly;

    internal sealed record Item(string Id, JsonElement Record)
    {
        public override string ToString() => Summary(Record);
    }

    internal FarmScheduleQueueWindow(FarmApiClient api)
    {
        _api = api;
        Title = "Review queue"; Width = 760; Height = 860; MinWidth = 520; MinHeight = 520;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        SetResourceReference(BackgroundProperty, "SurfaceBrush"); SetResourceReference(ForegroundProperty, "TextBrush");
        var body = new StackPanel { Margin = new Thickness(24) };
        body.Children.Add(new TextBlock { Text = "Review prepared packages", FontSize = 24, FontWeight = FontWeights.SemiBold });
        body.Children.Add(new TextBlock { Text = "Approve or reject one package at a time. Your decision is recorded in the local queue only: this window never plans or runs a slot, never touches a phone and never posts. Approved packages get a slot only when you run `farm_schedule_cli.py plan --commit`.", TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 10, 0, 12) });
        body.Children.Add(new TextBlock { Text = "Waiting for review", FontWeight = FontWeights.SemiBold });
        body.Children.Add(_pending);
        body.Children.Add(_detail);
        var fields = new WrapPanel { Margin = new Thickness(0, 12, 0, 0) };
        fields.Children.Add(Field("Account label (only if the package has none, like acct-2)", _account));
        fields.Children.Add(Field("Reason (needed to reject)", _reason));
        body.Children.Add(fields);
        var actions = new WrapPanel { Margin = new Thickness(0, 12, 0, 0) };
        actions.Children.Add(_approve); actions.Children.Add(_reject); actions.Children.Add(_refresh);
        body.Children.Add(actions);
        body.Children.Add(_status);
        body.Children.Add(new TextBlock { Text = "Planned slots (read-only)", FontWeight = FontWeights.SemiBold });
        body.Children.Add(_slots);
        body.Children.Add(new TextBlock { Text = "Dry-run plan (read-only; nothing is committed)", FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 12, 0, 0) });
        body.Children.Add(_plan);
        Content = new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Loaded += async (_, _) => await RunAsync(() => RefreshAsync());
        _pending.SelectionChanged += (_, _) => { _account.Text = ""; _reason.Text = ""; ShowSelected(); };
        _approve.Click += async (_, _) => await RunAsync(ApproveAsync);
        _reject.Click += async (_, _) => await RunAsync(RejectAsync);
        _refresh.Click += async (_, _) => await RunAsync(() => RefreshAsync());
        Buttons();
    }

    private static TextBox ReadOnlyBox(double height) => new()
    {
        IsReadOnly = true, TextWrapping = TextWrapping.Wrap, Height = height, Margin = new Thickness(0, 6, 0, 0),
        VerticalContentAlignment = VerticalAlignment.Top, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
    };
    private static Button ActionButton(string text) => new() { Content = text, Padding = new Thickness(12, 8, 12, 8), Margin = new Thickness(0, 0, 8, 0) };
    private static StackPanel Field(string label, TextBox box)
    {
        var panel = new StackPanel { Margin = new Thickness(0, 0, 12, 0) };
        panel.Children.Add(new TextBlock { Text = label, Margin = new Thickness(0, 0, 0, 4), TextWrapping = TextWrapping.Wrap, MaxWidth = 300 });
        panel.Children.Add(box);
        return panel;
    }
    internal static bool IsAccountLabel(string value) => Label.IsMatch(value) && !Hexish.IsMatch(value);

    private async Task RunAsync(Func<Task> action)
    {
        if (_busy) return;
        _busy = true; Buttons();
        try { await action(); }
        catch (Exception ex) { _status.Text = ex.Message; }
        finally { _busy = false; Buttons(); }
    }
    private void Buttons()
    {
        bool chosen = _pending.SelectedItem is Item;
        _approve.IsEnabled = _reject.IsEnabled = !_busy && _reviewOnly && chosen;
        _account.IsEnabled = _reason.IsEnabled = !_busy && _reviewOnly && chosen;
        _refresh.IsEnabled = _pending.IsEnabled = !_busy;
    }

    private async Task ApproveAsync()
    {
        var item = Selected();
        string account = _account.Text.Trim();
        bool hasAccount = item.Record.TryGetProperty("account", out var current) && current.ValueKind == JsonValueKind.String;
        if (account.Length == 0 && !hasAccount)
            throw new InvalidOperationException($"Package {item.Id} has no account yet. Type its account label (like acct-2), then approve.");
        if (account.Length > 0 && !IsAccountLabel(account))
            throw new InvalidOperationException("An account is an opaque label like acct-2: lowercase letters, digits and dashes. Never a handle or a device ID.");
        await DecideAsync("/approve", account.Length == 0 ? new { id = item.Id } : new { id = item.Id, account }, item.Id);
    }
    private async Task RejectAsync()
    {
        var item = Selected();
        string reason = _reason.Text.Trim();
        if (reason.Length == 0) throw new InvalidOperationException($"Say why package {item.Id} is rejected. A rejected package is final; changed content comes back as a new package.");
        await DecideAsync("/reject", new { id = item.Id, reason }, item.Id);
    }
    private Item Selected() => _pending.SelectedItem as Item ?? throw new InvalidOperationException("Choose a package waiting for review.");

    // Approve and reject are safe to repeat: a second approve or reject of the same package changes
    // nothing. So a lost answer is settled by reading the queue again, never by resending blindly.
    private async Task DecideAsync(string action, object body, string id)
    {
        string note;
        try
        {
            var result = await _api.SendAsync(QueueRoute + action, body);
            note = $"Package {id} is {result.GetProperty("package").GetProperty("state").GetString()}.";
            if (!Off(result, "startsRuns") || !Off(result, "phoneInput"))
                note += " The backend did not confirm this decision started nothing; check it before going on.";
        }
        catch (FarmRequestRejectedException ex) when (ex.DefinitelyNotAccepted) { note = $"Package {id} was not changed: {ex.Message}"; }
        catch (Exception ex) { note = $"Package {id}: the answer was lost ({ex.Message}). The queue below was read again; check it before deciding again."; }
        await RefreshAsync(note);
    }

    private async Task RefreshAsync(string? note = null)
    {
        try { Apply(await _api.SendAsync(QueueRoute)); }
        catch (Exception ex) when (note is not null) { throw new InvalidOperationException(note + " Reading the queue again failed: " + ex.Message, ex); }
        if (note is not null) _status.Text = note + "\n" + _status.Text;
    }

    private static bool Off(JsonElement element, string name) => element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.False;

    internal void Apply(JsonElement response)
    {
        var view = response.GetProperty("scheduleQueue");
        var schedule = view.GetProperty("schedule"); var plan = view.GetProperty("plan");
        _reviewOnly = Off(response, "startsRuns") && Off(response, "phoneInput") && Off(response, "publishing")
            && plan.TryGetProperty("dryRun", out var dry) && dry.ValueKind == JsonValueKind.True;
        string? selected = (_pending.SelectedItem as Item)?.Id;
        string account = _account.Text, reason = _reason.Text;
        var items = view.GetProperty("pending").EnumerateArray().Select(p => new Item(PackageId(p.GetProperty("id")), p.Clone())).ToArray();
        _pending.ItemsSource = items;
        _pending.SelectedItem = items.FirstOrDefault(i => i.Id == selected) ?? items.FirstOrDefault();
        if (selected is not null && (_pending.SelectedItem as Item)?.Id == selected) { _account.Text = account; _reason.Text = reason; }
        ShowSelected();
        int planned = schedule.GetProperty("slots").GetArrayLength();
        _status.Text = $"{items.Length} waiting for review · {planned} planned slot(s) · {Count(schedule, "approved")} approved without a slot · {Count(schedule, "running")} running.";
        if (!_reviewOnly) _status.Text += "\nThis backend did not confirm the view is review-only (no runs, no phone input, no posting, dry-run plan). Approve and reject stay off.";
        _slots.Text = DescribeSlots(schedule);
        _plan.Text = DescribePlan(plan);
        Buttons();
    }

    private static int Count(JsonElement schedule, string state) => schedule.TryGetProperty(state, out var ids) ? ids.GetArrayLength() : 0;
    internal static string PackageId(JsonElement id) => id.ValueKind == JsonValueKind.Number ? id.GetRawText() : id.GetString() ?? "";
    private static string Text(JsonElement e, string name) => e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "";
    private static string When(JsonElement seconds) => DateTimeOffset.FromUnixTimeSeconds((long)seconds.GetDouble()).ToLocalTime().ToString("ddd yyyy-MM-dd HH:mm");
    private static string Phone(JsonElement package) =>
        package.TryGetProperty("source", out var source) && source.ValueKind == JsonValueKind.Object && source.TryGetProperty("slot", out var slot) && slot.ValueKind == JsonValueKind.Number
            ? "phone " + slot.GetRawText() : "no phone yet";
    private static string Account(JsonElement package) => Text(package, "account") is { Length: > 0 } account ? account : "account set at approve";

    internal static string Summary(JsonElement package) =>
        $"pkg {PackageId(package.GetProperty("id"))} · {Text(package, "platform")}/{Text(package, "format")} · {Phone(package)} · {Account(package)}";

    private void ShowSelected()
    {
        if (_pending.SelectedItem is not Item item) { _detail.Text = "Nothing is waiting for review."; Buttons(); return; }
        var p = item.Record; var lines = new List<string> { Summary(p) };
        string caption = Text(p, "caption");
        lines.Add(caption.Length > 0 ? "Caption: " + caption : "No caption.");
        if (p.TryGetProperty("source", out var source) && source.ValueKind == JsonValueKind.Object)
        {
            if (source.TryGetProperty("stagedFiles", out var files) && files.ValueKind == JsonValueKind.Array)
                lines.Add($"{files.GetArrayLength()} file(s): " + string.Join(", ", files.EnumerateArray().Select(f => Path.GetFileName(f.GetString() ?? ""))));
            if (Text(source, "manifestSha256") is { Length: >= 12 } sha) lines.Add("Manifest " + sha[..12] + "…");
        }
        if (p.TryGetProperty("submittedAt", out var at) && at.ValueKind == JsonValueKind.Number) lines.Add("Submitted " + When(at));
        _detail.Text = string.Join("\n", lines);
        Buttons();
    }

    internal static string DescribeSlots(JsonElement schedule)
    {
        var slots = schedule.GetProperty("slots").EnumerateArray().Select(s =>
            $"{When(s.GetProperty("at"))} · {Text(s, "account")} · {Text(s, "platform")}/{Text(s, "format")} · pkg {PackageId(s.GetProperty("id"))}").ToList();
        return slots.Count == 0 ? "No planned slots." : string.Join("\n", slots);
    }

    internal static string DescribePlan(JsonElement plan)
    {
        var lines = new List<string> { "Dry run: what `plan --commit` would add now. Nothing here is recorded or run." };
        foreach (var p in plan.GetProperty("proposed").EnumerateArray())
            lines.Add($"Would plan pkg {PackageId(p.GetProperty("id"))} at {When(p.GetProperty("slot"))}");
        foreach (var u in plan.GetProperty("unplaced").EnumerateArray())
            lines.Add($"No slot for pkg {PackageId(u.GetProperty("id"))} ({Text(u, "account")}, {Text(u, "platform")}): {Text(u, "reason")}");
        var lapsing = plan.GetProperty("lapsing").EnumerateArray().Select(PackageId).ToArray();
        if (lapsing.Length > 0) lines.Add("Lapsing (slot passed unrun; never run late): " + string.Join(", ", lapsing));
        if (lines.Count == 1) lines.Add("Nothing approved is waiting for a slot.");
        return string.Join("\n", lines);
    }
}
