using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace IMouse2.Kernel;

/// <summary>Separate read-only handle; never changes polling, flushes queues or writes reports.</summary>
internal static class HidInputReader
{
    internal static FileStream Open(HidBoard board)
    {
        var handle = CreateFileW(board.Path, 0x80000000, 3, IntPtr.Zero, 3, 0x40000000, IntPtr.Zero);
        try
        {
            if (handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
            if (!HidD_GetPreparsedData(handle, out var preparsed)) throw new Win32Exception(Marshal.GetLastWin32Error());
            try
            {
                if (HidP_GetCaps(preparsed, out var caps) != 0x110000
                    || caps.UsagePage != 0xFF00 || caps.InputLength != 17 || caps.OutputLength != 9)
                    throw new InvalidDataException("Unexpected HID input report capabilities.");
            }
            finally { HidD_FreePreparsedData(preparsed); }
            // Buffer size 1 disables managed read-ahead; each read requests one report.
            return new FileStream(handle, FileAccess.Read, 1, isAsync: true);
        }
        catch { handle.Dispose(); throw; }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Caps
    {
        public ushort Usage, UsagePage, InputLength, OutputLength, FeatureLength;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 17)] public ushort[] Reserved;
        public ushort NumberLinkCollectionNodes, NumberInputButtonCaps, NumberInputValueCaps, NumberInputDataIndices;
        public ushort NumberOutputButtonCaps, NumberOutputValueCaps, NumberOutputDataIndices;
        public ushort NumberFeatureButtonCaps, NumberFeatureValueCaps, NumberFeatureDataIndices;
    }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFileW(string path, uint access, uint share, IntPtr security,
        uint creation, uint flags, IntPtr template);
    [DllImport("hid.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.U1)]
    private static extern bool HidD_GetPreparsedData(SafeFileHandle handle, out IntPtr preparsed);
    [DllImport("hid.dll")]
    [return: MarshalAs(UnmanagedType.U1)]
    private static extern bool HidD_FreePreparsedData(IntPtr preparsed);
    [DllImport("hid.dll")]
    private static extern int HidP_GetCaps(IntPtr preparsed, out Caps caps);
}
