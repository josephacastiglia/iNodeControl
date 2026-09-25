# Read-only descriptor inspection. No port power, reset, or SET_FEATURE requests.
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class RackHubReadOnly {
    [StructLayout(LayoutKind.Sequential)] struct InterfaceData {
        public int Size; public Guid ClassGuid; public uint Flags; public IntPtr Reserved;
    }
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr SetupDiGetClassDevs(ref Guid guid, IntPtr enumerator, IntPtr parent, uint flags);
    [DllImport("setupapi.dll", SetLastError=true)]
    static extern bool SetupDiEnumDeviceInterfaces(IntPtr set, IntPtr device, ref Guid guid, uint index, ref InterfaceData data);
    [DllImport("setupapi.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern bool SetupDiGetDeviceInterfaceDetail(IntPtr set, ref InterfaceData data, IntPtr detail, uint length, out uint required, IntPtr device);
    [DllImport("setupapi.dll")] static extern bool SetupDiDestroyDeviceInfoList(IntPtr set);
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr CreateFile(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool DeviceIoControl(IntPtr handle, uint code, byte[] input, int inputSize, byte[] output, int outputSize, out uint returned, IntPtr overlapped);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    public sealed class Result {
        public string Path; public string Error; public uint Returned;
        public int Ports; public string Characteristics; public bool IndicatorsAdvertised; public string Raw;
    }
    public static Result[] Inspect() {
        var results = new List<Result>();
        var guid = new Guid("f18a0e88-c30c-11d0-8815-00a0c906bed8");
        IntPtr set = SetupDiGetClassDevs(ref guid, IntPtr.Zero, IntPtr.Zero, 0x12);
        if (set == new IntPtr(-1)) throw new System.ComponentModel.Win32Exception();
        try {
            for (uint i=0; ; i++) {
                var data = new InterfaceData { Size=Marshal.SizeOf(typeof(InterfaceData)) };
                if (!SetupDiEnumDeviceInterfaces(set, IntPtr.Zero, ref guid, i, ref data)) {
                    int error=Marshal.GetLastWin32Error();
                    if(error!=259) throw new System.ComponentModel.Win32Exception(error);
                    break;
                }
                uint required;
                SetupDiGetDeviceInterfaceDetail(set, ref data, IntPtr.Zero, 0, out required, IntPtr.Zero);
                IntPtr detail=Marshal.AllocHGlobal((int)required);
                try {
                    Marshal.WriteInt32(detail, IntPtr.Size==8 ? 8 : 6);
                    if(!SetupDiGetDeviceInterfaceDetail(set,ref data,detail,required,out required,IntPtr.Zero))
                        throw new System.ComponentModel.Win32Exception();
                    string path=Marshal.PtrToStringUni(IntPtr.Add(detail,4));
                    if(path.IndexOf("vid_1a40&pid_0201",StringComparison.OrdinalIgnoreCase)<0) continue;
                    var result=new Result { Path=path };
                    results.Add(result);
                    // Descriptor IOCTL is FILE_ANY_ACCESS; request no data read/write access.
                    IntPtr handle=CreateFile(path,0,3,IntPtr.Zero,3,0,IntPtr.Zero);
                    if(handle==new IntPtr(-1)) { result.Error="Open: "+Marshal.GetLastWin32Error(); continue; }
                    try {
                        byte[] input=new byte[76], output=new byte[76]; uint returned;
                        if(!DeviceIoControl(handle,0x220408,input,input.Length,output,output.Length,out returned,IntPtr.Zero)) {
                            result.Error="GET_NODE_INFORMATION: "+Marshal.GetLastWin32Error(); continue;
                        }
                        result.Returned=returned;
                        result.Raw=BitConverter.ToString(output,0,(int)Math.Min(returned,76));
                        if(returned<11 || output[5]!=0x29) { result.Error="Unexpected descriptor layout"; continue; }
                        result.Ports=output[6];
                        ushort characteristics=BitConverter.ToUInt16(output,7);
                        result.Characteristics="0x"+characteristics.ToString("X4");
                        result.IndicatorsAdvertised=(characteristics & 0x80)!=0;
                    } finally { CloseHandle(handle); }
                } finally { Marshal.FreeHGlobal(detail); }
            }
        } finally { SetupDiDestroyDeviceInfoList(set); }
        return results.ToArray();
    }
}
'@
[RackHubReadOnly]::Inspect() | ConvertTo-Json -Depth 4 | Tee-Object -FilePath (Join-Path $PSScriptRoot 'hub-indicators.json')
