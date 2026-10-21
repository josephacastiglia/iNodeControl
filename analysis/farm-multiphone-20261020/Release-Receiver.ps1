# Advertises one held receiver on the running one-at-a-time kernel, so the phone being
# connected sees exactly one new Screen Mirroring choice. Sends no phone input.
param([Parameter(Mandatory)][ValidatePattern('^[0-9A-Fa-f]{4}$')][string]$Board,[ValidateSet('held')][string]$Stage='held')
$ErrorActionPreference='Stop'
$taskDir=Join-Path $PSScriptRoot $Stage
$taskPrep=Get-Content -LiteralPath (Join-Path $taskDir 'preparation.json') -Raw | ConvertFrom-Json
$taskProcs=Get-Content -LiteralPath (Join-Path $taskDir 'processes.json') -Raw | ConvertFrom-Json
$taskKernel=Get-CimInstance Win32_Process -Filter "ProcessId=$($taskProcs.kernel.pid)"
if(!$taskKernel -or $taskKernel.ExecutablePath -ne $taskPrep.kernel){throw 'The prepared kernel is not running.'}
if(@($taskPrep.held) -notcontains $Board.ToUpperInvariant()){throw "Board $Board is not one of this kernel's held receivers."}
$taskBody=@{fun='/device/airplay/connect';data=@{pid=$Board.ToUpperInvariant()}} | ConvertTo-Json -Compress
$taskResult=(Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:9916/api/' -Body $taskBody -ContentType 'application/json' -TimeoutSec 5).data
if($taskResult.code -ne 0){throw "Kernel refused: $($taskResult.message)"}
$taskName=$taskResult.name
$taskDeadline=[datetime]::UtcNow.AddSeconds(20)
do{
    Start-Sleep -Milliseconds 500
    $taskRow=@((Invoke-RestMethod 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 3).data.receivers | Where-Object name -eq $taskName)[0]
}while($taskRow.receiver_pid -le 0 -and [datetime]::UtcNow -lt $taskDeadline)
$taskRecord=[pscustomobject]@{utc=[datetime]::UtcNow.ToString('o');board=$Board.ToUpperInvariant();receiver=$taskName;started=$taskResult.started;receiver_pid=$taskRow.receiver_pid;state=$taskRow.receiver_state}
$taskRecord | ConvertTo-Json -Compress | Add-Content -LiteralPath (Join-Path $taskDir 'releases.jsonl') -Encoding utf8
if($taskRow.receiver_pid -le 0){throw "$taskName did not start within 20 s."}
$taskRecord
