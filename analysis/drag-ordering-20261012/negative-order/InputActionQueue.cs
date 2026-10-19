namespace IMouse2;

// Created on the UI thread, before any delay or thread-pool scheduling.
internal sealed class InputContext(ApiClient api, string ids, CancellationToken connection, CancellationTokenSource control)
{
    internal ApiClient Api { get; } = api;
    internal string Ids { get; } = ids;
    internal CancellationToken Connection { get; } = connection;
    internal CancellationTokenSource Control { get; } = control;
    internal CancellationToken ControlToken { get; } = control.Token;
    internal bool SameScope(InputContext? other) => other is not null && ReferenceEquals(Api, other.Api)
        && Ids == other.Ids && Connection == other.Connection && ControlToken == other.ControlToken;
}

/// <summary>
/// Orders complete console actions, including a drag's final release. Stop and
/// Resume bypass this queue. The lease client still owns network/phone safety.
/// </summary>
internal sealed class InputActionQueue(Func<InputContext, bool> cancelledByUser, Func<Func<Task>, Task>? start = null)
{
    private readonly object _gate = new();
    private readonly Func<Func<Task>, Task> _start = start ?? (work => Task.Run(work));
    private Task _tail = Task.CompletedTask;
    private InputContext? _failedScope;
    private Exception? _failure;

    internal bool IsRunning { get { lock (_gate) return !_tail.IsCompleted; } }
    internal Task WhenIdle { get { lock (_gate) return _tail; } }

    internal Task Enqueue(InputContext context, Func<CancellationToken, Task> action)
    {
        Task prior;
        var finished = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        lock (_gate) { prior = _tail; _tail = finished.Task; }
        return _start(async () =>
        {
            try
            {
                // The fence always waits for cleanup, even if this queued action has
                // already been cancelled. Otherwise a later action could overtake it.
                // Deliberate regression: do not wait for the previous complete action.
                lock (_gate)
                    if (context.SameScope(_failedScope) && !cancelledByUser(context))
                        throw new InputNotSentException(_failure!);
                using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(context.Connection, context.ControlToken);
                lifetime.Token.ThrowIfCancellationRequested();
                await action(lifetime.Token).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                if (context.Api.UsesInputOwnership && ex is not InputNotSentException && !cancelledByUser(context))
                    lock (_gate) { _failedScope = context; _failure = ex; }
                throw;
            }
            finally { finished.TrySetResult(); }
        });
    }
}
