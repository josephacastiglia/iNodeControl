$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Gate8Min {
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$procs = @(Get-Process | Where-Object { $_.MainWindowTitle -match 'iMouse' })
if ($procs.Count -lt 1) { throw 'no iMouse console window' }
$p = $procs[0]
$hwnd = $p.MainWindowHandle
if ($hwnd -eq [IntPtr]::Zero) { throw 'console has no main window' }
[Win32Gate8Min]::ShowWindow($hwnd, 6) | Out-Null
Start-Sleep -Milliseconds 250
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$cond = New-Object System.Windows.Automation.PropertyCondition (
  [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::CheckBox)
$els = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
$boxes = @()
foreach ($c in $els) {
  $tog = 'n/a'
  try { $tog = $c.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState.ToString() } catch {}
  $boxes += [pscustomobject]@{ name = $c.Current.Name; id = $c.Current.AutomationId; toggle = $tog }
}
$iconic = [Win32Gate8Min]::IsIconic($hwnd)
$mirror = @($boxes | Where-Object { $_.id -eq 'SelectAllBox' -or $_.name -match 'Mirror' })
$on = @($mirror | Where-Object { $_.toggle -eq 'On' })
[pscustomobject]@{
  console_pid = $p.Id
  window = $p.MainWindowTitle
  hwnd = $hwnd.ToInt64()
  iconic = $iconic
  mirror_boxes = $mirror
  mirror_on_count = $on.Count
} | ConvertTo-Json -Depth 5
if (-not $iconic -or $on.Count -gt 0) { exit 2 }
