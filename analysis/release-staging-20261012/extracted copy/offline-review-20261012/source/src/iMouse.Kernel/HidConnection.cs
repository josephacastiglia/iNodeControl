using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace IMouse2.Kernel;

/// <summary>Matches the vendor's observed interrupt OUT WriteFile transport.</summary>
public interface IHidTransport : IDisposable
{
    Task SendAsync(byte[] data,CancellationToken ct);
}
public sealed class HidConnection : IHidTransport
{
    private readonly FileStream _stream;
    public HidConnection(string pid)
    {
        var board = HidHost.Enumerate().SingleOrDefault(b => b.Pid.Equals(pid, StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException("Board " + pid);
        var handle = CreateFileW(board.Path, 0xC0000000, 3, IntPtr.Zero, 3, 0x40000000, IntPtr.Zero);
        if (handle.IsInvalid) { int error = Marshal.GetLastWin32Error(); handle.Dispose(); throw new Win32Exception(error); }
        _stream = new FileStream(handle, FileAccess.ReadWrite, 9, true);
    }

    public async Task SendAsync(byte[] data, CancellationToken ct)
    {
        if (data.Length != 8) throw new ArgumentException("Exactly eight data bytes required.");
        byte[] report = new byte[9];
        data.CopyTo(report, 1); // Report ID zero is the HID API prefix.
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
        timeout.CancelAfter(TimeSpan.FromSeconds(2));
        await _stream.WriteAsync(report, timeout.Token).ConfigureAwait(false);
        await _stream.FlushAsync(timeout.Token).ConfigureAwait(false);
    }

    public void Dispose() => _stream.Dispose();

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security,
        uint creation, uint flags, IntPtr template);
}
