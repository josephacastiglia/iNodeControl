$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$prep = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$checks = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'focused-tests.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $checks.passed -or $checks.skipped) { throw 'Offline checks are incomplete.' }
$processFile = Join-Path $PSScriptRoot 'processes.json'
if (Test-Path -LiteralPath $processFile) { throw 'This window already has a process record. Never start a duplicate.' }
$processes = @(Get-CimInstance Win32_Process -Filter "Name='iMouse2.exe' OR Name='iMouse2.Kernel.exe' OR Name='uxplay.exe'" | Select-Object ProcessId,ExecutablePath,CommandLine)
$tcp = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -In @(9911,9913,9914,9915,9916,9917,7110,7111,7112,7120,7121,7122))
$udp = @(Get-NetUDPEndpoint | Where-Object LocalPort -In @(7110,7111,7112,7120,7121,7122))
[ordered]@{utc=[datetime]::UtcNow.ToString('o');processes=$processes;tcp=$tcp;udp=$udp;phoneInput=$false} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'initial-rack.json') -Encoding UTF8
if ($processes.Count -or $tcp.Count -or $udp.Count) { throw 'Rack or test services are active. Nothing was started.' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath ([IO.Path]::ChangeExtension($prep.kernel,'.dll'))).Hash.ToLowerInvariant() -ne $prep.kernelSha256) { throw 'Kernel changed.' }
$protected = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'protected-files.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $protected.PSObject.Properties) { if ((Get-FileHash -Algorithm SHA256 -LiteralPath $entry.Name).Hash.ToLowerInvariant() -ne $entry.Value.sha256) { throw ('Protected file changed: '+$entry.Name) } }
foreach ($argument in $prep.arguments) { if ($argument.Contains('"')) { throw 'Unexpected quote in startup argument.' } }
$arguments = (($prep.arguments | ForEach-Object { '"'+$_+'"' }) -join ' ')
$kernel = Start-Process -FilePath $prep.kernel -ArgumentList $arguments -WorkingDirectory ([IO.Path]::GetDirectoryName($prep.kernel)) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'kernel.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'kernel.stderr.txt')
[ordered]@{utc=[datetime]::UtcNow.ToString('o');kernel=@{pid=$kernel.Id;path=$prep.kernel;arguments=$prep.arguments};backend=$null;phoneInput=$false;desktopControl=$false} | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $processFile -Encoding UTF8
$deadline = [datetime]::UtcNow.AddSeconds(25)
do {
  Start-Sleep -Milliseconds 300
  try { $status = (Invoke-RestMethod -Uri 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 2).data } catch { $status=$null }
  if ($kernel.HasExited) { throw 'Candidate kernel exited; inspect its retained logs.' }
} while ((-not $status -or $status.receivers.Count -ne 1 -or $status.receivers[0].receiver_pid -le 0) -and [datetime]::UtcNow -lt $deadline)
if (-not $status -or $status.process.pid -ne $kernel.Id -or $status.allowed.Count -ne 1 -or $status.allowed[0] -cne 'C24C' -or $status.receivers.Count -ne 1 -or $status.receivers[0].name -cne 'iMouse2-C24C') { throw 'Candidate readiness did not match its preparation.' }
$status | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'receiver-ready.json') -Encoding UTF8
[ordered]@{kernelPid=$kernel.Id;receiverPid=$status.receivers[0].receiver_pid;name=$status.receivers[0].name;live=$status.receivers[0].live;phoneInput=$false} | ConvertTo-Json
