<#
.SYNOPSIS
  One timed rediscovery trial for ONE release receiver (C24C by default): verify the mapping,
  stop that receiver by the chosen method, confirm the kernel's supervisor starts exactly one
  identical replacement, and record readiness, connection and live video separately.

.DESCRIPTION
  Methods:
    Forced    terminate the uxplay process (what the kernel's shutdown does today).
    Graceful  Ctrl+C to uxplay's own console (its handler stops the RAOP server, unregisters
              DNS-SD, exits); refused unless the receiver log then shows "Stopping RAOP Server".
  -DryRun performs every read-only check and signals nothing.

  Never touches the other receiver, the kernel, the network or any setting. Refuses unless:
  the target PID is the kernel's current receiver for the device, its executable is the release
  uxplay, its parent is the release kernel, its arguments name the expected receiver and allow
  only that device, the other receiver is running, and the supervisor has restart budget left.
  Appearance in the phone's Screen Mirroring list is observed by the operator; this script
  records the times that software can see (exit, replacement, readiness, connection request,
  live video). Observation ends at -WindowMinutes; recovery beyond that is not attempted.
#>
param(
    [ValidateSet('Forced', 'Graceful')][string]$Method = 'Forced',
    [string]$DeviceId = '86:1D:4A:04:2F:F6',
    [string]$Name = 'iMouse2-C24C',
    [string]$OtherName = 'iMouse2-C241',
    [string]$Condition = '',
    [int]$WindowMinutes = 25,
    [string]$OutDir = 'C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20260927-rediscovery',
    [datetime]$StartAt = [datetime]::MinValue,   # T0 is not before this time, so the operator is told first
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0'
$uxplay = Join-Path $root 'tools\airplay\uxplay\build-imouse\uxplay.exe'
$kernelExe = Join-Path $root 'release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe'
$log = Join-Path $root "analysis\two-phone-config\receiver-$($Name.Substring(8)).log"
$helper = Join-Path $PSScriptRoot '..\kernel-window\Stop-ConsoleProcessGracefully.ps1'
New-Item -ItemType Directory -Force $OutDir | Out-Null
$stamp = Get-Date -Format 'HHmmss'
$record = Join-Path $OutDir "trial-$stamp-$Method$(if ($Condition) { "-$Condition" })$(if ($DryRun) { '-dryrun' }).txt"
function Note([string]$text) { $line = '{0:HH:mm:ss.fff} {1}' -f (Get-Date), $text; $line; Add-Content -LiteralPath $record -Value $line -Encoding UTF8 }
function Fail([string]$text) { Note "REFUSED: $text"; exit 2 }
function Status { (Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 3).data }
function Receiver($s, $n) { $s.receivers | Where-Object name -eq $n | Select-Object -First 1 }
function Uxplays($n) { @(Get-CimInstance Win32_Process -Filter "Name='uxplay.exe'" | Where-Object { $_.CommandLine -match ('-n ' + [regex]::Escape($n) + '( |$)') }) }
function Txt($n) {
    $o = Join-Path $env:TEMP "claude\dnssd-trial-$n.txt"
    $p = Start-Process 'C:\Windows\System32\dns-sd.exe' -ArgumentList '-L', $n, '_airplay._tcp', 'local' -RedirectStandardOutput $o -NoNewWindow -PassThru
    Start-Sleep 3; Stop-Process -Id $p.Id -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 300
    $t = (Get-Content $o | Where-Object { $_ -match 'deviceid=' }) -join ' '
    [regex]::Match($t, 'deviceid=\S+').Value + ' ' + [regex]::Match($t, 'pk=\S+').Value
}

Note "trial: method=$Method condition=$Condition device=$DeviceId receiver=$Name window=$WindowMinutes min dryrun=$DryRun"
# --- mapping and preconditions -------------------------------------------------------------
$s = Status
$r = Receiver $s $Name; $other = Receiver $s $OtherName
if (-not $r -or $r.deviceid -ne $DeviceId) { Fail "kernel reports no receiver $Name for $DeviceId" }
$procs = @(Uxplays $Name)
if ($procs.Count -ne 1) { Fail "expected exactly one uxplay named $Name, found $($procs.Count)" }
$target = $procs[0]
if ($target.ProcessId -ne $r.receiver_pid) { Fail "kernel says PID $($r.receiver_pid) but the $Name process is $($target.ProcessId)" }
if ([IO.Path]::GetFullPath($target.ExecutablePath) -ine [IO.Path]::GetFullPath($uxplay)) { Fail "PID $($target.ProcessId) is $($target.ExecutablePath)" }
$kernel = Get-CimInstance Win32_Process -Filter "ProcessId=$($target.ParentProcessId)"
if (-not $kernel -or [IO.Path]::GetFullPath($kernel.ExecutablePath) -ine [IO.Path]::GetFullPath($kernelExe)) { Fail "parent $($target.ParentProcessId) is not the release kernel" }
if ($target.CommandLine -notmatch ('-restrict -allow ' + [regex]::Escape($DeviceId) + '( |$)')) { Fail "arguments do not restrict $Name to $DeviceId" }
if (-not $other -or -not (Get-Process -Id $other.receiver_pid -ErrorAction SilentlyContinue)) { Fail "the other receiver $OtherName is not running" }
if ($r.receiver_restarts -ge 3) { Fail "supervisor has used $($r.receiver_restarts) of 5 relaunches; at least two must remain unused after this trial" }
$argsBefore = $target.CommandLine.Trim()
$idBefore = Txt $Name
$otherBefore = @{ pid = $other.receiver_pid; frames = $other.frames }
Note "mapping ok: $Name pid $($target.ProcessId) (kernel $($kernel.ProcessId)), live=$($r.live) frames=$($r.frames) restarts=$($r.receiver_restarts)"
Note "identity before: $idBefore"
Note "args before: $argsBefore"
Note "other receiver $OtherName pid $($other.receiver_pid) live=$($other.live) frames=$($other.frames)"
if ($DryRun) { Note 'dry run: nothing signalled'; exit 0 }

# --- stop ------------------------------------------------------------------------------------
$browse = Join-Path $OutDir "dns-sd-browse-$stamp.txt"
$ds = Start-Process 'C:\Windows\System32\dns-sd.exe' -ArgumentList '-B', '_airplay._tcp', 'local' -RedirectStandardOutput $browse -WindowStyle Hidden -PassThru
if ($StartAt -gt (Get-Date)) { Note ("waiting until T0 = {0:HH:mm:ss}" -f $StartAt); while ((Get-Date) -lt $StartAt) { Start-Sleep -Milliseconds 200 } }
$r = Receiver (Status) $Name
if ($r.receiver_pid -ne $target.ProcessId -or -not (Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue)) { Stop-Process -Id $ds.Id -ErrorAction SilentlyContinue; Fail "the receiver changed while waiting for T0" }
Note "just before T0: $Name live=$($r.live) frames=$($r.frames)"
$logLinesBefore = (Get-Content $log).Count
$t0 = Get-Date; Note "T0 stop issued ($Method) to PID $($target.ProcessId)"
if ($Method -eq 'Forced') { Stop-Process -Id $target.ProcessId -Force }
else {
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $helper -ProcessId $target.ProcessId -ExpectedPath $uxplay -TimeoutSeconds 20
    $out | ForEach-Object { Note "  helper: $_" }
    if ($LASTEXITCODE -notin 0, 4) { Note "GRACEFUL STOP DID NOT COMPLETE (helper exit $LASTEXITCODE); nothing else was signalled. End the session and wait for recovery."; exit 3 }
}
$old = Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue
if ($old) { [void]$old.WaitForExit(20000) }
Note "old receiver exited: $(-not (Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue))"
if ($Method -eq 'Graceful') {
    $newLines = Get-Content $log | Select-Object -Skip $logLinesBefore
    $clean = [bool]($newLines | Select-String 'Stopping RAOP Server')
    Note "graceful path confirmed in log (Stopping RAOP Server): $clean"
}

# --- replacement -----------------------------------------------------------------------------
$replacement = $null
for ($i = 0; $i -lt 60 -and -not $replacement; $i++) {
    Start-Sleep -Milliseconds 500
    $now = @(Uxplays $Name | Where-Object ProcessId -ne $target.ProcessId)
    if ($now.Count -ge 1) { $replacement = $now }
}
if (-not $replacement) { Note 'NO REPLACEMENT within 30 s. Nothing else was signalled; end the session.'; exit 3 }
Start-Sleep 2
$all = @(Uxplays $Name)
Note "replacement count: $($all.Count) (expected 1); new PID $($all[0].ProcessId) started $((Get-Process -Id $all[0].ProcessId).StartTime.ToString('HH:mm:ss.fff'))"
$argsAfter = $all[0].CommandLine.Trim()
Note "arguments identical: $($argsAfter -eq $argsBefore)"
if ($argsAfter -ne $argsBefore) { Note "args after: $argsAfter" }

# --- readiness, connection, live video, other receiver ---------------------------------------
$ready = $null; $request = $null; $live = $null; $sawOffline = $false; $end = $t0.AddMinutes($WindowMinutes)
while ((Get-Date) -lt $end -and -not $live) {
    $newLines = Get-Content $log | Select-Object -Skip $logLinesBefore
    if (-not $ready) { $m = $newLines | Select-String 'Initialized server socket' | Select-Object -First 1; if ($m) { $ready = $m.Line.Substring(11, 12); Note "receiver ready (log): $ready" } }
    if ($ready -and -not $idAfterDone) { $idAfter = Txt $Name; Note "identity after: $idAfter (identical: $($idAfter -eq $idBefore))"; $idAfterDone = $true }
    if (-not $request) { $m = $newLines | Select-String ('connection request .*deviceID = ' + [regex]::Escape($DeviceId)) | Select-Object -First 1; if ($m) { $request = $m.Line.Substring(11, 12); Note "connection request from $DeviceId (log): $request" } }
    $st = Status; $rr = Receiver $st $Name
    # The frame counter is not reset by a receiver restart, so live video counts only after offline was seen.
    if (-not $rr.live -and -not $sawOffline) { $sawOffline = $true; Note ("video offline after stop at {0:HH:mm:ss.fff}" -f (Get-Date)) }
    if ($sawOffline -and $rr.live) { $live = Get-Date; Note ("live video again: frames $($rr.frames) at {0:HH:mm:ss.fff}" -f $live) }
    Start-Sleep 3
}
$st = Status; $o2 = Receiver $st $OtherName
Note "other receiver ${OtherName}: pid $($o2.receiver_pid) (unchanged: $($o2.receiver_pid -eq $otherBefore.pid)) live=$($o2.live) frames $($otherBefore.frames) -> $($o2.frames)"
Stop-Process -Id $ds.Id -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 300
Get-Content $browse | Where-Object { $_ -match [regex]::Escape($Name) } | ForEach-Object { Note "  dns-sd: $($_.Trim())" }
Note ("summary: stop->ready {0}; stop->request {1}; stop->live {2}; restarts now {3}" -f $(if ($ready) { $ready } else { 'n/a' }), $(if ($request) { $request } else { "none within $WindowMinutes min" }), $(if ($live) { '{0:N0} s' -f ($live - $t0).TotalSeconds } else { "none within $WindowMinutes min" }), (Receiver $st $Name).receiver_restarts)
