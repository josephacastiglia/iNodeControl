# Candidate-5 only. Set the Send text box, invoke its real Click handler, or read the activity log.
# Does not move the mouse. Refuses any other process, mirroring, a ticked follower, or a selected phone that is not C24C.
param(
  [Parameter(Mandatory)][int]$ProcessId,
  [Parameter(Mandatory)][ValidateSet('set','press','log','wait','send','release-lease')][string]$Action,
  [string]$Text = '',
  [string]$Previous = '',
  [double]$TimeoutSec = 4
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$p = Get-Process -Id $ProcessId -ErrorAction Stop
if ($p.Path -notlike '*imouse-candidate-5\iMouse2.exe') { throw "PID $ProcessId is not candidate-5" }
$root = [Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
if (-not $root) { throw 'candidate-5 has no main window' }
$TC = [Windows.Automation.TreeScope]::Descendants
function ById([string]$id) {
  New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
}
function NameOf($e) {
  $n = $e.Current.Name
  if (-not $n) {
    $t = $e.FindFirst($TC, (New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::Text)))
    if ($t) { $n = $t.Current.Name }
  }
  $n
}
function Invoke-Id([string]$id) {
  $e = $root.FindFirst($TC, (ById $id))
  if (-not $e) { throw "missing $id" }
  $e.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
}
function Ensure-Controls {
  if (-not $root.FindFirst($TC, (ById 'BatchMode'))) {
    Invoke-Id 'ControlsButton'
    Start-Sleep -Milliseconds 400
  }
}
function Assert-MirrorOff {
  Ensure-Controls
  $boxes = $root.FindAll($TC, (New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::CheckBox)))
  foreach ($b in $boxes) {
    $nm = NameOf $b
    if ($b.Current.AutomationId -eq 'BatchMode' -or $nm -like 'Mirror*') {
      $st = $b.GetCurrentPattern([Windows.Automation.TogglePattern]::Pattern).Current.ToggleState
      if ("$st" -ne 'Off') { throw "Refusing: '$nm' is $st" }
    }
  }
  if (-not ($boxes | Where-Object { $_.Current.AutomationId -eq 'BatchMode' })) { throw 'Controls drawer is not open' }
}
function Item-Label($item) {
  $names = @()
  if ($item.Current.Name) { $names += $item.Current.Name }
  foreach ($d in $item.FindAll([Windows.Automation.TreeScope]::Descendants, [Windows.Automation.Condition]::TrueCondition)) {
    if ($d.Current.Name) { $names += $d.Current.Name }
  }
  $names -join ' '
}
function Assert-SelectedC24C {
  $list = $root.FindFirst($TC, (ById 'DeviceList'))
  if (-not $list) { throw 'DeviceList not found' }
  $items = $list.FindAll([Windows.Automation.TreeScope]::Descendants, (New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::ListItem)))
  $hit = $null
  foreach ($item in $items) {
    $sp = $item.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern)
    if ($sp.Current.IsSelected) { $hit = $item; break }
  }
  if (-not $hit) { throw 'No phone is selected' }
  $label = Item-Label $hit
  if (-not (Is-C24CLabel $label)) { throw "Refusing: selected phone is '$label', not C24C" }
}
function Is-C24CLabel([string]$label) {
  $label -like '*C24C*' -or $label -like '*2F:F6*'
}
function Select-C24C {
  # ponytail: 10s covers the console HTTP timeout (8s) plus list apply. Raise if device/get is slower.
  $deadline = (Get-Date).AddSeconds(10)
  $hit = $null
  do {
    $list = $root.FindFirst($TC, (ById 'DeviceList'))
    if ($list) {
      $items = $list.FindAll([Windows.Automation.TreeScope]::Descendants, (New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::ListItem)))
      foreach ($item in $items) {
        if (Is-C24CLabel (Item-Label $item)) { $hit = $item; break }
      }
    }
    if ($hit) { break }
    if ((Get-Date) -ge $deadline) { break }
    Start-Sleep -Milliseconds 200
  } while ($true)
  if (-not $hit) { throw 'C24C is not in the device list after Connect' }
  $hit.GetCurrentPattern([Windows.Automation.SelectionItemPattern]::Pattern).Select()
}
function Read-Event {
  if (-not $root.FindFirst($TC, (ById 'LastEvent'))) {
    Invoke-Id 'ActivityButton'
    Start-Sleep -Milliseconds 300
  }
  $top = ''
  $list = $root.FindFirst($TC, (ById 'ActivityList'))
  if ($list) {
    $item = $list.FindFirst([Windows.Automation.TreeScope]::Descendants, (New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::ListItem)))
    if ($item) { $top = NameOf $item }
  }
  if (-not $top) {
    $ev = $root.FindFirst($TC, (ById 'LastEvent'))
    if ($ev) { $top = $ev.Current.Name }
  }
  $top
}
function Set-SendBox([string]$value) {
  Assert-SelectedC24C
  Assert-MirrorOff
  $tb = $root.FindFirst($TC, (New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::NameProperty, 'Text to type on target phones')))
  if (-not $tb) { throw 'Send text box not found' }
  $vp = $tb.GetCurrentPattern([Windows.Automation.ValuePattern]::Pattern)
  $vp.SetValue($value)
  return $vp.Current.Value
}
function Format-Readback([string]$v) {
  $hex = ([Text.Encoding]::ASCII.GetBytes($v) | ForEach-Object { $_.ToString('X2') }) -join ' '
  "value=[$v] length=$($v.Length) bytes=$hex"
}
function Press-SendText {
  Assert-SelectedC24C
  Assert-MirrorOff
  $btns = $root.FindAll($TC, (New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ControlTypeProperty, [Windows.Automation.ControlType]::Button)))
  $hits = @($btns | Where-Object { (NameOf $_) -eq 'Send text' -and -not $_.Current.AutomationId })
  if ($hits.Count -ne 1) { throw "Expected exactly one 'Send text' button, found $($hits.Count)" }
  if (-not $hits[0].Current.IsEnabled) { throw "'Send text' is disabled" }
  $ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $hits[0].GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
  return $ms
}

switch ($Action) {
  'set' { Format-Readback (Set-SendBox $Text) }
  'press' {
    $ms = Press-SendText
    "invoked_ms=$ms"
    "pressed 'Send text'"
  }
  'send' {
    $v = Set-SendBox $Text
    Format-Readback $v
    if ($v -ne $Text) { throw "box readback is [$v], not [$Text]" }
    $ms = Press-SendText
    "invoked_ms=$ms"
    "pressed 'Send text'"
  }
  'release-lease' {
    Invoke-Id 'SettingsButton'
    Start-Sleep -Milliseconds 400
    Invoke-Id 'DisconnectButton'
    Start-Sleep -Milliseconds 300
    Invoke-Id 'ConnectButton'
    Select-C24C
    Assert-SelectedC24C
    'released'
  }
  'log' { "event=[{0}]" -f (Read-Event) }
  'wait' {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $last = $Previous
    do {
      $last = Read-Event
      if ($last -and $last -ne $Previous -and $last -like '*Send text*') { break }
      if ((Get-Date) -ge $deadline) { break }
      Start-Sleep -Milliseconds 200
    } while ($true)
    "event=[$last]"
  }
}
