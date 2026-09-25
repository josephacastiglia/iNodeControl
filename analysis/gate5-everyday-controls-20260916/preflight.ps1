$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Gate5 {
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

$procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'iMouse|uxplay|IMService|IMConsole' } |
  Select-Object ProcessId, Name, ExecutablePath
$console = Get-Process | Where-Object { $_.MainWindowTitle -match 'iMouse' }

$s1 = Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 5
Start-Sleep -Seconds 2
$s2 = Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 5

$uia = $null
if ($console) {
  $p = $console | Select-Object -First 1
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
  $uia = [pscustomobject]@{
    window = $root.Current.Name
    console_pid = $p.Id
    hwnd = $hwnd.ToInt64()
    iconic = [Win32Gate5]::IsIconic($hwnd)
    visible = [Win32Gate5]::IsWindowVisible($hwnd)
    SelectAllLabel = $(if ($lab) { $lab.Current.Name } else { '' })
    totals = @($tot | Select-Object -Unique)
    checkboxes = $boxes
  }
}

[pscustomobject]@{
  kernel_pid_31944 = [bool](Get-Process -Id 31944 -ErrorAction SilentlyContinue)
  frames = [pscustomobject]@{
    t0 = $s1.data.receivers | Select-Object deviceid, name, live, frames, receiver_state, receiver_pid
    t2 = $s2.data.receivers | Select-Object deviceid, name, live, frames, receiver_state, receiver_pid
  }
  processes = $procs
  consoles = @($console | Select-Object Id, ProcessName, MainWindowTitle, MainWindowHandle)
  uia = $uia
} | ConvertTo-Json -Depth 8
