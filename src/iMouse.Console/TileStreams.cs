namespace IMouse2;

public sealed record TileStatusView(string Label, string Detail, bool Warning)
{
    public static TileStatusView From(PreviewStatus? preview, bool online, bool paused)
    {
        if (!online) return new("Offline", "This phone is not mirroring.", false);
        if (paused) return new("Paused", "Tile preview is paused; its image is not updating.", false);
        if (preview is null) return new("Waiting", "Waiting for a tile preview.", false);
        if (preview.FetchFailed) return new("No updates", preview.Text, true);
        return new(preview.State switch {
            "recent" => "Recent", "quiet" => "May be old", "unknown" => "Age unknown", _ => "Waiting"
        }, preview.Text, preview.State == "quiet");
    }
}

public sealed class TileStream
{
    private readonly CancellationTokenSource _stop;
    public string Id { get; }
    public int Connection { get; }
    public CancellationToken Token { get; }
    public PreviewFreshness Freshness { get; }
    // Used on the UI thread only, just like the selected-preview rate meter.
    public RateMeter Rate { get; }
    internal TileStream(string id, int connection, CancellationToken lifetime, TimeProvider clock)
    {
        Id = id; Connection = connection; Freshness = new(clock); Rate = new(clock);
        _stop = CancellationTokenSource.CreateLinkedTokenSource(lifetime);
        Token = _stop.Token;
    }
    internal void Cancel() { try { _stop.Cancel(); } catch (ObjectDisposedException) { } }
    internal void Dispose() => _stop.Dispose();
}

/// <summary>Owns per-tile lifetimes, independently of WPF. A retired stream can never
/// publish into a replacement tile or remove its replacement when it finally exits.</summary>
public sealed class TileStreams
{
    private readonly object _gate = new();
    private readonly Dictionary<string, TileStream> _current = new();
    private readonly HashSet<TileStream> _running = new();
    private readonly TimeProvider _clock;
    public TileStreams(TimeProvider? clock = null) => _clock = clock ?? TimeProvider.System;
    public int RunningCount { get { lock (_gate) return _running.Count; } }
    public TileStream? Find(string id) { lock (_gate) return _current.GetValueOrDefault(id); }
    public bool IsCurrent(TileStream stream)
    {
        lock (_gate) return !stream.Token.IsCancellationRequested && ReferenceEquals(_current.GetValueOrDefault(stream.Id), stream);
    }
    public IReadOnlyList<TileStream> Reconcile(IEnumerable<string> ids, int connection, CancellationToken lifetime)
    {
        var wanted = ids.ToHashSet();
        var retired = new List<TileStream>(); var created = new List<TileStream>();
        lock (_gate)
        {
            foreach (var pair in _current.ToArray())
                if (!wanted.Contains(pair.Key) || pair.Value.Connection != connection || pair.Value.Token.IsCancellationRequested)
                { _current.Remove(pair.Key); retired.Add(pair.Value); }
            if (!lifetime.IsCancellationRequested)
                foreach (var id in wanted)
                    if (!_current.ContainsKey(id))
                    {
                        var stream = new TileStream(id, connection, lifetime, _clock);
                        _current.Add(id, stream); _running.Add(stream); created.Add(stream);
                    }
        }
        foreach (var stream in retired) stream.Cancel();
        return created;
    }
    public void Complete(TileStream stream)
    {
        lock (_gate)
        {
            if (ReferenceEquals(_current.GetValueOrDefault(stream.Id), stream)) _current.Remove(stream.Id);
            _running.Remove(stream);
        }
        stream.Cancel(); stream.Dispose();
    }
    public void Stop()
    {
        TileStream[] retired;
        lock (_gate) { retired = _current.Values.ToArray(); _current.Clear(); }
        foreach (var stream in retired) stream.Cancel();
    }
}

public readonly record struct TileFetchResult(bool Success, bool Cancelled);

/// <summary>Shared bound on tile screenshot requests. Holds a slot only during fetch,
/// never during decoding, presentation or retry delay. ApiClient bounds the full
/// screenshot transfer, including its body, with the request deadline.</summary>
public sealed class TileFetchScheduler
{
    private readonly SemaphoreSlim _slots;
    public TileFetchScheduler(int concurrency = 3)
    {
        if (concurrency < 1) throw new ArgumentOutOfRangeException(nameof(concurrency));
        _slots = new(concurrency, concurrency);
    }
    public async Task<TileFetchResult> FetchAsync(Func<CancellationToken, Task> fetch, CancellationToken ct)
    {
        bool acquired = false;
        try
        {
            await _slots.WaitAsync(ct).ConfigureAwait(false); acquired = true;
            ct.ThrowIfCancellationRequested();
            await fetch(ct).ConfigureAwait(false);
            ct.ThrowIfCancellationRequested();
            return new(true, false);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { return new(false, true); }
        catch (Exception) { return new(false, false); }
        finally { if (acquired) _slots.Release(); }
    }
}
