# Private kernel with four receivers (C24C, C214, 724E, F215) so each phone can mirror.
# Refuses if any rack/test service or listener exists. Starts no backend and sends no input.
# -Stage held starts the one-at-a-time mode: every receiver held until Release-Receiver.ps1.
param([ValidateSet('','held','slots')][string]$Stage='')
$ErrorActionPreference='Stop'
$taskDir=if($Stage){Join-Path $PSScriptRoot $Stage}else{$PSScriptRoot}
$taskProcessFile=Join-Path $taskDir 'processes.json'
if(Test-Path -LiteralPath $taskProcessFile){throw 'This multi-phone kernel already has a process record. Do not start duplicates.'}
$taskPrep=Get-Content -LiteralPath (Join-Path $taskDir 'preparation.json') -Raw | ConvertFrom-Json
$taskHeld=@($taskPrep.held | Where-Object {$_})
$taskExpected=@($taskPrep.receivers).Count-$taskHeld.Count
$taskPorts=@(9911,9913,9914,9915,9916,9917)+@($taskPrep.receivers | ForEach-Object {$_.port; $_.port+1; $_.port+2})
$taskProcesses=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('iMouse2.exe','iMouse2.Kernel.exe','uxplay.exe','ReelProbe.exe','TikTokProbe.exe','XProbe.exe') -or ($_.CommandLine -and $_.CommandLine -match 'python[^\r\n]*imouse_farm_server\.py') })
$taskTcp=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -In $taskPorts)
if($taskProcesses.Count -or $taskTcp.Count){throw 'Rack/test services are active. Nothing was stopped or started.'}
if((Get-FileHash -LiteralPath ([IO.Path]::ChangeExtension($taskPrep.kernel,'.dll')) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.kernelSha256){throw 'Kernel changed.'}
foreach($taskName in 'devices.json','receivers.json','pointer-calibration.json'){
    if((Get-FileHash -LiteralPath (Join-Path $taskPrep.runDirectory "data\$taskName") -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.dataSha256.$taskName){throw "Prepared $taskName changed."}
}
function Quote-TaskArguments($taskValues){ foreach($v in $taskValues){if($v.Contains('"')){throw 'Unexpected quote.'}}; (($taskValues | ForEach-Object {'"'+$_+'"'}) -join ' ') }
$taskValidator=Start-Process -FilePath $taskPrep.kernel -ArgumentList (Quote-TaskArguments (@($taskPrep.arguments)+@('--validate-startup'))) -WorkingDirectory ([IO.Path]::GetDirectoryName($taskPrep.kernel)) -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $taskDir 'kernel-validation.stdout.txt') -RedirectStandardError (Join-Path $taskDir 'kernel-validation.stderr.txt')
if($taskValidator.ExitCode -ne 0){throw 'Offline kernel startup validation failed; nothing was started.'}
$taskKernel=Start-Process -FilePath $taskPrep.kernel -ArgumentList (Quote-TaskArguments $taskPrep.arguments) -WorkingDirectory ([IO.Path]::GetDirectoryName($taskPrep.kernel)) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskDir 'kernel.stdout.txt') -RedirectStandardError (Join-Path $taskDir 'kernel.stderr.txt')
@{utc=[datetime]::UtcNow.ToString('o');kernel=@{pid=$taskKernel.Id;path=$taskPrep.kernel};phoneInput=$false} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $taskProcessFile -Encoding utf8
$taskDeadline=[datetime]::UtcNow.AddSeconds(40)
do{
    Start-Sleep -Milliseconds 500
    try{$taskStatus=(Invoke-RestMethod 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 3).data}catch{$taskStatus=$null}
    if($taskKernel.HasExited){throw 'Kernel exited. Preserve its logs.'}
}while((!$taskStatus -or @($taskStatus.receivers | Where-Object {$_.receiver_pid -gt 0}).Count -ne $taskExpected -or @($taskStatus.receivers | Where-Object {$_.receiver_state -eq 'held'}).Count -ne $taskHeld.Count) -and [datetime]::UtcNow -lt $taskDeadline)
$taskStatus | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $taskDir 'receivers-ready.json') -Encoding utf8
if(!$taskStatus -or $taskStatus.build_identity.sha256 -cne $taskPrep.kernelSha256 -or @($taskStatus.allowed).Count -ne @($taskPrep.inputEnabled).Count){throw 'Kernel identity or allow-list differs.'}
if(@($taskStatus.receivers | Where-Object {$_.receiver_state -eq 'held'}).Count -ne $taskHeld.Count){throw 'Held receivers differ from the preparation.'}
$taskStatus.receivers | ForEach-Object { [pscustomobject]@{receiver=$_.name; state=$_.receiver_state; pid=$_.receiver_pid; live=$_.live} } | Format-Table -AutoSize | Out-String
