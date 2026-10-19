$ErrorActionPreference = 'Stop'
$taskRepo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$taskOutput = Join-Path $taskRepo 'output/codex-farm-recovery-20261019'
& dotnet build (Join-Path $taskRepo 'src/iMouse.Console/iMouse.Console.csproj') --no-restore -c Release -o $taskOutput *> (Join-Path $PSScriptRoot 'native-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'Native build failed. Read native-build.txt.' }
$taskProcess = Start-Process -FilePath (Join-Path $taskOutput 'iMouse2.exe') -ArgumentList @('--self-test') -WorkingDirectory $taskOutput -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'native-self-test.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'native-self-test.stderr.txt') -PassThru -Wait
if ($taskProcess.ExitCode -ne 0) { throw 'Headless self-tests failed; preserve the candidate failure report.' }
$taskTests = Get-Content -LiteralPath (Join-Path $taskOutput 'qa/self-tests.json') -Raw | ConvertFrom-Json
Copy-Item -LiteralPath (Join-Path $taskOutput 'qa/self-tests.json') -Destination (Join-Path $PSScriptRoot 'native-self-tests.json')
Copy-Item -LiteralPath (Join-Path $taskOutput 'qa/farm-draft-recovery-headless.png') -Destination (Join-Path $PSScriptRoot 'native-inspection.png')
$taskSummary = [pscustomobject]@{passed=$taskTests.passed; exitCode=$taskProcess.ExitCode; desktopControl=$false; phoneInput=$false; dllSha256=(Get-FileHash -LiteralPath (Join-Path $taskOutput 'iMouse2.dll') -Algorithm SHA256).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'native-summary.json'), ($taskSummary | ConvertTo-Json))
$taskSummary | ConvertTo-Json -Compress
