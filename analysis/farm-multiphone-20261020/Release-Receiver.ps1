# Advertises one held (or withdrawn) receiver on a running multi-phone kernel, so the phone being
# connected sees exactly one new Screen Mirroring choice. Sends no phone input.
#   -Stage held|slots  the single kernel (default 'held');  -Rack A|B  that rack's own kernel.
param([Parameter(Mandatory)][ValidatePattern('^[0-9A-Fa-f]{4}$')][string]$Board,[ValidateSet('','held','slots')][string]$Stage='',[ValidateSet('','A','B')][string]$Rack='')
$ErrorActionPreference='Stop'
# State (preparations, process records, logs) sits beside this script in a checkout; installed, Farm.ps1 sets
# IMOUSE_FARM_DATA and the state is in the data folder. Python: IMOUSE_FARM_PYTHON when installed, else PATH.
$taskState=if($env:IMOUSE_FARM_DATA){Join-Path $env:IMOUSE_FARM_DATA 'analysis\farm-multiphone-20261020'}else{$PSScriptRoot}
if($Stage -and $Rack){throw 'Choose -Stage or -Rack, not both.'}
if(!$Stage -and !$Rack){$Stage='held'}
$taskDir=if($Rack){Join-Path $taskState ('rack-'+$Rack.ToLowerInvariant())}else{Join-Path $taskState $Stage}
$taskPrep=Get-Content -LiteralPath (Join-Path $taskDir 'preparation.json') -Raw | ConvertFrom-Json
if([string]$taskPrep.rack -cne $Rack){throw "The preparation's rack ('$($taskPrep.rack)') is not -Rack '$Rack'."}
$taskApi=([string]$taskPrep.arguments[0]).TrimEnd('/')
$taskProcs=Get-Content -LiteralPath (Join-Path $taskDir 'processes.json') -Raw | ConvertFrom-Json
$taskKernel=Get-CimInstance Win32_Process -Filter "ProcessId=$($taskProcs.kernel.pid)"
if(!$taskKernel -or $taskKernel.ExecutablePath -ne $taskPrep.kernel){throw 'The prepared kernel is not running.'}
$Board=$Board.ToUpperInvariant()
if(@($taskPrep.receivers | ForEach-Object {$_.board.ToUpperInvariant()}) -notcontains $Board){throw "Board $Board has no receiver on this kernel."}
$taskBody=@{fun='/device/airplay/connect';data=@{pid=$Board}} | ConvertTo-Json -Compress
$taskResult=(Invoke-RestMethod -Method Post -Uri "$taskApi/" -Body $taskBody -ContentType 'application/json' -TimeoutSec 5).data
if($taskResult.code -ne 0){throw "Kernel refused: $($taskResult.message)"}
$taskName=$taskResult.name
$taskDeadline=[datetime]::UtcNow.AddSeconds(20)
do{
    Start-Sleep -Milliseconds 500
    $taskRow=@((Invoke-RestMethod "$taskApi/kernel/status" -TimeoutSec 3).data.receivers | Where-Object name -eq $taskName)[0]
}while($taskRow.receiver_pid -le 0 -and [datetime]::UtcNow -lt $taskDeadline)
$taskRecord=[pscustomobject]@{utc=[datetime]::UtcNow.ToString('o');rack=$Rack;board=$Board;receiver=$taskName;started=$taskResult.started;receiver_pid=$taskRow.receiver_pid;state=$taskRow.receiver_state}
$taskRecord | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $taskDir 'releases.jsonl') -Encoding utf8
if($taskRow.receiver_pid -le 0){throw "$taskName did not start within 20 s."}
$taskRecord
