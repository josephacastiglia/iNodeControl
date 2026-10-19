$ErrorActionPreference='Stop'
$taskLive=Join-Path $PSScriptRoot 'live-repeat-20261011'
$taskRecord=Join-Path $taskLive 'candidate-start.json'
if (Test-Path -LiteralPath $taskRecord) { throw 'Candidate startup already recorded; no duplicate started' }
$taskExe=Join-Path $taskLive 'candidate\iMouse2.exe'
$taskData=Join-Path $taskLive 'console data'
$taskDll=Join-Path $taskLive 'candidate\iMouse2.dll'
$taskExpected=Get-Content -LiteralPath (Join-Path $taskLive 'preflight-hashes.json') -Encoding UTF8 -Raw | ConvertFrom-Json
if ((Get-FileHash -LiteralPath $taskDll).Hash.ToLowerInvariant() -ne $taskExpected.candidate_console_sha256) { throw 'Candidate hash changed' }
$taskSettings=Get-Content -LiteralPath (Join-Path $taskData 'settings.json') -Encoding UTF8 -Raw | ConvertFrom-Json
if ($taskSettings.address -ne 'http://127.0.0.1:9913' -or $taskSettings.trackPointer -ne $false) { throw 'Isolated address/hover settings incorrect' }
if (Get-CimInstance Win32_Process -Filter "Name='iMouse2.exe'") { throw 'Another console is running; no candidate started' }
$taskTest=Get-Content -LiteralPath (Join-Path $taskLive 'test-start.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$taskProc=Get-CimInstance Win32_Process -Filter "ProcessId=$($taskTest.kernel_pid)"
if (!$taskProc -or $taskProc.ExecutablePath -ne (Join-Path $PSScriptRoot 'build\iMouse2.Kernel.exe')) { throw 'Test kernel process mismatch' }
$taskKernel=(Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 5).data
$taskInput=(Invoke-RestMethod 'http://127.0.0.1:9913/api/input/status' -TimeoutSec 5).data
if (($taskKernel.allowed -join ',') -ne 'C24C' -or !$taskKernel.live -or !$taskKernel.fka_pass_through_probe_enabled -or $taskKernel.receiver_pid -ne $taskTest.receiver_pid) { throw 'Test kernel configuration mismatch' }
if ($taskInput.phones.Count -ne 1 -or $taskInput.phones[0].id -ne '86:1D:4A:04:2F:F6' -or @($taskInput.phones | Where-Object { $_.owned -or $_.active -or $_.stopped -or $_.releasing -or $_.release_failed }).Count) { throw 'Phone unavailable; no candidate started' }
$taskSettingsPath=Join-Path $env:APPDATA 'iMouse2\settings.json'
$taskOperatorHash=(Get-FileHash -LiteralPath $taskSettingsPath).Hash
$taskArgs=@(('--data-dir="'+$taskData+'"'),'--address=http://127.0.0.1:9913')
# This is the explicitly requested interactive test console, so its window is visible.
$taskStarted=Start-Process -FilePath $taskExe -ArgumentList $taskArgs -WorkingDirectory (Split-Path -Parent $taskExe) -PassThru
@{pid=$taskStarted.Id;exe=$taskExe;arguments=$taskArgs;data_dir=$taskData;time_utc=(Get-Date).ToUniversalTime().ToString('o');operator_settings_sha256_before=$taskOperatorHash} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $taskRecord -Encoding UTF8
Start-Sleep -Milliseconds 800
if ((Get-FileHash -LiteralPath $taskSettingsPath).Hash -ne $taskOperatorHash) { throw 'Operator settings changed; stop testing and restore' }
$taskAfter=(Invoke-RestMethod 'http://127.0.0.1:9913/api/input/status' -TimeoutSec 5).data
if (@($taskAfter.phones | Where-Object { $_.owned -or $_.active }).Count) { throw 'Unexpected automatic ownership/input; stop testing and restore' }
'Candidate started by exact path with isolated settings and no automatic ownership.'
$taskStarted | Select-Object Id,Path | ConvertTo-Json
