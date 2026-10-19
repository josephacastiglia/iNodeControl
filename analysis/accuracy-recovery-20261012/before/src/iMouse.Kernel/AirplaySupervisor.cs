namespace IMouse2.Kernel;

public interface IReceiverHandle : IDisposable
{
    int Id { get; }
    Task WaitForExitAsync(CancellationToken ct);
}

public enum ReceiverPhase { Starting, Running, Restarting, Failed }

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
    private ReceiverPhase _phase = ReceiverPhase.Starting;
    private readonly CancellationTokenSource _stop = new();

    public AirplaySupervisor(Func<IReceiverHandle> start, int maxRestarts = DefaultMaxRestarts, TimeSpan? delay = null)
    {
        if (maxRestarts < 0) throw new ArgumentOutOfRangeException(nameof(maxRestarts));
        _start = start;
        _maxRestarts = maxRestarts;
        _delay = delay ?? DefaultDelay;
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
                        new("failed", "Receiver failed after repeated crashes. Restart the independent kernel.", 0, _restarts),
                    ReceiverPhase.Running =>
                        new("running", "", _current?.Id ?? 0, _restarts),
                    _ => new("stopped", "", 0, _restarts)
                };
            }
        }
    }

    public async Task RunAsync(CancellationToken ct)
    {
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct, _stop.Token);
        var token = linked.Token;
        while (!token.IsCancellationRequested)
        {
            Set(ReceiverPhase.Starting);
            IReceiverHandle handle;
            try { handle = _start(); }
            catch (Exception ex)
            {
                Console.WriteLine("Receiver start failed: " + ex.Message);
                if (!await BackoffAsync(token)) return;
                continue;
            }
            lock (_gate) { _current = handle; _phase = ReceiverPhase.Running; }
            Console.WriteLine("Receiver running, pid " + handle.Id);
            try { await handle.WaitForExitAsync(token); }
            catch (OperationCanceledException) { break; }
            finally
            {
                lock (_gate) { if (ReferenceEquals(_current, handle)) _current = null; }
                try { handle.Dispose(); } catch { }
            }
            if (token.IsCancellationRequested) break;
            Console.WriteLine("Receiver exited.");
            if (!await BackoffAsync(token)) return;
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

    private void Set(ReceiverPhase phase) { lock (_gate) _phase = phase; }

    public void Dispose()
    {
        _stop.Cancel();
        IReceiverHandle? current;
        lock (_gate) { current = _current; _current = null; }
        try { current?.Dispose(); } catch { }
    }
}
