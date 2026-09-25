$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32C241Diag {
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$p = Get-Process -Id 34852 -ErrorAction Stop
$hwnd = $p.MainWindowHandle
if ($hwnd -eq [IntPtr]::Zero) { throw 'console has no main window' }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$cond = New-Object System.Windows.Automation.PropertyCondition (
  [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::CheckBox)
$els = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
$boxes = @()
foreach ($c in $els) {
  $tog = 'n/a'
  try {
    $tog = $c.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState.ToString()
  } catch {}
  $boxes += [pscustomobject]@{ name = $c.Current.Name; id = $c.Current.AutomationId; toggle = $tog }
}
$mirror = @($boxes | Where-Object { $_.id -eq 'SelectAllBox' -or $_.name -match 'Mirror' })
$on = @($mirror | Where-Object { $_.toggle -eq 'On' })
if ($on.Count -gt 0) { throw 'Mirror-to-all is ON; refusing to continue' }
[Win32C241Diag]::ShowWindow($hwnd, 6) | Out-Null
Start-Sleep -Milliseconds 250
$iconic = [Win32C241Diag]::IsIconic($hwnd)
[pscustomobject]@{
  console_pid = 34852
  window = $p.MainWindowTitle
  hwnd = $hwnd.ToInt64()
  iconic = $iconic
  mirror_on_count = $on.Count
  mirror_boxes = $mirror
  all_boxes = $boxes
} | ConvertTo-Json -Depth 5
if (-not $iconic) { exit 2 }
