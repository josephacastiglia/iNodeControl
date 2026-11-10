# Starts the rack's kernel so each prepared phone can mirror. Starts no backend and sends no input.
# One kernel serves both racks, from slots\preparation.json. Refuses if anything of the farm is already
# there: a kernel, a receiver, the console, a window backend or one of their listeners (rack_kernels.py
# check-start). A sandbox preparation ("sandbox": true; the off-rack trials write one) is checked only
# against its own kernel, receivers and ports, so it can run beside the live rack.
# Prepared receivers start held; Release-Receiver.ps1 advertises one at a time.
# The kernel is launched detached (WMI Win32_Process.Create, parent outside this session), so it survives
# the Claude app or session restarting; it stops gracefully through its stop file (Stop-Multiphone.ps1),
# and its console output goes to kernel.console.txt.
# The kernel counts as started (processes.json) only once it came up as prepared: same build, same
# allow-list, the held receivers held and every other receiver running. Until then its record is
# processes-starting.json, which the watchdog and the windows ignore. A kernel that does not get there
# within 40 s is stopped again and its record kept as processes-failed-<time>.json.
[CmdletBinding()]param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'RackState.ps1')
$taskPy=Get-RackPython
$taskDir=Get-RackKernelFolder
$taskProcessFile=Join-Path $taskDir 'processes.json'
$taskStarting=Join-Path $taskDir 'processes-starting.json'
if(Test-Path -LiteralPath $taskProcessFile){throw 'The kernel already has a process record. Do not start duplicates.'}
if(Test-Path -LiteralPath $taskStarting){throw 'An earlier start left processes-starting.json: it was interrupted before the kernel was confirmed or stopped. Check the PID it names before starting again.'}
$taskPrepFile=Join-Path $taskDir 'preparation.json'
$taskPrep=Get-Content -LiteralPath $taskPrepFile -Raw | ConvertFrom-Json
$taskApi=([string]$taskPrep.arguments[0]).TrimEnd('/')
if($taskApi -notmatch '^http://127\.0\.0\.1:\d+/api$'){throw 'The preparation does not start a loopback kernel.'}
# What is running, for rack_kernels.py to judge (command lines go to it on stdin only, never to a file).
$taskNames=@('iMouse2.exe','iMouse2.Kernel.exe','uxplay.exe','ReelProbe.exe','TikTokProbe.exe','XProbe.exe')
$taskSnap=@{
    processes=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in $taskNames -or ($_.CommandLine -and $_.CommandLine -match 'python[^\r\n]*imouse_farm_server\.py') } | ForEach-Object { @{Name=$_.Name;ProcessId=$_.ProcessId;CommandLine=$_.CommandLine} })
    listeners=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object LocalPort | Sort-Object -Unique)
} | ConvertTo-Json -Depth 4 -Compress
$taskVerdict=$taskSnap | & $taskPy (Join-Path $PSScriptRoot 'rack_kernels.py') check-start --prep $taskPrepFile
if($LASTEXITCODE -eq 3){throw "Nothing was stopped or started: $taskVerdict"}elseif($LASTEXITCODE){throw "Start check failed (exit $LASTEXITCODE); nothing was started."}
if((Get-FileHash -LiteralPath ([IO.Path]::ChangeExtension($taskPrep.kernel,'.dll')) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.kernelSha256){throw 'Kernel changed.'}
foreach($taskName in 'devices.json','receivers.json','pointer-calibration.json'){
    if((Get-FileHash -LiteralPath (Join-Path $taskPrep.runDirectory "data\$taskName") -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.dataSha256.$taskName){throw "Prepared $taskName changed."}
}
function Quote-TaskArguments($taskValues){ foreach($v in $taskValues){if($v.Contains('"')){throw 'Unexpected quote.'}}; (($taskValues | ForEach-Object {'"'+$_+'"'}) -join ' ') }
$taskStopFile=Join-Path $taskDir 'stop-request.txt'
$taskConsoleLog=Join-Path $taskDir 'kernel.console.txt'
$taskArgs=@($taskPrep.arguments)+@('--stop-file',$taskStopFile,'--console-log',$taskConsoleLog)
$taskValidator=Start-Process -FilePath $taskPrep.kernel -ArgumentList (Quote-TaskArguments (@($taskArgs)+@('--validate-startup'))) -WorkingDirectory ([IO.Path]::GetDirectoryName($taskPrep.kernel)) -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $taskDir 'kernel-validation.stdout.txt') -RedirectStandardError (Join-Path $taskDir 'kernel-validation.stderr.txt')
if($taskValidator.ExitCode -ne 0){throw 'Offline kernel startup validation failed; nothing was started. Its reason is in kernel-validation.stderr.txt.'}
if(Test-Path -LiteralPath $taskStopFile){Remove-Item -LiteralPath $taskStopFile}
# A stop marker left by an earlier kernel's stop means nothing for the one about to start.
Remove-Item -LiteralPath (Join-Path $taskDir 'stopping.json') -ErrorAction SilentlyContinue
$taskStartup=New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}
$taskCreated=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine=('"'+$taskPrep.kernel+'" '+(Quote-TaskArguments $taskArgs)); CurrentDirectory=[IO.Path]::GetDirectoryName($taskPrep.kernel); ProcessStartupInformation=$taskStartup}
if($taskCreated.ReturnValue -ne 0){throw "Detached kernel launch failed (Win32_Process.Create $($taskCreated.ReturnValue)); nothing was started."}
$taskKernelId=[int]$taskCreated.ProcessId
# Not processes.json yet: nothing may treat this kernel as started before it is confirmed below (a
# watchdog check would restart a kernel that died during its own startup).
@{utc=[datetime]::UtcNow.ToString('o');kernel=@{pid=$taskKernelId;path=$taskPrep.kernel};api=$taskApi;phoneInput=$false;launch='detached';stopFile=$taskStopFile;consoleLog=$taskConsoleLog} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $taskStarting -Encoding utf8
$taskDeadline=[datetime]::UtcNow.AddSeconds(40)
do{
    Start-Sleep -Milliseconds 500
    try{$taskStatus=(Invoke-RestMethod "$taskApi/kernel/status" -TimeoutSec 3).data}catch{$taskStatus=$null}
    $taskExited=!(Get-Process -Id $taskKernelId -ErrorAction SilentlyContinue)
    $taskProblem=Get-RackStartProblem $taskStatus $taskPrep $taskExited
}while($taskProblem -and !$taskExited -and [datetime]::UtcNow -lt $taskDeadline)
if($taskStatus){$taskStatus | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $taskDir 'receivers-ready.json') -Encoding utf8}
if(!$taskProblem){
    Rename-Item -LiteralPath $taskStarting -NewName 'processes.json'
    $taskStatus.receivers | ForEach-Object { [pscustomobject]@{receiver=$_.name; state=$_.receiver_state; pid=$_.receiver_pid; live=$_.live} } | Format-Table -AutoSize | Out-String
    return
}
# It did not come up as prepared. Nothing uses it yet, so it is not left half-started: ask it to stop
# the way Stop-Multiphone.ps1 does, and withdraw any AirPlay name its receivers advertised meanwhile.
if(!$taskExited){
    [IO.File]::WriteAllText($taskStopFile,[string]$taskKernelId)
    $taskDeadline=[datetime]::UtcNow.AddSeconds(45)
    while((Get-Process -Id $taskKernelId -ErrorAction SilentlyContinue) -and [datetime]::UtcNow -lt $taskDeadline){Start-Sleep -Milliseconds 500}
}
if(Get-Process -Id $taskKernelId -ErrorAction SilentlyContinue){
    Rename-Item -LiteralPath $taskStarting -NewName 'processes.json'
    throw "$taskProblem The kernel is still running and did not stop when asked; its record is processes.json. Stop it with Stop-Multiphone.ps1 and inspect before starting again."
}
Rename-Item -LiteralPath $taskStarting -NewName ('processes-failed-' + [datetime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '.json')
$taskBoards=@($taskPrep.receivers | ForEach-Object {'--board'; $_.board})
try{
    $ErrorActionPreference='Continue'
    & $taskPy (Join-Path $PSScriptRoot '..\..\tools\mdns_goodbye.py') --receivers (Join-Path $taskPrep.runDirectory 'data\receivers.json') --status-url "$taskApi/kernel/status" @taskBoards *> $null
}catch{}finally{$ErrorActionPreference='Stop'}
throw "$taskProblem The kernel is not running; its record is processes-failed-<time>.json and its logs are beside it. Nothing was started."
