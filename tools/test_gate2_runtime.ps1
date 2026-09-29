$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $root 'Open iMouse 2.0.ps1'
$consoleExe = Join-Path $root 'release\iMouse2-two-phone-candidate\iMouse2.exe'
$kernelExe = Join-Path $root 'release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe'
$evidenceDir = Join-Path $root 'analysis\gate2-single-app'
$evidencePath = Join-Path $evidenceDir 'gate2-evidence.json'
$settingsPath = Join-Path $env:APPDATA 'iMouse2\settings.json'
$expectedTitle = "iMouse 2.0 $([char]0x2014) Independent AirPlay"
$expectedBadge = "v2.0-rc1 $([char]0x00B7) Independent AirPlay"
$protected = [System.Collections.Generic.HashSet[int]]::new()
$failed = [System.Collections.Generic.List[string]]::new()

function Add-Fail([string]$msg) { $script:failed.Add($msg) }
function Protect([int]$procId) { if ($procId -gt 0) { [void]$script:protected.Add($procId) } }
function Stop-Owned([int]$procId) {
    if ($procId -le 0 -or $script:protected.Contains($procId)) { return }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue
    $name = if ($proc) { [string]$proc.Name } else { '' }
    if ($name -match '^(iMouse2\.exe|iMouse2\.Kernel\.exe)$') { return }
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}

function Get-AppState {
    $listeners = @(Get-NetTCPConnection -LocalPort 9913 -State Listen -ErrorAction SilentlyContinue)
    $owners = @($listeners | Where-Object { $_.OwningProcess } | ForEach-Object { [int]$_.OwningProcess } | Select-Object -Unique)
    $kernels = @(Get-CimInstance Win32_Process -Filter "Name = 'iMouse2.Kernel.exe'" -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.ExecutablePath -ieq $kernelExe })
    $consoles = @(Get-CimInstance Win32_Process -Filter "Name = 'iMouse2.exe'" -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.ExecutablePath -ieq $consoleExe })
    $consolePid = 0
    $title = ''
    if ($consoles.Count) {
        $consolePid = [int]$consoles[0].ProcessId
        $window = Get-Process -Id $consolePid -ErrorAction SilentlyContinue
        if ($window) { $title = [string]$window.MainWindowTitle }
    }
    [pscustomobject]@{
        PortOwners = @($owners)
        KernelPid = $(if ($kernels.Count) { [int]$kernels[0].ProcessId } else { 0 })
        KernelCount = $kernels.Count
        ConsolePid = $consolePid
        ConsoleCount = $consoles.Count
        Title = $title
    }
}

function Invoke-Script([string]$script, [int]$timeoutSec) {
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
    $proc = Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList $arg -PassThru -WindowStyle Hidden
    $null = $proc.Handle
    $exited = $proc.WaitForExit($timeoutSec * 1000)
    if (-not $exited) { Stop-Owned $proc.Id }
    [pscustomobject]@{ Pid = $proc.Id; TimedOut = (-not $exited); ExitCode = $(if ($exited) { $proc.ExitCode } else { $null }) }
}

function Read-ErrorFile([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return '' }
    for ($i = 0; $i -lt 10; $i++) {
        $text = Get-Content -LiteralPath $path -Raw -ErrorAction SilentlyContinue
        if (-not [string]::IsNullOrWhiteSpace($text)) { return $text.Trim() }
        Start-Sleep -Milliseconds 100
    }
    return ''
}

function New-StubTree([string]$dir, [string]$address) {
    foreach ($rel in @(
        'release\iMouse2-two-phone-candidate\iMouse2.exe',
        'release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe',
        'tools\airplay\uxplay\build-imouse\uxplay.exe',
        'analysis\two-phone-config\receivers.json',
        'analysis\two-phone-config\pointer-calibration.json')) {
        $path = Join-Path $dir $rel
        New-Item -ItemType Directory -Path (Split-Path $path) -Force | Out-Null
        Set-Content -LiteralPath $path -Value 'stub' -Encoding ascii
    }
    New-Item -ItemType Directory -Path (Join-Path $dir 'tools\airplay\msys64\ucrt64') -Force | Out-Null
    $data = Join-Path $dir 'release\iMouse2-two-phone-candidate\data'
    New-Item -ItemType Directory -Path $data -Force | Out-Null
    @{ address = $address } | ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $data 'settings.json') -Encoding ascii
}

function Invoke-Isolated([string]$name, [string]$address) {
    $dir = Join-Path $env:TEMP ("imouse2-gate2-" + $name + "-" + [guid]::NewGuid().ToString('n'))
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    $script = Join-Path $dir 'Open iMouse 2.0.ps1'
    Copy-Item -LiteralPath $launcher -Destination $script -Force
    if ($address) { New-StubTree $dir $address }
    $errPath = Join-Path $dir 'launch-error.txt'
    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
    $proc = Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList $arg -PassThru -WindowStyle Hidden
    $null = $proc.Handle
    $deadline = (Get-Date).AddSeconds(25)
    while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $errPath) -and -not $proc.HasExited) {
        Start-Sleep -Milliseconds 200
    }
    $text = Read-ErrorFile $errPath
    if (-not $proc.HasExited) { Stop-Owned $proc.Id }
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
    [pscustomobject]@{ Name = $name; Error = $text; Wrote = (-not [string]::IsNullOrWhiteSpace($text)) }
}

function Get-Badge([int]$consolePid) {
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    $proc = Get-Process -Id $consolePid
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
    $walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
    $pending = New-Object System.Collections.Generic.Queue[object]
    $pending.Enqueue($root)
    $badge = ''
    $seen = 0
    while ($pending.Count -gt 0 -and $seen -lt 4000 -and -not $badge) {
        $el = $pending.Dequeue()
        $seen++
        try { if ($el.Current.AutomationId -eq 'BuildIdentity') { $badge = [string]$el.Current.Name } } catch {}
        $child = $walker.GetFirstChild($el)
        while ($null -ne $child) {
            $pending.Enqueue($child)
            $child = $walker.GetNextSibling($child)
        }
    }
    [pscustomobject]@{ Title = [string]$root.Current.Name; Badge = $badge }
}

New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
$initial = Get-AppState
Protect $initial.KernelPid
Protect $initial.ConsolePid
if ($initial.KernelPid -le 0) { Add-Fail 'kernel on the release path is not running' }
if ($initial.PortOwners -notcontains 4 -and $initial.PortOwners -notcontains $initial.KernelPid) { Add-Fail "port 9913 owners $($initial.PortOwners -join ',')" }
if ($initial.ConsoleCount -ne 1) { Add-Fail "initial iMouse2.exe count $($initial.ConsoleCount)" }

$launches = @()
$passA = $false
if ($failed.Count -eq 0) {
    $passA = $true
    foreach ($n in 1, 2) {
        $before = Get-AppState
        $run = Invoke-Script $launcher 25
        Start-Sleep -Milliseconds 400
        $after = Get-AppState
        $ok = (-not $run.TimedOut) -and $run.ExitCode -eq 0 -and $after.KernelPid -eq $before.KernelPid -and $after.ConsolePid -eq $before.ConsolePid -and $after.ConsoleCount -eq 1 -and $after.KernelCount -eq 1
        if (-not $ok) {
            $passA = $false
            $err = Read-ErrorFile (Join-Path $root 'launch-error.txt')
            Add-Fail "relaunch $n timed_out=$($run.TimedOut) exit=$($run.ExitCode) kernel $($before.KernelPid)->$($after.KernelPid) console $($before.ConsolePid)->$($after.ConsolePid) count=$($after.ConsoleCount) $err"
        }
        $launches += [pscustomobject]@{ n = $n; exit_code = $run.ExitCode; timed_out = [bool]$run.TimedOut; kernel_pid = $after.KernelPid; console_pid = $after.ConsolePid; console_count = $after.ConsoleCount }
    }
}

$brand = $null
$diag = $null
$passB = $false
if ($failed.Count -eq 0) {
    $brand = Get-Badge $initial.ConsolePid
    if ($brand.Title -ne $expectedTitle) { Add-Fail "window title '$($brand.Title)'" }
    if ($brand.Badge -ne $expectedBadge) { Add-Fail "badge '$($brand.Badge)'" }
    $py = @(Get-Command py, python -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    $diagDir = Join-Path $evidenceDir 'diagnostics'
    if (-not $py) { Add-Fail 'python not found for diagnostics export' }
    else {
        $pyArgs = @()
        if ((Split-Path $py -Leaf) -eq 'py.exe') { $pyArgs += '-3' }
        $pyArgs += @((Join-Path $root 'tools\export_diagnostics.py'), '--out', $diagDir)
        $export = & $py @pyArgs 2>&1 | Out-String
        $diagPath = @($export.Trim() -split "`r?`n" | Where-Object { $_ -like '*.json' } | Select-Object -Last 1)
        if (-not $diagPath -or -not (Test-Path -LiteralPath $diagPath)) { Add-Fail "diagnostics export missing: $export" }
        else {
            $doc = Get-Content -LiteralPath $diagPath -Raw | ConvertFrom-Json
            $bin = @($doc.binaries | Where-Object { $_.name -eq 'iMouse2.exe' } | Select-Object -First 1)
            $hash = (Get-FileHash -LiteralPath $consoleExe -Algorithm SHA256).Hash
            if ([string]$doc.console.window_title -ne $expectedTitle) { Add-Fail "diagnostics title '$($doc.console.window_title)'" }
            if (-not $bin -or [string]::IsNullOrWhiteSpace([string]$bin.sha256)) { Add-Fail 'diagnostics export has no iMouse2.exe sha256' }
            elseif ([string]$bin.sha256 -ine $hash) { Add-Fail 'diagnostics sha256 does not match the running console' }
            $diag = [pscustomobject]@{ path = [string]$diagPath; window_title = [string]$doc.console.window_title; build_sha256 = [string]$bin.sha256; console_pid = $doc.console.pid }
        }
    }
    $passB = ($failed.Count -eq 0)
}

$settings = $null
$passC = $false
if ($passA -and $passB) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $settingsOut = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools\test_persistent_settings.ps1') 2>&1 | Out-String
    $settingsCode = $LASTEXITCODE
    $ErrorActionPreference = $prev
    $persisted = Test-Path -LiteralPath $settingsPath
    if ($settingsCode -ne 0 -or -not $persisted -or $settingsOut -notmatch 'Result\s*[:=]?\s*pass' -and $settingsOut -notmatch '\bpass\b') { Add-Fail "persistent settings exit=$settingsCode path=$persisted $settingsOut" }
    else {
        $json = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
        $settings = [pscustomobject]@{ path = $settingsPath; address = [string]$json.address; verifier = 'tools/test_persistent_settings.ps1' }
        $passC = $true
    }
}

$failures = @()
$passD = $false
if ($passA -and $passB -and $passC) {
    $missing = Invoke-Isolated 'missing' ''
    if ($missing.Error -notmatch 'Missing required file') { Add-Fail "missing-file error '$($missing.Error)'" }
    $wrong = Invoke-Isolated 'address' 'http://10.9.9.9:1'
    if ($wrong.Error -notmatch 'must use http://127\.0\.0\.1:9913') { Add-Fail "wrong-address error '$($wrong.Error)'" }
    $compete = Invoke-Isolated 'compete' 'http://127.0.0.1:9913'
    if ($compete.Error -notmatch 'occupied' -or $compete.Error -notmatch 'competing|unverified') { Add-Fail "competing-occupant error '$($compete.Error)'" }
    $afterFail = Get-AppState
    if ($afterFail.KernelPid -ne $initial.KernelPid) { Add-Fail "kernel pid changed during failure tests $($initial.KernelPid)->$($afterFail.KernelPid)" }
    $failures = @($missing, $wrong, $compete | ForEach-Object { [pscustomobject]@{ name = $_.Name; error = $_.Error; wrote_launch_error = $_.Wrote } })
    $passD = ($failed.Count -eq 0)
}

$final = Get-AppState
if ($final.KernelPid -ne $initial.KernelPid) { Add-Fail "kernel pid changed $($initial.KernelPid)->$($final.KernelPid)" }
if ($final.ConsolePid -ne $initial.ConsolePid -and $initial.ConsolePid -gt 0) { Add-Fail "console pid changed $($initial.ConsolePid)->$($final.ConsolePid)" }
$shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'iMouse 2.0 - Independent AirPlay.lnk'
$shortcutTarget = ''
if (Test-Path -LiteralPath $shortcut) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($shortcut)
    $shortcutTarget = [string]$lnk.Arguments
    if ($shortcutTarget -notmatch [regex]::Escape($launcher)) { Add-Fail "shortcut does not run $launcher" }
} else { Add-Fail 'desktop shortcut missing' }

$pass = $failed.Count -eq 0 -and $passA -and $passB -and $passC -and $passD
$report = [ordered]@{
    schema = 1
    at = (Get-Date).ToString('o')
    gate = 2
    model = 'Grok 4.7'
    pass = $pass
    kernel_not_stopped = ($final.KernelPid -eq $initial.KernelPid -and $final.KernelPid -gt 0)
    initial = [ordered]@{ port_owners = @($initial.PortOwners); kernel_pid = $initial.KernelPid; console_pid = $initial.ConsolePid; title = $initial.Title }
    shortcut = [ordered]@{ path = $shortcut; arguments = $shortcutTarget }
    single_instance = [ordered]@{ pass = $passA; launches = @($launches) }
    branding = [ordered]@{
        pass = $passB
        title = $(if ($brand) { $brand.Title } else { '' })
        badge = $(if ($brand) { $brand.Badge } else { '' })
        diagnostics = $diag
    }
    settings = $settings
    startup_failures = [ordered]@{ pass = $passD; cases = @($failures) }
    final = [ordered]@{ kernel_pid = $final.KernelPid; console_pid = $final.ConsolePid; console_count = $final.ConsoleCount }
    failures = @($failed)
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $evidencePath -Encoding utf8
if (-not $pass) { $failed | ForEach-Object { Write-Error $_ }; exit 1 }
[pscustomobject]@{ Result = 'pass'; Evidence = $evidencePath; KernelPid = $final.KernelPid; ConsolePid = $final.ConsolePid }
