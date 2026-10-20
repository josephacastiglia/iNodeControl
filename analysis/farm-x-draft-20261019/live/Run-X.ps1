# One X creation through the headless native handler. Never replays an
# existing attempt or native data folder; C24C must be free and live. The
# attempt output names the bound X handle, so it stays in the private run folder.
param([ValidateRange(1,5)][int]$Attempt=1)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$taskPrep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw | ConvertFrom-Json
$taskProcesses=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'processes.json') -Raw | ConvertFrom-Json
$taskOutput=Join-Path $taskPrep.runDirectory ('native-x-'+$Attempt)
if(Test-Path -LiteralPath $taskOutput){throw 'This attempt exists. Retrieve it; do not replay.'}
# A later attempt is a new request, never a replay. It is allowed only while every earlier
# attempt in this window is a confirmed, cleaned-up stop before any media import.
foreach($taskEarlier in @(1..$Attempt | Where-Object {$_ -lt $Attempt})){
    $taskEarlierResult=Join-Path ([regex]::Replace($taskOutput,'\d+$',[string]$taskEarlier)) 'result.json'
    if(!(Test-Path -LiteralPath $taskEarlierResult)){throw ('Attempt '+$taskEarlier+' has no retained result. No new attempt.')}
    $taskEarlierRun=(Get-Content -LiteralPath $taskEarlierResult -Raw | ConvertFrom-Json).run
    if(!$taskEarlierRun.terminal -or $taskEarlierRun.state -cne 'review_required' -or !$taskEarlierRun.retryBeforeImportAllowed -or $taskEarlierRun.cleanup -cne 'confirmed'){throw ('Attempt '+$taskEarlier+' is not a confirmed stop before import. No new attempt.')}
}
$taskActual=Get-CimInstance Win32_Process -Filter ('ProcessId='+$taskProcesses.kernel.pid)
if(!$taskActual -or $taskActual.ExecutablePath -cne $taskPrep.kernel){throw 'Kernel process changed.'}
$taskStatus=(Invoke-RestMethod 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 4).data
$taskReady=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'receiver-ready.json') -Raw | ConvertFrom-Json
if($taskStatus.process.pid -ne $taskProcesses.kernel.pid -or $taskStatus.build_identity.sha256 -cne $taskPrep.kernelSha256 -or $taskStatus.allowed.Count -ne 1 -or $taskStatus.allowed[0] -cne 'C24C' -or $taskStatus.receivers.Count -ne 1 -or !$taskStatus.receivers[0].live -or $taskStatus.receivers[0].receiver_pid -ne $taskReady.receivers[0].receiver_pid){throw 'Private C24C runtime/video changed.'}
$taskState=(Invoke-RestMethod 'http://127.0.0.1:9916/api/' -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 4).data
$taskPhones=@($taskState.phones)
if($taskPhones.Count -ne 1 -or $taskPhones[0].id -cne $taskPrep.expectedDeviceId -or $taskPhones[0].owned -or $taskPhones[0].active -or $taskPhones[0].stopped -or $taskPhones[0].releasing -or $taskPhones[0].release_failed){throw 'C24C is not free. No takeover allowed.'}
@{kernel=$taskStatus;input=$taskState;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ('pre-x-'+$Attempt+'.json')) -Encoding utf8
if((Get-FileHash -LiteralPath $taskPrep.assembly -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.nativeSha256 -or (Get-FileHash -LiteralPath $taskPrep.nativeProbe -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.nativeProbeSha256 -or (Get-FileHash -LiteralPath ([IO.Path]::ChangeExtension($taskPrep.nativeProbe,'.dll')) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.nativeProbeManagedSha256){throw 'Native binary changed.'}
$taskOptions=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'native-options-1.json') -Raw | ConvertFrom-Json
$taskOptions.output=$taskOutput
$taskOptions.dataDirectory=Join-Path $taskPrep.runDirectory ('native-x-'+$Attempt+'-data')
if(Test-Path -LiteralPath $taskOptions.dataDirectory){throw 'Retained native request exists. Reconcile it before starting.'}
$taskOptionFile=Join-Path $PSScriptRoot ('native-options-run-'+$Attempt+'.json')
if(Test-Path -LiteralPath $taskOptionFile){throw 'Run options already exist for this attempt.'}
[IO.File]::WriteAllText($taskOptionFile,($taskOptions | ConvertTo-Json))
$taskProbe=Start-Process -FilePath $taskPrep.nativeProbe -ArgumentList ('"'+$taskOptionFile+'"') -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot ('native-x-'+$Attempt+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ('native-x-'+$Attempt+'.stderr.txt'))
@{pid=$taskProbe.Id;path=$taskPrep.nativeProbe;exeSha256=$taskPrep.nativeProbeSha256;managedSha256=$taskPrep.nativeProbeManagedSha256;options=$taskOptionFile;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot ('driver-'+$Attempt+'.json')) -Encoding utf8
$taskProbe.WaitForExit()
@{pid=$taskProbe.Id;exitCode=$taskProbe.ExitCode;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot ('driver-'+$Attempt+'.exit.json')) -Encoding utf8
Get-Content -LiteralPath (Join-Path $PSScriptRoot ('driver-'+$Attempt+'.exit.json'))
