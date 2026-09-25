param([int]$Seconds = 720)
$ErrorActionPreference = 'Stop'
$out = Join-Path $PSScriptRoot '..\analysis\two-phone-live-test-20260914'
[IO.Directory]::CreateDirectory($out) | Out-Null
$log = Join-Path $out 'telemetry.jsonl'
$watch = [Diagnostics.Stopwatch]::StartNew()
while ($watch.Elapsed.TotalSeconds -lt $Seconds) {
    try {
        $status = (Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 5).data
        $processes = @(Get-Process -Id 2804,32328,20972,33972 -ErrorAction SilentlyContinue | ForEach-Object {
            @{ id=$_.Id; name=$_.ProcessName; working_set=$_.WorkingSet64; private_bytes=$_.PrivateMemorySize64; cpu_s=$_.CPU; responding=$_.Responding }
        })
        $row = @{ at=[DateTime]::UtcNow.ToString('o'); elapsed_s=$watch.Elapsed.TotalSeconds; logical_cpus=[Environment]::ProcessorCount; receivers=$status.receivers; processes=$processes }
    } catch { $row = @{ at=[DateTime]::UtcNow.ToString('o'); elapsed_s=$watch.Elapsed.TotalSeconds; error=$_.Exception.Message } }
    ($row | ConvertTo-Json -Depth 8 -Compress) | Add-Content -LiteralPath $log
    Start-Sleep -Seconds 5
}
Write-Output "Monitoring complete: $log"
