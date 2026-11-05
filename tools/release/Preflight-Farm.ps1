# Marketing Farm preflight. READ-ONLY: it inspects this PC and prints what the operator must do.
# It never installs, starts, stops, enables or configures anything (no services, drivers, firewall
# rules, registry, PATH or execution policy). Steps that need an administrator are marked (admin).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File Preflight-Farm.ps1 [-InstallRoot DIR] [-DataRoot DIR] [-Python EXE] [-Package DIR] [-Json]
#   exit 0 = no failed check, 1 = at least one failed check
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\iMouseFarm'),
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'iMouseFarm'),
    [string]$Python = '',
    [string]$Package = '',
    [switch]$Json
)
$ErrorActionPreference = 'Stop'
$script:checks = New-Object System.Collections.Generic.List[object]
function Add-Check([string]$Id, [string]$Status, [string]$Detail, [string]$Step = '') {
    $script:checks.Add([pscustomobject][ordered]@{ id = $Id; status = $Status; detail = $Detail; step = $Step })
}
function Read-JsonFile([string]$Path) { [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json }
function Invoke-Probe([scriptblock]$Block, [string]$Id) {
    try { & $Block } catch { Add-Check $Id 'warn' ("could not check: " + $_.Exception.Message) 'Run the preflight again; if it repeats, check this item by hand.' }
}

# Receiver and media ports (kernel prep: receivers at 7110 + 10*n, each using port..port+2, TCP and UDP;
# window media servers bind the PC's LAN address).
$ReceiverLow = 7100; $ReceiverHigh = 7599
$MediaPorts = @(9917, 9927, 9937, 9947)
$Pins = [ordered]@{ 'Pillow' = '9.5.0'; 'numpy' = '2.3.1'; 'opencv-python-headless' = '5.0.0.93' }
if (!$Package) { $Package = Split-Path -Parent $PSScriptRoot }
$releaseFile = Join-Path $Package 'release.json'
if (Test-Path -LiteralPath $releaseFile) {
    $release = Read-JsonFile $releaseFile
    if ($release.components.farm.pins) { $Pins = [ordered]@{}; $release.components.farm.pins.PSObject.Properties | ForEach-Object { $Pins[$_.Name] = [string]$_.Value } }
}

# 1. Windows
Invoke-Probe {
    $os = Get-CimInstance Win32_OperatingSystem
    $build = [int]$os.BuildNumber
    if ([Environment]::Is64BitOperatingSystem -and $build -ge 19041) { Add-Check 'windows' 'ok' "$($os.Caption) build $build, 64-bit" }
    else { Add-Check 'windows' 'fail' "$($os.Caption) build $build" 'Use Windows 10 (2004 or later) or Windows 11, 64-bit.' }
} 'windows'
if ($PSVersionTable.PSVersion.Major -ne 5) { Add-Check 'powershell' 'warn' "PowerShell $($PSVersionTable.PSVersion); the farm scripts are tested on Windows PowerShell 5.1" 'Run the farm from Windows PowerShell 5.1 (powershell.exe).' }
else { Add-Check 'powershell' 'ok' "Windows PowerShell $($PSVersionTable.PSVersion)" }
Invoke-Probe {
    $policy = Get-ExecutionPolicy
    if ($policy -in 'Restricted', 'AllSigned') { Add-Check 'execution-policy' 'warn' "effective policy $policy" 'Start farm scripts with: powershell -NoProfile -ExecutionPolicy Bypass -File <script> (affects that process only).' }
    else { Add-Check 'execution-policy' 'ok' "effective policy $policy" }
} 'execution-policy'

# 2. .NET 8 runtimes (kernel: Microsoft.NETCore.App 8; console: also Microsoft.WindowsDesktop.App 8)
Invoke-Probe {
    $dotnet = @((Join-Path $env:ProgramFiles 'dotnet\dotnet.exe'), (Get-Command dotnet.exe -ErrorAction SilentlyContinue).Source) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    $runtimes = if ($dotnet) { @(& $dotnet --list-runtimes 2>$null) } else { @() }
    $core = @($runtimes | Where-Object { $_ -match '^Microsoft\.NETCore\.App 8\.' })
    $desk = @($runtimes | Where-Object { $_ -match '^Microsoft\.WindowsDesktop\.App 8\.' })
    if ($core.Count -and $desk.Count) { Add-Check 'dotnet' 'ok' ("{0}; {1}" -f ($core[-1] -replace ' \[.*$', ''), ($desk[-1] -replace ' \[.*$', '')) }
    else { Add-Check 'dotnet' 'fail' ("NETCore.App 8: {0}; WindowsDesktop.App 8: {1}" -f [bool]$core.Count, [bool]$desk.Count) '(admin) Install the .NET 8 Desktop Runtime x64 (windowsdesktop-runtime-8.0.x-win-x64.exe from https://dotnet.microsoft.com/download/dotnet/8.0); it includes the .NET 8 runtime.' }
} 'dotnet'

# 3. Python 3.11 x64 and the pinned packages
$py = $null
Invoke-Probe {
    $installFile = Join-Path $InstallRoot 'install.json'
    $fromInstall = if (Test-Path -LiteralPath $installFile) { (Read-JsonFile $installFile).python } else { $null }
    $launcher = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    $fromPy = if ($launcher) { (& $launcher -3.11 -c "import sys; print(sys.executable)" 2>$null) } else { $null }
    $candidates = @($Python, $fromInstall, $fromPy, (Get-Command python.exe -ErrorAction SilentlyContinue).Source)
    $script:py = $candidates | Where-Object { $_ -and $_ -notlike '*\WindowsApps\*' -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
    if (!$script:py) { Add-Check 'python' 'fail' 'no Python 3.11 found (the Microsoft Store stub does not count)' 'Install Python 3.11 x64 from https://www.python.org/downloads/windows/ ("Install for current user" is enough), then run the preflight again with -Python <path to python.exe>.'; return }
    $info = (& $script:py -E -c "import sys,struct; print('%d.%d.%d %d' % (sys.version_info[:3] + (struct.calcsize('P')*8,)))" 2>$null)
    if ($info -match '^3\.11\.\d+ 64$') { Add-Check 'python' 'ok' "$($script:py) ($info-bit)" }
    else { Add-Check 'python' 'fail' "$($script:py) reports '$info'" 'Install Python 3.11 x64 and pass -Python <path to its python.exe>.' }
} 'python'
if ($py) {
    Invoke-Probe {
        $names = ($Pins.Keys | ForEach-Object { "'$_'" }) -join ','
        $code = "import importlib.metadata as m, json`nout={}`nfor n in [$names]:`n    try: out[n]=m.version(n)`n    except Exception: out[n]=None`nprint(json.dumps(out))"
        $found = (& $py -E -c $code 2>$null) | ConvertFrom-Json
        $bad = @($Pins.Keys | Where-Object { $found.$_ -ne $Pins[$_] } | ForEach-Object { "$_ wants $($Pins[$_]), has $(if ($found.$_) { $found.$_ } else { 'none' })" })
        $req = Join-Path $Package 'farm\tools\requirements-farm.txt'
        if (!$bad.Count) { Add-Check 'python-packages' 'ok' (($Pins.Keys | ForEach-Object { "$_ $($Pins[$_])" }) -join ', ') }
        else { Add-Check 'python-packages' 'fail' ($bad -join '; ') ("Run: `"$py`" -m pip install --user -r `"$req`"") }
    } 'python-packages'
}

# 4. ffmpeg / ffprobe with libx264 (video draft preparation)
Invoke-Probe {
    $ff = (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue).Source
    $fp = (Get-Command ffprobe.exe -ErrorAction SilentlyContinue).Source
    if (!$ff -or !$fp) { Add-Check 'ffmpeg' 'fail' "ffmpeg: $([bool]$ff), ffprobe: $([bool]$fp) on PATH" 'Install an ffmpeg build with libx264 (for example the gyan.dev "full" build), unzip it to a folder you keep, and add its bin folder to your user PATH (System Properties > Environment Variables). Open a new PowerShell afterwards.'; return }
    $enc = (& $ff -hide_banner -encoders 2>$null) -join "`n"
    if ($enc -match 'libx264') { Add-Check 'ffmpeg' 'ok' "$ff (libx264)" }
    else { Add-Check 'ffmpeg' 'fail' "$ff has no libx264 encoder" 'Replace it with an ffmpeg build that includes libx264.' }
} 'ffmpeg'

# 5. Windows OCR (Read-FarmImageText.ps1 uses Windows.Media.Ocr)
Invoke-Probe {
    $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    $english = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Where-Object { $_.LanguageTag -like 'en*' })
    if ($engine -and $english.Count) { Add-Check 'ocr' 'ok' ("Windows OCR: " + (($english | ForEach-Object LanguageTag) -join ', ')) }
    else { Add-Check 'ocr' 'fail' 'no English Windows OCR recognizer' 'Settings > Time & language > Language & region: add English (United States) with its basic typing/OCR features.' }
} 'ocr'

# 6. Bonjour (dns-sd browse used by auto_connect.py and card_survey.py; receivers use their own mDNS)
Invoke-Probe {
    $svc = Get-Service -Name 'Bonjour Service' -ErrorAction SilentlyContinue
    $dnssd = @((Get-Command dns-sd.exe -ErrorAction SilentlyContinue).Source, (Join-Path $env:ProgramFiles 'Bonjour\dns-sd.exe'), (Join-Path $env:windir 'System32\dns-sd.exe')) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if ($svc -and $svc.Status -eq 'Running' -and $dnssd) { Add-Check 'bonjour' 'ok' "Bonjour Service running; $dnssd" }
    elseif ($svc -and $dnssd) { Add-Check 'bonjour' 'fail' "Bonjour Service is $($svc.Status)" '(admin) Start the Bonjour Service (services.msc > Bonjour Service > Start, startup type Automatic).' }
    else { Add-Check 'bonjour' 'fail' "service: $([bool]$svc), dns-sd.exe: $([bool]$dnssd)" '(admin) Install Bonjour for Windows (Apple "Bonjour Print Services for Windows" 2.0.2, or the Bonjour that comes with iTunes), then check dns-sd.exe is in C:\Windows\System32 or on PATH.' }
} 'bonjour'

# 7. Input boards: WCH USB HID boards (VID_720A) on Windows' own HID driver; no vendor driver is needed
Invoke-Probe {
    $boards = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -match 'VID_720A' -and $_.Class -eq 'HIDClass' })
    $bad = @($boards | Where-Object { $_.Status -ne 'OK' })
    if (!$boards.Count) { Add-Check 'usb-boards' 'warn' 'no VID_720A HID board is connected now' 'Plug the rack hub in and run the preflight again; each board appears as a HID device (built-in HID driver, nothing to install).' }
    elseif ($bad.Count) { Add-Check 'usb-boards' 'fail' "$($boards.Count) board interfaces, $($bad.Count) not OK" 'Replug the failing boards; in Device Manager > Human Interface Devices they must show no warning. Do not install a vendor driver.' }
    else { Add-Check 'usb-boards' 'ok' "$($boards.Count) VID_720A HID interfaces, all OK" }
} 'usb-boards'
Invoke-Probe {
    $vendor = Get-Service -Name 'iMouseService' -ErrorAction SilentlyContinue
    if ($vendor -and $vendor.Status -eq 'Running') { Add-Check 'vendor-service' 'fail' 'the vendor iMouseService is running and can hold the boards' '(admin) Stop the vendor service and set it to Disabled (services.msc > iMouseService). Keep the vendor software installed; tools/restore_vendor_services.ps1 restores it.' }
    elseif ($vendor) { Add-Check 'vendor-service' 'ok' "vendor iMouseService present, $($vendor.Status)" }
    else { Add-Check 'vendor-service' 'ok' 'no vendor iMouseService' }
} 'vendor-service'

# 8. Firewall: inbound allow for the receiver ports (TCP and UDP) and the window media ports (TCP)
function Test-PortsCovered($rules, [string]$Protocol, [int[]]$Ports) {
    foreach ($p in $Ports) {
        $hit = $false
        foreach ($r in $rules) {
            if ($r.Protocol -ne $Protocol -and $r.Protocol -ne 'Any') { continue }
            foreach ($lp in @($r.LocalPort)) {
                if ($lp -eq 'Any' -or $lp -eq [string]$p) { $hit = $true; break }
                if ($lp -match '^(\d+)-(\d+)$' -and $p -ge [int]$Matches[1] -and $p -le [int]$Matches[2]) { $hit = $true; break }
            }
            if ($hit) { break }
        }
        if (!$hit) { return $false }
    }
    return $true
}
Invoke-Probe {
    # Two bulk reads joined by InstanceID (a per-rule filter lookup takes about a minute on a busy PC).
    $allowed = @{}
    Get-NetFirewallRule -Direction Inbound -Action Allow -Enabled True -ErrorAction SilentlyContinue | ForEach-Object { $allowed[$_.InstanceID] = $_ }
    $rules = @(Get-NetFirewallPortFilter -All -ErrorAction SilentlyContinue | Where-Object { $allowed.ContainsKey($_.InstanceID) } | ForEach-Object {
        [pscustomobject]@{ Name = $allowed[$_.InstanceID].DisplayName; Profile = [string]$allowed[$_.InstanceID].Profile; Protocol = [string]$_.Protocol; LocalPort = @($_.LocalPort) }
    })
    $edges = @($ReceiverLow, ($ReceiverLow + 10), ($ReceiverHigh - 90), $ReceiverHigh)
    $tcp = Test-PortsCovered $rules 'TCP' $edges
    $udp = Test-PortsCovered $rules 'UDP' $edges
    $receiverStep = "(admin) New-NetFirewallRule -DisplayName 'iMouse Farm receivers TCP' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $ReceiverLow-$ReceiverHigh -Profile Private ; New-NetFirewallRule -DisplayName 'iMouse Farm receivers UDP' -Direction Inbound -Action Allow -Protocol UDP -LocalPort $ReceiverLow-$ReceiverHigh -Profile Private"
    if ($tcp -and $udp) { Add-Check 'firewall-receivers' 'ok' "inbound TCP and UDP $ReceiverLow-$ReceiverHigh allowed by port rule" }
    else { Add-Check 'firewall-receivers' 'fail' "no enabled inbound port rule covers both TCP ($tcp) and UDP ($udp) $ReceiverLow-$ReceiverHigh (per-program uxplay rules do not survive an update: each version has its own path)" $receiverStep }
    $media = Test-PortsCovered $rules 'TCP' $MediaPorts
    $mediaStep = "(admin) New-NetFirewallRule -DisplayName 'iMouse Farm media' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $($MediaPorts -join ',') -Profile Private"
    if ($media) { Add-Check 'firewall-media' 'ok' "inbound TCP $($MediaPorts -join ', ') allowed" }
    else { Add-Check 'firewall-media' 'fail' "phones cannot reach the window media servers on TCP $($MediaPorts -join ', ')" $mediaStep }
} 'firewall'
Invoke-Probe {
    $public = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object { $_.NetworkCategory -eq 'Public' })
    if ($public.Count) { Add-Check 'network-profile' 'warn' ("public network: " + (($public | ForEach-Object InterfaceAlias) -join ', ')) '(admin) Set the farm Wi-Fi network to Private (Settings > Network & internet > Wi-Fi > the network > Private), so the Private-profile rules apply.' }
    else { Add-Check 'network-profile' 'ok' 'no connected network is Public' }
} 'network-profile'

# 9. Folders: install and data apart, neither inside a source checkout
function Find-Checkout([string]$Path) {
    $p = [IO.Path]::GetFullPath($Path)
    while ($p) { if (Test-Path -LiteralPath (Join-Path $p '.git')) { return $p }; $parent = Split-Path -Parent $p; if ($parent -eq $p) { break }; $p = $parent }
    return $null
}
Invoke-Probe {
    $ir = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\') + '\'
    $dr = [IO.Path]::GetFullPath($DataRoot).TrimEnd('\') + '\'
    $problems = @()
    if ($ir.StartsWith($dr, [StringComparison]::OrdinalIgnoreCase) -or $dr.StartsWith($ir, [StringComparison]::OrdinalIgnoreCase)) { $problems += 'install root and data folder contain each other' }
    foreach ($pair in @(@('install root', $InstallRoot), @('data folder', $DataRoot))) {
        $co = Find-Checkout $pair[1]; if ($co) { $problems += "$($pair[0]) is inside the source checkout $co" }
        if ($pair[1] -match 'Desktop\\Claude Code') { $problems += "$($pair[0]) is in the dev folder" }
    }
    if ($problems.Count) { Add-Check 'folders' 'fail' ($problems -join '; ') 'Choose an install root and a data folder outside every source checkout and apart from each other (defaults: %LOCALAPPDATA%\Programs\iMouseFarm and %LOCALAPPDATA%\iMouseFarm).' }
    else { Add-Check 'folders' 'ok' "install $InstallRoot; data $DataRoot" }
    $drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($InstallRoot)).Substring(0, 1)) -ErrorAction SilentlyContinue
    if ($drive -and $drive.Free -lt 3GB) { Add-Check 'disk' 'warn' ("{0:N1} GB free" -f ($drive.Free / 1GB)) 'Free at least 3 GB: each installed version is about 200 MB and run evidence grows.' }
    elseif ($drive) { Add-Check 'disk' 'ok' ("{0:N1} GB free" -f ($drive.Free / 1GB)) }
} 'folders'

# 10. Ports the farm listens on (loopback kernels and backends); in use now = a farm or another app runs
Invoke-Probe {
    $listen = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object LocalPort | Sort-Object -Unique)
    $busy = @(9916, 9926, 9915, 9925, 9935, 9945 | Where-Object { $_ -in $listen })
    if ($busy.Count) { Add-Check 'ports' 'warn' "in use now: $($busy -join ', ')" 'If no farm is running on this PC, find the program on those ports (Get-NetTCPConnection -LocalPort <port>) and close it.' }
    else { Add-Check 'ports' 'ok' 'kernel and backend ports are free' }
} 'ports'

$failed = @($script:checks | Where-Object status -eq 'fail')
if ($Json) {
    [pscustomobject][ordered]@{ ok = ($failed.Count -eq 0); readOnly = $true; checks = $script:checks } | ConvertTo-Json -Depth 4
} else {
    $script:checks | Format-Table id, status, detail -AutoSize -Wrap | Out-String -Width 160
    $steps = @($script:checks | Where-Object { $_.status -ne 'ok' -and $_.step })
    if ($steps.Count) {
        'Operator steps (this preflight changed nothing):'
        $n = 0; foreach ($c in $steps) { $n++; "  $n. [$($c.id)] $($c.step)" }
    } else { 'All checks passed. Nothing was changed.' }
}
if ($failed.Count) { exit 1 } else { exit 0 }
