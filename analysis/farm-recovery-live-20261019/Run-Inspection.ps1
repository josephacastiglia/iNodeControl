param([ValidateRange(1,4)][int]$Attempt=1,[ValidateSet('none','lostAdmissionAndStatus','cancelAfterFirstAction')][string]$Faults='none')
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$taskPrep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw | ConvertFrom-Json
if($Faults -ne 'none'){
    $taskFault=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'fault-preparation.json') -Raw | ConvertFrom-Json
    $taskPrep.nativeProbe=$taskFault.path
    $taskPrep.nativeProbeSha256=$taskFault.sha256
    $taskPrep | Add-Member -NotePropertyName nativeProbeManagedSha256 -NotePropertyValue $taskFault.managedSha256 -Force
}
$taskProcesses=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'processes.json') -Raw | ConvertFrom-Json
$taskOutput=Join-Path $PSScriptRoot ('native-inspection-'+$Attempt)
if(Test-Path -LiteralPath $taskOutput){throw 'This attempt exists. Retrieve it; do not replay.'}
$taskActual=Get-CimInstance Win32_Process -Filter ('ProcessId='+$taskProcesses.kernel.pid)
if(!$taskActual -or $taskActual.ExecutablePath -cne $taskPrep.kernel){throw 'Kernel process changed.'}
$taskStatus=(Invoke-RestMethod 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 4).data
$taskReady=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'receiver-ready.json') -Raw | ConvertFrom-Json
if($taskStatus.process.pid -ne $taskProcesses.kernel.pid -or $taskStatus.build_identity.sha256 -cne $taskPrep.kernelSha256 -or $taskStatus.allowed.Count -ne 1 -or $taskStatus.allowed[0] -cne 'C24C' -or $taskStatus.receivers.Count -ne 1 -or !$taskStatus.receivers[0].live -or $taskStatus.receivers[0].receiver_pid -ne $taskReady.receivers[0].receiver_pid){throw 'Private C24C runtime/video changed.'}
$taskState=(Invoke-RestMethod 'http://127.0.0.1:9916/api/' -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 4).data
$taskPhones=@($taskState.phones)
if($taskPhones.Count -ne 1 -or $taskPhones[0].id -cne $taskPrep.expectedDeviceId -or $taskPhones[0].owned -or $taskPhones[0].active -or $taskPhones[0].stopped -or $taskPhones[0].releasing -or $taskPhones[0].release_failed){throw 'C24C is not free. No takeover allowed.'}
@{kernel=$taskStatus;input=$taskState;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ('pre-inspection-'+$Attempt+'.json')) -Encoding utf8
if((Get-FileHash -LiteralPath $taskPrep.assembly -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.nativeSha256 -or (Get-FileHash -LiteralPath $taskPrep.nativeProbe -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.nativeProbeSha256 -or (Get-FileHash -LiteralPath ([IO.Path]::ChangeExtension($taskPrep.nativeProbe,'.dll')) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.nativeProbeManagedSha256){throw 'Native binary changed.'}
$taskOptions=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'native-options-1.json') -Raw | ConvertFrom-Json
$taskOptions.output=$taskOutput
$taskOptions.dataDirectory=Join-Path $taskPrep.runDirectory ('native-live-'+$Attempt+'-data')
if($Faults -ne 'none'){$taskOptions | Add-Member -NotePropertyName faultMode -NotePropertyValue $Faults -Force}
if(Test-Path -LiteralPath $taskOptions.dataDirectory){throw 'Retained native request exists. Reconcile it before starting.'}
$taskOptionFile=Join-Path $PSScriptRoot ('native-options-'+$Attempt+'.json')
[IO.File]::WriteAllText($taskOptionFile,($taskOptions | ConvertTo-Json))
$taskProbe=Start-Process -FilePath $taskPrep.nativeProbe -ArgumentList ('"'+$taskOptionFile+'"') -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot ('native-inspection-'+$Attempt+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ('native-inspection-'+$Attempt+'.stderr.txt'))
@{pid=$taskProbe.Id;path=$taskPrep.nativeProbe;exeSha256=$taskPrep.nativeProbeSha256;managedSha256=$taskPrep.nativeProbeManagedSha256;options=$taskOptionFile;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot ('driver-'+$Attempt+'.json')) -Encoding utf8
$taskProbe.WaitForExit()
@{pid=$taskProbe.Id;exitCode=$taskProbe.ExitCode;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot ('driver-'+$Attempt+'.exit.json')) -Encoding utf8
Get-Content -LiteralPath (Join-Path $PSScriptRoot ('driver-'+$Attempt+'.exit.json'))
