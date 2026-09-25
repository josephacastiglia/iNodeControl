$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Gate5Min {
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$p = Get-Process -Id 34852
$hwnd = $p.MainWindowHandle
[Win32Gate5Min]::ShowWindow($hwnd, 6) | Out-Null
Start-Sleep -Milliseconds 200
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$cond = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::CheckBox)
$els = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
$boxes = @()
foreach ($c in $els) {
  $tog = 'n/a'
  try { $tog = $c.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState.ToString() } catch {}
  $boxes += [pscustomobject]@{ name = $c.Current.Name; id = $c.Current.AutomationId; toggle = $tog }
}
$iconic = [Win32Gate5Min]::IsIconic($hwnd)
$mirror = @($boxes | Where-Object { $_.id -eq 'SelectAllBox' -or $_.name -match 'Mirror' })
$on = @($mirror | Where-Object { $_.toggle -eq 'On' })
[pscustomobject]@{
  console_pid = 34852
  hwnd = $hwnd.ToInt64()
  iconic = $iconic
  mirror_boxes = $mirror
  mirror_on_count = $on.Count
} | ConvertTo-Json -Depth 5
if (-not $iconic -or $on.Count -gt 0) { exit 2 }
