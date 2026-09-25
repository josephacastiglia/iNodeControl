# Gate 1 evidence after a reboot. A missing vendor window is not a pass.
# Does not reboot, does not delete C:\iMouseXP, does not stop HidUsb / VID_720A.
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$vendorRoot = 'C:\iMouseXP'
$audit = Join-Path $root 'analysis\independence-audit'
$evidencePath = Join-Path $audit 'cold-boot-evidence.json'
$shotDir = Join-Path $audit 'cold-boot-shots'
$backupPath = Join-Path $audit 'vendor-service-backup.json'
$launcher = Join-Path $root 'Open iMouse 2.0.ps1'
$api = 'http://127.0.0.1:9913/api'
$named = @('IMService.exe', 'AirplayMirroring.exe', 'IMConsole.exe', 'DisplayCore.exe')

function Test-VendorPath([string]$path) {
    -not [string]::IsNullOrWhiteSpace($path) -and $path.StartsWith($vendorRoot, [StringComparison]::OrdinalIgnoreCase)
}
function Get-VendorProcesses {
    @(Get-CimInstance Win32_Process | ForEach-Object {
        $path = [string]$_.ExecutablePath
        $name = [string]$_.Name
        if (-not (($name -in $named) -or (Test-VendorPath $path))) { return }
        [pscustomobject]@{
            name = $name
            pid = [int]$_.ProcessId
            path = $path
            reason = $(if ($name -in $named) { 'named-vendor' } else { 'vendor-directory' })
        }
    })
}
function Get-PortState([int]$port) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    $owners = @($listeners | Where-Object OwningProcess | ForEach-Object {
        $owning = [int]$_.OwningProcess
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $owning" -ErrorAction SilentlyContinue
        [pscustomobject]@{
            pid = $owning
            name = $(if ($proc) { [string]$proc.Name } else { '' })
            path = $(if ($proc) { [string]$proc.ExecutablePath } else { '' })
        }
    } | Sort-Object pid -Unique)
    [pscustomobject]@{ port = $port; listening = [bool]$listeners.Count; owners = @($owners) }
}
function Get-Ours {
    @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(iMouse2|iMouse2\.Kernel|uxplay)(\.exe)?$' } | ForEach-Object {
        [pscustomobject]@{ name = [string]$_.Name; pid = [int]$_.ProcessId; path = [string]$_.ExecutablePath }
    })
}
function Read-BmpInfo([byte[]]$bytes) {
    if ($null -eq $bytes -or $bytes.Length -lt 26 -or $bytes[0] -ne 0x42 -or $bytes[1] -ne 0x4D) { return $null }
    $w = [BitConverter]::ToInt32($bytes, 18)
    $h = [BitConverter]::ToInt32($bytes, 22)
    if ($h -lt 0) { $h = -$h }
    if ($w -le 0 -or $h -le 0) { return $null }
    [pscustomobject]@{ bytes = $bytes.Length; width = $w; height = $h }
}
function Invoke-Kernel([string]$method, [string]$url, $body) {
    $params = @{ Method = $method; Uri = $url; TimeoutSec = 20 }
    if ($null -ne $body) {
        $params.Body = ($body | ConvertTo-Json -Compress -Depth 6)
        $params.ContentType = 'application/json'
    }
    Invoke-RestMethod @params
}

$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
$vendor = @(Get-VendorProcesses)
$ports = @(9911, 17000 | ForEach-Object { Get-PortState $_ })
$portsFree = -not @($ports | Where-Object listening).Count
if ($CheckOnly) {
    $fake = New-Object byte[] 26
    $fake[0] = 0x42; $fake[1] = 0x4D
    [BitConverter]::GetBytes([int]1080).CopyTo($fake, 18)
    [BitConverter]::GetBytes([int]1920).CopyTo($fake, 22)
    $info = Read-BmpInfo $fake
    if ($info.width -ne 1080 -or $info.height -ne 1920) { throw 'bmp parser failed' }
    if (Read-BmpInfo ([byte[]](0, 1, 2))) { throw 'bmp parser accepted garbage' }
    [pscustomobject]@{
        Result = 'check-only'
        Launched = $false
        VendorProcesses = $vendor.Count
        PortsFree = [bool]$portsFree
        Boot = $boot.ToString('o')
        Note = 'Not a Gate 1 result. Missing vendor window is not proof.'
    }
    return
}

$failures = New-Object System.Collections.Generic.List[string]
function Fail([string]$msg) { $script:failures.Add($msg); Write-Host "FAIL $msg" }
if (-not (Test-Path -LiteralPath $vendorRoot)) { Fail "$vendorRoot missing; this test does not delete it" }
if (-not (Test-Path -LiteralPath $backupPath)) { Fail 'vendor-service-backup.json missing; run prepare_cold_boot.ps1 first' }
$backupAt = $null
if (Test-Path -LiteralPath $backupPath) {
    $backupAt = [datetime](Get-Content -LiteralPath $backupPath -Raw | ConvertFrom-Json).at
    if ($boot -lt $backupAt) { Fail 'Windows has not rebooted since the vendor backup was written' }
}
$svcKey = 'HKLM:\SYSTEM\CurrentControlSet\Services\iMouseService'
if (-not (Test-Path -LiteralPath $svcKey)) { Fail 'iMouseService registry key missing; service must be disabled, not deleted' }
else {
    $start = [int](Get-ItemProperty -LiteralPath $svcKey).Start
    if ($start -ne 4) { Fail "iMouseService Start is $start, expected 4 (Disabled)" }
}
if ($vendor.Count) { Fail ("vendor processes still running: " + (($vendor | ForEach-Object { "$($_.name):$($_.pid)" }) -join ', ')) }
if (-not $portsFree) { Fail '9911 or 17000 is still listening' }
$hid = [int](Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Services\HidUsb').Start

$launch = $null
$kernel = $null
$boards = @()
$inputRows = @()
$videoRows = @()
if ($failures.Count -eq 0) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher
    $launch = [pscustomobject]@{ exit_code = $LASTEXITCODE; script = $launcher }
    if ($LASTEXITCODE -ne 0) { Fail "launcher exit $LASTEXITCODE" }
    $vendorAfter = @(Get-VendorProcesses)
    if ($vendorAfter.Count) { Fail 'vendor process appeared after launch' }
    $portsAfter = @(9911, 17000 | ForEach-Object { Get-PortState $_ })
    if (@($portsAfter | Where-Object listening).Count) { Fail 'vendor port opened after launch' }
    $ports = $portsAfter
    $vendor = $vendorAfter
    try {
        $kernel = Invoke-Kernel GET "$api/kernel/status" $null
        if ($kernel.status -ne 200 -or $kernel.data.code -ne 0) { Fail 'kernel status not ready' }
    } catch { Fail "kernel status: $($_.Exception.Message)" }
    try {
        $usb = Invoke-Kernel GET "$api/config/usb/get" $null
        $boards = @($usb.data.list)
        foreach ($need in @('C24C', 'C241')) {
            if (-not @($boards | Where-Object { $_.pid -eq $need }).Count) { Fail "board $need not discovered" }
        }
    } catch { Fail "board discovery: $($_.Exception.Message)" }
    $receivers = Get-Content -LiteralPath (Join-Path $root 'analysis\two-phone-config\receivers.json') -Raw | ConvertFrom-Json
    $deadline = (Get-Date).AddSeconds(20)
    do {
        try { $kernel = Invoke-Kernel GET "$api/kernel/status" $null } catch { break }
        $ids = @($receivers | ForEach-Object { $_.DeviceId })
        $ready = @($kernel.data.receivers | Where-Object { $_.deviceid -in $ids -and $_.receiver_state -ne 'failed' -and $_.receiver_pid -gt 0 })
        if ($ready.Count -eq $ids.Count) { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    $liveIds = @($kernel.data.receivers | Where-Object { $_.live } | ForEach-Object { $_.deviceid })
    if ($liveIds.Count -lt $receivers.Count) {
        Write-Host 'Video is offline. Recast C24C -> iMouse2-C24C and C241 -> iMouse2-C241, then press Enter.'
        if ([Environment]::UserInteractive) { Read-Host | Out-Null } else { Fail 'video offline and not interactive' }
        try { $kernel = Invoke-Kernel GET "$api/kernel/status" $null } catch { Fail "kernel status after recast: $($_.Exception.Message)" }
    }
    New-Item -ItemType Directory -Force -Path $shotDir | Out-Null
    foreach ($phone in $receivers) {
        $id = [string]$phone.DeviceId
        $row = [ordered]@{ id = $id; board = [string]$phone.BoardPid; acquire_code = $null; click_code = $null; home_code = $null; released = $false }
        $token = $null
        try {
            $acq = Invoke-Kernel POST "$api/" @{ fun = '/input/acquire'; data = @{ id = $id; lease_ms = 15000 } }
            $row.acquire_code = $acq.data.code
            $token = @($acq.data.leases)[0].token
            if ($acq.data.code -ne 0 -or [string]::IsNullOrWhiteSpace($token)) { Fail "$id input acquire code $($acq.data.code) $($acq.data.message)" }
            else {
                $click = Invoke-Kernel POST "$api/" @{ fun = '/mouse/click'; data = @{ id = $id; x = 250; y = 900; button = 1; token = $token } }
                $row.click_code = $click.data.code
                if ($click.data.code -ne 0) { Fail "$id click code $($click.data.code) $($click.data.message)" }
                $sent = Invoke-Kernel POST "$api/" @{ fun = '/key/sendkey'; data = @{ id = $id; fn_key = 'Home'; token = $token } }
                $row.home_code = $sent.data.code
                if ($sent.data.code -ne 0) { Fail "$id home code $($sent.data.code) $($sent.data.message)" }
            }
        } catch { Fail "$id input: $($_.Exception.Message)" }
        finally {
            if ($token) {
                try {
                    Invoke-Kernel POST "$api/" @{ fun = '/input/release'; data = @{ id = $id; token = $token } } | Out-Null
                    $row.released = $true
                } catch { Fail "$id release: $($_.Exception.Message)" }
            }
        }
        $inputRows += [pscustomobject]$row
        $rec = @($kernel.data.receivers | Where-Object { $_.deviceid -eq $id }) | Select-Object -First 1
        $shotPath = Join-Path $shotDir ($phone.BoardPid + '.bmp')
        $bmp = $null
        if ($rec -and $rec.live) {
            try {
                $bytes = (New-Object Net.WebClient).DownloadData("$api/pic/screenshot?id=$([uri]::EscapeDataString($id))&binary=true")
                [IO.File]::WriteAllBytes($shotPath, $bytes)
                $bmp = Read-BmpInfo $bytes
            } catch { Fail "$id screenshot: $($_.Exception.Message)" }
        }
        if (-not $rec -or -not $rec.live -or -not $bmp) { Fail "$id video not live or not a BMP frame" }
        $videoRows += [pscustomobject]@{
            id = $id
            live = [bool]($rec -and $rec.live)
            receiver_state = $(if ($rec) { [string]$rec.receiver_state } else { '' })
            receiver_pid = $(if ($rec) { [int]$rec.receiver_pid } else { 0 })
            frames = $(if ($rec) { $rec.frames } else { $null })
            bmp = [bool]$bmp
            width = $(if ($bmp) { $bmp.width } else { 0 })
            height = $(if ($bmp) { $bmp.height } else { 0 })
            bytes = $(if ($bmp) { $bmp.bytes } else { 0 })
            path = $(if ($bmp) { $shotPath } else { '' })
        }
    }
}

$evidence = [ordered]@{
    schema = 1
    at = (Get-Date).ToString('o')
    gate = 1
    boot_time = $boot.ToString('o')
    backup_at = $(if ($backupAt) { $backupAt.ToString('o') } else { $null })
    missing_vendor_window_is_not_proof = $true
    vendor_root_exists = (Test-Path -LiteralPath $vendorRoot)
    hidusb_start = $hid
    vendor_processes = @($vendor)
    vendor_process_count = @($vendor).Count
    ports = @($ports)
    ports_free = -not [bool]@($ports | Where-Object listening).Count
    launch = $launch
    kernel = $kernel
    boards = @($boards | ForEach-Object { [pscustomobject]@{ vid = $_.vid; pid = $_.pid; state = $_.state } })
    process_identities = [pscustomobject]@{ vendor = @($vendor); ours = @(Get-Ours) }
    input = @($inputRows)
    video = @($videoRows)
    failures = @($failures)
    pass = ($failures.Count -eq 0)
    note = 'Pass requires absent vendor processes, free 9911/17000, disabled iMouseService, kernel on 9913, boards C24C and C241, input code 0, and a real BMP. A missing vendor window is not proof.'
}
New-Item -ItemType Directory -Force -Path $audit | Out-Null
$evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $evidencePath -Encoding utf8
Write-Host "evidence: $evidencePath pass=$($evidence.pass)"
if (-not $evidence.pass) { exit 1 }
[pscustomobject]@{ Result = 'pass'; Evidence = $evidencePath }
