using System.Diagnostics;

namespace IMouse2;

// Each press owns this mailbox. Neither a new press nor an old worker's cleanup
// can reset another press's release flag or overwrite its final coordinate.
internal sealed class DragGesture(InputContext context, int x, int y, bool hold)
{
    internal InputContext Context { get; } = context;
    internal int X { get; } = x;
    internal int Y { get; } = y;
    internal bool Hold { get; } = hold;
    private readonly object _gate = new();
    private (int X, int Y)? _pending;
    private bool _released;
    private TaskCompletionSource _changed = NewSignal();
    private static TaskCompletionSource NewSignal() => new(TaskCreationOptions.RunContinuationsAsynchronously);

    internal void Move((int X, int Y) point)
    {
        lock (_gate)
        {
            if (_released) return;
            _pending = point;
            _changed.TrySetResult();
        }
    }

    internal void Release((int X, int Y)? final = null)
    {
        lock (_gate)
        {
            if (_released) return;
            if (final is not null) _pending = final;
            _released = true;
            _changed.TrySetResult();
        }
    }

    internal async Task<((int X, int Y)? Point, bool Released)> ReadAsync(CancellationToken ct)
    {
        while (true)
        {
            ct.ThrowIfCancellationRequested();
            Task changed;
            lock (_gate)
            {
                if (_pending is not null || _released)
                {
                    var next = (_pending, _released);
                    _pending = null;
                    if (!_released) _changed = NewSignal();
                    return next;
                }
                changed = _changed.Task;
            }
            await changed.WaitAsync(ct).ConfigureAwait(false);
        }
    }
}

internal sealed record DragResult(int Moves, int LastX, string Trace, long DurationMs,
    bool Released, Exception? Failure, Exception? ReleaseFailure);

internal static class DragInput
{
    internal static async Task<DragResult> RunAsync(DragGesture gesture, CancellationToken ct)
    {
        var api = gesture.Context.Api;
        string ids = gesture.Context.Ids;
        bool pressed = false, released = false;
        int moves = 0, lastX = -1;
        string trace = "";
        Exception? failure = null, releaseFailure = null;
        var elapsed = Stopwatch.StartNew();
        try
        {
            ct.ThrowIfCancellationRequested();
            await api.MoveAsync(ids, gesture.X, gesture.Y, ct).ConfigureAwait(false);
            long moveMs = elapsed.ElapsedMilliseconds;
            await api.CommandAsync("/mouse/down", new() { ["id"] = ids, ["button"] = "1" }, ct).ConfigureAwait(false);
            trace = $"[setup move {moveMs} ms, down {elapsed.ElapsedMilliseconds - moveMs} ms] ";
            pressed = true;
            while (true)
            {
                var next = await gesture.ReadAsync(ct).ConfigureAwait(false);
                if (next.Point is { } point)
                {
                    long began = elapsed.ElapsedMilliseconds;
                    await api.MoveAsync(ids, point.X, point.Y, ct).ConfigureAwait(false);
                    moves++; lastX = point.X;
                    if (trace.Length < 400) trace += $"{(next.Released ? "final" : "")}({point.X},{point.Y})+{elapsed.ElapsedMilliseconds - began}ms ";
                }
                if (next.Released) break;
            }
        }
        catch (Exception ex) { failure = ex; }
        finally
        {
            // A failed owned command already triggers lease-scoped cleanup in the
            // client/kernel. An extra up would only be refused and double-log it.
            // Legacy mode retains its best-effort release after a move failure.
            if (pressed && !ct.IsCancellationRequested && (failure is null || !api.UsesInputOwnership))
            {
                try
                {
                    await api.CommandAsync("/mouse/up", new() { ["id"] = ids, ["button"] = "1" }, ct).ConfigureAwait(false);
                    released = true;
                }
                catch (Exception ex) { releaseFailure = ex; }
            }
        }
        return new(moves, lastX, trace, elapsed.ElapsedMilliseconds, released, failure, releaseFailure);
    }
}
