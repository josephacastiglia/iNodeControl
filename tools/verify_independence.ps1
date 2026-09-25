$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$vendorRoot = 'C:\iMouseXP'
$reportDir = Join-Path $root 'analysis\independence-audit'
$reportPath = Join-Path $reportDir 'report.json'
$needles = @(
    'C:\iMouseXP', 'IMService.exe', 'IMConsole.exe', 'AirplayMirroring.exe',
    'AirplayMirroring.dll', 'DisplayCore.exe', 'iMouseKeyboard.dll', 'MouseKeyItem.dll'
)
$ours = @(
    (Join-Path $root 'release\iMouse2-two-phone-candidate\iMouse2.exe'),
    (Join-Path $root 'release\iMouse2-two-phone-candidate\iMouse2.dll'),
    (Join-Path $root 'release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe'),
    (Join-Path $root 'release\iMouse2-kernel-two-phone\iMouse2.Kernel.dll'),
    (Join-Path $root 'tools\airplay\uxplay\build-imouse\uxplay.exe')
)

function Test-VendorPath([string]$path) {
    if ([string]::IsNullOrWhiteSpace($path)) { return $false }
    try { $path = [IO.Path]::GetFullPath($path) } catch { return $false }
    $path.StartsWith($vendorRoot, [StringComparison]::OrdinalIgnoreCase)
}

$procs = @(Get-CimInstance Win32_Process | ForEach-Object {
    $path = [string]$_.ExecutablePath
    $name = [string]$_.Name
    $vendor = ($name -in @('IMService.exe', 'AirplayMirroring.exe')) -or (Test-VendorPath $path)
    if (-not $vendor) { return }
    [pscustomobject]@{
        name = $name
        pid = [int]$_.ProcessId
        path = $path
        reason = $(if ($name -eq 'IMService.exe') { 'named-vendor' } elseif ($name -eq 'AirplayMirroring.exe') { 'named-vendor' } else { 'vendor-directory' })
    }
})

$ports = @(9911, 17000 | ForEach-Object {
    $port = $_
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    $owners = @($listeners | Where-Object OwningProcess | ForEach-Object {
        $owning = [int]$_.OwningProcess
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $owning" -ErrorAction SilentlyContinue
        $path = if ($proc) { [string]$proc.ExecutablePath } else { '' }
        $name = if ($proc) { [string]$proc.Name } else { '' }
        [pscustomobject]@{
            pid = $owning
            name = $name
            path = $path
            vendor = ($name -in @('IMService.exe', 'AirplayMirroring.exe', 'IMConsole.exe')) -or (Test-VendorPath $path)
        }
    } | Sort-Object pid -Unique)
    [pscustomobject]@{ port = $port; listening = [bool]$listeners.Count; owners = @($owners) }
})

$links = @($ours | ForEach-Object {
    $path = $_
    $present = Test-Path -LiteralPath $path
    $hits = @()
    if ($present) {
        $bytes = [IO.File]::ReadAllBytes($path)
        $ascii = [Text.Encoding]::ASCII.GetString($bytes)
        $utf16 = [Text.Encoding]::Unicode.GetString($bytes)
        foreach ($needle in $needles) {
            if ($ascii.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
                $utf16.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $hits += $needle
            }
        }
    }
    [pscustomobject]@{
        path = $path
        present = $present
        vendor_string_hits = $hits
    }
})

$report = [ordered]@{
    at = (Get-Date).ToString('o')
    gate = 1
    product = "iMouse 2.0 $([char]0x2014) Independent AirPlay"
    vendor_root = $vendorRoot
    vendor_root_exists = (Test-Path -LiteralPath $vendorRoot)
    vendor_processes = $procs
    vendor_process_count = $procs.Count
    ports = $ports
    runtime_links = $links
    zero_vendor_string_links = -not @($links | Where-Object { $_.vendor_string_hits.Count }).Count
    cold_boot_not_executed = $true
    cold_boot_procedure = @(
        'Disable IMService startup (services.msc or the vendor startup entry). Do not delete C:\iMouseXP.',
        'Reboot Windows. Do not start the vendor console, IMService, or AirplayMirroring.',
        'Launch the desktop shortcut iMouse 2.0 - Independent AirPlay (Open iMouse 2.0.ps1).',
        'Confirm IMService.exe, AirplayMirroring.exe, and every process under C:\iMouseXP\ are absent.',
        'Confirm 9911 and 17000 are not owned by a vendor process.',
        'Recast C24C to iMouse2-C24C and C241 to iMouse2-C241 if mirroring is down.',
        'Run one real input check and one video check per phone. A missing vendor window is not proof.',
        'Re-run tools/verify_independence.ps1 and keep this report with the live result.'
    )
    note = 'Tooling audit only. Vendor processes may still be running. This does not close Gate 1.'
}

New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding utf8
[pscustomobject]@{
    Result = 'pass'
    Report = $reportPath
    VendorProcesses = $procs.Count
    ZeroVendorStringLinks = $report.zero_vendor_string_links
}
