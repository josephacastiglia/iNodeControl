# Read-only restoration audit. Do not start, stop or reconfigure anything.
$ErrorActionPreference = 'Stop'
$protected = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'protected-files.json') -Encoding UTF8 | ConvertFrom-Json
$checks = @($protected.PSObject.Properties | ForEach-Object {
    $actual = (Get-FileHash -LiteralPath $_.Name -Algorithm SHA256).Hash.ToLowerInvariant()
    [ordered]@{ path=$_.Name; sha256=$actual; unchanged=($actual -eq $_.Value.sha256) }
})
$rack = @(Get-CimInstance Win32_Process -Filter "Name='iMouse2.exe' OR Name='iMouse2.Kernel.exe' OR Name='uxplay.exe'" |
    Select-Object ProcessId,Name,ExecutablePath,CreationDate)
$ports = @(9913,9916,7110,7111,7112)
$tcp = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -In $ports |
    Select-Object LocalAddress,LocalPort,OwningProcess)
$udp = @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object LocalPort -In $ports |
    Select-Object LocalAddress,LocalPort,OwningProcess)
$result = [ordered]@{
    recordedUtc=[datetime]::UtcNow.ToString('o'); protectedFiles=$checks;
    allProtectedFilesUnchanged=(@($checks | Where-Object { -not $_.unchanged }).Count -eq 0);
    rackProcesses=$rack; tcpListeners=$tcp; udpListeners=$udp;
    initialStoppedStateRestored=($rack.Count -eq 0 -and $tcp.Count -eq 0 -and $udp.Count -eq 0)
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'final-rack.json') -Encoding UTF8
[ordered]@{ protectedFiles=$checks.Count; unchanged=$result.allProtectedFilesUnchanged;
    rackProcesses=$rack.Count; tcpListeners=$tcp.Count; udpListeners=$udp.Count;
    restored=$result.initialStoppedStateRestored } | ConvertTo-Json
if (-not $result.initialStoppedStateRestored -or -not $result.allProtectedFilesUnchanged) { exit 2 }
