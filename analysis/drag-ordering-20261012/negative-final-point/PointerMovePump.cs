namespace IMouse2;

// Captured together on the UI thread. A delayed worker must never read a new
// selection, connection, or Resume lifetime on behalf of an old movement.
internal sealed record PointerMove(ApiClient Api, string Ids, int X, int Y,
    CancellationToken Connection, CancellationToken Control)
{
    internal bool Cancelled => Connection.IsCancellationRequested || Control.IsCancellationRequested;
    internal bool SameScope(PointerMove? other) => other is not null && ReferenceEquals(Api, other.Api) && Ids == other.Ids
        && Connection == other.Connection && Control == other.Control;
}

/// <summary>One in-flight hover and one replaceable pending position.</summary>
internal sealed class PointerMovePump
{
    private readonly object _gate = new();
    private readonly Func<PointerMove, CancellationToken, Task> _send;
    private readonly Action<Func<Task>> _start;
    private PointerMove? _pending, _failedScope;
    private bool _running, _closed;
    private TaskCompletionSource _idle = Completed();

    internal PointerMovePump(Func<PointerMove, CancellationToken, Task>? send = null,
        Action<Func<Task>>? start = null)
    {
        _send = send ?? ((move, ct) => move.Api.MoveAsync(move.Ids, move.X, move.Y, ct));
        _start = start ?? (worker => { _ = Task.Run(worker); });
    }

    private static TaskCompletionSource Completed()
    {
        var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        done.SetResult();
        return done;
    }

    internal bool IsRunning { get { lock (_gate) return _running; } }
    internal Task WhenIdle { get { lock (_gate) return _idle.Task; } }

    internal void Post(PointerMove move)
    {
        lock (_gate)
        {
            if (_closed || move.Ids.Length == 0 || move.Cancelled || move.SameScope(_failedScope)) return;
            _pending = move;
            if (_running) return;
            _running = true;
            _idle = new(TaskCreationOptions.RunContinuationsAsynchronously);
        }
        _start(RunAsync);
    }

    // Do not cancel a dispatched hover here: in ownership mode that would pause
    // input. Its call has already entered the per-phone command queue, before the
    // gesture that follows this clear. There is no fixed delay on the drag path.
    internal void ClearPending() { lock (_gate) _pending = null; }
    internal void Close() { lock (_gate) { _closed = true; _pending = null; } }

    private async Task RunAsync()
    {
        while (true)
        {
            PointerMove move;
            Task operation;
            CancellationTokenSource? lifetime = null;
            lock (_gate)
            {
                if (_closed || _pending is null)
                {
                    // Empty and idle become visible atomically. A new arrival either
                    // belongs to this worker or starts the next one; it cannot strand.
                    _running = false;
                    _idle.TrySetResult();
                    return;
                }
                move = _pending;
                _pending = null;
                if (move.Cancelled || move.SameScope(_failedScope)) continue;
                try
                {
                    lifetime = CancellationTokenSource.CreateLinkedTokenSource(move.Connection, move.Control);
                    // Only synchronous submission is protected, never an awaited network
                    // response. ApiClient enters its lease queue before its first wait.
                    // Thus ClearPending cannot return between taking a move and submitting it.
                    operation = _send(move, lifetime.Token);
                }
                catch (Exception ex) { operation = Task.FromException(ex); }
            }
            try { await operation.ConfigureAwait(false); }
            catch
            {
                // Never replay a failed/uncertain move. Resume or a new selection has a
                // new scope. A failure from the old scope must not erase that new work.
                lock (_gate)
                {
                    _failedScope = move.Api.UsesInputOwnership ? move : null;
                    if (_pending?.SameScope(move) == true) _pending = null;
                }
            }
            finally { lifetime?.Dispose(); }
        }
    }
}
