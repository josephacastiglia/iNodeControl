param([Parameter(Mandatory=$true)][string]$RunDir)
$ErrorActionPreference='Stop'
if (Test-Path -LiteralPath $RunDir) { throw 'Preserve prior evidence' }
$repo=Split-Path (Split-Path $PSScriptRoot)
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $repo 'Open iMouse 2.0.ps1'),[ref]$null,[ref]$null)
$fn=$ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$true) | Where-Object Name -eq 'Start-ReleaseKernel'
. ([scriptblock]::Create($fn.Extent.Text))
$done=(Join-Path $RunDir 'done.txt').Replace("'","''")
$code="[Console]::Error.WriteLine('first'); Start-Sleep -Seconds 2; [Console]::Error.WriteLine('last'); [IO.File]::WriteAllText('$done','finished')"
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($code))
$shell=Join-Path $PSHOME 'powershell.exe'
if (Test-Path -LiteralPath (Join-Path $PSHOME 'pwsh.exe')) { $shell=Join-Path $PSHOME 'pwsh.exe' }
$start=Start-ReleaseKernel -Exe $shell -Arguments @('-NoProfile','-NonInteractive','-EncodedCommand',$encoded) -WorkingDirectory $RunDir
[pscustomobject]@{pid=$start.Process.Id; log=$start.ErrorLog; parent_finished_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json
# Exit normally, without waiting for the synthetic child. It writes once more later.
