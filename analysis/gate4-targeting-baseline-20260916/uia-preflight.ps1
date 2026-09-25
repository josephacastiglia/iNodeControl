$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Gate4 {
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$p = Get-Process -Id 34852
$hwnd = $p.MainWindowHandle
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
$cond = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::CheckBox)
$els = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
$boxes = @()
foreach ($c in $els) {
  $tog = 'n/a'
  try { $tog = $c.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState.ToString() } catch {}
  $boxes += [pscustomobject]@{ name = $c.Current.Name; id = $c.Current.AutomationId; toggle = $tog; offscreen = [bool]$c.Current.IsOffscreen }
}
$idcond = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'SelectAllLabel')
$lab = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $idcond)
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
$tot = @()
foreach ($e in $all) {
  $n = $e.Current.Name
  if ($n -match 'phones' -and $n -match 'boards') { $tot += $n }
}
[pscustomobject]@{
  window = $root.Current.Name
  console_pid = 34852
  hwnd = $hwnd.ToInt64()
  iconic = [Win32Gate4]::IsIconic($hwnd)
  visible = [Win32Gate4]::IsWindowVisible($hwnd)
  SelectAllLabel = $(if ($lab) { $lab.Current.Name } else { '' })
  totals = @($tot | Select-Object -Unique)
  checkboxes = $boxes
} | ConvertTo-Json -Depth 5
