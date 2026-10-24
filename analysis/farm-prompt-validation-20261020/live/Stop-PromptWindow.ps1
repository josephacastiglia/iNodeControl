# Graceful stop of one prompt-validation part, then restoration and protected-file checks.
# Refuses unless the recorded kernel is still the same process and C24C is free. Nothing is force-killed.
param([Parameter(Mandatory)][ValidateSet('A','B')][string]$Part)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$taskPrep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw | ConvertFrom-Json
$taskProcesses=Get-Content -LiteralPath (Join-Path $PSScriptRoot ('processes-'+$Part+'.json')) -Raw | ConvertFrom-Json
$taskReady=(Get-Content -LiteralPath (Join-Path $PSScriptRoot ('receiver-ready-'+$Part+'.json')) -Raw | ConvertFrom-Json).data
$taskHelper=Join-Path $taskRoot 'tools/kernel-window/Stop-ConsoleProcessGracefully.ps1'
$taskSteps=@(Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -and $_.CommandLine -match 'farm_prompt_validation\.py'})
if($taskSteps.Count){throw 'A validation step is still running. Let it finish; nothing is force-killed.'}
$taskActual=Get-CimInstance Win32_Process -Filter ('ProcessId='+$taskProcesses.kernel.pid)
if(!$taskActual -or $taskActual.ExecutablePath -cne $taskProcesses.kernel.path -or $taskActual.ExecutablePath -cne $taskPrep.kernel){throw 'Private kernel identity changed. Nothing is force-killed.'}
$taskStatus=((Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 5).Content | ConvertFrom-Json).data
$taskInputRaw=(Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:9916/api/' -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 5).Content
$taskPhone=@(($taskInputRaw | ConvertFrom-Json).data.phones)
if($taskStatus.process.pid -ne $taskProcesses.kernel.pid -or $taskStatus.process.started_utc -cne $taskReady.process.started_utc -or $taskStatus.build_identity.sha256 -cne $taskPrep.kernelSha256 -or $taskPhone.Count -ne 1 -or $taskPhone[0].id -cne $taskPrep.expectedDeviceId -or $taskPhone[0].owned -or $taskPhone[0].active -or $taskPhone[0].stopped -or $taskPhone[0].releasing -or $taskPhone[0].release_failed){throw 'Kernel identity or free input state is unconfirmed. Nothing is force-killed.'}
@{part=$Part;kernel=$taskStatus;input=($taskInputRaw | ConvertFrom-Json).data;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ('final-live-state-'+$Part+'.json')) -Encoding utf8
$taskArguments='-NoProfile -ExecutionPolicy Bypass -File "'+$taskHelper+'" -ProcessId '+$taskProcesses.kernel.pid+' -ExpectedPath "'+$taskProcesses.kernel.path+'" -TimeoutSeconds 20'
$taskStop=Start-Process -FilePath powershell.exe -ArgumentList $taskArguments -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $PSScriptRoot ('stop-kernel-'+$Part+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ('stop-kernel-'+$Part+'.stderr.txt'))
if($taskStop.ExitCode -ne 0){throw ('Graceful stop unconfirmed for part '+$Part+'. Nothing is force-killed.')}
$taskRemaining=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -in @('iMouse2.exe','iMouse2.Kernel.exe','uxplay.exe','NativeProbe.exe','ReelProbe.exe','TikTokProbe.exe','XProbe.exe') -or ($_.CommandLine -and $_.CommandLine -match 'python[^\r\n]*(imouse_farm_server|farm_prompt_validation)\.py') } | Select-Object ProcessId,ExecutablePath,CommandLine)
$taskTcp=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -In @(9913,9914,9915,9916,9917,7110,7111,7112,7120,7121,7122) | Select-Object LocalPort,OwningProcess)
$taskUdp=@(Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object LocalPort -In @(7110,7111,7112,7120,7121,7122) | Select-Object LocalPort,OwningProcess)
$taskBefore=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'protected-before.json') -Raw | ConvertFrom-Json
$taskProtected=@(foreach($taskFile in $taskBefore){$taskHash=(Get-FileHash -LiteralPath $taskFile.path -Algorithm SHA256).Hash.ToLowerInvariant();@{path=$taskFile.path;sha256=$taskHash;unchanged=($taskHash -ceq $taskFile.sha256)}})
$taskRestored=$taskRemaining.Count -eq 0 -and $taskTcp.Count -eq 0 -and $taskUdp.Count -eq 0 -and @($taskProtected | Where-Object {!$_.unchanged}).Count -eq 0
@{part=$Part;restored=$taskRestored;processes=$taskRemaining;tcp=$taskTcp;udp=$taskUdp;protectedFiles=$taskProtected;installedReleaseStarted=$false;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ('restoration-'+$Part+'.json')) -Encoding utf8
if(!$taskRestored){throw 'Restoration needs review. Preserve the process/log record.'}
Write-Output ('Part '+$Part+' stopped; initial stopped state restored; '+$taskProtected.Count+' protected files unchanged.')
