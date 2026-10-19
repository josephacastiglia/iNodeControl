$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$prep = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$checks = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'offline-tests.json') -Encoding UTF8 -Raw | ConvertFrom-Json
if (-not $checks.passed -or $checks.skipped) { throw 'Offline preparation is incomplete.' }
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'processes.json')) { throw 'This window has already been started. Inspect the saved process record.' }
$processes = @(Get-CimInstance Win32_Process -Filter "Name='iMouse2.exe' OR Name='iMouse2.Kernel.exe' OR Name='uxplay.exe'" | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine,CreationDate)
$ports = @(9911,9913,9914,9915,9916,7110,7111,7112,7120,7121,7122)
$tcp = @(Get-NetTCPConnection -State Listen | Where-Object LocalPort -In $ports | Select-Object LocalAddress,LocalPort,OwningProcess)
$udp = @(Get-NetUDPEndpoint | Where-Object LocalPort -In $ports | Select-Object LocalAddress,LocalPort,OwningProcess)
[ordered]@{capturedUtc=[datetime]::UtcNow.ToString('o');processes=$processes;tcpListeners=$tcp;udpEndpoints=$udp;phoneInput=$false;desktopControl=$false} |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'initial-rack.json') -Encoding UTF8
if ($processes.Count -or $tcp.Count -or $udp.Count) { throw 'Rack/test processes or ports are active. Nothing was started.' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath ([IO.Path]::ChangeExtension($prep.kernel, '.dll'))).Hash.ToLowerInvariant() -ne $prep.validation.build.sha256) { throw 'Kernel changed.' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $prep.nativeAssembly).Hash.ToLowerInvariant() -ne $prep.nativeSha256) { throw 'Native candidate changed.' }
$sources = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'validation-sources.json') -Encoding UTF8 -Raw | ConvertFrom-Json
foreach ($item in $sources.PSObject.Properties) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root $item.Name)).Hash.ToLowerInvariant() -ne $item.Value) { throw "Source changed: $($item.Name)" }
}
$protected = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'protected-files.json') -Encoding UTF8 -Raw | ConvertFrom-Json
foreach ($item in $protected.PSObject.Properties) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $item.Name).Hash.ToLowerInvariant() -ne $item.Value.sha256) { throw "Protected file changed: $($item.Name)" }
}
function Quote-Arguments($values) {
    foreach ($value in $values) { if ($value.Contains('"')) { throw 'Unexpected quote in argument.' } }
    return (($values | ForEach-Object { '"' + $_ + '"' }) -join ' ')
}
$record = [ordered]@{startedUtc=[datetime]::UtcNow.ToString('o');kernel=$null;backend=$null;phoneInput=$false;desktopControl=$false}
function Save-Processes { $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'processes.json') -Encoding UTF8 }
try {
    $kernel = Start-Process -FilePath $prep.kernel -ArgumentList (Quote-Arguments $prep.arguments) -WorkingDirectory ([IO.Path]::GetDirectoryName($prep.kernel)) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'kernel.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'kernel.stderr.txt')
    $record.kernel = @{pid=$kernel.Id;path=$prep.kernel;arguments=$prep.arguments}; Save-Processes
    $python = 'C:\Users\joey_\AppData\Local\Programs\Python\Python311\python.exe'
    $arguments = @('-u', $prep.backendWrapper, '--fault-record', $prep.localFaultRecord, '--', '--host', '127.0.0.1', '--port', '9915', '--mode', 'live', '--no-browser', '--data-dir', $prep.backendData, '--draft-workflow-config', (Join-Path $PSScriptRoot 'candidate-workflow-config.json'))
    $backend = Start-Process -FilePath $python -ArgumentList (Quote-Arguments $arguments) -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'backend.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'backend.stderr.txt')
    $record.backend = @{pid=$backend.Id;path=$python;arguments=$arguments}; Save-Processes
    & $python (Join-Path $PSScriptRoot 'read_ready.py')
    if ($LASTEXITCODE -ne 0) { throw 'Read-only readiness check failed. Inspect and gracefully stop only the recorded candidate processes.' }
} catch {
    Save-Processes
    throw
}
