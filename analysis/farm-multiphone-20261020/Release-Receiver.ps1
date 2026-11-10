# Advertises one held (or withdrawn) receiver on the running kernel, so the phone being connected sees
# exactly one new Screen Mirroring choice. Sends no phone input. Every answer the kernel gives goes to
# releases.jsonl, a refusal too ('problem' says what went wrong); the bring-up (rack_recovery.py) calls
# this script and reads that record.
#   -Board C24C
param([Parameter(Mandatory)][ValidatePattern('^[0-9A-Fa-f]{4}$')][string]$Board)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'RackState.ps1')
$taskDir=Get-RackState 'slots'
$taskPrep=Get-Content -LiteralPath (Join-Path $taskDir 'preparation.json') -Raw | ConvertFrom-Json
$taskApi=([string]$taskPrep.arguments[0]).TrimEnd('/')
$taskProcs=Get-Content -LiteralPath (Join-Path $taskDir 'processes.json') -Raw | ConvertFrom-Json
$taskKernel=Get-CimInstance Win32_Process -Filter "ProcessId=$($taskProcs.kernel.pid)"
if(!$taskKernel -or $taskKernel.ExecutablePath -ne $taskPrep.kernel){throw 'The prepared kernel is not running.'}
$Board=$Board.ToUpperInvariant()
if(@($taskPrep.receivers | ForEach-Object {$_.board.ToUpperInvariant()}) -notcontains $Board){throw "Board $Board has no receiver on this kernel."}
$taskBody=@{fun='/device/airplay/connect';data=@{pid=$Board}} | ConvertTo-Json -Compress
$taskResult=(Invoke-RestMethod -Method Post -Uri "$taskApi/" -Body $taskBody -ContentType 'application/json' -TimeoutSec 5).data
$taskName=@($taskPrep.receivers | Where-Object {$_.board.ToUpperInvariant() -eq $Board})[0].name
$taskRow=$null
if($taskResult.code -eq 0){
    $taskDeadline=[datetime]::UtcNow.AddSeconds(20)
    do{
        Start-Sleep -Milliseconds 500
        $taskRow=@((Invoke-RestMethod "$taskApi/kernel/status" -TimeoutSec 3).data.receivers | Where-Object name -eq $taskName)[0]
    }while($taskRow.receiver_pid -le 0 -and [datetime]::UtcNow -lt $taskDeadline)
}
$taskProblem=if($taskResult.code -ne 0){"Kernel refused: $($taskResult.message)"}elseif($taskRow.receiver_pid -le 0){"$taskName did not start within 20 s."}else{''}
$taskRecord=[pscustomobject]@{utc=[datetime]::UtcNow.ToString('o');board=$Board;receiver=$taskName;code=$taskResult.code;started=$taskResult.started;receiver_pid=$taskRow.receiver_pid;state=$taskRow.receiver_state;problem=$taskProblem}
$taskRecord | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $taskDir 'releases.jsonl') -Encoding utf8
if($taskProblem){throw $taskProblem}
$taskRecord
