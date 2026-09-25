$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Gate6 {
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$p = Get-Process -Id 29436 -ErrorAction Stop
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
  try { $tog = $c.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState.ToString() } catch {}
  $boxes += [pscustomobject]@{ name = $c.Current.Name; id = $c.Current.AutomationId; toggle = $tog }
}
$idcond = New-Object System.Windows.Automation.PropertyCondition (
  [System.Windows.Automation.AutomationElement]::AutomationIdProperty, 'SelectAllLabel')
$lab = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $idcond)
$mirror = @($boxes | Where-Object { $_.id -eq 'SelectAllBox' -or $_.name -match 'Mirror' })
$on = @($mirror | Where-Object { $_.toggle -eq 'On' })
if ($on.Count -gt 0) { throw 'Mirror-to-all is ON; refusing to continue' }
[Win32Gate6]::ShowWindow($hwnd, 6) | Out-Null
Start-Sleep -Milliseconds 300
$iconic = [Win32Gate6]::IsIconic($hwnd)
[pscustomobject]@{
  console_pid = 29436
  window = $p.MainWindowTitle
  hwnd = $hwnd.ToInt64()
  iconic = $iconic
  visible = [Win32Gate6]::IsWindowVisible($hwnd)
  SelectAllLabel = $(if ($lab) { $lab.Current.Name } else { '' })
  mirror_on_count = $on.Count
  mirror_boxes = $mirror
  checkboxes = $boxes
} | ConvertTo-Json -Depth 5
if (-not $iconic) { exit 2 }
