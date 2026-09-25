$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$kernelExe = Join-Path $projectRoot 'release\iMouse2-kernel-verified\iMouse2.Kernel.exe'
$receiverExe = Join-Path $projectRoot 'tools\airplay\uxplay\build-imouse\uxplay.exe'
$runtimeRoot = Join-Path $projectRoot 'tools\airplay\msys64\ucrt64'
$configDir = Join-Path $projectRoot 'analysis\single-phone-config'
foreach ($requiredPath in @($kernelExe, $receiverExe, $runtimeRoot, $configDir)) {
    if (!(Test-Path -LiteralPath $requiredPath)) { throw "Missing build dependency: $requiredPath" }
}
$portProbe = [System.Net.Sockets.TcpClient]::new()
try {
    $pending = $portProbe.ConnectAsync('127.0.0.1', 9913)
    $occupied = $pending.Wait(500) -and $portProbe.Connected
} catch { $occupied = $false } finally { $portProbe.Dispose() }
if ($occupied) { throw 'Port 9913 is in use. Close the previous iMouse test kernel, then start this build.' }
# Run in this terminal so Ctrl+C gives the kernel a chance to release held inputs
# and shut down its child receiver. No vendor service is stopped by this script.
& $kernelExe 'http://127.0.0.1:9913/api/' --data-dir $configDir --input-pid C24C `
    --receiver $receiverExe --receiver-runtime $runtimeRoot
exit $LASTEXITCODE
