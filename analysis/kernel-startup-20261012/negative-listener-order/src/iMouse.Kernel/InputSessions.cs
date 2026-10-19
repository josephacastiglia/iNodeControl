using System.Text.Json;

namespace IMouse2.Kernel;

/// <summary>
/// A lease spans commands (including down/move/up), while each board has at most
/// one active command and no hidden input backlog. Tokens are coordination
/// capabilities, not a substitute for HTTP authentication.
/// </summary>
public sealed class InputSessions : IAsyncDisposable
{
    private sealed class Lease(string token, long deadline, int duration)
    {
        public string Token = token;
        public long Deadline = deadline;
        public int Duration = duration;
        public CancellationTokenSource Cancel = new();
    }
    private sealed class Slot(Phone phone)
    {
        public readonly string Id = phone.deviceid, Pid = phone.pid, Uid = phone.uid;
        public Lease? Owner;
        public TaskCompletionSource? Active;
        public TaskCompletionSource? Cleaning;
        public bool Stopped;
        public string Message = "";
        public bool ReleaseFailed;
        public long Generation;
    }
    private readonly object _sync = new();
    private readonly DeviceStore _store;
    private readonly InputRouter _input;
    private readonly Dictionary<string, Slot> _slots = new(StringComparer.OrdinalIgnoreCase);
    private readonly Func<long> _clock;
    private readonly CancellationTokenSource _shutdown = new();
    private readonly Task _watch;
    private bool _closed;
    private Task? _dispose;
    public InputSessions(DeviceStore store, InputRouter input, Func<long>? clock = null)
    {
        _store = store; _input = input; _clock = clock ?? (() => Environment.TickCount64);
        _watch = WatchAsync();
    }
    private static TaskCompletionSource Completion() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    private static string Text(JsonElement data, string name) => data.ValueKind == JsonValueKind.Object && data.TryGetProperty(name, out var value) ? value.ToString() : "";
    private Phone[] Targets(JsonElement data)
    {
        var ids = Text(data, "id").Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Distinct().ToArray();
        if (ids.Length == 0) throw new ArgumentException("id required");
        var all = _store.All();
        var phones = ids.Select(id => all.SingleOrDefault(p => p.deviceid == id) ?? throw new KeyNotFoundException(id)).ToArray();
        if (phones.Any(p => !_input.Enabled(p.pid))) throw new ArgumentException("Every phone needs an enabled calibrated board.");
        if (phones.Select(p => p.pid).Distinct(StringComparer.OrdinalIgnoreCase).Count() != phones.Length)
            throw new ArgumentException("Multiple phones claim one board.");
        return phones;
    }
    private Slot Get(Phone phone)
    {
        if (!_slots.TryGetValue(phone.pid, out var slot)) _slots[phone.pid] = slot = new(phone);
        if (slot.Id != phone.deviceid || slot.Uid != phone.uid)
        {
            BeginClose(slot, true, "Binding changed; restart the kernel after verifying configuration.");
            throw new InvalidOperationException("Binding changed; previous input ownership is invalid.");
        }
        return slot;
    }
    private string Token(JsonElement data, string id)
    {
        if (data.TryGetProperty("tokens", out var tokens) && tokens.ValueKind == JsonValueKind.Object && tokens.TryGetProperty(id, out var token))
            return token.ToString();
        return Text(data, "token");
    }
    private void ValidateOwner(Slot slot, JsonElement data)
    {
        if (_closed || slot.Stopped || slot.Cleaning is not null) throw new InvalidOperationException("Input stopped or recovering; inspect status before resuming.");
        if (slot.Owner is null || slot.Owner.Token != Token(data, slot.Id)) throw new InvalidOperationException("A valid per-phone input lease is required.");
        if (_clock() >= slot.Owner.Deadline)
        {
            BeginClose(slot, true, "Controller lease expired.");
            throw new InvalidOperationException("Controller lease expired; input stopped.");
        }
    }
    public object Acquire(JsonElement data)
    {
        var phones = Targets(data);
        int duration = int.TryParse(Text(data, "lease_ms"), out var value) ? value : 30_000;
        if (duration is < 1000 or > 120_000) throw new ArgumentException("lease_ms must be 1000–120000.");
        lock (_sync)
        {
            var slots = phones.Select(Get).ToArray();
            foreach (var slot in slots)
            {
                if (slot.Owner is not null && _clock() >= slot.Owner.Deadline) BeginClose(slot, true, "Controller lease expired.");
                if (_closed || slot.Stopped || slot.Cleaning is not null || slot.Owner is not null || slot.Active is not null)
                    return new { code = 409, message = "A target is owned, stopped, or recovering. No leases acquired." };
            }
            foreach (var slot in slots) slot.Owner = new(Guid.NewGuid().ToString("N"), _clock() + duration, duration);
            return new { code = 0, leases = slots.Select(s => new { id = s.Id, token = s.Owner!.Token, lease_ms = duration }).ToArray() };
        }
    }
    public object Renew(JsonElement data)
    {
        var phones = Targets(data);
        lock (_sync)
        {
            var slots = phones.Select(Get).ToArray();
            foreach (var slot in slots) ValidateOwner(slot, data);
            foreach (var slot in slots) slot.Owner!.Deadline = _clock() + slot.Owner.Duration;
            return new { code = 0 };
        }
    }
    public object Resume(JsonElement data)
    {
        var phones = Targets(data);
        lock (_sync)
        {
            var slots = phones.Select(Get).ToArray();
            if (_closed || slots.Any(s => s.Cleaning is not null || s.Active is not null || s.Owner is not null || s.ReleaseFailed))
                return new { code = 409, message = "Cleanup must finish successfully before resuming." };
            if (data.TryGetProperty("expected_generations", out var expected) && slots.Any(s =>
                expected.ValueKind != JsonValueKind.Object || !expected.TryGetProperty(s.Id, out var value) ||
                !value.TryGetInt64(out var generation) || generation != s.Generation))
                return new { code = 409, message = "Input state changed; inspect status before resuming." };
            foreach (var slot in slots) { slot.Stopped = false; slot.Message = ""; }
            return new { code = 0, message = "Input ready for a new lease. Old tokens remain invalid." };
        }
    }
    public object Status()
    {
        lock (_sync) return new { code = 0, protocol = 1, phones = _store.All().Where(p => _input.Enabled(p.pid)).Select(p =>
        {
            _slots.TryGetValue(p.pid, out var s);
            return new { id = p.deviceid, owned = s?.Owner is not null, active = s?.Active is not null,
                stopped = s?.Stopped ?? false, releasing = s?.Cleaning is not null,
                release_failed = s?.ReleaseFailed ?? false, message = s?.Message ?? "",
                generation = s?.Generation ?? 0,
                lease_remaining_ms = s?.Owner is { } lease ? Math.Max(0, lease.Deadline - _clock()) : 0 };
        }).ToArray() };
    }
    public async Task<object> StopAsync(JsonElement data, bool release = false)
    {
        var phones = Targets(data);
        Slot[] slots; Task[] tasks;
        lock (_sync)
        {
            slots = phones.Select(Get).ToArray();
            if (release) foreach (var slot in slots) ValidateOwner(slot, data);
            tasks = slots.Select(s => BeginClose(s, !release, release ? "Controller released." : "Stopped by operator.")).ToArray();
        }
        await Task.WhenAll(tasks);
        lock (_sync) return new { code = slots.Any(s => s.ReleaseFailed) ? 33 : 0,
            message = slots.Any(s => s.ReleaseFailed) ? "Release failed; input remains stopped. Check the board." : "Input released; previous tokens revoked." };
    }
    // Called with _sync held. Cleanup yields before cancellation or HID operations.
    private Task BeginClose(Slot slot, bool stop, string message)
    {
        slot.Stopped |= stop; slot.Message = message;
        slot.Generation++;
        if (slot.Cleaning is not null) return slot.Cleaning.Task;
        var lease = slot.Owner; slot.Owner = null;
        var drained = slot.Active?.Task ?? Task.CompletedTask;
        var finished = slot.Cleaning = Completion();
        _ = CloseAsync(slot, lease, drained, finished);
        return finished.Task;
    }
    private async Task CloseAsync(Slot slot, Lease? lease, Task drained, TaskCompletionSource finished)
    {
        await Task.Yield();
        string? failure = null;
        try
        {
            if (lease is not null) await lease.Cancel.CancelAsync();
            await drained;
            await _input.ReleaseAsync(slot.Pid);
        }
        catch (Exception ex) { failure = ex.Message; }
        finally
        {
            lease?.Cancel.Dispose();
            lock (_sync)
            {
                if (failure is not null) { slot.Stopped = true; slot.ReleaseFailed = true; slot.Message = failure; }
                slot.Cleaning = null;
                finished.TrySetResult();
            }
        }
    }
    public async Task<object> DispatchAsync(string fun, JsonElement data)
    {
        var phones = Targets(data);
        foreach (var phone in phones) _input.ValidateCommand(fun, data, phone.pid);
        Slot[] slots; Lease[] leases;
        lock (_sync)
        {
            slots = phones.Select(Get).ToArray();
            foreach (var slot in slots) ValidateOwner(slot, data);
            // Reject instead of accumulating delayed taps. Clients serialize commands
            // within their own lease; separate boards are free to run concurrently.
            if (slots.Any(s => s.Active is not null)) return new { code = 409, message = "Input busy; no commands queued." };
            leases = slots.Select(s => s.Owner!).ToArray();
            foreach (var slot in slots) slot.Active = Completion();
        }
        var results = await Task.WhenAll(slots.Select((slot, i) => ExecuteAsync(slot, leases[i], fun, data)));
        return new { code = results.All(r => r.code == 0) ? 0 : 33, results };
    }
    private sealed record CommandResult(string id, int code, string message);
    private async Task<CommandResult> ExecuteAsync(Slot slot, Lease lease, string fun, JsonElement data)
    {
        int code = 33; string message = "Input failed.";
        try
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(lease.Cancel.Token);
            deadline.CancelAfter(TimeSpan.FromSeconds(8));
            var values = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(data.GetRawText())!;
            values["id"] = JsonSerializer.SerializeToElement(slot.Id);
            var result = JsonSerializer.SerializeToElement(await _input.DispatchAsync(fun, JsonSerializer.SerializeToElement(values), deadline.Token));
            code = result.GetProperty("code").GetInt32();
            if (result.TryGetProperty("results", out var details))
            {
                var detail = details[0]; code = detail.GetProperty("code").GetInt32(); message = detail.GetProperty("message").GetString() ?? "";
            }
            else message = result.ToString();
        }
        catch (Exception ex) { message = ex.Message; }
        Task cleanup = Task.CompletedTask;
        lock (_sync)
        {
            slot.Active!.TrySetResult(); slot.Active = null;
            if (code != 0) cleanup = BeginClose(slot, true, message);
        }
        await cleanup;
        return new(slot.Id, code, message);
    }
    private async Task WatchAsync()
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(100));
        try
        {
            while (await timer.WaitForNextTickAsync(_shutdown.Token))
                lock (_sync)
                    foreach (var slot in _slots.Values)
                        if (slot.Owner is { } lease && _clock() >= lease.Deadline) BeginClose(slot, true, "Controller lease expired.");
        }
        catch (OperationCanceledException) { }
    }
    public ValueTask DisposeAsync()
    {
        lock (_sync) return new(_dispose ??= DisposeCoreAsync());
    }
    private async Task DisposeCoreAsync()
    {
        Task[] tasks;
        lock (_sync) { _closed = true; tasks = _slots.Values.Select(s => BeginClose(s, true, "Kernel shutting down.")).ToArray(); }
        _shutdown.Cancel();
        await _watch;
        await Task.WhenAll(tasks);
        _shutdown.Dispose();
    }
}
