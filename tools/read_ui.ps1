param([string]$Action = 'read', [string]$Select = '')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$p = @(Get-Process iMouse2 | Where-Object { $_.Path -like '*two-phone-candidate*' })
if ($p.Count -ne 1) { throw "expected 1 candidate console, got $($p.Count)" }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
function FindId($id) {
    $c = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
    $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
}
function FindName($name) {
    $c = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::NameProperty, $name)
    $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
}
if ($Action -eq 'activity') {
    $btn = FindId 'ActivityButton'
    if ($null -eq $btn) { throw 'no ActivityButton' }
    $btn.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    Start-Sleep -Milliseconds 400
}
if ($Select.Length -gt 0) {
    $list = FindId 'DeviceList'
    if ($null -eq $list) { throw 'no DeviceList' }
    $name = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::NameProperty, $Select)
    $el = $list.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $name)
    if ($null -eq $el) { throw "no list name $Select" }
    $item = $el
    while ($item -ne $null -and $item.Current.ControlType.ProgrammaticName -ne 'ControlType.ListItem') {
        $item = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($item)
    }
    if ($null -eq $item) { $item = $el }
    $sel = $item.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
    $sel.Select()
    Start-Sleep -Milliseconds 500
}
$fs = FindId 'FrameStatus'
$st = FindId 'StatusInfo'
$ti = FindId 'SelectedTitle'
@{
    console_id = $p.Id
    hwnd = $p.MainWindowHandle.ToInt64()
    selected = if ($ti) { $ti.Current.Name } else { '' }
    frame = if ($fs) { $fs.Current.Name } else { '' }
    status = if ($st) { $st.Current.Name } else { '' }
    frame_offscreen = if ($fs) { [bool]$fs.Current.IsOffscreen } else { $true }
} | ConvertTo-Json -Compress
