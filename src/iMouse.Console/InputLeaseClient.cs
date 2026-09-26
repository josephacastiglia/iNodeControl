using System.Runtime.ExceptionServices;
using System.Text.Json;

namespace IMouse2;

/// <summary>Private controller tokens; independent serialization per phone.</summary>
internal sealed class InputLeaseClient : IAsyncDisposable
{
    private sealed class Phone
    {
        public readonly SemaphoreSlim Gate = new(1, 1);
        public CancellationTokenSource Life = new();
        public string? Token;
        public bool Paused;
    }
    private readonly object _sync = new();
    private readonly Dictionary<string, Phone> _phones = new();
    private readonly SemaphoreSlim _acquire = new(1, 1);
    private readonly Func<string, Dictionary<string, object>, CancellationToken, Task<JsonElement>> _send;
    private readonly Func<CancellationToken, Task> _verify;
    private readonly CancellationTokenSource _shutdown = new();
    private readonly Task _heartbeat;
    private Task? _dispose;
    private bool _closed;
    private long _operatorEpoch;
    public event Action<string>? Notice;
    public InputLeaseClient(Func<string, Dictionary<string, object>, CancellationToken, Task<JsonElement>> send,
        Func<CancellationToken, Task> verify, TimeSpan? renewalInterval = null)
    {
        _send = send; _verify = verify;
        _heartbeat = RenewAsync(renewalInterval ?? TimeSpan.FromSeconds(10));
    }
    private static string[] Ids(string ids) => ids.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries).Distinct().Order().ToArray();
    private Phone Get(string id) { if (!_phones.TryGetValue(id, out var p)) _phones[id] = p = new(); return p; }
    private static Dictionary<string, object> Payload(string[] ids, Dictionary<string, string>? tokens = null) =>
        tokens is null ? new() { ["id"] = string.Join(',', ids) } : new() { ["id"] = string.Join(',', ids), ["tokens"] = tokens };
    public async Task<JsonElement> CommandAsync(string function, Dictionary<string, object> data, CancellationToken caller)
    {
        JsonElement result = default;
        var (_, failure) = await SequenceAsync(function, [data], _ => { }, (_, r) => result = r, caller).ConfigureAwait(false);
        if (failure is not null) ExceptionDispatchInfo.Throw(failure);
        return result;
    }
    /// <summary>
    /// Sends the steps in order under one hold of each phone's gate and one lease, so every
    /// step carries the same tokens and nothing else from this console lands between them.
    /// <paramref name="sending"/> runs just before a step leaves, <paramref name="confirmed"/>
    /// after the kernel accepted it. The first failure ends the sequence and pauses the phones
    /// like any failed command; the failed step is never resent, because it may have partly
    /// run. Refusals before anything could be sent (paused, closed, caller cancelled) throw.
    /// </summary>
    public async Task<(InputEnd End, Exception? Failure)> SequenceAsync(string function, IReadOnlyList<Dictionary<string, object>> steps,
        Action<int> sending, Action<int, JsonElement> confirmed, CancellationToken caller)
    {
        caller.ThrowIfCancellationRequested();
        if (steps.Count == 0) throw new ArgumentException("A sequence needs at least one step.");
        string scope = steps[0].GetValueOrDefault("id")?.ToString() ?? "";
        if (steps.Any(s => (s.GetValueOrDefault("id")?.ToString() ?? "") != scope))
            throw new ArgumentException("Every step of a sequence must address the same phones.");
        var ids = Ids(scope);
        if (ids.Length == 0) throw new ApiException("Select a phone first.");
        Phone[] phones; CancellationToken[] lifetimes;
        lock (_sync)
        {
            if (_closed) throw new ObjectDisposedException(nameof(InputLeaseClient));
            phones = ids.Select(Get).ToArray();
            if (phones.Any(p => p.Paused)) throw new ApiException("Input paused. Inspect the phone, then choose Resume input.");
            lifetimes = phones.Select(p => p.Life.Token).Append(caller).Append(_shutdown.Token).ToArray();
        }
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(lifetimes);
        var ct = linked.Token; int held = 0; bool paused = false;
        try
        {
            foreach (var phone in phones) { await phone.Gate.WaitAsync(ct).ConfigureAwait(false); held++; }
            await _verify(ct).ConfigureAwait(false);
            await _acquire.WaitAsync(ct).ConfigureAwait(false);
            try
            {
                string[] missing;
                lock (_sync) missing = ids.Where((id, i) => phones[i].Token is null).ToArray();
                if (missing.Length > 0)
                {
                    var acquired = await _send("/input/acquire", Payload(missing), ct).ConfigureAwait(false);
                    var leases = acquired.GetProperty("leases").EnumerateArray()
                        .ToDictionary(l => l.GetProperty("id").GetString()!, l => l.GetProperty("token").GetString()!);
                    bool obsolete;
                    lock (_sync)
                    {
                        obsolete = ct.IsCancellationRequested;
                        if (!obsolete) foreach (var id in missing) Get(id).Token = leases[id];
                    }
                    if (obsolete)
                    {
                        try { await _send("/input/release", Payload(missing, leases), CancellationToken.None).ConfigureAwait(false); } catch { }
                        ct.ThrowIfCancellationRequested();
                    }
                }
            }
            finally { _acquire.Release(); }
            Dictionary<string, string> tokens;
            lock (_sync) { ct.ThrowIfCancellationRequested(); tokens = ids.Select((id, i) => (id, token: phones[i].Token!)).ToDictionary(x => x.id, x => x.token); }
            for (int step = 0; step < steps.Count; step++)
            {
                // Pause marks the phone under the lock before it cancels, so checking both
                // closes the gap in which a Stop could otherwise let one more step out.
                lock (_sync) { ct.ThrowIfCancellationRequested(); paused = phones.Any(p => p.Paused); }
                if (paused) throw new OperationCanceledException(ct);
                var payload = new Dictionary<string, object>(steps[step]) { ["tokens"] = tokens };
                sending(step);
                confirmed(step, await _send(function, payload, ct).ConfigureAwait(false));
            }
            return (InputEnd.Completed, null);
        }
        catch (Exception ex)
        {
            // Decide before Pause below cancels ct. Only this client's lifetimes, the caller
            // and HttpClient's own timeout cancel anything here, so a cancellation none of
            // ours requested is the timeout, and that step's outcome is unknown.
            var end = ex is not OperationCanceledException ? InputEnd.Failed
                : ct.IsCancellationRequested || paused ? InputEnd.Cancelled : InputEnd.TimedOut;
            string[] current;
            lock (_sync) current = ids.Where((id, i) => phones[i].Life.Token == lifetimes[i]).ToArray();
            Pause(current);
            if (current.Length > 0 && ex is not OperationCanceledException) Notice?.Invoke("Input paused: " + ex.Message);
            return (end, ex);
        }
        finally { for (int i = held - 1; i >= 0; i--) phones[i].Gate.Release(); }
    }
    private void Pause(string[] ids)
    {
        CancellationTokenSource[] sources;
        lock (_sync) { sources = ids.Select(Get).Select(p => { p.Paused = true; return p.Life; }).ToArray(); }
        foreach (var source in sources) source.Cancel();
    }
    public async Task StopAsync(string ids)
    {
        Interlocked.Increment(ref _operatorEpoch);
        var targets = Ids(ids); if (targets.Length == 0) return;
        Pause(targets);
        // Deliberately bypass ordinary command locks, including an in-flight acquire.
        await _verify(CancellationToken.None).ConfigureAwait(false);
        await _send("/input/stop", Payload(targets), CancellationToken.None).ConfigureAwait(false);
        await DrainAsync(targets).ConfigureAwait(false);
        lock (_sync) foreach (var id in targets) Get(id).Token = null;
    }
    private async Task DrainAsync(string[] ids)
    {
        foreach (var id in ids)
        {
            Phone p; lock (_sync) p = Get(id);
            await p.Gate.WaitAsync().ConfigureAwait(false); p.Gate.Release();
        }
    }
    public async Task ResumeAsync(string ids)
    {
        long epoch = Interlocked.Read(ref _operatorEpoch);
        lock (_sync) if (_closed) throw new ObjectDisposedException(nameof(InputLeaseClient));
        var targets = Ids(ids); if (targets.Length == 0) return;
        Pause(targets);
        await DrainAsync(targets).ConfigureAwait(false);
        await ReleaseAsync(ids, invalidateResume: false).ConfigureAwait(false);
        await _verify(CancellationToken.None).ConfigureAwait(false);
        var status = await _send("/input/status", new(), CancellationToken.None).ConfigureAwait(false);
        var generations = status.GetProperty("phones").EnumerateArray().Where(p => targets.Contains(p.GetProperty("id").GetString()))
            .ToDictionary(p => p.GetProperty("id").GetString()!, p => p.GetProperty("generation").GetInt64());
        if (epoch != Interlocked.Read(ref _operatorEpoch)) throw new ApiException("A newer Stop cancelled Resume.");
        var resume = Payload(targets); resume["expected_generations"] = generations;
        await _send("/input/resume", resume, CancellationToken.None).ConfigureAwait(false);
        if (epoch != Interlocked.Read(ref _operatorEpoch)) throw new ApiException("A newer Stop cancelled Resume.");
        lock (_sync) foreach (var id in targets) { var p = Get(id); p.Token = null; p.Life = new(); p.Paused = false; }
    }
    public async Task ReleaseAsync(string ids, bool invalidateResume = true)
    {
        if (invalidateResume) Interlocked.Increment(ref _operatorEpoch);
        var targets = Ids(ids); if (targets.Length == 0) return;
        Pause(targets);
        await DrainAsync(targets).ConfigureAwait(false);
        // Release individually: one expired token must not prevent release of others.
        foreach (var id in targets)
        {
            string? token; lock (_sync) { token = Get(id).Token; Get(id).Token = null; }
            if (token is not null)
                try { await _send("/input/release", new() { ["id"] = id, ["token"] = token }, CancellationToken.None).ConfigureAwait(false); }
                catch (Exception ex) { Notice?.Invoke("Release not confirmed; inspect input status: " + ex.Message); }
        }
    }
    public void ReadyScope(string ids)
    {
        lock (_sync) foreach (var id in Ids(ids))
        {
            var p = Get(id);
            // Only a new selection after an explicit release may reset local lifetime.
            // Server stopped state still requires explicit Resume and rejects acquisition.
            if (p.Token is null) { p.Life = new(); p.Paused = false; }
        }
    }
    private async Task RenewAsync(TimeSpan interval)
    {
        using var timer = new PeriodicTimer(interval);
        try
        {
            while (await timer.WaitForNextTickAsync(_shutdown.Token).ConfigureAwait(false))
            {
                KeyValuePair<string, string>[] leases;
                lock (_sync) leases = _phones.Where(p => p.Value.Token is not null && !p.Value.Paused)
                    .Select(p => new KeyValuePair<string, string>(p.Key, p.Value.Token!)).ToArray();
                foreach (var lease in leases)
                    try { await _send("/input/renew", new() { ["id"] = lease.Key, ["token"] = lease.Value }, _shutdown.Token).ConfigureAwait(false); }
                    catch (OperationCanceledException) when (_shutdown.IsCancellationRequested) { return; }
                    catch (Exception ex)
                    {
                        bool current; lock (_sync) current = Get(lease.Key).Token == lease.Value;
                        if (current) { Pause([lease.Key]); Notice?.Invoke("Ownership renewal failed: " + ex.Message); }
                    }
            }
        }
        catch (OperationCanceledException) { }
    }
    public ValueTask DisposeAsync() { lock (_sync) return new(_dispose ??= CloseAsync()); }
    private async Task CloseAsync()
    {
        string ids; lock (_sync) { _closed = true; ids = string.Join(',', _phones.Keys); }
        _shutdown.Cancel();
        await ReleaseAsync(ids).ConfigureAwait(false);
        await _heartbeat.ConfigureAwait(false);
    }
}
