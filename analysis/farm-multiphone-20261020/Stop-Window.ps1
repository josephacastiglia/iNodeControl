# Stops one window's backend (and only it). Leaves the kernel, receivers and other windows running.
param([Parameter(Mandatory)][ValidatePattern('^[a-z]+(-[a-z]+)?-slot\d+$')][string]$Window)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'RackState.ps1')
$taskDir=Get-RackState "windows\$Window"
$taskPrep=Get-Content -LiteralPath (Join-Path $taskDir 'preparation.json') -Raw | ConvertFrom-Json
$taskProcs=Get-Content -LiteralPath (Join-Path $taskDir 'processes.json') -Raw | ConvertFrom-Json
# The kernel API is the one the rack preparation starts (:9916 unless the preparation says otherwise).
$taskApi='http://127.0.0.1:9916/api'
if($taskPrep.rackPreparation -and (Test-Path -LiteralPath $taskPrep.rackPreparation)){$taskApi=([string](Get-Content -LiteralPath $taskPrep.rackPreparation -Raw | ConvertFrom-Json).arguments[0]).TrimEnd('/')}
$taskBefore=(Invoke-RestMethod "$taskApi/" -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 5).data
if(@($taskBefore.phones | Where-Object {$_.id -ceq $taskPrep.phone.deviceId -and ($_.owned -or $_.active -or $_.releasing)}).Count){throw 'A run still holds this phone; let it finish or cancel it first.'}
$taskBackend=Get-CimInstance Win32_Process -Filter "ProcessId=$($taskProcs.backend.pid)"
if($taskBackend){
    if($taskBackend.CommandLine -notmatch [regex]::Escape($taskPrep.backendData)){throw 'Backend process identity changed; nothing was stopped.'}
    Stop-Process -Id $taskProcs.backend.pid -Confirm:$false
    Wait-Process -Id $taskProcs.backend.pid -Timeout 15 -ErrorAction SilentlyContinue
}
$taskTcp=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -In @($taskPrep.backendPort,$taskPrep.mediaPort))
if($taskTcp.Count){throw 'This window''s ports are still listening.'}
$taskInput=(Invoke-RestMethod "$taskApi/" -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 5).data
$taskMine=@($taskInput.phones | Where-Object {$_.id -ceq $taskPrep.phone.deviceId})
Rename-Item -LiteralPath (Join-Path $taskDir 'processes.json') -NewName ('processes-stopped-' + [datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.json')
[ordered]@{window=$Window;stopped=$true;phoneOwned=$taskMine[0].owned;phoneStopped=$taskMine[0].stopped} | ConvertTo-Json -Compress
