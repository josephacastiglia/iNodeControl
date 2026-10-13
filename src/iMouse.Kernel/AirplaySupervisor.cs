namespace IMouse2.Kernel;

public interface IReceiverHandle : IDisposable
{
    // Successful disposal must confirm receiver exit. Throw if cleanup is unknown.
    int Id { get; }
    string? DiagnosticWarning => null;
    Task WaitForExitAsync(CancellationToken ct);
}

public enum ReceiverPhase { Starting, Running, Restarting, Failed, Stopped }

// Restarts counts replacement attempts actually begun, including failed starts.
// A failed cleanup retains the last known PID; it is not proof the child is alive.
public sealed record ReceiverInfo(string State, string Message, int Pid, int Restarts);

/// <summary>A partially started child could not be cleaned up; its factory must not be retried.</summary>
public sealed class ReceiverCleanupException(int processId, string message, Exception innerException)
    : Exception(message, innerException)
{
    public int ProcessId { get; } = processId;
}

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
    private int _failurePid;
    private string _failureMessage = "";
    private string _retryReason = "";
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
                        new("restarting", "Receiver restarting" + (_retryReason.Length == 0 ? "" : ". " + _retryReason), 0, _restarts),
                    ReceiverPhase.Failed =>
                        new("failed", _failureMessage, _failurePid, _restarts),
                    ReceiverPhase.Running =>
                        new("running", _current?.DiagnosticWarning ?? "", _current?.Id ?? 0, _restarts),
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
        bool replacement = false;
        try
        {
            while (!token.IsCancellationRequested)
            {
                lock (_gate)
                {
                    // A cancelled delay must not spend a retry. Claim an attempt
                    // just before invoking the factory, also checking Dispose.
                    if (_disposed || token.IsCancellationRequested || _cleanupFailed) break;
                    if (replacement) _restarts++;
                    _phase = ReceiverPhase.Starting;
                }
                replacement = true;
                IReceiverHandle handle;
                try { handle = _start(); }
                catch (ReceiverCleanupException ex)
                {
                    RecordCleanupFailure(ex.ProcessId, ex);
                    return;
                }
                catch (Exception ex)
                {
                    string reason = "Receiver start failed: " + ex.Message;
                    Console.WriteLine(reason);
                    if (token.IsCancellationRequested || !await BackoffAsync(token, reason)) return;
                    continue;
                }
                bool published;
                lock (_gate)
                {
                    published = !_disposed && !token.IsCancellationRequested;
                    if (published) { _current = handle; _phase = ReceiverPhase.Running; _retryReason = ""; }
                }
                if (!published)
                {
                    DisposeHandle(handle);
                    break;
                }
                bool released = false;
                string exitReason = "Receiver exited unexpectedly.";
                try
                {
                    Console.WriteLine("Receiver running, pid " + handle.Id);
                    await handle.WaitForExitAsync(token);
                }
                catch (OperationCanceledException) when (token.IsCancellationRequested) { break; }
                catch (Exception ex) { exitReason = "Receiver wait failed: " + ex.Message; }
                finally { released = Release(handle); }
                if (!released) return;
                if (token.IsCancellationRequested) break;
                Console.WriteLine(exitReason);
                if (!await BackoffAsync(token, exitReason)) return;
            }
        }
        finally
        {
            lock (_gate)
                if (_cleanupFailed) _phase = ReceiverPhase.Failed;
                else if (_phase != ReceiverPhase.Failed)
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
        int pid = 0;
        try { pid = handle.Id; }
        catch (Exception) { } // Identity lookup must never prevent the cleanup attempt.
        try { handle.Dispose(); return true; }
        catch (Exception ex)
        {
            RecordCleanupFailure(ex is ReceiverCleanupException cleanup ? cleanup.ProcessId : pid, ex);
            return false;
        }
    }

    private void RecordCleanupFailure(int pid, Exception ex)
    {
        lock (_gate)
        {
            _cleanupFailed = true;
            _phase = ReceiverPhase.Failed;
            _failurePid = pid;
            _failureMessage = "Receiver cleanup failed; no replacement started. Last known receiver PID: " +
                (pid == 0 ? "unknown" : pid.ToString()) + ". Inspect the receiver process. " + ex.Message;
        }
    }

    private async Task<bool> BackoffAsync(CancellationToken ct, string reason)
    {
        lock (_gate)
        {
            if (_disposed || ct.IsCancellationRequested || _cleanupFailed) return false;
            _retryReason = reason;
            if (_restarts >= _maxRestarts)
            {
                _phase = ReceiverPhase.Failed;
                _failureMessage = $"Receiver restart limit reached ({_maxRestarts}). {reason} Inspect the receiver log before restarting the kernel.";
                Console.WriteLine("Receiver retry limit reached (" + _maxRestarts + ").");
                return false;
            }
            _phase = ReceiverPhase.Restarting;
        }
        try { await Task.Delay(_delay, ct); }
        catch (OperationCanceledException) { return false; }
        return true;
    }

    public void Dispose()
    {
        IReceiverHandle? current;
        lock (_gate)
        {
            if (_disposed) return;
            _disposed = true;
            current = _current; _current = null;
            if (_phase != ReceiverPhase.Failed) _phase = ReceiverPhase.Stopped;
        }
        _stop.Cancel();
        if (current is not null) DisposeHandle(current);
    }
}
