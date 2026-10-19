$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$taskPrep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw | ConvertFrom-Json
$taskProcesses=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'processes.json') -Raw | ConvertFrom-Json
$taskReady=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'receiver-ready.json') -Raw | ConvertFrom-Json
$taskHelper=Join-Path $taskRoot 'tools/kernel-window/Stop-ConsoleProcessGracefully.ps1'
foreach($taskTarget in @(@{name='backend';record=$taskProcesses.backend},@{name='kernel';record=$taskProcesses.kernel})){
    if(!$taskTarget.record){continue}
    $taskActual=Get-CimInstance Win32_Process -Filter ('ProcessId='+$taskTarget.record.pid)
    if(!$taskActual -or $taskActual.ExecutablePath -cne $taskTarget.record.path){throw ('Private process identity changed: '+$taskTarget.name)}
    if($taskTarget.name -eq 'backend' -and ($taskActual.CommandLine -notlike '*imouse_farm_server.py*' -or $taskActual.CommandLine -notlike ('*'+$taskPrep.backendData+'*'))){throw 'Backend command line changed.'}
    if($taskTarget.name -eq 'kernel'){
        $taskStatus=(Invoke-RestMethod 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 5).data
        $taskInput=(Invoke-RestMethod 'http://127.0.0.1:9916/api/' -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 5).data
        $taskPhone=@($taskInput.phones)
        if($taskStatus.process.pid -ne $taskProcesses.kernel.pid -or $taskStatus.process.started_utc -cne $taskReady.process.started_utc -or $taskStatus.build_identity.sha256 -cne $taskPrep.kernelSha256 -or $taskPhone.Count -ne 1 -or $taskPhone[0].id -cne $taskPrep.expectedDeviceId -or $taskPhone[0].owned -or $taskPhone[0].active -or $taskPhone[0].stopped -or $taskPhone[0].releasing -or $taskPhone[0].release_failed){throw 'Kernel identity or free input state is unconfirmed. Nothing will be force-killed.'}
        @{kernel=$taskStatus;input=$taskInput;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 14 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'final-live-state.json') -Encoding utf8
    }
    $taskArguments='-NoProfile -ExecutionPolicy Bypass -File "'+$taskHelper+'" -ProcessId '+$taskTarget.record.pid+' -ExpectedPath "'+$taskTarget.record.path+'" -TimeoutSeconds 20'
    $taskStop=Start-Process -FilePath powershell.exe -ArgumentList $taskArguments -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $PSScriptRoot ('stop-'+$taskTarget.name+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ('stop-'+$taskTarget.name+'.stderr.txt'))
    if($taskStop.ExitCode -ne 0){throw ('Graceful stop unconfirmed: '+$taskTarget.name+'. Nothing is force-killed.')}
}
$taskRemaining=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -in @('iMouse2.exe','iMouse2.Kernel.exe','uxplay.exe','NativeProbe.exe','ReelProbe.exe') -or ($_.CommandLine -and $_.CommandLine -match 'python[^\r\n]*imouse_farm_server\.py') } | Select-Object ProcessId,ExecutablePath,CommandLine)
$taskTcp=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -In @(9913,9914,9915,9916,9917,7110,7111,7112,7120,7121,7122) | Select-Object LocalPort,OwningProcess)
$taskUdp=@(Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object LocalPort -In @(7110,7111,7112,7120,7121,7122) | Select-Object LocalPort,OwningProcess)
$taskBefore=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'protected-before.json') -Raw | ConvertFrom-Json
$taskProtected=@(foreach($taskFile in $taskBefore){$taskHash=(Get-FileHash -LiteralPath $taskFile.path -Algorithm SHA256).Hash.ToLowerInvariant();@{path=$taskFile.path;sha256=$taskHash;unchanged=($taskHash -ceq $taskFile.sha256)}})
$taskRestored=$taskRemaining.Count -eq 0 -and $taskTcp.Count -eq 0 -and $taskUdp.Count -eq 0 -and @($taskProtected | Where-Object {!$_.unchanged}).Count -eq 0
@{restored=$taskRestored;processes=$taskRemaining;tcp=$taskTcp;udp=$taskUdp;protectedFiles=$taskProtected;installedReleaseStarted=$false;utc=[datetime]::UtcNow.ToString('o')} | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'restoration.json') -Encoding utf8
if(!$taskRestored){throw 'Restoration needs review. Preserve the process/log record.'}
Write-Output ('Initial stopped state restored; '+$taskProtected.Count+' protected files unchanged.')
