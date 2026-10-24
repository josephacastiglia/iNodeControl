# Permission-prompt validation window. Run only in an agreed window with the operator present.
# Part A starts the normal private C24C kernel (observe and trials); part B starts the same kernel
# with the move-only absolute probe. No farm backend or media service is started.
# Refuses if any rack/test service or listener exists, or while the other part is not restored.
# -CheckOnly runs the same refusals and the read-only preparation recheck, then starts nothing.
param([Parameter(Mandatory)][ValidateSet('A','B')][string]$Part,[switch]$CheckOnly)
$ErrorActionPreference='Stop'
$taskPrep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw | ConvertFrom-Json
$taskPython=$taskPrep.python
$taskPart=$taskPrep.parts.$Part
$taskProcessFile=Join-Path $PSScriptRoot ('processes-'+$Part+'.json')
if(Test-Path -LiteralPath $taskProcessFile){throw ('Part '+$Part+' already has a process record. Do not start duplicates.')}
$taskOther=if($Part -eq 'A'){'B'}else{'A'}
if(Test-Path -LiteralPath (Join-Path $PSScriptRoot ('processes-'+$taskOther+'.json'))){
    $taskOtherRestore=Join-Path $PSScriptRoot ('restoration-'+$taskOther+'.json')
    if(!(Test-Path -LiteralPath $taskOtherRestore) -or !((Get-Content -LiteralPath $taskOtherRestore -Raw | ConvertFrom-Json).restored)){throw ('Part '+$taskOther+' has not been stopped and restored. Nothing was started.')}
}
$taskProcesses=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('iMouse2.exe','iMouse2.Kernel.exe','uxplay.exe','NativeProbe.exe','ReelProbe.exe','TikTokProbe.exe','XProbe.exe') -or ($_.CommandLine -and $_.CommandLine -match 'python[^\r\n]*(imouse_farm_server|farm_prompt_validation)\.py|dotnet[^\r\n]*iMouse2(\.Kernel)?\.dll') } | Select-Object ProcessId,ExecutablePath,CommandLine)
$taskTcp=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -In @(9911,9913,9914,9915,9916,9917,7110,7111,7112,7120,7121,7122) | Select-Object LocalAddress,LocalPort,OwningProcess)
$taskUdp=@(Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object LocalPort -In @(7110,7111,7112,7120,7121,7122) | Select-Object LocalAddress,LocalPort,OwningProcess)
$taskRackFile=if($CheckOnly){Join-Path $PSScriptRoot ('check-only-'+$Part+'.json')}else{Join-Path $PSScriptRoot ('initial-rack-'+$Part+'.json')}
[ordered]@{utc=[datetime]::UtcNow.ToString('o');part=$Part;checkOnly=[bool]$CheckOnly;processes=$taskProcesses;tcp=$taskTcp;udp=$taskUdp;phoneInput=$false} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $taskRackFile -Encoding utf8
if($taskProcesses.Count -or $taskTcp.Count -or $taskUdp.Count){throw 'Rack/test services are active. Nothing was stopped or started.'}
& $taskPython (Join-Path $PSScriptRoot 'verify_preparation.py') --part $Part
if($LASTEXITCODE -ne 0){throw 'Read-only preparation recheck failed; nothing was started.'}
if($CheckOnly){Write-Output ('Part '+$Part+' check only: no rack/test service or listener, and the preparation matches. Nothing was started.');return}
function Quote-TaskArguments($taskValues){
    foreach($taskValue in $taskValues){if($taskValue.Contains('"')){throw 'Unexpected startup quote.'}}
    return (($taskValues | ForEach-Object {'"'+$_+'"'}) -join ' ')
}
$taskKernelFolder=[IO.Path]::GetDirectoryName($taskPrep.kernel)
$taskValidateArgs=@($taskPart.arguments)+@('--validate-startup')
$taskValidator=Start-Process -FilePath $taskPrep.kernel -ArgumentList (Quote-TaskArguments $taskValidateArgs) -WorkingDirectory $taskKernelFolder -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $PSScriptRoot ('kernel-validation-'+$Part+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ('kernel-validation-'+$Part+'.stderr.txt'))
if($taskValidator.ExitCode -ne 0){throw 'Offline kernel startup validation failed; no service was started.'}
$taskValidation=Get-Content -LiteralPath (Join-Path $PSScriptRoot ('kernel-validation-'+$Part+'.stdout.txt')) -Raw | ConvertFrom-Json
$taskProbeBoard=if($Part -eq 'B'){'C24C'}else{$null}
if(!$taskValidation.valid -or $taskValidation.build.sha256 -cne $taskPrep.kernelSha256 -or $taskValidation.absolute_probe_board -cne $taskProbeBoard -or @($taskValidation.hid_reply_boards).Count -ne [int]($Part -eq 'B') -or $taskValidation.receiver_count -ne 1){throw 'Kernel startup validation differs from the prepared part; no service was started.'}
$taskKernel=Start-Process -FilePath $taskPrep.kernel -ArgumentList (Quote-TaskArguments $taskPart.arguments) -WorkingDirectory $taskKernelFolder -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot ('kernel-'+$Part+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ('kernel-'+$Part+'.stderr.txt'))
[ordered]@{utc=[datetime]::UtcNow.ToString('o');part=$Part;kernel=@{pid=$taskKernel.Id;path=$taskPrep.kernel;arguments=$taskPart.arguments};backend=$null;phoneInput=$false;desktopControl=$false} | ConvertTo-Json -Depth 9 | Set-Content -LiteralPath $taskProcessFile -Encoding utf8
$taskDeadline=[datetime]::UtcNow.AddSeconds(25)
do{
    Start-Sleep -Milliseconds 300
    try{$taskRaw=(Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 2).Content;$taskStatus=($taskRaw | ConvertFrom-Json).data}catch{$taskStatus=$null}
    if($taskKernel.HasExited){throw 'Private kernel exited. Preserve logs; do not start another.'}
}while((!$taskStatus -or @($taskStatus.receivers).Count -ne 1 -or $taskStatus.receivers[0].receiver_pid -le 0) -and [datetime]::UtcNow -lt $taskDeadline)
# Kept before the checks, so Stop-PromptWindow.ps1 can still stop a kernel that fails them.
if($taskStatus){[IO.File]::WriteAllText((Join-Path $PSScriptRoot ('receiver-ready-'+$Part+'.json')),$taskRaw)}
if(!$taskStatus -or $taskStatus.process.pid -ne $taskKernel.Id -or $taskStatus.build_identity.sha256 -cne $taskPrep.kernelSha256 -or @($taskStatus.allowed).Count -ne 1 -or $taskStatus.allowed[0] -cne 'C24C' -or @($taskStatus.receivers).Count -ne 1 -or $taskStatus.receivers[0].name -cne 'iMouse2-C24C' -or $taskStatus.input_configuration.absolute_probe_board -cne $taskProbeBoard -or @($taskStatus.input_configuration.hid_reply_boards).Count -ne [int]($Part -eq 'B')){throw 'Private kernel readiness differs from the prepared part.'}
if($Part -eq 'B' -and $taskStatus.control_compatibility.absolute_probe -notlike 'experimental moves only*'){throw 'The kernel does not report the move-only probe.'}
$taskState=(Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:9916/api/' -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 5).Content
[IO.File]::WriteAllText((Join-Path $PSScriptRoot ('input-before-'+$Part+'.json')),$taskState)
[ordered]@{part=$Part;kernel=$taskPart.kernel;kernelPid=$taskKernel.Id;receiverPid=$taskStatus.receivers[0].receiver_pid;receiverName=$taskStatus.receivers[0].name;live=$taskStatus.receivers[0].live;absoluteProbe=$taskStatus.input_configuration.absolute_probe_board;phoneInput=$false;desktopControl=$false} | ConvertTo-Json -Compress
