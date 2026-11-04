# Separate native candidate. Does not restart the rack or alter installed shortcuts.
param([switch]$ValidateOnly, [string]$PythonPath, [string]$DraftWorkflowConfig, [string]$DraftCreationConfig)
$ErrorActionPreference = 'Stop'
$repoDir = $PSScriptRoot
$candidateDir = Join-Path $repoDir 'output\codex-farm-recovery-20261019'
$candidateExe = Join-Path $candidateDir 'iMouse2.exe'
$mode = if ($DraftWorkflowConfig -or $DraftCreationConfig) { 'live' } else { 'simulate' }
$consoleAddress = if ($DraftWorkflowConfig -or $DraftCreationConfig) { 'http://127.0.0.1:9916' } else { 'http://127.0.0.1:9913' }
$candidateData = Join-Path $candidateDir $(if ($DraftCreationConfig) { 'draft-creation-data' } elseif ($DraftWorkflowConfig) { 'draft-workflow-data' } else { 'candidate-data' })
foreach ($configPath in @($DraftWorkflowConfig, $DraftCreationConfig) | Where-Object { $_ }) {
    $configPath = (Resolve-Path -LiteralPath $configPath).Path
    $workflowIdentity = [IO.File]::ReadAllText($configPath) | ConvertFrom-Json
    if ($workflowIdentity.version -ne 1 -or $workflowIdentity.api -cne 'http://127.0.0.1:9916/api' -or $workflowIdentity.kernelSha256 -cnotmatch '^[0-9a-f]{64}$' -or !$workflowIdentity.expectedUid) {
        throw 'The draft workflow needs a prepared isolated C24C kernel identity on 9916.'
    }
}
$serverScript = Join-Path $repoDir 'tools\imouse_farm_server.py'
$serverUrl = 'http://127.0.0.1:9915'
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
$pythonCandidates = @($PythonPath, (Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python\Python311\python.exe'), $pythonCommand.Source)
$pythonExe = $pythonCandidates | Where-Object { $_ -and $_ -notlike '*\WindowsApps\*' -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (!(Test-Path -LiteralPath $candidateExe -PathType Leaf)) { throw "Build the candidate first: $candidateExe" }
if (!$pythonExe) { throw 'Python was not found. Pass -PythonPath with the full path to your Python executable.' }
$expectedBytes = New-Object System.IO.MemoryStream
foreach ($name in @('imouse_farm_server.py', 'imouse_social_automation.py', 'farm_jobs.py', 'farm_drafts.py', 'farm_media_transfer.py', 'farm_transfers.py', 'farm_capabilities.py', 'farm_video.py', 'farm_image.py', 'farm_observations.py', 'Read-FarmImageText.ps1', 'farm_preparation_schedule.py', 'farm_frame_evidence.py', 'farm_draft_verification.py', 'farm_draft_media.py', 'farm_carousel_inspection.py', 'farm_draft_rehearsal.py', 'farm_screen_layout.py', 'farm_transitions.py', 'farm_live_verification.py', 'farm_draft_transport.py', 'farm_draft_workflow.py', 'farm_draft_runs.py', 'farm_draft_anchors.json', 'farm_draft_creation.py', 'farm_creation_runs.py', 'farm_creation_layout.py', 'farm_creation_badges.json', 'farm_creation_browser.json', 'farm_creation_controls.json', 'farm_draft_recovery.py', 'farm_format_coverage.py', 'farm_reel_layout.py', 'farm_reel_controls.json', 'farm_reel_creation.py', 'farm_reel_runs.py', 'farm_tiktok_layout.py', 'farm_tiktok_controls.json', 'farm_tiktok_creation.py', 'farm_tiktok_runs.py', 'farm_permission_prompts.py', 'farm_x_layout.py', 'farm_x_creation.py', 'farm_x_runs.py', 'farm_youtube_layout.py', 'farm_youtube_controls.json', 'farm_youtube_creation.py', 'farm_youtube_runs.py')) {
    $bytes = [IO.File]::ReadAllBytes((Join-Path $repoDir ('tools\' + $name)))
    $expectedBytes.Write($bytes, 0, $bytes.Length)
}
$hasher = [Security.Cryptography.SHA256]::Create()
try { $expectedSource = ([BitConverter]::ToString($hasher.ComputeHash($expectedBytes.ToArray()))).Replace('-', '').ToLowerInvariant() }
finally { $hasher.Dispose(); $expectedBytes.Dispose() }
if ($ValidateOnly) {
    [pscustomobject]@{ Candidate = $candidateExe; DataDirectory = $candidateData; FarmEndpoint = $serverUrl; Mode = $mode; ConsoleAddress = $consoleAddress; DraftWorkflowConfig = $DraftWorkflowConfig; DraftCreationConfig = $DraftCreationConfig; SourceHash = $expectedSource; StartsProcesses = $false }
    return
}
[IO.Directory]::CreateDirectory($candidateData) | Out-Null
$settingsPath = Join-Path $candidateData 'settings.json'
if (!(Test-Path -LiteralPath $settingsPath)) {
    [IO.File]::WriteAllText($settingsPath, (@{address=$consoleAddress;trackPointer=$false} | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
}
$settings = [IO.File]::ReadAllText($settingsPath) | ConvertFrom-Json
if ($settings.address -ne $consoleAddress) { throw 'Candidate settings target a different service; no process was started.' }
if ($settings.trackPointer -ne $false) { throw 'Candidate hover tracking is enabled. Set trackPointer to false in its own settings before using this launcher.' }
$health = $null
try { $health = Invoke-RestMethod ($serverUrl + '/health') -TimeoutSec 2 } catch { }
if (!$health) {
    $outLog = Join-Path $candidateData 'farm-server.stdout.log'
    $errLog = Join-Path $candidateData 'farm-server.stderr.log'
    $arguments = @('-u', ('"' + $serverScript + '"'), '--no-browser', '--mode', $mode, '--port', '9915')
    if ($DraftWorkflowConfig) { $arguments += @('--draft-workflow-config', ('"' + $DraftWorkflowConfig + '"')) }
    if ($DraftCreationConfig) { $arguments += @('--draft-creation-config', ('"' + $DraftCreationConfig + '"')) }
    $arguments += @('--data-dir', ('"' + (Join-Path $candidateData 'backend') + '"'))
    $backend = Start-Process -FilePath $pythonExe -ArgumentList $arguments -WorkingDirectory $repoDir -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
    for ($attempt = 0; $attempt -lt 20 -and !$health; $attempt++) {
        if ($backend.HasExited) { throw "Candidate farm server exited. Read $errLog" }
        Start-Sleep -Milliseconds 250
        try { $health = Invoke-RestMethod ($serverUrl + '/health') -TimeoutSec 1 } catch { }
    }
}
if (!$health -or $health.protocolVersion -ne 2 -or $health.executionMode -ne $mode -or $health.sourceHash -ne $expectedSource) {
    throw 'Port 9915 is not serving this exact candidate backend. No existing process was stopped and the console was not opened.'
}
if ([bool]$health.draftWorkflow.enabled -ne [bool]$DraftWorkflowConfig) { throw 'The running backend has different draft workflow permissions.' }
if ([bool]$health.draftCreation.enabled -ne [bool]$DraftCreationConfig) { throw 'The running backend has different new-draft permissions.' }
if ([bool]$health.reelCreation.enabled -ne [bool]$DraftCreationConfig) { throw 'The running backend has different Reel draft permissions.' }
if ([bool]$health.tiktokCreation.enabled -ne [bool]$DraftCreationConfig) { throw 'The running backend has different TikTok draft permissions.' }
if ([bool]$health.xCreation.enabled -ne [bool]$DraftCreationConfig) { throw 'The running backend has different X draft permissions.' }
# YouTube also needs its phone in the configuration, so a creation configuration may leave it disabled; never the reverse.
if ([bool]$health.youtubeCreation.enabled -and -not $DraftCreationConfig) { throw 'The running backend has different YouTube draft permissions.' }
# Visible by design: this script is the user's explicit app launcher.
Start-Process -FilePath $candidateExe -ArgumentList @(('--address=' + $consoleAddress), ('--data-dir="' + $candidateData + '"')) -WorkingDirectory $candidateDir
