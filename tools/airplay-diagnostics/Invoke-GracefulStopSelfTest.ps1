<#
.SYNOPSIS
  Step 0: validates the graceful receiver stop on a DISPOSABLE uxplay, isolated from the rack.

.DESCRIPTION
  Launches the release uxplay executable, unchanged, the way the kernel launches receivers
  (own hidden console, same runtime environment, same video/audio sink options) but with its
  own identity so nothing on the rack is shared:
    name uxplay-selftest-noconnect (not an iMouse2- name), ports 7150-7152, MAC/device ID
    02:49:4D:32:00:99, and -restrict -allow 00:00:5E:00:53:99 (an IANA documentation address no
    phone has), so every real phone is refused at the connection handshake.
  It does advertise on the LAN while it runs (uxplay always registers with Bonjour); this script
  keeps that to about a minute. It then stops it with Stop-ConsoleProcessGracefully.ps1 (which
  refuses unless the console holds only the target) and records: the uxplay log, the
  "Stopping RAOP Server" line, a goodbye (TTL 0) seen by mdns_listen.py, process exit, and the
  ports freed. If the graceful stop fails, it reports and leaves the process for the operator's
  decision; it never force-kills automatically.
#>
param([string]$OutDir = 'C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20260927-rediscovery\step0')
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0'
$uxplay = Join-Path $root 'tools\airplay\uxplay\build-imouse\uxplay.exe'
$runtime = Join-Path $root 'tools\airplay\msys64\ucrt64'
$name = 'uxplay-selftest-noconnect'; $port = 7150; $mac = '02:49:4D:32:00:99'; $allow = '00:00:5E:00:53:99'
New-Item -ItemType Directory -Force $OutDir | Out-Null
$record = Join-Path $OutDir 'step0.txt'; $log = Join-Path $OutDir 'uxplay-selftest.log'; $listen = Join-Path $OutDir 'mdns-listen-step0.txt'
function Note([string]$t) { $l = '{0:HH:mm:ss.fff} {1}' -f (Get-Date), $t; $l; Add-Content -LiteralPath $record -Value $l -Encoding UTF8 }

# --- isolation checks before launch ----------------------------------------------------------
$busy = @(Get-NetTCPConnection -LocalPort $port, ($port + 1), ($port + 2) -ErrorAction SilentlyContinue) + @(Get-NetUDPEndpoint -LocalPort $port, ($port + 1), ($port + 2) -ErrorAction SilentlyContinue)
if ($busy.Count) { Note "REFUSED: ports $port-$($port + 2) are in use"; exit 2 }
$rack = Get-CimInstance Win32_Process -Filter "Name='uxplay.exe'" | ForEach-Object { $_.CommandLine }
if ($rack | Where-Object { $_ -match [regex]::Escape($mac) -or $_ -match "-n $name" -or $_ -match "-p $port" }) { Note 'REFUSED: identity or ports overlap a running receiver'; exit 2 }
Note "rack receivers untouched: $((Get-CimInstance Win32_Process -Filter "Name='uxplay.exe'" | ForEach-Object { $_.ProcessId }) -join ', ')"

# --- listener, then launch -------------------------------------------------------------------
$py = Start-Process python -ArgumentList "`"$(Join-Path $PSScriptRoot 'mdns_listen.py')`"", '192.168.4.26', '75', "`"$listen`"" -WindowStyle Hidden -PassThru
# Bonjour's own view: Add when registered, Rmv when withdrawn. (The LAN listener cannot see this
# host's own multicast announcements, as the first Step 0 run showed.)
$browse = Join-Path $OutDir 'dns-sd-browse.txt'
$ds = Start-Process 'C:\Windows\System32\dns-sd.exe' -ArgumentList '-B', '_airplay._tcp', 'local' -RedirectStandardOutput $browse -WindowStyle Hidden -PassThru
Start-Sleep 2
$si = New-Object Diagnostics.ProcessStartInfo $uxplay
$si.UseShellExecute = $false; $si.CreateNoWindow = $true; $si.RedirectStandardOutput = $true; $si.RedirectStandardError = $true
$si.WorkingDirectory = Split-Path $uxplay
$si.EnvironmentVariables['PATH'] = (Join-Path $runtime 'bin') + ';' + $env:PATH
$si.EnvironmentVariables['GST_PLUGIN_SYSTEM_PATH_1_0'] = Join-Path $runtime 'lib\gstreamer-1.0'
$si.EnvironmentVariables['GST_PLUGIN_SCANNER_1_0'] = Join-Path $runtime 'libexec\gstreamer-1.0\gst-plugin-scanner.exe'
$si.EnvironmentVariables['IMOUSE2_FRAME_PIPE'] = '\\.\pipe\uxplay-selftest-' + [guid]::NewGuid().ToString('N')
$si.Arguments = "-n $name -nh -s 500x1080 -fps 30 -avdec -vs appsink -as fakesink -p $port -restrict -allow $allow -m $mac"
$proc = New-Object Diagnostics.Process; $proc.StartInfo = $si
$sink = { if ($EventArgs.Data) { Add-Content -LiteralPath $Event.MessageData -Value ((Get-Date).ToString('HH:mm:ss.fff') + ' ' + $EventArgs.Data) -Encoding UTF8 } }
$e1 = Register-ObjectEvent $proc OutputDataReceived -Action $sink -MessageData $log
$e2 = Register-ObjectEvent $proc ErrorDataReceived -Action $sink -MessageData $log
[void]$proc.Start(); $proc.BeginOutputReadLine(); $proc.BeginErrorReadLine()
Note "disposable receiver started: PID $($proc.Id), args: $($si.Arguments)"

$ready = $false
for ($i = 0; $i -lt 40 -and -not $ready; $i++) { Start-Sleep -Milliseconds 500; $ready = (Test-Path $log) -and [bool](Select-String -Path $log -Pattern 'Initialized server socket' -Quiet) }
Note "ready (log 'Initialized server socket'): $ready"
Start-Sleep 5
$seen = $false
for ($i = 1; $i -le 4 -and -not $seen; $i++) {
    $seen = [bool](& python (Join-Path $PSScriptRoot 'mdns_probe.py') 192.168.4.26 3 '_airplay._tcp.local' | Select-String $name)
    Note "probe $i before stop answered for ${name}: $seen"
}

# --- graceful stop ---------------------------------------------------------------------------
$helper = Join-Path $PSScriptRoot '..\kernel-window\Stop-ConsoleProcessGracefully.ps1'
$out = & powershell -NoProfile -ExecutionPolicy Bypass -File $helper -ProcessId $proc.Id -ExpectedPath $uxplay -TimeoutSeconds 20
$out | ForEach-Object { Note "  helper: $_" }
$helperExit = $LASTEXITCODE
Start-Sleep 2
Note "helper exit $helperExit; disposable receiver exited: $($proc.HasExited)$(if ($proc.HasExited) { " (exit code $($proc.ExitCode))" })"
Note "log shows 'Stopping RAOP Server': $([bool](Select-String -Path $log -Pattern 'Stopping RAOP Server' -Quiet))"
$busy = @(Get-NetTCPConnection -LocalPort $port, ($port + 1), ($port + 2) -State Listen -ErrorAction SilentlyContinue)
Note "ports $port-$($port + 2) freed: $($busy.Count -eq 0)"
Start-Sleep 3
$after = @(1..2 | ForEach-Object { [bool](& python (Join-Path $PSScriptRoot 'mdns_probe.py') 192.168.4.26 3 '_airplay._tcp.local' | Select-String $name) })
Note "probes after stop still answered for ${name}: $($after -join ', ')"
Stop-Process -Id $ds.Id -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 300
Get-Content $browse | Where-Object { $_ -match $name } | ForEach-Object { Note "  dns-sd: $($_.Trim())" }
Note "withdrawn in Bonjour (dns-sd Rmv): $([bool](Select-String -Path $browse -Pattern ('Rmv.*' + $name) -Quiet))"
Wait-Process -Id $py.Id -Timeout 90 -ErrorAction SilentlyContinue
$bye = Select-String -Path $listen -Pattern "GOODBYE.*$name" -Quiet
Note "goodbye (TTL 0) for $name seen by the LAN listener: $([bool]$bye) (this host's own multicast may not be visible to it)"
Unregister-Event -SourceIdentifier $e1.Name; Unregister-Event -SourceIdentifier $e2.Name
if (-not $proc.HasExited) { Note 'DISPOSABLE RECEIVER STILL RUNNING: not force-killed; operator decision needed.'; exit 3 }
Note "rack receivers still: $((Get-CimInstance Win32_Process -Filter "Name='uxplay.exe'" | ForEach-Object { $_.ProcessId }) -join ', ')"
