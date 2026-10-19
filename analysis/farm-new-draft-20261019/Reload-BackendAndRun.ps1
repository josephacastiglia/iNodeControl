param([Parameter(Mandatory=$true)][ValidateRange(4,18)][int]$Attempt)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if(Test-Path -LiteralPath (Join-Path $PSScriptRoot ('live-attempt-'+$Attempt))){throw 'Attempt already exists; never replay it.'}
$processFile=Join-Path $PSScriptRoot 'processes.json'
$p=Get-Content -LiteralPath $processFile -Raw -Encoding UTF8|ConvertFrom-Json
$process=Get-CimInstance Win32_Process -Filter ('ProcessId='+$p.backend.pid)
if($process.ExecutablePath -cne $p.backend.path -or $process.CommandLine -notlike '*imouse_farm_server.py*'){throw 'Backend identity changed.'}
# The preceding attempt is terminal. Preserve its full process/intent record.
Copy-Item -LiteralPath $processFile -Destination (Join-Path $PSScriptRoot ('before-attempt-'+$Attempt+'-processes.json'))
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'live-attempt-1/data/farm-pending-draft-creation.json') -Destination (Join-Path $PSScriptRoot ('before-attempt-'+$Attempt+'-pending.json'))
$python='C:\Users\joey_\AppData\Local\Programs\Python\Python311\python.exe'
& $python (Join-Path $PSScriptRoot 'seal_attempt.py') $Attempt
if($LASTEXITCODE -ne 0){throw 'Read-only preflight failed. Nothing was restarted.'}
$helper=Join-Path $root 'tools/kernel-window/Stop-ConsoleProcessGracefully.ps1'
$stopper=Start-Process -FilePath powershell.exe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "'+$helper+'" -ProcessId '+$p.backend.pid+' -ExpectedPath "'+$p.backend.path+'" -TimeoutSeconds 20') -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $PSScriptRoot ('stop-backend-before-'+$Attempt+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ('stop-backend-before-'+$Attempt+'.stderr.txt'))
if($stopper.ExitCode -ne 0){throw 'Backend graceful stop unconfirmed. Nothing is force-killed.'}
$prep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw -Encoding UTF8|ConvertFrom-Json
$arguments=$p.backend.arguments
$backend=Start-Process -FilePath $p.backend.path -ArgumentList (($arguments|ForEach-Object {'"'+$_+'"'})-join ' ') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot ('backend-attempt-'+$Attempt+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ('backend-attempt-'+$Attempt+'.stderr.txt'))
$p.backend=@{pid=$backend.Id;path=$p.backend.path;arguments=$arguments};$p|ConvertTo-Json -Depth 9|Set-Content -LiteralPath $processFile -Encoding UTF8
$deadline=[datetime]::UtcNow.AddSeconds(20)
do{Start-Sleep -Milliseconds 250;try{$health=Invoke-RestMethod -Uri 'http://127.0.0.1:9915/health' -TimeoutSec 2}catch{$health=$null}}while(-not $health -and [datetime]::UtcNow -lt $deadline)
if($health.sourceHash -cne $prep.backendSourceHash -or !$health.draftCreation.enabled -or $health.draftWorkflow.enabled){throw 'Backend identity/permission mismatch.'}
$health|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $PSScriptRoot ('backend-ready-attempt-'+$Attempt+'.json')) -Encoding UTF8
$options=Join-Path $PSScriptRoot ('live-attempt-'+$Attempt+'.options.json')
$probe=Start-Process -FilePath $prep.nativeProbe -ArgumentList ('"'+$options+'"') -WorkingDirectory $root -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $PSScriptRoot ('native-probe-attempt-'+$Attempt+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ('native-probe-attempt-'+$Attempt+'.stderr.txt'))
$p.nativeProbe=@{pid=$probe.Id;path=$prep.nativeProbe;options=$options};$p|ConvertTo-Json -Depth 9|Set-Content -LiteralPath $processFile -Encoding UTF8
[ordered]@{pid=$probe.Id;exitCode=$probe.ExitCode;utc=[datetime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $PSScriptRoot ('native-probe-attempt-'+$Attempt+'.exit.json')) -Encoding UTF8
Get-Content -LiteralPath (Join-Path $PSScriptRoot ('native-probe-attempt-'+$Attempt+'.exit.json'))
