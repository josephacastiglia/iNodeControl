# Stops a multi-phone kernel with Ctrl+C (it then ends each receiver it started), confirms nothing of it
# remains, and withdraws its receivers' AirPlay names. Never force-kills anything.
#   -Stage held|slots  the single kernel: afterwards no kernel, receiver or listener may remain at all.
#   -Rack A|B          one rack's kernel: afterwards none of this rack's kernel, receivers or listeners may
#                      remain; the other rack's kernel and phones keep running.
param([ValidateSet('','held','slots')][string]$Stage='',[ValidateSet('','A','B')][string]$Rack='')
$ErrorActionPreference='Stop'
# State (preparations, process records, logs) sits beside this script in a checkout; installed, Farm.ps1 sets
# IMOUSE_FARM_DATA and the state is in the data folder. Python: IMOUSE_FARM_PYTHON when installed, else PATH.
$taskState=if($env:IMOUSE_FARM_DATA){Join-Path $env:IMOUSE_FARM_DATA 'analysis\farm-multiphone-20261020'}else{$PSScriptRoot}
$taskPy=if($env:IMOUSE_FARM_PYTHON){$env:IMOUSE_FARM_PYTHON}else{'python'}
if($Stage -and $Rack){throw 'Choose -Stage or -Rack, not both.'}
$taskDir=if($Rack){Join-Path $taskState ('rack-'+$Rack.ToLowerInvariant())}elseif($Stage){Join-Path $taskState $Stage}else{$taskState}
$taskPrepFile=Join-Path $taskDir 'preparation.json'
$taskPrep=Get-Content -LiteralPath $taskPrepFile -Raw | ConvertFrom-Json
if([string]$taskPrep.rack -cne $Rack){throw "The preparation's rack ('$($taskPrep.rack)') is not -Rack '$Rack'."}
$taskApi=([string]$taskPrep.arguments[0]).TrimEnd('/')
$taskProcs=Get-Content -LiteralPath (Join-Path $taskDir 'processes.json') -Raw | ConvertFrom-Json
$taskHelper=Join-Path $PSScriptRoot '..\..\tools\kernel-window\Stop-ConsoleProcessGracefully.ps1'
if(Get-Process -Id $taskProcs.kernel.pid -ErrorAction SilentlyContinue){
    # The helper detaches from its console, so it runs in its own PowerShell process.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskHelper -ProcessId $taskProcs.kernel.pid -ExpectedPath $taskPrep.kernel
    if($LASTEXITCODE){throw "Graceful stop reported exit $LASTEXITCODE; inspect before doing anything else."}
}
$taskSnap=@{
    processes=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('iMouse2.Kernel.exe','uxplay.exe') } | ForEach-Object { @{Name=$_.Name;ProcessId=$_.ProcessId;CommandLine=$_.CommandLine} })
    listeners=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object LocalPort | Sort-Object -Unique)
} | ConvertTo-Json -Depth 4 -Compress
$taskRackArgs=if($Rack){@('--rack',$Rack)}else{@()}
$taskVerdict=$taskSnap | & $taskPy (Join-Path $PSScriptRoot 'rack_kernels.py') check-stopped --prep $taskPrepFile @taskRackArgs
if($LASTEXITCODE -eq 3){throw "Still present: $taskVerdict"}elseif($LASTEXITCODE){throw "Stop check failed (exit $LASTEXITCODE)."}
# The kernel kills receivers, so they never send their mDNS goodbye; send it for them, or every
# phone keeps listing the stopped names for 75 minutes.
$taskBoards=@($taskPrep.receivers | ForEach-Object {'--board'; $_.board})
& $taskPy (Join-Path $PSScriptRoot '..\..\tools\mdns_goodbye.py') --receivers (Join-Path $taskPrep.runDirectory 'data\receivers.json') --status-url "$taskApi/kernel/status" @taskBoards
if($LASTEXITCODE){throw 'Receivers stopped, but their AirPlay names were not withdrawn.'}
Rename-Item -LiteralPath (Join-Path $taskDir 'processes.json') -NewName ('processes-stopped-' + [datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.json')
if($Rack){"Stopped rack ${Rack}: none of its kernel, receivers or listeners remain."}else{'Stopped: no kernel, receiver or listener remains.'}
