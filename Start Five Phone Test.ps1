$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$kernelExe = Join-Path $projectRoot 'release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe'
$consoleExe = Join-Path $projectRoot 'release\iMouse2-two-phone-candidate\iMouse2.exe'
$configRoot = Join-Path $projectRoot 'analysis\five-phone-config'
$receiverExe = Join-Path $projectRoot 'tools\airplay\uxplay\build-imouse\uxplay.exe'
$runtimeRoot = Join-Path $projectRoot 'tools\airplay\msys64\ucrt64'
foreach ($path in @($kernelExe,$consoleExe,$receiverExe,(Join-Path $configRoot 'receivers.json'),(Join-Path $configRoot 'devices.json'),(Join-Path $configRoot 'pointer-calibration.json'))) {
    if (!(Test-Path -LiteralPath $path)) { throw "Missing required file: $path" }
}
$probe = [Net.Sockets.TcpClient]::new()
try { $occupied = $probe.ConnectAsync('127.0.0.1',9913).Wait(500) -and $probe.Connected }
catch { $occupied = $false } finally { $probe.Dispose() }
if ($occupied) { throw 'Port 9913 is not free. Close that kernel before starting the five-phone test.' }
$kernelArgs = @('http://127.0.0.1:9913/api/','--data-dir',('"'+$configRoot+'"'),
    '--input-pid','C24C,C241,C214,724E,F215','--receivers',('"'+(Join-Path $configRoot 'receivers.json')+'"'),
    '--receiver',('"'+$receiverExe+'"'),'--receiver-runtime',('"'+$runtimeRoot+'"'))
Start-Process -FilePath $kernelExe -ArgumentList $kernelArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $configRoot 'kernel-stdout.log') `
    -RedirectStandardError (Join-Path $configRoot 'kernel-stderr.log') | Out-Null
Start-Process -FilePath $consoleExe -WorkingDirectory (Split-Path $consoleExe)
