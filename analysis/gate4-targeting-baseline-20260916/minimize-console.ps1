$ErrorActionPreference = 'Stop'
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Min {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
}
"@
$p = Get-Process -Id 34852
[Win32Min]::ShowWindow($p.MainWindowHandle, 6) | Out-Null
Start-Sleep -Milliseconds 200
"ICONIC=$([Win32Min]::IsIconic($p.MainWindowHandle)) HWND=$($p.MainWindowHandle)"
