param([Parameter(Mandatory=$true)][string]$RecordName)
$ErrorActionPreference='Stop'
if ($RecordName -notmatch '^[a-z0-9-]+$') { throw 'Unsafe record name' }
$repo=Split-Path (Split-Path $PSScriptRoot)
$launcher=Join-Path $repo 'Open iMouse 2.0.ps1'
$ast=[Management.Automation.Language.Parser]::ParseFile($launcher,[ref]$null,[ref]$null)
foreach ($name in @('Start-ReleaseKernel','Read-ReleaseStartupError','Wait-ReleaseKernel')) {
    $fn=$ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$true) | Where-Object Name -eq $name
    . ([scriptblock]::Create($fn.Extent.Text))
}
# Never contact the installed service, including when the real validation child is alive.
function Invoke-RestMethod { throw 'Offline probe: no endpoint is contacted.' }
$kernel=Join-Path $repo 'analysis/runtime-startup-guard-20261013/final-kernel/iMouse2.Kernel.exe'
$dll=[IO.Path]::ChangeExtension($kernel,'.dll')
$expected='e0f00fa86c217e2c00913e22adc04c7c9c5477e670078b7a94f19e9d5af92e16'
if ((Get-FileHash -LiteralPath $dll).Hash -ine $expected) { throw 'Unexpected validation build' }
$data=Join-Path $repo 'output/candidate-runs/runtime-startup-20261013/kernel/data'
$broken=Join-Path $repo 'output/staging/combined-scope-release-20261012'
$run=Join-Path $PSScriptRoot $RecordName
if (Test-Path -LiteralPath $run) { throw 'Do not overwrite a prior probe' }
$protected=Get-Content -LiteralPath (Join-Path $repo 'analysis/runtime-provenance-20261012/protected-files.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($item in $protected) { if ((Get-FileHash -LiteralPath $item.path).Hash -ine $item.sha256) { throw 'Protected file changed before check' } }
$argsList=@('--validate-startup','http://127.0.0.1:9913/api/','--data-dir',('"'+$data+'"'),'--input-pid','C24C','--receivers',('"'+(Join-Path $data 'receivers.json')+'"'),
    '--receiver',('"'+(Join-Path $broken 'payload/receiver/uxplay.exe')+'"'),'--receiver-runtime',('"'+(Join-Path $broken 'dependencies/receiver-runtime/runtime')+'"'))
$started=Start-ReleaseKernel -Exe $kernel -Arguments $argsList -WorkingDirectory $run
if (!$started.Process.WaitForExit(15000)) { throw "Validation did not exit; PID $($started.Process.Id) preserved for inspection" }
$failure=''
try { Wait-ReleaseKernel $started | Out-Null } catch { $failure=$_.Exception.Message }
if ($null -ne $started.Process.ExitCode -and $started.Process.ExitCode -ne 2) { throw 'Wrong validation exit code' }
$exitText=if ($null -eq $started.Process.ExitCode) { 'exit code unavailable' } else { 'exit 2' }
foreach ($word in @($exitText,'Startup refused','libgstplayback.dll','libgstautodetect.dll','Verify the dependency package')) {
    if (!$failure.Contains($word)) { throw "Failure explanation missing $word : $failure" }
}
[IO.File]::WriteAllText((Join-Path $run 'displayed-message.txt'),$failure,[Text.UTF8Encoding]::new($false))
foreach ($item in $protected) { if ((Get-FileHash -LiteralPath $item.path).Hash -ine $item.sha256) { throw 'Protected file changed after check' } }
$result=[ordered]@{at_utc=[DateTime]::UtcNow.ToString('o'); powershell=$PSVersionTable.PSVersion.ToString(); passed=$true; exit_code=$started.Process.ExitCode;
    kernel_sha256=$expected; launcher_sha256=(Get-FileHash -LiteralPath $launcher).Hash.ToLowerInvariant(); pid=$started.Process.Id; process_exited=$started.Process.HasExited;
    validation_only=$true; service_reads_mocked=$true; no_dialog_shown=$true; protected_hashes_unchanged=$true; error_log=$started.ErrorLog;
    limitation='Actual kernel validation and launcher capture; no normal service startup, receiver, hardware or dialog interaction.'}
[IO.File]::WriteAllText((Join-Path $run 'result.json'),($result | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
$result | ConvertTo-Json -Depth 6
