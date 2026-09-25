# Gate 1 prepare. Never deletes C:\iMouseXP. Never changes HidUsb or VID_720A drivers. Never reboots.
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$vendorRoot = 'C:\iMouseXP'
$audit = Join-Path $root 'analysis\independence-audit'
$backupPath = Join-Path $audit 'vendor-service-backup.json'
$runKeys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run',
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce',
    'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce',
    'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce'
)

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Get-StartDword([string]$name) {
    $key = "HKLM:\SYSTEM\CurrentControlSet\Services\$name"
    if (-not (Test-Path -LiteralPath $key)) { return $null }
    [int](Get-ItemProperty -LiteralPath $key).Start
}
function Test-VendorImage([string]$path) {
    if ([string]::IsNullOrWhiteSpace($path)) { return $false }
    $path.IndexOf('\iMouseXP\', [StringComparison]::OrdinalIgnoreCase) -ge 0
}
function Get-BackupCanon($doc) {
    $lines = New-Object System.Collections.Generic.List[string]
    [void]$lines.Add('schema=1')
    foreach ($s in @($doc.services | Sort-Object name)) {
        [void]$lines.Add(('service|{0}|{1}|{2}|{3}' -f $s.name, $s.start_dword, $s.status, $s.image_path))
    }
    foreach ($e in @($doc.startup_entries | Sort-Object key, name)) {
        [void]$lines.Add(('startup|{0}|{1}|{2}' -f $e.key, $e.name, $e.value))
    }
    $lines -join "`n"
}
function Get-BackupHash($doc) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = (New-Object Text.UTF8Encoding $false).GetBytes((Get-BackupCanon $doc))
        ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '')
    } finally { $sha.Dispose() }
}
function Get-VendorSnapshot {
    $services = @(Get-CimInstance Win32_Service | Where-Object {
        $_.Name -in @('iMouseService', 'IMService') -or (Test-VendorImage $_.PathName)
    } | ForEach-Object {
        $reg = Get-ItemProperty -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\$($_.Name)"
        $type = [int]$reg.Type
        $image = [string]$_.PathName
        $protected = ($_.Name -eq 'HidUsb') -or ($image -match '720A') -or ($type -lt 16) -or -not (Test-VendorImage $image)
        [pscustomobject]@{
            name = [string]$_.Name
            display_name = [string]$_.DisplayName
            image_path = $image
            status = [string]$_.State
            start_mode = [string]$_.StartMode
            start_dword = [int]$reg.Start
            start_name = [string]$_.StartName
            process_id = [int]$_.ProcessId
            service_type = $type
            protected = [bool]$protected
            disable = -not $protected
        }
    })
    $entries = @()
    foreach ($key in $runKeys) {
        if (-not (Test-Path -LiteralPath $key)) { continue }
        $item = Get-Item -LiteralPath $key
        foreach ($prop in $item.GetValueNames()) {
            $value = [string]$item.GetValue($prop)
            $kind = [string]$item.GetValueKind($prop)
            if ($value -notmatch '(?i)iMouseXP|IMService\.exe|AirplayMirroring|IMConsole\.exe') { continue }
            $entries += [pscustomobject]@{ key = $key; name = $prop; value = $value; kind = $kind }
        }
    }
    $hid = Get-StartDword 'HidUsb'
    $procs = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -in @('IMService.exe', 'AirplayMirroring.exe', 'IMConsole.exe', 'DisplayCore.exe') -or
        (Test-VendorImage ([string]$_.ExecutablePath))
    } | ForEach-Object {
        [pscustomobject]@{ name = [string]$_.Name; pid = [int]$_.ProcessId; path = [string]$_.ExecutablePath }
    })
    [pscustomobject]@{
        services = $services
        startup_entries = @($entries)
        processes_seen = $procs
        hidusb_start = $hid
    }
}
function Save-Backup($snap) {
    $doc = [ordered]@{
        schema = 1
        at = (Get-Date).ToString('o')
        host = $env:COMPUTERNAME
        check_only = [bool]$CheckOnly
        applied = $false
        vendor_root = $vendorRoot
        vendor_root_exists = (Test-Path -LiteralPath $vendorRoot)
        protected_vid = '720A'
        services = @($snap.services)
        startup_entries = @($snap.startup_entries)
        startup_keys_scanned = $runKeys
        processes_seen = @($snap.processes_seen)
        protected_skipped = @([pscustomobject]@{ name = 'HidUsb'; start_dword = $snap.hidusb_start; reason = 'WCH VID_720A board driver; never disable' })
        integrity = [ordered]@{ sha256 = '' }
    }
    $doc.integrity.sha256 = Get-BackupHash $doc
    New-Item -ItemType Directory -Force -Path $audit | Out-Null
    $doc | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $backupPath -Encoding utf8
    $doc
}
function Test-BackupFile {
    $raw = Get-Content -LiteralPath $backupPath -Raw
    $doc = $raw | ConvertFrom-Json
    if ($doc.schema -ne 1) { throw 'backup schema != 1' }
    if ([string]::IsNullOrWhiteSpace($doc.integrity.sha256)) { throw 'backup missing sha256' }
    $again = Get-BackupHash $doc
    if ($again -ne $doc.integrity.sha256) { throw "backup hash mismatch: $again != $($doc.integrity.sha256)" }
    foreach ($s in @($doc.services)) {
        foreach ($field in @('name', 'status', 'start_dword', 'image_path')) {
            if ($null -eq $s.$field -or [string]$s.$field -eq '') { throw "backup service missing $field" }
        }
        if ($s.name -eq 'HidUsb' -or $s.disable -and ($s.image_path -match '720A' -or $s.service_type -lt 16)) {
            throw "backup marks a protected driver for disable: $($s.name)"
        }
    }
    $tampered = Get-BackupHash ([pscustomobject]@{
        services = @($doc.services | ForEach-Object {
            [pscustomobject]@{ name = $_.name; start_dword = 9; status = $_.status; image_path = $_.image_path }
        })
        startup_entries = @($doc.startup_entries)
    })
    if ($tampered -eq $doc.integrity.sha256) { throw 'hash did not change when start_dword was tampered' }
    $doc
}

if (-not (Test-Path -LiteralPath $vendorRoot)) { throw "Refusing to continue; $vendorRoot is missing. Nothing was deleted." }
$beforeHid = Get-StartDword 'HidUsb'
$snap = Get-VendorSnapshot
$targets = @($snap.services | Where-Object { $_.disable })
if ($targets.Count -lt 1) { throw 'No vendor service under C:\iMouseXP was discovered. Nothing was changed.' }
$existing = $null
if (Test-Path -LiteralPath $backupPath) {
    try { $existing = Test-BackupFile } catch { $existing = $null }
}
$liveDisabled = @($targets | Where-Object { $_.start_dword -ne 4 }).Count -eq 0
$keepExisting = $existing -and $liveDisabled -and @($existing.services | Where-Object { $_.start_dword -ne 4 }).Count -gt 0
if ($keepExisting) {
    $doc = $existing
    Write-Host "Kept existing pre-disable backup: $backupPath"
} else {
    $doc = Save-Backup $snap
    $doc = Test-BackupFile
}
$cmds = @($doc.services | Where-Object { $_.disable } | ForEach-Object { "sc.exe config $($_.name) start= disabled" })
foreach ($e in @($doc.startup_entries)) {
    if ($e.kind -ne 'String' -and $e.kind -ne 'ExpandString') { throw "Unsupported startup value type $($e.kind). Not modified." }
    $cmds += "Remove-ItemProperty -LiteralPath '$($e.key)' -Name '$($e.name)'"
}

$parseFailed = @()
foreach ($file in @('restore_vendor_services.ps1', 'post_reboot_test.ps1', 'prepare_cold_boot.ps1')) {
    $tokens = $null; $errs = $null
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $file), [ref]$tokens, [ref]$errs)
    if ($errs -and $errs.Count) { $parseFailed += "$file : $errs" }
}
if ($parseFailed.Count) { throw ($parseFailed -join '; ') }

$restore = Join-Path $PSScriptRoot 'restore_vendor_services.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restore -CheckOnly
if ($LASTEXITCODE -ne 0) { throw "restore -CheckOnly failed: $LASTEXITCODE" }

if (-not $CheckOnly) {
    if (-not (Test-Admin)) {
        Write-Host 'Not elevated. Nothing was changed. Run:'
        Write-Host "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"'"
        $cmds | ForEach-Object { Write-Host $_ }
        exit 2
    }
    foreach ($s in @($doc.services | Where-Object { $_.disable })) {
        if ($s.name -eq 'HidUsb' -or -not (Test-VendorImage $s.image_path) -or $s.service_type -lt 16) {
            throw "Refusing to disable $($s.name)"
        }
        # sc.exe wants start= as its own argv token. Do not Stop-Service; reboot is the cutover.
        & sc.exe @('config', [string]$s.name, 'start=', 'disabled') | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "sc.exe config $($s.name) failed: $LASTEXITCODE" }
        if ((Get-StartDword $s.name) -ne 4) { throw "$($s.name) Start dword is not 4 after disable" }
    }
    foreach ($e in @($doc.startup_entries)) {
        Remove-ItemProperty -LiteralPath $e.key -Name $e.name
    }
    $saved = Get-Content -LiteralPath $backupPath -Raw | ConvertFrom-Json
    $saved.applied = $true
    $saved.applied_at = (Get-Date).ToString('o')
    $saved | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $backupPath -Encoding utf8
    if ((Get-BackupHash $saved) -ne $saved.integrity.sha256) { throw 'apply rewrote backup canon; restore the file from git and do not reboot' }
}

$afterHid = Get-StartDword 'HidUsb'
if ($afterHid -ne $beforeHid) { throw "HidUsb Start changed from $beforeHid to $afterHid" }
if ($CheckOnly) {
    foreach ($s in $targets) {
        if ((Get-StartDword $s.name) -ne $s.start_dword) { throw "CheckOnly changed $($s.name) startup" }
    }
}

Write-Host @'

Gate 1 cold boot - this script does not reboot and does not stop processes.
1. When ready: powershell -File tools\prepare_cold_boot.ps1
   Disables iMouseService startup only. Does not delete C:\iMouseXP. Does not touch HidUsb / VID 720A.
2. Reboot Windows yourself. Do not start the vendor console, IMService, or AirplayMirroring.
3. powershell -File tools\post_reboot_test.ps1
   Recast C24C to iMouse2-C24C and C241 to iMouse2-C241 if asked.
4. Restore anytime: powershell -File tools\restore_vendor_services.ps1
'@
$cmds | ForEach-Object { Write-Host "command: $_" }
[pscustomobject]@{
    Result = 'pass'
    CheckOnly = [bool]$CheckOnly
    ServicesAltered = -not [bool]$CheckOnly
    Backup = $backupPath
    Service = (($targets | ForEach-Object { '{0} {1} {2} start={3}' -f $_.name, $_.status, $_.start_mode, $_.start_dword }) -join '; ')
    StartupEntries = @($doc.startup_entries).Count
    RestoreCheck = 'pass'
    Syntax = 'pass'
    HidUsbStart = $afterHid
    VendorRootExists = (Test-Path -LiteralPath $vendorRoot)
}
