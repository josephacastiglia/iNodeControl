$ErrorActionPreference = 'Stop'
$processes = @(Get-CimInstance Win32_Process -Filter "Name='iMouse2.exe' OR Name='iMouse2.Kernel.exe' OR Name='uxplay.exe'" |
    Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine, CreationDate)
$ports = @(9911,9913,9914,9915,9916,7110,7111,7112,7120,7121,7122)
$tcp = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -In $ports |
    Select-Object LocalAddress,LocalPort,OwningProcess)
$udp = @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object LocalPort -In $ports |
    Select-Object LocalAddress,LocalPort,OwningProcess)
$record = [ordered]@{ capturedUtc=[datetime]::UtcNow.ToString('o'); processes=$processes;
    tcpListeners=$tcp; udpEndpoints=$udp; phoneInput=$false; desktopControl=$false }
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'initial-rack.json') -Encoding UTF8
if ($processes.Count -or $tcp.Count -or $udp.Count) { throw 'Rack/test processes or ports are active; inspect before starting anything.' }
'Initial rack state recorded: stopped; no rack/test port occupied.'
