using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace IMouse2.Kernel;

/// <summary>
/// Per-move high-resolution pacing. Never shared between boards or outstanding
/// moves. Leaves reset, keyboard, drag and button-settle timing alone.
/// </summary>
internal sealed class MovementDelay : IDisposable
{
    private readonly EventWaitHandle _wait = new(false, EventResetMode.AutoReset);
    public MovementDelay()
    {
        // Synchronize | TIMER_MODIFY_STATE; unnamed auto-reset high-resolution timer.
        var handle = CreateWaitableTimerExW(IntPtr.Zero, null, 2, 0x00100002);
        if (handle.IsInvalid)
        {
            int error = Marshal.GetLastWin32Error();
            handle.Dispose(); _wait.Dispose();
            throw new Win32Exception(error);
        }
        _wait.SafeWaitHandle.Dispose();
        _wait.SafeWaitHandle = handle;
    }

    public async Task WaitAsync(int milliseconds, CancellationToken cancellation = default)
    {
        if (milliseconds < 1) throw new ArgumentOutOfRangeException(nameof(milliseconds));
        long due = -(long)milliseconds * 10_000;
        if (!SetWaitableTimer(_wait.SafeWaitHandle, ref due, 0, IntPtr.Zero, IntPtr.Zero, false))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var registration = ThreadPool.RegisterWaitForSingleObject(_wait,
            (_, _) => done.TrySetResult(), null, Timeout.Infinite, true);
        try { await done.Task.WaitAsync(cancellation).ConfigureAwait(false); }
        finally { registration.Unregister(null); }
    }

    public void Dispose() => _wait.Dispose();
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeWaitHandle CreateWaitableTimerExW(IntPtr attributes, string? name, uint flags, uint access);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWaitableTimer(SafeWaitHandle timer, ref long due, int period,
        IntPtr completion, IntPtr argument, [MarshalAs(UnmanagedType.Bool)] bool resume);
}
