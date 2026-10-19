param([ValidateSet('initial-rack.json','final-rack.json')][string]$RecordName='initial-rack.json')
$ErrorActionPreference = 'Stop'
$taskProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('iMouse2.exe','iMouse2.Kernel.exe','uxplay.exe','NativeProbe.exe') -or ($_.CommandLine -and $_.CommandLine -match 'python[^\r\n]*imouse_farm_server\.py|dotnet[^\r\n]*iMouse2(\.Kernel)?\.dll') } | Select-Object ProcessId,ExecutablePath,CommandLine)
$taskTcp = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -In @(9911,9913,9914,9915,9916,9917,7110,7111,7112,7120,7121,7122) | Select-Object LocalAddress,LocalPort,OwningProcess)
$taskUdp = @(Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object LocalPort -In @(7110,7111,7112,7120,7121,7122) | Select-Object LocalAddress,LocalPort,OwningProcess)
$taskState = [ordered]@{utc=[datetime]::UtcNow.ToString('o');processes=$taskProcesses;tcp=$taskTcp;udp=$taskUdp;phoneInput=$false;desktopControl=$false}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot $RecordName), ($taskState | ConvertTo-Json -Depth 7))
if ($taskProcesses.Count -or $taskTcp.Count -or $taskUdp.Count) { throw 'Rack/test services are active. Nothing was stopped or started.' }
[pscustomobject]@{processes=$taskProcesses.Count;tcp=$taskTcp.Count;udp=$taskUdp.Count} | ConvertTo-Json -Compress
