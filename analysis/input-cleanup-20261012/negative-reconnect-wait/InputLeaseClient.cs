using System.Diagnostics;
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
        // Why Paused was set: a command's failure or timeout, or a failed renewal, rather than
        // Stop, Resume, release or shutdown. Only the first pause records it.
        public bool PausedByFailure;
        // A /mouse/down may have reached the phone and no release has been confirmed since.
        public bool ButtonMaybeDown;
        public PhoneCleanup? LastRelease;
        // The release started after a failure; Resume and release wait for it before reusing the lease.
        public Task Cleanup = Task.CompletedTask;
    }
    private readonly object _sync = new();
    private readonly Dictionary<string, Phone> _phones = new();
    private readonly HashSet<Task> _operatorTasks = [];
    private readonly SemaphoreSlim _acquire = new(1, 1);
    private readonly Func<string, Dictionary<string, object>, CancellationToken, Task<JsonElement>> _send;
    private readonly Func<CancellationToken, Task> _verify;
    private readonly CancellationTokenSource _shutdown = new();
    private readonly Task _heartbeat;
    private Task<InputCloseResult>? _dispose;
    private bool _closed;
    private long _operatorEpoch;
    public event Action<string>? Notice;
    public event Action<InputCleanup>? Cleaned;
    public const string TimedOutNotice = "Input paused: request timed out; the outcome is unknown. Check the phone, then choose Resume input.";
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
    /// A step still waiting its turn when another command's failure paused the phones ends
    /// Cancelled with an <see cref="InputNotSentException"/>: it never left this console.
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
        var ct = linked.Token; int held = 0; bool paused = false, inFlight = false;
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
                        // Even a cancelled acquire can return a lease. Preserve its
                        // release outcome so shutdown cannot call an unknown hold clean.
                        foreach (var id in missing)
                        {
                            var release = await ReleaseHeldAsync(id, leases[id]).ConfigureAwait(false);
                            lock (_sync)
                            {
                                var p = Get(id); p.LastRelease = release.Phone;
                                if (!release.LeaseGone) p.Token = leases[id];
                            }
                        }
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
                // Once a press has left, whether the button is down is unknown until a release is confirmed.
                if (function == "/mouse/down") lock (_sync) foreach (var p in phones) p.ButtonMaybeDown = true;
                sending(step);
                inFlight = true;
                confirmed(step, await _send(function, payload, ct).ConfigureAwait(false));
                inFlight = false;
                // Each of these ends with a button-up report on the kernel.
                if (function is "/mouse/up" or "/mouse/click" or "/mouse/swipe" or "/mouse/reset")
                    lock (_sync) foreach (var p in phones) p.ButtonMaybeDown = false;
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
            string[] current; bool preempted;
            lock (_sync)
            {
                current = ids.Where((id, i) => phones[i].Life.Token == lifetimes[i]).ToArray();
                // Another command's failure or timeout, or a failed renewal, paused these phones
                // while this step waited its turn. That is neither a Stop nor a timeout of this
                // step: it never left, so say so rather than let it read as one or the other.
                preempted = end == InputEnd.Cancelled && !inFlight && current.Any(id => Get(id).PausedByFailure);
            }
            Pause(current, failure: end is InputEnd.Failed or InputEnd.TimedOut);
            // A timeout pauses like a failure and must say so, or the phone sits paused while the
            // console still reads ready. Only a cancellation this client was asked for is silent.
            if (current.Length > 0 && end != InputEnd.Cancelled)
                Notice?.Invoke(end == InputEnd.TimedOut ? TimedOutNotice : "Input paused: " + ex.Message);
            if (end is InputEnd.Failed or InputEnd.TimedOut) BeginCleanup(current, end);
            return (end, preempted ? new InputNotSentException(ex) : ex);
        }
        finally { for (int i = held - 1; i >= 0; i--) phones[i].Gate.Release(); }
    }
    private void Pause(string[] ids, bool failure = false)
    {
        CancellationTokenSource[] sources;
        lock (_sync)
        {
            sources = ids.Select(Get).Select(p =>
            {
                if (!p.Paused) p.PausedByFailure = failure;
                p.Paused = true; return p.Life;
            }).ToArray();
        }
        foreach (var source in sources) source.Cancel();
    }
    /// <summary>
    /// A failed or timed-out command may leave a button down: a drag's move timed out after its
    /// press, or its answer was lost. The lease is no longer renewed, so the kernel would lift the
    /// button only on expiry, 20-30 s later. Release it now instead, through /input/release with
    /// each phone's own token. That is the only ownership-scoped close in the protocol: /input/stop
    /// takes no token and would stop whoever holds the phone. Nothing is resent and nothing
    /// resumes; the phones stay paused until the operator chooses Resume input.
    /// </summary>
    private void BeginCleanup(string[] ids, InputEnd cause)
    {
        long detected = Stopwatch.GetTimestamp();
        (string Id, string Token, CancellationToken Life)[] held;
        lock (_sync) held = ids.Select(id => (Id: id, Phone: Get(id))).Where(x => x.Phone.ButtonMaybeDown && x.Phone.Token is not null)
            .Select(x => (x.Id, x.Phone.Token!, x.Phone.Life.Token)).ToArray();
        if (held.Length == 0) return;
        long epoch = Interlocked.Read(ref _operatorEpoch);
        // On the pool: the failed command's token is cancelled and it still holds these phones'
        // gates, and a caller on the UI thread must not carry the release on its dispatcher.
        var task = Task.Run(() => CleanupAsync(held, cause, epoch, detected));
        lock (_sync) foreach (var h in held) Get(h.Id).Cleanup = task;
    }
    private async Task CleanupAsync((string Id, string Token, CancellationToken Life)[] held, InputEnd cause, long epoch, long detected)
    {
        var results = await Task.WhenAll(held.Select(h => ReleaseHeldAsync(h.Id, h.Token))).ConfigureAwait(false);
        var elapsed = Stopwatch.GetElapsedTime(detected);
        bool current;
        lock (_sync)
        {
            for (int i = 0; i < held.Length; i++)
            {
                var p = Get(held[i].Id);
                if (p.Life.Token != held[i].Life || p.Token != held[i].Token) continue;   // released or resumed since
                if (results[i].LeaseGone) p.Token = null;
                if (results[i].Phone.Confirmed) p.ButtonMaybeDown = false;
                p.LastRelease = results[i].Phone;
            }
            current = epoch == Interlocked.Read(ref _operatorEpoch) && held.All(h => Get(h.Id).Life.Token == h.Life);
        }
        try { Cleaned?.Invoke(new InputCleanup(cause, results.Select(r => r.Phone).ToArray(), elapsed, detected, current)); }
        catch { /* A listener's failure must not fail Resume or shutdown, which wait for this task. */ }
    }
    private async Task<(PhoneCleanup Phone, bool LeaseGone)> ReleaseHeldAsync(string id, string token)
    {
        try
        {
            await _send("/input/release", new() { ["id"] = id, ["token"] = token }, CancellationToken.None).ConfigureAwait(false);
            return (new(id, true, "the kernel closed this lease and released the button"), true);
        }
        catch (ApiException ex) when (ex.Code == 33)
        {
            // The kernel closed the lease but its button-up write failed; it keeps the phone stopped.
            return (new(id, false, "the kernel could not complete the release on the board (" + ex.Message + ")"), true);
        }
        catch (ApiException ex) when (ex.Code == 409)
        {
            // Not this console's lease any more, and the refusal changed nothing: the kernel closed
            // it itself (the failed command, its 8 s deadline, expiry or a Stop). Ask how that ended.
            return (await ClosedByKernelAsync(id).ConfigureAwait(false), true);
        }
        catch (Exception ex)
        {
            // No usable answer: the lease may still be live. Keep its token so Resume tries the release again.
            string what = ex is OperationCanceledException ? "no answer to the release request" : "the release request failed";
            return (new(id, false, what + " (" + ex.Message + ")"), false);
        }
    }
    private async Task<PhoneCleanup> ClosedByKernelAsync(string id)
    {
        try
        {
            long giveUp = Stopwatch.GetTimestamp() + 3 * Stopwatch.Frequency;
            while (true)
            {
                var status = await _send("/input/status", new(), CancellationToken.None).ConfigureAwait(false);
                var phone = status.GetProperty("phones").EnumerateArray().FirstOrDefault(p => JsonValue.Text(p, "id") == id);
                if (phone.ValueKind != JsonValueKind.Object) return new(id, false, "the kernel no longer lists this phone");
                static bool Flag(JsonElement e, string name) => e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.True;
                if (Flag(phone, "release_failed"))
                    return new(id, false, "the kernel's own release failed (" + JsonValue.Text(phone, "message") + ")");
                // Every close raises the generation, so 0 means this kernel never closed a lease on
                // the phone: it was restarted, and nothing here shows the button came up.
                if (JsonValue.Int(phone, "generation") == 0) return new(id, false, "the kernel has no record of this lease (restarted?)");
                if (!Flag(phone, "releasing")) return new(id, true, "the kernel had already closed this lease and released the button");
                if (Stopwatch.GetTimestamp() > giveUp) return new(id, false, "the kernel was still releasing after 3 s");
                await Task.Delay(50).ConfigureAwait(false);
            }
        }
        catch (Exception ex) { return new(id, false, "status unavailable after the release was refused (" + ex.Message + ")"); }
    }
    private Task OperatorAsync(Func<Task> action)
    {
        var finished = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        lock (_sync)
        {
            if (_closed) return Task.FromException(new ObjectDisposedException(nameof(InputLeaseClient)));
            _operatorTasks.Add(finished.Task);
        }
        return RunAsync();
        async Task RunAsync()
        {
            try { await action().ConfigureAwait(false); }
            finally
            {
                lock (_sync) { _operatorTasks.Remove(finished.Task); finished.TrySetResult(); }
            }
        }
    }
    public Task StopAsync(string ids) => OperatorAsync(() => StopCoreAsync(ids));
    private async Task StopCoreAsync(string ids)
    {
        Interlocked.Increment(ref _operatorEpoch);
        var targets = Ids(ids); if (targets.Length == 0) return;
        Pause(targets);
        // Deliberately bypass ordinary command locks, including an in-flight acquire.
        await _verify(CancellationToken.None).ConfigureAwait(false);
        await _send("/input/stop", Payload(targets), CancellationToken.None).ConfigureAwait(false);
        await DrainAsync(targets).ConfigureAwait(false);
        lock (_sync) foreach (var id in targets)
        {
            var p = Get(id); p.Token = null; p.ButtonMaybeDown = false;
            p.LastRelease = new(id, true, "the kernel confirmed Stop and released input");
        }
    }
    private async Task DrainAsync(string[] ids)
    {
        foreach (var id in ids)
        {
            Phone p; lock (_sync) p = Get(id);
            await p.Gate.WaitAsync().ConfigureAwait(false); p.Gate.Release();
        }
    }
    public Task ResumeAsync(string ids) => OperatorAsync(() => ResumeCoreAsync(ids));
    private async Task ResumeCoreAsync(string ids)
    {
        long epoch = Interlocked.Read(ref _operatorEpoch);
        lock (_sync) if (_closed) throw new ObjectDisposedException(nameof(InputLeaseClient));
        var targets = Ids(ids); if (targets.Length == 0) return;
        Pause(targets);
        await DrainAsync(targets).ConfigureAwait(false);
        await ReleaseCoreAsync(ids, invalidateResume: false).ConfigureAwait(false);
        await _verify(CancellationToken.None).ConfigureAwait(false);
        var status = await _send("/input/status", new(), CancellationToken.None).ConfigureAwait(false);
        var generations = status.GetProperty("phones").EnumerateArray().Where(p => targets.Contains(p.GetProperty("id").GetString()))
            .ToDictionary(p => p.GetProperty("id").GetString()!, p => p.GetProperty("generation").GetInt64());
        if (epoch != Interlocked.Read(ref _operatorEpoch)) throw new ApiException("A newer Stop cancelled Resume.");
        var resume = Payload(targets); resume["expected_generations"] = generations;
        await _send("/input/resume", resume, CancellationToken.None).ConfigureAwait(false);
        if (epoch != Interlocked.Read(ref _operatorEpoch)) throw new ApiException("A newer Stop cancelled Resume.");
        lock (_sync) foreach (var id in targets) { var p = Get(id); p.Token = null; p.Life = new(); p.Paused = p.PausedByFailure = false; }
    }
    public Task ReleaseAsync(string ids) => OperatorAsync(() => ReleaseCoreAsync(ids));
    private async Task ReleaseCoreAsync(string ids, bool invalidateResume = true)
    {
        if (invalidateResume) Interlocked.Increment(ref _operatorEpoch);
        var targets = Ids(ids); if (targets.Length == 0) return;
        Pause(targets);
        await DrainAsync(targets).ConfigureAwait(false);
        // A release after a failure may still be on its way with these tokens. Let it answer first,
        // so its result stands and the same token is not released twice. Resume comes through here.
        Task[] cleanups; lock (_sync) cleanups = targets.Select(id => Get(id).Cleanup).ToArray();
        await Task.WhenAll(cleanups).ConfigureAwait(false);
        // Release individually: one expired token must not prevent release of others.
        foreach (var id in targets)
        {
            string? token; CancellationToken life;
            lock (_sync) { var p = Get(id); token = p.Token; life = p.Life.Token; p.Token = null; }
            if (token is not null)
                try
                {
                    await _send("/input/release", new() { ["id"] = id, ["token"] = token }, CancellationToken.None).ConfigureAwait(false);
                    lock (_sync)
                    {
                        var p = Get(id);
                        if (p.Life.Token == life && p.Token is null)
                        { p.ButtonMaybeDown = false; p.LastRelease = new(id, true, "the kernel confirmed the release"); }
                    }
                }
                catch (Exception ex)
                {
                    lock (_sync)
                    {
                        var p = Get(id);
                        if (p.Life.Token == life && p.Token is null)
                            p.LastRelease = new(id, false, "release was not confirmed (" + ex.Message + ")");
                    }
                    Notice?.Invoke("Release not confirmed; inspect input status: " + ex.Message);
                }
        }
    }
    public void ReadyScope(string ids)
    {
        lock (_sync) foreach (var id in Ids(ids))
        {
            var p = Get(id);
            // Only a new selection after an explicit release may reset local lifetime.
            // Server stopped state still requires explicit Resume and rejects acquisition.
            if (p.Token is null) { p.Life = new(); p.Paused = p.PausedByFailure = false; }
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
                        // A phone paused since this renewal left already has its notice, usually for
                        // the failure that also revoked the lease; the refusal adds nothing to it.
                        bool current; lock (_sync) { var p = Get(lease.Key); current = p.Token == lease.Value && !p.Paused; }
                        if (current) { Pause([lease.Key], failure: true); Notice?.Invoke("Ownership renewal failed: " + ex.Message); }
                    }
            }
        }
        catch (OperationCanceledException) { }
    }
    public ValueTask DisposeAsync() => new(CloseAsync());
    internal Task<InputCloseResult> CloseAsync()
    {
        lock (_sync)
        {
            if (_dispose is not null) return _dispose;
            _closed = true;
            Interlocked.Increment(ref _operatorEpoch);
            return _dispose = Task.Run(async () =>
            {
                try { return await CloseCoreAsync().ConfigureAwait(false); }
                catch (Exception) { return new InputCloseResult([], "input cleanup failed before it could be confirmed"); }
            });
        }
    }
    private async Task<InputCloseResult> CloseCoreAsync()
    {
        _shutdown.Cancel();
        Task[] operators; lock (_sync) operators = _operatorTasks.ToArray();
        await Task.WhenAll(operators).ConfigureAwait(false);
        string[] ids; lock (_sync) ids = _phones.Keys.ToArray();
        Pause(ids);
        await DrainAsync(ids).ConfigureAwait(false);
        Task[] cleanups; lock (_sync) cleanups = ids.Select(id => Get(id).Cleanup).ToArray();
        await Task.WhenAll(cleanups).ConfigureAwait(false);
        // Independent phone releases run together, instead of taking up to eight
        // seconds per phone. Every request still carries only that phone's own token.
        var results = await Task.WhenAll(ids.Select(async id =>
        {
            string? token; PhoneCleanup? previous; bool buttonMaybeDown;
            lock (_sync) { var p = Get(id); token = p.Token; previous = p.LastRelease; buttonMaybeDown = p.ButtonMaybeDown; }
            if (token is null) return previous ?? new(id, !buttonMaybeDown,
                buttonMaybeDown ? "no release confirmation is available" : "no managed input lease remains");
            var released = await ReleaseHeldAsync(id, token).ConfigureAwait(false);
            lock (_sync)
            {
                var p = Get(id);
                if (p.Token == token)
                {
                    if (released.LeaseGone) p.Token = null;
                    if (released.Phone.Confirmed) p.ButtonMaybeDown = false;
                    p.LastRelease = released.Phone;
                }
            }
            return released.Phone;
        })).ConfigureAwait(false);
        await _heartbeat.ConfigureAwait(false);
        return new(results);
    }
}
