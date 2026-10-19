$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$taskRecordFile=Join-Path $PSScriptRoot 'processes.json'
$taskPrep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw | ConvertFrom-Json
$taskProcesses=Get-Content -LiteralPath $taskRecordFile -Raw | ConvertFrom-Json
if(Test-Path -LiteralPath (Join-Path $PSScriptRoot 'backend-restart.json')){throw 'Backend restart already recorded. Do not repeat.'}
$taskActual=Get-CimInstance Win32_Process -Filter ('ProcessId='+$taskProcesses.backend.pid)
if(!$taskActual -or $taskActual.ExecutablePath -cne $taskProcesses.backend.path -or $taskActual.CommandLine -notlike '*imouse_farm_server.py*' -or $taskActual.CommandLine -notlike ('*'+$taskPrep.backendData+'*')){throw 'Private backend process changed.'}
$taskHealth=Invoke-RestMethod 'http://127.0.0.1:9915/health' -TimeoutSec 5
if($taskHealth.sourceHash -cne $taskPrep.backendSourceHash -or $taskHealth.draftRecovery.storeId -cne $taskPrep.recoveryStoreId){throw 'Backend identity changed.'}
$taskBefore=(Invoke-RestMethod 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 5).data
$taskInputBefore=(Invoke-RestMethod 'http://127.0.0.1:9916/api/' -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 5).data
$taskPhone=@($taskInputBefore.phones)
if($taskBefore.process.pid -ne $taskProcesses.kernel.pid -or $taskBefore.build_identity.sha256 -cne $taskPrep.kernelSha256 -or $taskPhone.Count -ne 1 -or $taskPhone[0].id -cne $taskPrep.expectedDeviceId -or $taskPhone[0].owned -or $taskPhone[0].active -or $taskPhone[0].stopped -or $taskPhone[0].releasing -or $taskPhone[0].release_failed){throw 'Kernel identity or free input unconfirmed.'}
$taskHistory=(Invoke-RestMethod ('http://127.0.0.1:9915/api/farm/draft-recoveries?draft_id='+$taskPrep.draftId) -TimeoutSec 5).runs
foreach($taskRun in $taskHistory){
    $taskValue=(Invoke-RestMethod ('http://127.0.0.1:9915/api/farm/draft-recoveries/'+$taskRun.id) -TimeoutSec 5).run
    if(!$taskValue.terminal -or $taskValue.cleanup -cne 'confirmed'){throw 'An inspection is still active or needs cleanup. Backend will remain running.'}
}
Copy-Item -LiteralPath $taskRecordFile -Destination (Join-Path $PSScriptRoot 'processes.before-backend-restart.json')
$taskHelper=Join-Path $taskRoot 'tools/kernel-window/Stop-ConsoleProcessGracefully.ps1'
$taskArgs='-NoProfile -ExecutionPolicy Bypass -File "'+$taskHelper+'" -ProcessId '+$taskProcesses.backend.pid+' -ExpectedPath "'+$taskProcesses.backend.path+'" -TimeoutSeconds 20'
$taskStop=Start-Process -FilePath powershell.exe -ArgumentList $taskArgs -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'restart-stop-backend.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'restart-stop-backend.stderr.txt')
if($taskStop.ExitCode -ne 0){throw 'Graceful backend stop unconfirmed; do not restart.'}
if(Get-NetTCPConnection -State Listen -LocalPort 9915 -ErrorAction SilentlyContinue){throw 'Private backend port remains occupied.'}
foreach($taskArg in $taskProcesses.backend.arguments){if($taskArg.Contains('"')){throw 'Unexpected quote in retained startup argument.'}}
$taskNew=Start-Process -FilePath $taskProcesses.backend.path -ArgumentList (($taskProcesses.backend.arguments | ForEach-Object {'"'+$_+'"'}) -join ' ') -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'backend-restarted.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'backend-restarted.stderr.txt')
$taskOldPid=$taskProcesses.backend.pid
$taskProcesses.backend.pid=$taskNew.Id
$taskProcesses | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath $taskRecordFile -Encoding utf8
$taskDeadline=[datetime]::UtcNow.AddSeconds(20)
do{
    Start-Sleep -Milliseconds 200
    try{$taskHealth=Invoke-RestMethod 'http://127.0.0.1:9915/health' -TimeoutSec 2}catch{$taskHealth=$null}
    if($taskNew.HasExited){throw 'New private backend exited; preserve logs.'}
}while(!$taskHealth -and [datetime]::UtcNow -lt $taskDeadline)
if(!$taskHealth -or $taskHealth.sourceHash -cne $taskPrep.backendSourceHash -or $taskHealth.draftRecovery.storeId -cne $taskPrep.recoveryStoreId -or !$taskHealth.draftRecovery.inspectionOnly -or $taskHealth.draftRecovery.publishing -or $taskHealth.draftRecovery.messaging){throw 'Restarted backend failed identity/scope check.'}
$taskAfter=(Invoke-RestMethod 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 5).data
$taskInputAfter=(Invoke-RestMethod 'http://127.0.0.1:9916/api/' -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 5).data
$taskSame=$taskAfter.process.pid -eq $taskBefore.process.pid -and $taskAfter.process.started_utc -ceq $taskBefore.process.started_utc -and $taskAfter.receivers[0].receiver_pid -eq $taskBefore.receivers[0].receiver_pid -and $taskAfter.receivers[0].receiver_restarts -eq $taskBefore.receivers[0].receiver_restarts -and $taskInputAfter.phones[0].generation -eq $taskInputBefore.phones[0].generation -and !$taskInputAfter.phones[0].owned -and !$taskInputAfter.phones[0].active
@{passed=$taskSame;oldBackendPid=$taskOldPid;newBackendPid=$taskNew.Id;before=@{kernel=$taskBefore;input=$taskInputBefore};after=@{kernel=$taskAfter;input=$taskInputAfter};kind='graceful restart after all inspections terminal';midCommandCrashTest=$false;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'backend-restart.json') -Encoding utf8
if(!$taskSame){throw 'Kernel/receiver/input state changed during backend-only restart.'}
Write-Output ('Backend restarted '+$taskOldPid+' -> '+$taskNew.Id+'; kernel, receiver and input generation unchanged.')
