# Stop only this run's exact process through its normal Ctrl+C shutdown.
$ErrorActionPreference = 'Stop'
$record = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'started.json') -Encoding UTF8 | ConvertFrom-Json
$target = Get-CimInstance Win32_Process -Filter "ProcessId=$($record.pid)"
if (-not $target) { 'Recorded candidate is no longer running; nothing signalled.'; exit 0 }
$startedUtc = if ($record.startedUtc -is [datetime]) {
    $record.startedUtc.ToUniversalTime()
} else {
    [datetime]::Parse($record.startedUtc, [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
}
if ($target.ExecutablePath -ine $record.path -or
    [Math]::Abs(($target.CreationDate.ToUniversalTime() - $startedUtc).TotalSeconds) -gt 1) {
    throw 'The recorded PID belongs to a different process; nothing signalled.'
}
$helper = Join-Path $PSScriptRoot '..\..\tools\kernel-window\Stop-ConsoleProcessGracefully.ps1'
& $helper -ProcessId $record.pid -ExpectedPath $record.path -TimeoutSeconds 20
exit $LASTEXITCODE
