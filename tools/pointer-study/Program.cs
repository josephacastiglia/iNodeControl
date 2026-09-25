using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using Microsoft.Win32.SafeHandles;

if (args.Length > 0 && args[0] == "--router-suite")
{
    await LiveRouter.RunAsync(args);
    return;
}
if (args.Length > 0 && args[0] == "--move")
{
    await LiveMove.RunAsync(args);
    return;
}
// The timing mode is deliberately hardware-free.
if (args.Length != 2 || args[0] != "--timing")
    throw new ArgumentException("Usage: PointerStudy --timing OUTPUT_JSON (opens no HID handles)");
var results = new List<object>();
using var timer = new PreciseDelay();
foreach (int requested in new[] { 3, 6, 10, 15 })
foreach (string mode in new[] { "task-delay", "waitable-timer" })
{
    Func<Task> delay = mode == "task-delay" ? () => Task.Delay(requested) : () => timer.WaitAsync(requested);
    for (int i = 0; i < 5; i++) await delay();
    var gaps = new List<double>();
    var process = Process.GetCurrentProcess();
    double cpuBefore = process.TotalProcessorTime.TotalMilliseconds;
    var total = Stopwatch.StartNew();
    for (int i = 0; i < 80; i++)
    {
        var watch = Stopwatch.StartNew();
        await delay();
        gaps.Add(watch.Elapsed.TotalMilliseconds);
    }
    double elapsed = total.Elapsed.TotalMilliseconds;
    process.Refresh();
    double cpu = process.TotalProcessorTime.TotalMilliseconds - cpuBefore;
    var sorted = gaps.Order().ToArray();
    var row = new { mode, requested_ms = requested, count = gaps.Count,
        mean_ms = gaps.Average(), min_ms = sorted[0], p50_ms = sorted[40], p95_ms = sorted[76], max_ms = sorted[^1],
        elapsed_ms = elapsed, cpu_ms = cpu, gaps_ms = gaps };
    results.Add(row);
    Console.WriteLine($"{mode} request={requested}ms mean={gaps.Average():F2} p95={sorted[76]:F2} CPU={cpu:F1}ms");
}
File.WriteAllText(args[1], JsonSerializer.Serialize(new { at = DateTimeOffset.UtcNow, hardware_opened = false, results }, new JsonSerializerOptions { WriteIndented = true }));

// One outstanding wait per instance. Auto-reset timer; native handle and registered
// wait have bounded lifetimes, no busy-spin and no global timer-resolution change.
sealed class PreciseDelay : IDisposable
{
    private readonly EventWaitHandle _wait = new(false, EventResetMode.AutoReset);
    public PreciseDelay()
    {
        var handle = CreateWaitableTimerExW(IntPtr.Zero, null, 2, 0x00100002);
        if (handle.IsInvalid) { int error = Marshal.GetLastWin32Error(); handle.Dispose(); _wait.Dispose(); throw new Win32Exception(error); }
        _wait.SafeWaitHandle.Dispose();
        _wait.SafeWaitHandle = handle;
    }
    public async Task WaitAsync(int milliseconds)
    {
        if (milliseconds < 1) throw new ArgumentOutOfRangeException(nameof(milliseconds));
        long due = -(long)milliseconds * 10_000;
        if (!SetWaitableTimer(_wait.SafeWaitHandle, ref due, 0, IntPtr.Zero, IntPtr.Zero, false))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var registration = ThreadPool.RegisterWaitForSingleObject(_wait, (_, _) => done.TrySetResult(), null, Timeout.Infinite, true);
        try { await done.Task.ConfigureAwait(false); }
        finally { registration.Unregister(null); }
    }
    public void Dispose() => _wait.Dispose();
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeWaitHandle CreateWaitableTimerExW(IntPtr attributes, string? name, uint flags, uint access);
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWaitableTimer(SafeWaitHandle timer, ref long due, int period, IntPtr completion, IntPtr argument, [MarshalAs(UnmanagedType.Bool)] bool resume);
}
