$ErrorActionPreference='Stop'
$taskPrep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw | ConvertFrom-Json
$taskProbe=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'fault-preparation.json') -Raw | ConvertFrom-Json
if((Get-FileHash -LiteralPath $taskProbe.path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskProbe.sha256 -or (Get-FileHash -LiteralPath ([IO.Path]::ChangeExtension($taskProbe.path,'.dll')) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskProbe.managedSha256){throw 'Prepared result-recovery probe changed.'}
$taskOptions=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'native-options-2.json') -Raw | ConvertFrom-Json
$taskValue=(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'native-inspection-2/result.json') -Raw | ConvertFrom-Json).run
if(!$taskValue.terminal -or !$taskValue.savedDraftVerified){throw 'Second inspection has no completed result to recover.'}
$taskOptions.output=Join-Path $PSScriptRoot 'native-result-recovery'
$taskOptions.dataDirectory=Join-Path $taskPrep.runDirectory 'native-result-recovery-data'
$taskOptions.faultMode='recoverOnly'
$taskOptions | Add-Member -NotePropertyName expectedId -NotePropertyValue $taskValue.id
if((Test-Path -LiteralPath $taskOptions.output) -or (Test-Path -LiteralPath $taskOptions.dataDirectory)){throw 'Retained-result probe already exists; never repeat it.'}
New-Item -ItemType Directory -Path $taskOptions.dataDirectory | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'native-inspection-2/retained-bookmark.json') -Destination (Join-Path $taskOptions.dataDirectory 'farm-pending-draft-inspection.json')
$taskFile=Join-Path $PSScriptRoot 'retained-result-options.json'
[IO.File]::WriteAllText($taskFile,($taskOptions | ConvertTo-Json))
$taskProcess=Start-Process -FilePath $taskProbe.path -ArgumentList ('"'+$taskFile+'"') -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'native-result-recovery.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'native-result-recovery.stderr.txt')
@{pid=$taskProcess.Id;exitCode=$taskProcess.ExitCode;utc=[datetime]::UtcNow.ToString('o');phoneInput=$false;desktopControl=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'native-result-recovery.exit.json') -Encoding utf8
if($taskProcess.ExitCode -ne 0){throw 'Native retained-result recovery failed; preserve the output.'}
Get-Content -LiteralPath (Join-Path $PSScriptRoot 'native-result-recovery/checks.json')
