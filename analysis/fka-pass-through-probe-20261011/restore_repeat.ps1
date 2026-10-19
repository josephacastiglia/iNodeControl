param([Parameter(Mandatory)][ValidateSet('Kernel','Console')][string]$Stage)
$ErrorActionPreference='Stop'
$taskMain='C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0'
$taskLive=Join-Path $PSScriptRoot 'live-repeat-20261011'
$taskLauncher=Join-Path $taskMain 'Open iMouse 2.0.ps1'
$taskTest=Get-Content -LiteralPath (Join-Path $taskLive 'test-start.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$taskTestExe=Join-Path $PSScriptRoot 'build\iMouse2.Kernel.exe'
if ($Stage -eq 'Kernel') {
    $taskState=(Invoke-RestMethod 'http://127.0.0.1:9913/api/input/status' -TimeoutSec 5).data
    if ($taskState.phones.Count -ne 1 -or $taskState.phones[0].id -ne '86:1D:4A:04:2F:F6' -or $taskState.phones[0].active -or $taskState.phones[0].releasing) { throw 'Unexpected configuration or active work; restoration stopped before closing anything' }
    $taskCandidateRecord=Join-Path $taskLive 'candidate-start.json'
    if (Test-Path -LiteralPath $taskCandidateRecord) {
        $taskCandidate=Get-Content -LiteralPath $taskCandidateRecord -Encoding UTF8 -Raw | ConvertFrom-Json
        $taskCandidateProc=Get-CimInstance Win32_Process -Filter "ProcessId=$($taskCandidate.pid)"
        if ($taskCandidateProc) {
            if ($taskCandidateProc.ExecutablePath -ne (Join-Path $taskLive 'candidate\iMouse2.exe')) { throw 'Candidate identity changed; nothing closed' }
            $taskRunning=Get-Process -Id $taskCandidate.pid
            if (!$taskRunning.CloseMainWindow() -or !$taskRunning.WaitForExit(10000)) { throw 'Candidate did not close normally; no process killed' }
        }
    }
    $taskFree=(Invoke-RestMethod 'http://127.0.0.1:9913/api/input/status' -TimeoutSec 5).data
    if (@($taskFree.phones | Where-Object { $_.owned -or $_.active -or $_.releasing }).Count) { throw 'Test ownership remains; kernel not stopped' }
    $taskFree | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $taskLive 'before-restoration-input.json') -Encoding UTF8
    foreach ($taskRelative in @('release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe','release\iMouse2-kernel-two-phone\iMouse2.Kernel.dll','analysis\two-phone-config\devices.json','analysis\two-phone-config\receivers.json','analysis\two-phone-config\pointer-calibration.json','Open iMouse 2.0.ps1')) {
        if ((Get-FileHash -LiteralPath (Join-Path $taskMain $taskRelative)).Hash -ne (Get-FileHash -LiteralPath (Join-Path $taskLive ('release-snapshot\'+$taskRelative))).Hash) { throw "Release file changed: $taskRelative" }
    }
    $taskHelper=Join-Path $taskLive 'release-snapshot\Stop-ConsoleProcessGracefully.ps1'
    $taskStop=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$taskHelper+'"'),'-ProcessId',([string]$taskTest.kernel_pid),'-ExpectedPath',('"'+$taskTestExe+'"'),'-TimeoutSeconds','20') -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $taskLive 'test-stop.txt') -RedirectStandardError (Join-Path $taskLive 'test-stop-error.txt')
    Get-Content -LiteralPath (Join-Path $taskLive 'test-stop.txt') -Encoding UTF8
    if ($taskStop.ExitCode -ne 0) { throw "Test shutdown incomplete: exit $($taskStop.ExitCode)" }
    if (Get-CimInstance Win32_Process -Filter "ProcessId=$($taskTest.kernel_pid) OR ProcessId=$($taskTest.receiver_pid)") { throw 'Test process remains; no duplicate started' }
    $taskTcp=[Net.Sockets.TcpClient]::new()
    try { $taskBusy=$taskTcp.ConnectAsync('127.0.0.1',9913).Wait(500) -and $taskTcp.Connected } catch { $taskBusy=$false } finally { $taskTcp.Dispose() }
    if ($taskBusy) { throw 'Port 9913 remains occupied' }
    $taskExe=Join-Path $taskMain 'release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe'
    $taskConfig=Join-Path $taskMain 'analysis\two-phone-config'
    $taskReceiver=Join-Path $taskMain 'tools\airplay\uxplay\build-imouse\uxplay.exe'
    $taskRuntime=Join-Path $taskMain 'tools\airplay\msys64\ucrt64'
    $taskArgs=@('http://127.0.0.1:9913/api/','--data-dir',('"'+$taskConfig+'"'),'--input-pid','C24C,C241','--receivers',('"'+(Join-Path $taskConfig 'receivers.json')+'"'),'--receiver',('"'+$taskReceiver+'"'),'--receiver-runtime',('"'+$taskRuntime+'"'))
    $taskStarted=Start-Process -FilePath $taskExe -ArgumentList $taskArgs -WorkingDirectory $taskMain -WindowStyle Hidden -PassThru
    $taskStatus=$null
    for($taskTry=0;$taskTry -lt 20;$taskTry++) { try { $taskStatus=(Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 2).data; break } catch { if ($taskStarted.HasExited) { throw }; Start-Sleep -Milliseconds 300 } }
    if (!$taskStatus -or ($taskStatus.allowed -join ',') -ne 'C24C,C241' -or $taskStatus.receivers.Count -ne 2) { throw 'Release startup incomplete' }
    @{kernel_pid=$taskStarted.Id;status=$taskStatus;time_utc=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $taskLive 'release-kernel-restored.json') -Encoding UTF8
    & $taskLauncher -CheckOnly | Format-List
    'Release kernel restored. Operator recasting and installed console pending.'
} else {
    $taskKernel=(Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 5).data
    $taskInput=(Invoke-RestMethod 'http://127.0.0.1:9913/api/input/status' -TimeoutSec 5).data
    if ($taskKernel.receivers.Count -ne 2 -or @($taskKernel.receivers | Where-Object { !$_.live }).Count) { throw 'Both phones must be mirroring before opening the console' }
    if (@($taskInput.phones | Where-Object { $_.owned -or $_.active -or $_.releasing }).Count -or ($taskInput.phones | Where-Object id -eq 'FE:A9:BC:D7:A0:44').generation -ne 0) { throw 'Unexpected release ownership; no console opened' }
    & $taskLauncher
    Start-Sleep -Milliseconds 800
    $taskConsole=Get-CimInstance Win32_Process -Filter "Name='iMouse2.exe'" | Where-Object { $_.ExecutablePath -eq (Join-Path $taskMain 'release\iMouse2-two-phone-candidate\iMouse2.exe') }
    if (@($taskConsole).Count -ne 1) { throw 'Installed console restoration incomplete' }
    $taskFinal=(Invoke-RestMethod 'http://127.0.0.1:9913/api/input/status' -TimeoutSec 5).data
    @{time_utc=(Get-Date).ToUniversalTime().ToString('o');console=($taskConsole | Select-Object ProcessId,ExecutablePath,CommandLine);kernel=$taskKernel;input=$taskFinal} | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $taskLive 'console-restored.json') -Encoding UTF8
    $taskConsole | Select-Object ProcessId,ExecutablePath | ConvertTo-Json
    $taskFinal | ConvertTo-Json -Depth 8
}
