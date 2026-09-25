# Restores vendor startup from analysis/independence-audit/vendor-service-backup.json.
# Never deletes C:\iMouseXP. Never changes HidUsb or VID_720A drivers. Never reboots.
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backupPath = Join-Path $root 'analysis\independence-audit\vendor-service-backup.json'

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
function Get-ScArg([int]$dword, $delayed) {
    if ($dword -eq 2 -and $delayed) { return 'delayed-auto' }
    switch ($dword) {
        2 { 'auto' }
        3 { 'demand' }
        4 { 'disabled' }
        default { throw "unsupported start dword $dword" }
    }
}
function Get-StartDword([string]$name) {
    [int](Get-ItemProperty -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\$name").Start
}

if (-not (Test-Path -LiteralPath $backupPath)) { throw "Missing backup: $backupPath" }
$doc = Get-Content -LiteralPath $backupPath -Raw | ConvertFrom-Json
if ($doc.schema -ne 1) { throw 'backup schema != 1' }
$hash = Get-BackupHash $doc
if ($hash -ne $doc.integrity.sha256) { throw "backup hash mismatch: $hash != $($doc.integrity.sha256)" }
if ($doc.vendor_root -and -not (Test-Path -LiteralPath $doc.vendor_root)) {
    throw "Refusing to restore; $($doc.vendor_root) is missing. Nothing was deleted by this script."
}

$actions = @()
foreach ($s in @($doc.services)) {
    if ($s.name -eq 'HidUsb' -or [string]$s.image_path -match '720A' -or $s.service_type -lt 16) {
        throw "Refusing to touch protected driver $($s.name)"
    }
    if (-not (Test-Path -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\$($s.name)")) {
        throw "Service $($s.name) is gone. Not recreating it."
    }
    $arg = Get-ScArg ([int]$s.start_dword) $s.delayed_auto
    $actions += [pscustomobject]@{ kind = 'start-type'; name = [string]$s.name; arg = $arg; dword = [int]$s.start_dword }
    if ([string]$s.status -eq 'Running') {
        $actions += [pscustomobject]@{ kind = 'start'; name = [string]$s.name }
    }
}
foreach ($e in @($doc.startup_entries)) {
    if ($e.kind -and $e.kind -ne 'String' -and $e.kind -ne 'ExpandString') {
        throw "Unsupported startup value type $($e.kind). Not modified."
    }
    $actions += [pscustomobject]@{ kind = 'startup'; key = [string]$e.key; name = [string]$e.name; value = [string]$e.value; kindName = $(if ($e.kind) { [string]$e.kind } else { 'String' }) }
}
if (@($actions | Where-Object { $_.name -eq 'HidUsb' -or $_.key -match '720A' }).Count) { throw 'restore plan touched a protected driver' }

$actions | ForEach-Object {
    if ($_.kind -eq 'start-type') { Write-Host ("sc.exe config {0} start= {1}" -f $_.name, $_.arg) }
    elseif ($_.kind -eq 'start') { Write-Host "Start-Service $($_.name)" }
    else { Write-Host "restore startup $($_.key) :: $($_.name)" }
}
if ($CheckOnly) {
    [pscustomobject]@{ Result = 'pass'; Actions = $actions.Count; Applied = $false; Backup = $backupPath }
    return
}

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Restore must be elevated. Nothing was changed.' }

foreach ($a in $actions) {
    if ($a.kind -eq 'start-type') {
        & sc.exe @('config', $a.name, 'start=', $a.arg) | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "sc.exe config $($a.name) failed: $LASTEXITCODE" }
        $now = Get-StartDword $a.name
        if ($now -ne $a.dword -and -not ($a.arg -eq 'delayed-auto' -and $now -eq 2)) {
            throw "$($a.name) Start is $now, expected $($a.dword)"
        }
    } elseif ($a.kind -eq 'startup') {
        if (-not (Test-Path -LiteralPath $a.key)) { throw "Missing startup key $($a.key)" }
        New-ItemProperty -LiteralPath $a.key -Name $a.name -Value $a.value -PropertyType $a.kindName -Force | Out-Null
        $got = [string](Get-Item -LiteralPath $a.key).GetValue($a.name)
        if ($got -ne $a.value) { throw "startup value mismatch for $($a.name)" }
    }
}
foreach ($a in @($actions | Where-Object kind -eq 'start')) {
    Start-Service -Name $a.name
    $running = $false
    for ($i = 0; $i -lt 10; $i++) {
        if ((Get-Service -Name $a.name).Status -eq 'Running') { $running = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $running) { throw "$($a.name) did not return to Running" }
}
[pscustomobject]@{ Result = 'pass'; Actions = $actions.Count; Applied = $true; Backup = $backupPath }
