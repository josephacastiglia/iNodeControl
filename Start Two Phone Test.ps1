$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$kernelExe = Join-Path $projectRoot 'release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe'
$consoleExe = Join-Path $projectRoot 'release\iMouse2-two-phone-candidate\iMouse2.exe'
$configRoot = Join-Path $projectRoot 'analysis\two-phone-config'
$receiverExe = Join-Path $projectRoot 'tools\airplay\uxplay\build-imouse\uxplay.exe'
$runtimeRoot = Join-Path $projectRoot 'tools\airplay\msys64\ucrt64'
foreach ($path in @($kernelExe,$consoleExe,$receiverExe,(Join-Path $configRoot 'receivers.json'))) {
    if (!(Test-Path -LiteralPath $path)) {throw "Missing required file: $path"}
}
$probe = [Net.Sockets.TcpClient]::new()
try { $occupied = $probe.ConnectAsync('127.0.0.1',9913).Wait(500) -and $probe.Connected }
catch {$occupied=$false} finally {$probe.Dispose()}
if ($occupied) {
    $status = Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 3
    $ids = @($status.data.receivers.deviceid | Sort-Object)
    if (($ids -join ',') -ne '86:1D:4A:04:2F:F6,FE:A9:BC:D7:A0:44') {
        throw 'Port 9913 belongs to a different configuration; close that kernel before starting this test.'
    }
} else {
    $kernelArgs=@('http://127.0.0.1:9913/api/','--data-dir',('"'+$configRoot+'"'),
        '--input-pid','C24C,C241','--receivers',('"'+(Join-Path $configRoot 'receivers.json')+'"'),
        '--receiver',('"'+$receiverExe+'"'),'--receiver-runtime',('"'+$runtimeRoot+'"'))
    Start-Process -FilePath $kernelExe -ArgumentList $kernelArgs -WorkingDirectory $projectRoot -WindowStyle Hidden
}
Start-Process -FilePath $consoleExe -WorkingDirectory (Split-Path $consoleExe)
