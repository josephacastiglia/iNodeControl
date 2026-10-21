# Stops the multi-phone kernel with Ctrl+C (it then ends each receiver it started) and
# confirms no kernel, receiver or listener remains. Never force-kills anything.
param([ValidateSet('','held')][string]$Stage='')
$ErrorActionPreference='Stop'
$taskDir=if($Stage){Join-Path $PSScriptRoot $Stage}else{$PSScriptRoot}
$taskPrep=Get-Content -LiteralPath (Join-Path $taskDir 'preparation.json') -Raw | ConvertFrom-Json
$taskProcs=Get-Content -LiteralPath (Join-Path $taskDir 'processes.json') -Raw | ConvertFrom-Json
$taskHelper=Join-Path $PSScriptRoot '..\..\tools\kernel-window\Stop-ConsoleProcessGracefully.ps1'
if(Get-Process -Id $taskProcs.kernel.pid -ErrorAction SilentlyContinue){
    # The helper detaches from its console, so it runs in its own PowerShell process.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskHelper -ProcessId $taskProcs.kernel.pid -ExpectedPath $taskPrep.kernel
    if($LASTEXITCODE){throw "Graceful stop reported exit $LASTEXITCODE; inspect before doing anything else."}
}
$taskPorts=@(9916)+@($taskPrep.receivers | ForEach-Object {$_.port; $_.port+1; $_.port+2})
$taskLeft=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('iMouse2.Kernel.exe','uxplay.exe') })
$taskTcp=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -In $taskPorts)
if($taskLeft.Count -or $taskTcp.Count){throw "Still present: $($taskLeft.Count) processes, $($taskTcp.Count) listeners."}
# The kernel kills receivers, so they never send their mDNS goodbye; send it for them, or every
# phone keeps listing the stopped names for 75 minutes.
$taskBoards=@($taskPrep.receivers | ForEach-Object {'--board'; $_.board})
& python (Join-Path $PSScriptRoot '..\..\tools\mdns_goodbye.py') --receivers (Join-Path $taskPrep.runDirectory 'data\receivers.json') @taskBoards
eceivers.json') @taskBoards
if($LASTEXITCODE){throw 'Receivers stopped, but their AirPlay names were not withdrawn.'}
Rename-Item -LiteralPath (Join-Path $taskDir 'processes.json') -NewName ('processes-stopped-' + [datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.json')
'Stopped: no kernel, receiver or listener remains.'
