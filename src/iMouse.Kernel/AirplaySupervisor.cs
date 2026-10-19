namespace IMouse2.Kernel;

public interface IReceiverHandle : IDisposable
{
    int Id { get; }
    Task WaitForExitAsync(CancellationToken ct);
}

public enum ReceiverPhase { Starting, Running, Restarting, Failed, Stopped }

public sealed record ReceiverInfo(string State, string Message, int Pid, int Restarts);

/// <summary>
/// Restarts a crashed UxPlay child a bounded number of times. Does not recast the
/// iPhone; after a successful relaunch the console must prompt for Screen Mirroring.
/// </summary>
public sealed class AirplaySupervisor : IDisposable
{
    public const int DefaultMaxRestarts = 5;
    public static readonly TimeSpan DefaultDelay = TimeSpan.FromSeconds(2);

    private readonly Func<IReceiverHandle> _start;
    private readonly int _maxRestarts;
    private readonly TimeSpan _delay;
    private readonly object _gate = new();
    private IReceiverHandle? _current;
    private int _restarts;
    private int _runStarted;
    private bool _disposed;
    private bool _cleanupFailed;
    private string _failureMessage = "Receiver failed after repeated crashes. Restart the independent kernel.";
    private ReceiverPhase _phase = ReceiverPhase.Starting;
    private readonly CancellationTokenSource _stop = new();

    public AirplaySupervisor(Func<IReceiverHandle> start, int maxRestarts = DefaultMaxRestarts, TimeSpan? delay = null)
    {
        if (maxRestarts < 0) throw new ArgumentOutOfRangeException(nameof(maxRestarts));
        _start = start ?? throw new ArgumentNullException(nameof(start));
        _maxRestarts = maxRestarts;
        _delay = delay ?? DefaultDelay;
        if (_delay < TimeSpan.Zero || _delay.TotalMilliseconds > uint.MaxValue - 1)
            throw new ArgumentOutOfRangeException(nameof(delay));
    }

    public ReceiverInfo Info
    {
        get
        {
            lock (_gate)
            {
                return _phase switch
                {
                    ReceiverPhase.Starting or ReceiverPhase.Restarting =>
                        new("restarting", "Receiver restarting", _current?.Id ?? 0, _restarts),
                    ReceiverPhase.Failed =>
                        new("failed", _failureMessage, 0, _restarts),
                    ReceiverPhase.Running =>
                        new("running", "", _current?.Id ?? 0, _restarts),
                    _ => new("stopped", "", 0, _restarts)
                };
            }
        }
    }

    public async Task RunAsync(CancellationToken ct)
    {
        if (Interlocked.Exchange(ref _runStarted, 1) != 0)
            throw new InvalidOperationException("A receiver supervisor can run only once.");
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct, _stop.Token);
        var token = linked.Token;
        try
        {
            while (!token.IsCancellationRequested)
            {
                Set(ReceiverPhase.Starting);
                IReceiverHandle handle;
                try { handle = _start(); }
                catch (Exception ex)
                {
                    Console.WriteLine("Receiver start failed: " + ex.Message);
                    if (token.IsCancellationRequested || !await BackoffAsync(token)) return;
                    continue;
                }
                bool published;
                lock (_gate)
                {
                    published = !_disposed && !token.IsCancellationRequested;
                    if (published) { _current = handle; _phase = ReceiverPhase.Running; }
                }
                if (!published)
                {
                    DisposeHandle(handle);
                    break;
                }
                bool released = false;
                try
                {
                    Console.WriteLine("Receiver running, pid " + handle.Id);
                    await handle.WaitForExitAsync(token);
                }
                catch (OperationCanceledException) when (token.IsCancellationRequested) { break; }
                catch (Exception ex) { Console.WriteLine("Receiver wait failed: " + ex.Message); }
                finally { released = Release(handle); }
                if (!released) return;
                if (token.IsCancellationRequested) break;
                Console.WriteLine("Receiver exited.");
                if (!await BackoffAsync(token)) return;
            }
        }
        finally
        {
            lock (_gate)
                if (_cleanupFailed) _phase = ReceiverPhase.Failed;
                else if (token.IsCancellationRequested || _phase != ReceiverPhase.Failed)
                    _phase = ReceiverPhase.Stopped;
        }
    }

    private bool Release(IReceiverHandle handle)
    {
        lock (_gate)
        {
            if (!ReferenceEquals(_current, handle)) return !_cleanupFailed;
            _current = null;
        }
        return DisposeHandle(handle);
    }

    private bool DisposeHandle(IReceiverHandle handle)
    {
        try { handle.Dispose(); return true; }
        catch (Exception ex)
        {
            lock (_gate)
            {
                _cleanupFailed = true;
                _phase = ReceiverPhase.Failed;
                _failureMessage = "Receiver cleanup failed; no replacement started. Inspect the receiver process. " + ex.Message;
            }
            return false;
        }
    }

    private async Task<bool> BackoffAsync(CancellationToken ct)
    {
        lock (_gate)
        {
            _restarts++;
            if (_restarts > _maxRestarts)
            {
                _phase = ReceiverPhase.Failed;
                Console.WriteLine("Receiver retry limit reached (" + _maxRestarts + ").");
                return false;
            }
            _phase = ReceiverPhase.Restarting;
        }
        try { await Task.Delay(_delay, ct); }
        catch (OperationCanceledException) { return false; }
        return true;
    }

    private void Set(ReceiverPhase phase) { lock (_gate) if (!_disposed) _phase = phase; }

    public void Dispose()
    {
        IReceiverHandle? current;
        lock (_gate)
        {
            if (_disposed) return;
            _disposed = true;
            current = _current; _current = null;
            _phase = _cleanupFailed ? ReceiverPhase.Failed : ReceiverPhase.Stopped;
        }
        _stop.Cancel();
        if (current is not null) DisposeHandle(current);
    }
}
