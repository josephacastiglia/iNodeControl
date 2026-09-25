$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$kernelExe = Join-Path $projectRoot 'release\iMouse2-kernel-precise-candidate\iMouse2.Kernel.exe'
$configRoot = Join-Path $projectRoot 'analysis\two-phone-config'
$receiverExe = Join-Path $projectRoot 'tools\airplay\uxplay\build-imouse\uxplay.exe'
$runtimeRoot = Join-Path $projectRoot 'tools\airplay\msys64\ucrt64'
foreach ($required in @($kernelExe,$receiverExe,(Join-Path $configRoot 'receivers.json'),(Join-Path $configRoot 'pointer-calibration.json'))) {
    if (!(Test-Path -LiteralPath $required)) { throw "Missing: $required" }
}
$probe = [Net.Sockets.TcpClient]::new()
try { $occupied = $probe.ConnectAsync('127.0.0.1',9913).Wait(500) -and $probe.Connected }
catch { $occupied = $false } finally { $probe.Dispose() }
if ($occupied) { throw '9913 is occupied. This launcher never stops processes. Verify and close only the independent kernel and its two receiver children before switching.' }
$launchArgs = @('http://127.0.0.1:9913/api/','--data-dir',('"'+$configRoot+'"'),
    '--input-pid','C24C,C241','--precise-movement','--receivers',('"'+(Join-Path $configRoot 'receivers.json')+'"'),
    '--receiver',('"'+$receiverExe+'"'),'--receiver-runtime',('"'+$runtimeRoot+'"'))
$evidenceRoot = Join-Path $projectRoot 'analysis\pointer-reliability-20260915'
$process = Start-Process -FilePath $kernelExe -ArgumentList $launchArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $evidenceRoot 'candidate-kernel.stdout.log') `
    -RedirectStandardError (Join-Path $evidenceRoot 'candidate-kernel.stderr.log')
Write-Output "Started precise-movement candidate PID $($process.Id). Recast C24C and C241. Console stays on 9913."
