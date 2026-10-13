$ErrorActionPreference = 'Stop'
$taskCases = @(
    @{ name='current-settings'; folder='control-current'; mode='settings'; expect=0; text='18 persistence checks passed' },
    @{ name='current-bindings'; folder='control-current'; mode='bindings'; expect=0; text='12 persistence checks passed' },
    @{ name='negative-settings'; folder='negative-settings-overwrite'; mode='settings'; expect=1; text='FAIL: Failed primary replacement reports a save failure' },
    @{ name='negative-bindings'; folder='negative-binding-publish'; mode='bindings'; expect=1; text='FAIL: Failed binding save preserves the in-memory assignment' }
)
$taskResults = foreach ($taskCase in $taskCases) {
    $taskDll = Join-Path $PSScriptRoot ('controls/' + $taskCase.folder + '/bin/Release/net8.0-windows/PersistenceChecks.dll')
    $taskLog = Join-Path $PSScriptRoot ($taskCase.name + '.txt')
    & dotnet $taskDll $taskCase.mode *> $taskLog
    $taskCode = $LASTEXITCODE
    $taskText = Get-Content -LiteralPath $taskLog -Encoding UTF8 -Raw
    $taskOk = (($taskCase.expect -eq 0 -and $taskCode -eq 0) -or ($taskCase.expect -eq 1 -and $taskCode -ne 0)) -and $taskText.Contains($taskCase.text)
    [ordered]@{ name=$taskCase.name; exit_code=$taskCode; expected=$taskCase.text; verified=$taskOk }
}
$taskResults | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'control-results.json') -Encoding UTF8
$taskResults | ConvertTo-Json
if (@($taskResults | Where-Object { -not $_.verified }).Count -ne 0) { exit 1 }
