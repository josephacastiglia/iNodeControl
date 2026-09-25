param([Parameter(Mandatory=$true)][int]$ConsoleId,
      [Parameter(Mandatory=$true)][string]$Phase,
      [int]$Seconds = 90)
$ErrorActionPreference = 'Stop'
$out = Join-Path $PSScriptRoot '..\analysis\candidate-validation-20260915'
[IO.Directory]::CreateDirectory($out) | Out-Null
if ($Phase -notmatch '^[a-z0-9-]+$') { throw 'Invalid phase' }
$log = Join-Path $out ($Phase + '-telemetry.jsonl')
if (Test-Path -LiteralPath $log) { throw 'Refusing to overwrite existing benchmark' }
$watch = [Diagnostics.Stopwatch]::StartNew()
do {
    try {
        $status = (Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 5).data
        if (($status.allowed | Sort-Object) -join ',' -ne 'C241,C24C') { throw 'Unexpected input scope' }
        $ids = @($ConsoleId,32328) + @($status.receivers | ForEach-Object {$_.receiver_pid})
        $processes = @(Get-Process -Id $ids -ErrorAction Stop | ForEach-Object {
            @{ id=$_.Id; name=$_.ProcessName; working_set=$_.WorkingSet64; private_bytes=$_.PrivateMemorySize64; cpu_s=$_.CPU; responding=$_.Responding }
        })
        $row = @{ at=[DateTime]::UtcNow.ToString('o'); elapsed_s=$watch.Elapsed.TotalSeconds; logical_cpus=[Environment]::ProcessorCount; console_id=$ConsoleId; phase=$Phase; receivers=$status.receivers; processes=$processes }
    } catch { $row = @{ at=[DateTime]::UtcNow.ToString('o'); elapsed_s=$watch.Elapsed.TotalSeconds; error=$_.Exception.Message } }
    ($row | ConvertTo-Json -Depth 8 -Compress) | Add-Content -LiteralPath $log
    if ($watch.Elapsed.TotalSeconds -ge $Seconds) { break }
    Start-Sleep -Seconds 2
} while ($true)
Write-Output "Completed $Phase benchmark: $log"
