$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$taskPython='C:\Users\joey_\AppData\Local\Programs\Python\Python311\python.exe'
$taskProcessFile=Join-Path $PSScriptRoot 'processes.json'
if(Test-Path -LiteralPath $taskProcessFile){throw 'This live window already has a process record. Do not start duplicates.'}
$taskProcesses=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('iMouse2.exe','iMouse2.Kernel.exe','uxplay.exe','NativeProbe.exe') -or ($_.CommandLine -and $_.CommandLine -match 'python[^\r\n]*imouse_farm_server\.py|dotnet[^\r\n]*iMouse2(\.Kernel)?\.dll') } | Select-Object ProcessId,ExecutablePath,CommandLine)
$taskTcp=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -In @(9911,9913,9914,9915,9916,9917,7110,7111,7112,7120,7121,7122) | Select-Object LocalAddress,LocalPort,OwningProcess)
$taskUdp=@(Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object LocalPort -In @(7110,7111,7112,7120,7121,7122) | Select-Object LocalAddress,LocalPort,OwningProcess)
@{utc=[datetime]::UtcNow.ToString('o');processes=$taskProcesses;tcp=$taskTcp;udp=$taskUdp;phoneInput=$false} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'initial-rack.json') -Encoding utf8
if($taskProcesses.Count -or $taskTcp.Count -or $taskUdp.Count){throw 'Rack/test services are active. Nothing was stopped or started.'}
& $taskPython (Join-Path $PSScriptRoot 'preflight.py')
if($LASTEXITCODE -ne 0){throw 'Read-only preparation failed.'}
$taskPrep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw | ConvertFrom-Json
$taskLaunch=& (Join-Path $taskRoot 'Open Marketing Farm Candidate.ps1') -ValidateOnly -DraftCreationConfig $taskPrep.config
if($taskLaunch.SourceHash -cne $taskPrep.backendSourceHash -or $taskLaunch.StartsProcesses){throw 'Candidate source identity differs.'}
function Quote-TaskArguments($taskValues){
    foreach($taskValue in $taskValues){if($taskValue.Contains('"')){throw 'Unexpected startup quote.'}}
    return (($taskValues | ForEach-Object {'"'+$_+'"'}) -join ' ')
}
$taskValidateArgs=@($taskPrep.arguments)+@('--validate-startup')
$taskValidator=Start-Process -FilePath $taskPrep.kernel -ArgumentList (Quote-TaskArguments $taskValidateArgs) -WorkingDirectory ([IO.Path]::GetDirectoryName($taskPrep.kernel)) -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $PSScriptRoot 'kernel-validation.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'kernel-validation.stderr.txt')
if($taskValidator.ExitCode -ne 0){throw 'Offline kernel startup validation failed; no service was started.'}
$taskKernel=Start-Process -FilePath $taskPrep.kernel -ArgumentList (Quote-TaskArguments $taskPrep.arguments) -WorkingDirectory ([IO.Path]::GetDirectoryName($taskPrep.kernel)) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'kernel.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'kernel.stderr.txt')
$taskRecord=@{utc=[datetime]::UtcNow.ToString('o');kernel=@{pid=$taskKernel.Id;path=$taskPrep.kernel;arguments=$taskPrep.arguments};backend=$null;phoneInput=$false;desktopControl=$false}
$taskRecord | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath $taskProcessFile -Encoding utf8
$taskDeadline=[datetime]::UtcNow.AddSeconds(25)
do{
    Start-Sleep -Milliseconds 300
    try{$taskStatus=(Invoke-RestMethod 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 2).data}catch{$taskStatus=$null}
    if($taskKernel.HasExited){throw 'Private kernel exited. Preserve logs; do not start another.'}
}while((!$taskStatus -or $taskStatus.receivers.Count -ne 1 -or $taskStatus.receivers[0].receiver_pid -le 0) -and [datetime]::UtcNow -lt $taskDeadline)
if(!$taskStatus -or $taskStatus.process.pid -ne $taskKernel.Id -or $taskStatus.build_identity.sha256 -cne $taskPrep.kernelSha256 -or $taskStatus.allowed.Count -ne 1 -or $taskStatus.allowed[0] -cne 'C24C' -or $taskStatus.receivers.Count -ne 1 -or $taskStatus.receivers[0].name -cne 'iMouse2-C24C'){throw 'Private receiver readiness differs from preparation.'}
$taskStatus | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'receiver-ready.json') -Encoding utf8
$taskBackendArgs=@('-u',(Join-Path $taskRoot 'tools/imouse_farm_server.py'),'--no-browser','--mode','live','--port','9915','--data-dir',$taskPrep.backendData,'--draft-creation-config',$taskPrep.config)
$taskBackend=Start-Process -FilePath $taskPython -ArgumentList (Quote-TaskArguments $taskBackendArgs) -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'backend.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'backend.stderr.txt')
$taskRecord.backend=@{pid=$taskBackend.Id;path=$taskPython;arguments=$taskBackendArgs}
$taskRecord | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath $taskProcessFile -Encoding utf8
$taskDeadline=[datetime]::UtcNow.AddSeconds(20)
do{
    Start-Sleep -Milliseconds 250
    try{$taskHealth=Invoke-RestMethod 'http://127.0.0.1:9915/health' -TimeoutSec 2}catch{$taskHealth=$null}
    if($taskBackend.HasExited){throw 'Private backend exited; preserve its logs.'}
}while(!$taskHealth -and [datetime]::UtcNow -lt $taskDeadline)
if(!$taskHealth -or $taskHealth.sourceHash -cne $taskPrep.backendSourceHash -or $taskHealth.executionMode -cne 'live' -or !$taskHealth.draftRecovery.enabled -or !$taskHealth.draftRecovery.inspectionOnly -or $taskHealth.draftRecovery.storeId -cne $taskPrep.recoveryStoreId -or $taskHealth.draftRecovery.device -cne 'C24C' -or $taskHealth.draftRecovery.account -cne 'xs.halle.xo' -or $taskHealth.draftRecovery.publishing -or $taskHealth.draftRecovery.messaging){throw 'Backend identity or draft-only scope differs.'}
$taskHealth | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'backend-ready.json') -Encoding utf8
$taskState=Invoke-RestMethod 'http://127.0.0.1:9916/api/' -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 5
$taskState | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'input-before-connection.json') -Encoding utf8
[ordered]@{kernelPid=$taskKernel.Id;backendPid=$taskBackend.Id;receiverPid=$taskStatus.receivers[0].receiver_pid;receiverName=$taskStatus.receivers[0].name;live=$taskStatus.receivers[0].live;phoneInput=$false;desktopControl=$false} | ConvertTo-Json -Compress
