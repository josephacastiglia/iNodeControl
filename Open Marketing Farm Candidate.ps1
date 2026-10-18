# Separate native candidate. Does not restart the rack or alter installed shortcuts.
param([switch]$ValidateOnly, [string]$PythonPath)
$ErrorActionPreference = 'Stop'
$repoDir = $PSScriptRoot
$candidateDir = Join-Path $repoDir 'output\codex-farm-observations-20261017'
$candidateExe = Join-Path $candidateDir 'iMouse2.exe'
$candidateData = Join-Path $candidateDir 'candidate-data'
$serverScript = Join-Path $repoDir 'tools\imouse_farm_server.py'
$serverUrl = 'http://127.0.0.1:9915'
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
$pythonCandidates = @($PythonPath, (Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python\Python311\python.exe'), $pythonCommand.Source)
$pythonExe = $pythonCandidates | Where-Object { $_ -and $_ -notlike '*\WindowsApps\*' -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (!(Test-Path -LiteralPath $candidateExe -PathType Leaf)) { throw "Build the candidate first: $candidateExe" }
if (!$pythonExe) { throw 'Python was not found. Pass -PythonPath with the full path to your Python executable.' }
$expectedBytes = New-Object System.IO.MemoryStream
foreach ($name in @('imouse_farm_server.py', 'imouse_social_automation.py', 'farm_jobs.py', 'farm_drafts.py', 'farm_media_transfer.py', 'farm_transfers.py', 'farm_capabilities.py', 'farm_video.py', 'farm_observations.py', 'Read-FarmImageText.ps1', 'farm_preparation_schedule.py')) {
    $bytes = [IO.File]::ReadAllBytes((Join-Path $repoDir ('tools\' + $name)))
    $expectedBytes.Write($bytes, 0, $bytes.Length)
}
$hasher = [Security.Cryptography.SHA256]::Create()
try { $expectedSource = ([BitConverter]::ToString($hasher.ComputeHash($expectedBytes.ToArray()))).Replace('-', '').ToLowerInvariant() }
finally { $hasher.Dispose(); $expectedBytes.Dispose() }
if ($ValidateOnly) {
    [pscustomobject]@{ Candidate = $candidateExe; DataDirectory = $candidateData; FarmEndpoint = $serverUrl; Mode = 'simulate'; SourceHash = $expectedSource; StartsProcesses = $false }
    return
}
[IO.Directory]::CreateDirectory($candidateData) | Out-Null
$settingsPath = Join-Path $candidateData 'settings.json'
if (!(Test-Path -LiteralPath $settingsPath)) {
    [IO.File]::WriteAllText($settingsPath, '{"address":"http://127.0.0.1:9913","trackPointer":false}', (New-Object Text.UTF8Encoding($false)))
}
$settings = [IO.File]::ReadAllText($settingsPath) | ConvertFrom-Json
if ($settings.trackPointer -ne $false) { throw 'Candidate hover tracking is enabled. Set trackPointer to false in its own settings before using this launcher.' }
$health = $null
try { $health = Invoke-RestMethod ($serverUrl + '/health') -TimeoutSec 2 } catch { }
if (!$health) {
    $outLog = Join-Path $candidateData 'farm-server.stdout.log'
    $errLog = Join-Path $candidateData 'farm-server.stderr.log'
    $arguments = @('-u', ('"' + $serverScript + '"'), '--no-browser', '--mode', 'simulate', '--port', '9915')
    $backend = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WorkingDirectory $repoDir -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
    for ($attempt = 0; $attempt -lt 20 -and !$health; $attempt++) {
        if ($backend.HasExited) { throw "Candidate farm server exited. Read $errLog" }
        Start-Sleep -Milliseconds 250
        try { $health = Invoke-RestMethod ($serverUrl + '/health') -TimeoutSec 1 } catch { }
    }
}
if (!$health -or $health.protocolVersion -ne 2 -or $health.executionMode -ne 'simulate' -or $health.sourceHash -ne $expectedSource) {
    throw 'Port 9915 is not serving this exact simulation backend. No existing process was stopped and the console was not opened.'
}
# Visible by design: this script is the user's explicit app launcher.
Start-Process -FilePath $candidateExe -ArgumentList @('--address=http://127.0.0.1:9913', ('--data-dir="' + $candidateData + '"')) -WorkingDirectory $candidateDir
