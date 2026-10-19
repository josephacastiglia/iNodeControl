$ErrorActionPreference = 'Stop'
# Separate output; never the accepted codex-farm-recovery-20261019 build. The
# hidden --self-test uses mock transport only: no rack, phone or desktop input.
$taskRepo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$taskOutput = Join-Path $taskRepo 'output/claude-farm-reel-20261019'
if (Test-Path -LiteralPath (Join-Path $taskOutput 'qa/self-tests.json')) { Remove-Item -LiteralPath (Join-Path $taskOutput 'qa/self-tests.json') }
& dotnet build (Join-Path $taskRepo 'src/iMouse.Console/iMouse.Console.csproj') --no-restore -c Release -o $taskOutput *> (Join-Path $PSScriptRoot 'native-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'Native build failed. Read native-build.txt.' }
$taskProcess = Start-Process -FilePath (Join-Path $taskOutput 'iMouse2.exe') -ArgumentList @('--self-test') -WorkingDirectory $taskOutput -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'native-self-test.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'native-self-test.stderr.txt') -PassThru -Wait
$taskTests = Get-Content -LiteralPath (Join-Path $taskOutput 'qa/self-tests.json') -Raw | ConvertFrom-Json
Copy-Item -LiteralPath (Join-Path $taskOutput 'qa/self-tests.json') -Destination (Join-Path $PSScriptRoot 'native-self-tests.json')
$taskSummary = [pscustomobject]@{passed=$taskTests.passed; failed=$taskTests.failed; exitCode=$taskProcess.ExitCode; desktopControl=$false; phoneInput=$false; output=$taskOutput; dllSha256=(Get-FileHash -LiteralPath (Join-Path $taskOutput 'iMouse2.dll') -Algorithm SHA256).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'native-summary.json'), ($taskSummary | ConvertTo-Json))
if ($taskProcess.ExitCode -ne 0) { throw 'Headless self-tests failed; preserve the failure report.' }
foreach ($name in @('farm-reel-draft-headless.png', 'video-draft-headless.png')) {
    Copy-Item -LiteralPath (Join-Path $taskOutput ('qa/' + $name)) -Destination (Join-Path $PSScriptRoot ('native-' + $name))
}
$taskSummary | ConvertTo-Json -Compress
