using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;

namespace IMouse2.Kernel;

/// <summary>
/// One WCH board as Windows currently sees it. PID is the address.
/// Handles are shared for read/write, as verified on C24C. Shared handles do not
/// serialize commands from different processes: use exactly one input controller.
/// Enumeration does not open the handle.
/// </summary>
public sealed record HidBoard(string Vid, string Pid, string Path);

public static partial class HidHost
{
    public const string VendorId = "720A";

    public static List<HidBoard> Enumerate()
    {
        var hidGuid = HidGuid();
        var devs = SetupDiGetClassDevs(ref hidGuid, IntPtr.Zero, IntPtr.Zero, DigcfPresent | DigcfDeviceInterface);
        if (devs == Invalid) return [];
        var found = new List<HidBoard>();
        try
        {
            var data = new SpDeviceInterfaceData { CbSize = Marshal.SizeOf<SpDeviceInterfaceData>() };
            for (uint i = 0; SetupDiEnumDeviceInterfaces(devs, IntPtr.Zero, ref hidGuid, i, ref data); i++)
            {
                SetupDiGetDeviceInterfaceDetail(devs, ref data, IntPtr.Zero, 0, out uint needed, IntPtr.Zero);
                if (needed == 0) continue;
                var detail = Marshal.AllocHGlobal((int)needed);
                try
                {
                    Marshal.WriteInt32(detail, IntPtr.Size == 8 ? 8 : 6);
                    if (!SetupDiGetDeviceInterfaceDetail(devs, ref data, detail, needed, out _, IntPtr.Zero)) continue;
                    string path = Marshal.PtrToStringUni(detail + 4) ?? "";
                    var m = VidPid().Match(path);
                    if (!m.Success || !m.Groups[1].Value.Equals(VendorId, StringComparison.OrdinalIgnoreCase)) continue;
                    found.Add(new HidBoard(VendorId, m.Groups[2].Value.ToUpperInvariant(), path));
                }
                finally { Marshal.FreeHGlobal(detail); }
            }
        }
        finally { SetupDiDestroyDeviceInfoList(devs); }
        return found.DistinctBy(b => b.Pid).OrderBy(b => b.Pid).ToList();
    }

    public sealed record Caps(
        string Pid, string Path, string Open, ushort UsagePage, ushort Usage,
        ushort InputLen, ushort OutputLen, ushort FeatureLen, string ReportDescriptorHex, string OutputFields);

    public static Caps Describe(HidBoard board)
    {
        var handle = CreateFile(board.Path, GenericRead | GenericWrite, FileShareRead | FileShareWrite, IntPtr.Zero, OpenExisting, 0, IntPtr.Zero);
        if (handle == Invalid || handle == IntPtr.Zero)
        {
            handle = CreateFile(board.Path, GenericRead, FileShareRead | FileShareWrite, IntPtr.Zero, OpenExisting, 0, IntPtr.Zero);
            if (handle == Invalid || handle == IntPtr.Zero)
                return new Caps(board.Pid, board.Path, "busy " + Marshal.GetLastWin32Error(), 0, 0, 0, 0, 0, "", "");
        }
        try
        {
            string desc = ReadReportDescriptor(handle);
            if (!HidD_GetPreparsedData(handle, out var preparsed))
                return new Caps(board.Pid, board.Path, "no preparsed " + Marshal.GetLastWin32Error(), 0, 0, 0, 0, 0, desc, "");
            try
            {
                HidP_GetCaps(preparsed, out var caps);
                return new Caps(board.Pid, board.Path, "ok", caps.UsagePage, caps.Usage,
                    caps.InputReportByteLength, caps.OutputReportByteLength, caps.FeatureReportByteLength,
                    desc, OutputFields(preparsed, caps.NumberOutputValueCaps));
            }
            finally { HidD_FreePreparsedData(preparsed); }
        }
        finally { CloseHandle(handle); }
    }

    private static string ReadReportDescriptor(IntPtr handle)
    {
        var buf = new byte[256];
        if (!DeviceIoControl(handle, IoctlHidGetReportDescriptor, IntPtr.Zero, 0, buf, buf.Length, out uint got, IntPtr.Zero) || got == 0)
            return "ioctl " + Marshal.GetLastWin32Error();
        return Convert.ToHexString(buf.AsSpan(0, (int)got).ToArray());
    }

    private static string OutputFields(IntPtr preparsed, ushort count)
    {
        if (count == 0) return "no output values";
        var caps = new HidpValueCaps[count];
        ushort n = count;
        HidP_GetValueCaps(HidPOutput, caps, ref n, preparsed);
        return string.Join("; ", caps.Take(n).Select(c =>
            $"id={c.ReportID} page=0x{c.UsagePage:X4} bit={c.BitSize} count={c.ReportCount} abs={c.IsAbsolute}"));
    }

    [GeneratedRegex(@"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", RegexOptions.IgnoreCase)]
    private static partial Regex VidPid();

    private static Guid HidGuid()
    {
        HidD_GetHidGuid(out var g);
        return g;
    }

    private const int DigcfPresent = 0x2, DigcfDeviceInterface = 0x10;
    private const uint GenericRead = 0x80000000, GenericWrite = 0x40000000;
    private const uint FileShareRead = 1, FileShareWrite = 2, OpenExisting = 3;
    private static readonly IntPtr Invalid = new(-1);

    private const int HidPOutput = 1;
    private const uint IoctlHidGetReportDescriptor = 0x000B000F;

    [StructLayout(LayoutKind.Sequential)]
    private struct HidpValueCaps
    {
        public ushort UsagePage;
        public byte ReportID;
        public byte IsAlias;
        public ushort BitField, LinkCollection, LinkUsage, LinkUsagePage;
        public byte IsRange, IsStringRange, IsDesignatorRange, IsAbsolute, HasNull, Reserved;
        public ushort BitSize, ReportCount;
        public ushort Reserved2, Reserved3, Reserved4, Reserved5, UnitsExp, Units;
        public int LogicalMin, LogicalMax, PhysicalMin, PhysicalMax;
        public ushort UsageMin, UsageMax, StringMin, StringMax, DesignatorMin, DesignatorMax, DataIndexMin, DataIndexMax;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct HidpCaps
    {
        public ushort Usage, UsagePage;
        public ushort InputReportByteLength, OutputReportByteLength, FeatureReportByteLength;
        public ushort Reserved1, Reserved2, Reserved3, Reserved4, Reserved5, Reserved6, Reserved7,
            Reserved8, Reserved9, Reserved10, Reserved11, Reserved12, Reserved13, Reserved14, Reserved15, Reserved16, Reserved17;
        public ushort NumberLinkCollectionNodes;
        public ushort NumberInputButtonCaps, NumberInputValueCaps, NumberInputDataIndices;
        public ushort NumberOutputButtonCaps, NumberOutputValueCaps, NumberOutputDataIndices;
        public ushort NumberFeatureButtonCaps, NumberFeatureValueCaps, NumberFeatureDataIndices;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct SpDeviceInterfaceData
    {
        public int CbSize;
        public Guid InterfaceClassGuid;
        public int Flags;
        public IntPtr Reserved;
    }

    [DllImport("hid.dll", SetLastError = true)]
    private static extern void HidD_GetHidGuid(out Guid guid);

    [DllImport("setupapi.dll", SetLastError = true)]
    private static extern IntPtr SetupDiGetClassDevs(ref Guid classGuid, IntPtr enumerator, IntPtr parent, int flags);

    [DllImport("setupapi.dll", SetLastError = true)]
    private static extern bool SetupDiEnumDeviceInterfaces(IntPtr devs, IntPtr info, ref Guid guid, uint index, ref SpDeviceInterfaceData data);

    [DllImport("setupapi.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetupDiGetDeviceInterfaceDetail(IntPtr devs, ref SpDeviceInterfaceData data, IntPtr detail, uint detailSize, out uint required, IntPtr info);

    [DllImport("setupapi.dll", SetLastError = true)]
    private static extern bool SetupDiDestroyDeviceInfoList(IntPtr devs);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateFile(string path, uint access, uint share, IntPtr sec, uint disp, uint flags, IntPtr template);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr handle);

    [DllImport("hid.dll", SetLastError = true)]
    private static extern bool HidD_GetPreparsedData(IntPtr handle, out IntPtr preparsed);

    [DllImport("hid.dll", SetLastError = true)]
    private static extern bool HidD_FreePreparsedData(IntPtr preparsed);

    [DllImport("hid.dll", SetLastError = true)]
    private static extern int HidP_GetCaps(IntPtr preparsed, out HidpCaps caps);

    [DllImport("hid.dll", SetLastError = true)]
    private static extern int HidP_GetValueCaps(int reportType, [Out] HidpValueCaps[] caps, ref ushort length, IntPtr preparsed);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool DeviceIoControl(IntPtr handle, uint code, IntPtr inBuf, int inLen, byte[] outBuf, int outLen, out uint returned, IntPtr overlapped);
}
