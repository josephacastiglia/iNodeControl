using System.Diagnostics;

namespace IMouse2.Kernel;

// Keeps process ownership separate from receiver arguments and log formatting.
// The narrow adapter also allows delayed exit and partial startup to be tested.
internal interface IReceiverProcess : IDisposable
{
    int Id { get; }
    bool HasExited { get; }
    bool Start();
    void BeginOutputReadLine();
    void BeginErrorReadLine();
    Task WaitForExitAsync(CancellationToken ct);
    bool WaitForExit(int milliseconds);
    void KillTree();
}

internal sealed class SystemReceiverProcess(Process process) : IReceiverProcess
{
    public int Id => process.Id;
    public bool HasExited => process.HasExited;
    public bool Start() => process.Start();
    public void BeginOutputReadLine() => process.BeginOutputReadLine();
    public void BeginErrorReadLine() => process.BeginErrorReadLine();
    public Task WaitForExitAsync(CancellationToken ct) => process.WaitForExitAsync(ct);
    public bool WaitForExit(int milliseconds) => process.WaitForExit(milliseconds);
    public void KillTree() => process.Kill(entireProcessTree: true);
    public void Dispose() => process.Dispose();
}

internal sealed class ReceiverProcessLifetime : IReceiverHandle
{
    internal const int ExitTimeoutMilliseconds = 5000;
    private readonly IReceiverProcess _process;
    private readonly object _cleanupGate = new();
    private bool _disposed;
    public ReceiverProcessLifetime(IReceiverProcess process)
    {
        _process = process;
        bool started = false;
        try
        {
            if (!_process.Start()) throw new InvalidOperationException("Receiver process did not start.");
            started = true;
            _process.BeginOutputReadLine();
            _process.BeginErrorReadLine();
        }
        catch (Exception startupFailure)
        {
            int pid = KnownId();
            try
            {
                // Start itself can fail after associating a child. Check identity
                // as well as the return value before treating it as unstarted.
                if (started || pid != 0) Dispose();
                else _process.Dispose();
            }
            catch (Exception cleanupFailure)
            {
                throw new ReceiverCleanupException(pid,
                    "Receiver startup failed: " + startupFailure.Message +
                    " Cleanup is unconfirmed: " + cleanupFailure.Message,
                    new AggregateException(startupFailure, cleanupFailure));
            }
            throw;
        }
    }

    public int Id
    {
        get { try { return _disposed || _process.HasExited ? 0 : _process.Id; } catch (InvalidOperationException) { return 0; } }
    }
    public Task WaitForExitAsync(CancellationToken ct) => _process.WaitForExitAsync(ct);
    public void Dispose()
    {
        lock (_cleanupGate)
        {
            if (_disposed) return;
            int pid = KnownId();
            try
            {
                if (!_process.HasExited)
                {
                    try { _process.KillTree(); }
                    catch (InvalidOperationException) when (_process.HasExited) { } // Exited between check and kill.
                }
                // A kill request is not exit confirmation. Use a bounded wait;
                // do not discard the handle or permit retry while exit is unknown.
                if (!_process.WaitForExit(ExitTimeoutMilliseconds))
                    throw new TimeoutException("Receiver exit was not confirmed within five seconds.");
                _process.Dispose();
                _disposed = true;
            }
            catch (Exception ex)
            {
                throw new ReceiverCleanupException(pid, "Receiver exit/cleanup could not be confirmed: " + ex.Message, ex);
            }
        }
    }

    private int KnownId() { try { return _process.Id; } catch (Exception) { return 0; } }
}
