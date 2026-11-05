# Restarts or withdraws ONE receiver on a running multi-phone kernel (built 4 Nov or later), without
# stopping the kernel or any other receiver. The kernel stops that board's UxPlay, confirms its exit,
# sends the AirPlay goodbye a killed UxPlay never sends, then starts it again (default) or keeps it held.
# Sends no phone input. A phone whose input another controller leases is refused unless -Token is that
# lease's token. After a restart the phone must choose the receiver again in Screen Mirroring.
#   -Board C24C [-Stage slots | -Rack A|B] [-Hold] [-Withdraw] [-Token <lease token>]
#   -Hold      stop and withdraw, start nothing (Release-Receiver.ps1 advertises it again)
#   -Withdraw  same as -Hold, through /device/airplay/withdraw
param([Parameter(Mandatory)][ValidatePattern('^[0-9A-Fa-f]{4}$')][string]$Board,[ValidateSet('','held','slots')][string]$Stage='',
    [ValidateSet('','A','B')][string]$Rack='',[switch]$Hold,[switch]$Withdraw,[string]$Token='')
$ErrorActionPreference='Stop'
# State (preparations, process records, logs) sits beside this script in a checkout; installed, Farm.ps1 sets
# IMOUSE_FARM_DATA and the state is in the data folder. Python: IMOUSE_FARM_PYTHON when installed, else PATH.
$taskState=if($env:IMOUSE_FARM_DATA){Join-Path $env:IMOUSE_FARM_DATA 'analysis\farm-multiphone-20261020'}else{$PSScriptRoot}
if($Stage -and $Rack){throw 'Choose -Stage or -Rack, not both.'}
if(!$Stage -and !$Rack){$Stage='slots'}
$taskDir=if($Rack){Join-Path $taskState ('rack-'+$Rack.ToLowerInvariant())}else{Join-Path $taskState $Stage}
$taskPrep=Get-Content -LiteralPath (Join-Path $taskDir 'preparation.json') -Raw | ConvertFrom-Json
if([string]$taskPrep.rack -cne $Rack){throw "The preparation's rack ('$($taskPrep.rack)') is not -Rack '$Rack'."}
$taskApi=([string]$taskPrep.arguments[0]).TrimEnd('/')
$taskProcs=Get-Content -LiteralPath (Join-Path $taskDir 'processes.json') -Raw | ConvertFrom-Json
$taskKernel=Get-CimInstance Win32_Process -Filter "ProcessId=$($taskProcs.kernel.pid)"
if(!$taskKernel -or $taskKernel.ExecutablePath -ne $taskPrep.kernel){throw 'The prepared kernel is not running.'}
$Board=$Board.ToUpperInvariant()
if(@($taskPrep.receivers | ForEach-Object {$_.board.ToUpperInvariant()}) -notcontains $Board){throw "Board $Board has no receiver on this kernel."}
$taskBefore=@((Invoke-RestMethod "$taskApi/kernel/status" -TimeoutSec 3).data.receivers)
$taskName=@($taskPrep.receivers | Where-Object {$_.board.ToUpperInvariant() -eq $Board})[0].name
$taskOld=@($taskBefore | Where-Object name -eq $taskName)[0]
if($null -eq $taskOld.receiver_generation){throw 'This kernel predates per-receiver restart; nothing was changed.'}
$taskFun=if($Withdraw){'/device/airplay/withdraw'}else{'/device/airplay/restart'}
$taskData=@{pid=$Board;hold=[bool]($Hold -or $Withdraw)}
if($Token){$taskData.token=$Token}
$taskBody=@{fun=$taskFun;data=$taskData} | ConvertTo-Json -Compress
# The stop waits up to 5 s for exit confirmation and the goodbye takes about 2 s.
$taskResult=(Invoke-RestMethod -Method Post -Uri "$taskApi/" -Body $taskBody -ContentType 'application/json' -TimeoutSec 30).data
$taskWantRunning=!($Hold -or $Withdraw) -and $taskResult.code -eq 0
$taskDeadline=[datetime]::UtcNow.AddSeconds(20)
do{
    Start-Sleep -Milliseconds 500
    $taskRow=@((Invoke-RestMethod "$taskApi/kernel/status" -TimeoutSec 3).data.receivers | Where-Object name -eq $taskName)[0]
}while($taskWantRunning -and $taskRow.receiver_pid -le 0 -and [datetime]::UtcNow -lt $taskDeadline)
# Other receivers must be exactly as they were: same PIDs (0 stays 0), same generations.
$taskAfter=@((Invoke-RestMethod "$taskApi/kernel/status" -TimeoutSec 3).data.receivers)
$taskMoved=@($taskBefore | Where-Object name -ne $taskName | ForEach-Object {
    $n=$_.name; $now=@($taskAfter | Where-Object name -eq $n)[0]
    if($now.receiver_pid -ne $_.receiver_pid -or $now.receiver_generation -ne $_.receiver_generation){$n}
})
$taskRecord=[pscustomobject]@{utc=[datetime]::UtcNow.ToString('o');rack=$Rack;board=$Board;receiver=$taskName;action=$taskFun;hold=$taskData.hold;
    code=$taskResult.code;message=$taskResult.message;withdrawn=$taskResult.withdrawn;started=$taskResult.started;
    pid_before=$taskOld.receiver_pid;pid_after=$taskRow.receiver_pid;generation_before=$taskOld.receiver_generation;generation_after=$taskRow.receiver_generation;
    state=$taskRow.receiver_state;others_changed=@($taskMoved)}
$taskRecord | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $taskDir 'restarts.jsonl') -Encoding utf8
if($taskResult.code -ne 0){throw "Kernel refused or reported a problem (code $($taskResult.code)): $($taskResult.message)"}
if($taskMoved.Count){throw ('Other receivers changed during the restart: ' + ($taskMoved -join ', '))}
if($taskWantRunning -and $taskRow.receiver_pid -le 0){throw "$taskName did not start again within 20 s."}
$taskRecord
