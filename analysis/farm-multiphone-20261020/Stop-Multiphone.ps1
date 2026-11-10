# Stops the rack's kernel gracefully (it then ends each receiver it started), confirms nothing of it
# remains, and withdraws its receivers' AirPlay names. Never force-kills anything. A kernel that
# Start-Multiphone.ps1 launched stops through its stop file; one whose record names no stop file (the
# off-rack trial starts one attached) gets Ctrl+C. If the stop fails, the boards whose input it left
# stopped go to input-stops.jsonl, so the bring-up (rack_recovery.py bringup) resumes exactly those
# (never an operator's stop). Afterwards no kernel, receiver or listener may remain (rack_kernels.py
# check-stopped; a sandbox preparation is checked only against its own).
# Before the kernel is asked to exit, stopping.json records that this stop is on purpose. The record
# (processes.json) is renamed only at the very end, after the leftover check and the goodbye; without
# the marker a watchdog check in between would see a recorded kernel that is gone and start it again.
# The marker is removed once the record is renamed. If the stop fails it stays, so a kernel that
# finishes its shutdown late is still not restarted.
[CmdletBinding()]param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'RackState.ps1')
$taskPy=Get-RackPython
$taskDir=Get-RackState 'slots'
$taskPrepFile=Join-Path $taskDir 'preparation.json'
$taskPrep=Get-Content -LiteralPath $taskPrepFile -Raw | ConvertFrom-Json
$taskApi=([string]$taskPrep.arguments[0]).TrimEnd('/')
$taskProcs=Get-Content -LiteralPath (Join-Path $taskDir 'processes.json') -Raw | ConvertFrom-Json
$taskHelper=Join-Path $PSScriptRoot '..\..\tools\kernel-window\Stop-ConsoleProcessGracefully.ps1'
$taskPid=[int]$taskProcs.kernel.pid
$taskRunning=Get-CimInstance Win32_Process -Filter "ProcessId=$taskPid"
if($taskRunning -and $taskRunning.ExecutablePath -ne $taskPrep.kernel){throw "PID $taskPid is no longer the prepared kernel; nothing was stopped."}
$taskStopping=Join-Path $taskDir 'stopping.json'
@{utc=[datetime]::UtcNow.ToString('o');pid=$taskPid} | ConvertTo-Json -Compress | Set-Content -LiteralPath $taskStopping -Encoding ascii
if($taskRunning){
    # Input state before the stop: if the stop fails, the boards it left stopped go to the ledger.
    $taskBefore=Join-Path $taskDir 'input-before-stop.json'
    # Best effort: a snapshot that cannot be taken never blocks the stop (only the ledger is lost).
    $taskSnapped=$false
    try{
        $ErrorActionPreference='Continue'
        & $taskPy (Join-Path $PSScriptRoot 'rack_recovery.py') snapshot --api $taskApi --out $taskBefore *> $null
        $taskSnapped=($LASTEXITCODE -eq 0)
    }catch{}finally{$ErrorActionPreference='Stop'}
    if($taskProcs.stopFile){
        # A detached kernel: write its PID to its stop file; it runs its Ctrl+C shutdown and consumes the file.
        [IO.File]::WriteAllText([string]$taskProcs.stopFile,[string]$taskPid)
        $taskDeadline=[datetime]::UtcNow.AddSeconds(45)
        while((Get-Process -Id $taskPid -ErrorAction SilentlyContinue) -and [datetime]::UtcNow -lt $taskDeadline){Start-Sleep -Milliseconds 500}
        $taskStopExit=if(Get-Process -Id $taskPid -ErrorAction SilentlyContinue){3}else{0}
    }else{
        # An attached kernel: the helper detaches from its console, so it runs in its own PowerShell process.
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskHelper -ProcessId $taskPid -ExpectedPath $taskPrep.kernel
        $taskStopExit=$LASTEXITCODE
    }
    if($taskStopExit){
        if($taskSnapped){& $taskPy (Join-Path $PSScriptRoot 'rack_recovery.py') ledger --api $taskApi --before $taskBefore --by 'Stop-Multiphone' --ledger (Join-Path $taskDir 'input-stops.jsonl')}
        throw "Graceful stop reported exit $taskStopExit; nothing was killed. Inspect before doing anything else."
    }
}
$taskSnap=@{
    processes=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('iMouse2.Kernel.exe','uxplay.exe') } | ForEach-Object { @{Name=$_.Name;ProcessId=$_.ProcessId;CommandLine=$_.CommandLine} })
    listeners=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object LocalPort | Sort-Object -Unique)
} | ConvertTo-Json -Depth 4 -Compress
$taskVerdict=$taskSnap | & $taskPy (Join-Path $PSScriptRoot 'rack_kernels.py') check-stopped --prep $taskPrepFile
if($LASTEXITCODE -eq 3){throw "Still present: $taskVerdict"}elseif($LASTEXITCODE){throw "Stop check failed (exit $LASTEXITCODE)."}
# The kernel kills receivers, so they never send their mDNS goodbye; send it for them, or every
# phone keeps listing the stopped names for 75 minutes.
$taskBoards=@($taskPrep.receivers | ForEach-Object {'--board'; $_.board})
& $taskPy (Join-Path $PSScriptRoot '..\..\tools\mdns_goodbye.py') --receivers (Join-Path $taskPrep.runDirectory 'data\receivers.json') --status-url "$taskApi/kernel/status" @taskBoards
if($LASTEXITCODE){throw 'Receivers stopped, but their AirPlay names were not withdrawn.'}
Rename-Item -LiteralPath (Join-Path $taskDir 'processes.json') -NewName ('processes-stopped-' + [datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.json')
Remove-Item -LiteralPath $taskStopping
'Stopped: no kernel, receiver or listener of this preparation remains.'
