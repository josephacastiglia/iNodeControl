using System.Runtime.InteropServices;
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

    [GeneratedRegex(@"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", RegexOptions.IgnoreCase)]
    private static partial Regex VidPid();

    private static Guid HidGuid()
    {
        HidD_GetHidGuid(out var g);
        return g;
    }

    private const int DigcfPresent = 0x2, DigcfDeviceInterface = 0x10;
    private static readonly IntPtr Invalid = new(-1);

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
}
