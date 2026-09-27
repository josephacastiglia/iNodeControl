<#
.SYNOPSIS
  Captures a phone's mirrored screen from the kernel at a fixed interval, for a set duration, so
  a live input test has a frame record of the whole hold and recovery.

.DESCRIPTION
  Read-only: it only calls GET /api/pic/screenshot. Each frame is saved as PNG with its capture
  time; frames.tsv lists every attempt (time, HTTP result, bytes, SHA-256 of the PNG, or the
  error). started.txt is written before the first request, so a caller can confirm the capture
  is running before it acts; done.txt holds the summary. Exit code 0 only if every attempt
  produced a frame.

  Start it in the background with the path quoted, for example:
    Start-Process powershell -WindowStyle Hidden -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass',
      '-File', "`"$script`"", '-OutDir', "`"$dir`"", '-DeviceId', '86:1D:4A:04:2F:F6', '-Seconds', '60')
  The earlier ad-hoc burst never started because an unquoted path with a space split the -File argument.

.EXAMPLE
  .\Capture-PhoneFrames.ps1 -OutDir "C:\...\live\D7" -DeviceId 86:1D:4A:04:2F:F6 -Seconds 60 -IntervalMs 500
#>
param(
    [Parameter(Mandatory)][string]$OutDir,
    [Parameter(Mandatory)][string]$DeviceId,
    [string]$Kernel = 'http://127.0.0.1:9913',
    [int]$Seconds = 60,
    [int]$IntervalMs = 500
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing, System.Net.Http
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$index = Join-Path $OutDir 'frames.tsv'
$uri = '{0}/api/pic/screenshot?id={1}&binary=true' -f $Kernel.TrimEnd('/'), [Uri]::EscapeDataString($DeviceId)
$client = New-Object System.Net.Http.HttpClient
$client.Timeout = [TimeSpan]::FromSeconds(5)
$sha = [Security.Cryptography.SHA256]::Create()

"time`tframe`tresult`tbytes`tsha256" | Set-Content -LiteralPath $index -Encoding UTF8
('{0:o} pid {1} device {2} every {3} ms for {4} s' -f (Get-Date), $PID, $DeviceId, $IntervalMs, $Seconds) | Set-Content -LiteralPath (Join-Path $OutDir 'started.txt') -Encoding UTF8

$end = (Get-Date).AddSeconds($Seconds)
$n = 0; $ok = 0; $failed = 0
while ((Get-Date) -lt $end) {
    $t = Get-Date
    $name = '{0:D4}-{1:HHmmss-fff}.png' -f $n, $t
    try {
        $response = $client.GetAsync($uri).GetAwaiter().GetResult()
        $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        # The kernel answers a missing frame with JSON, not an image.
        if (-not $response.IsSuccessStatusCode -or $bytes.Length -lt 2 -or $bytes[0] -ne 0x42 -or $bytes[1] -ne 0x4D) {
            throw ('no frame: HTTP {0}, {1} bytes, starts "{2}"' -f [int]$response.StatusCode, $bytes.Length, [Text.Encoding]::ASCII.GetString($bytes, 0, [Math]::Min(60, $bytes.Length)))
        }
        $ms = New-Object IO.MemoryStream(, $bytes)
        $img = [Drawing.Image]::FromStream($ms)
        $out = Join-Path $OutDir $name
        $img.Save($out, [Drawing.Imaging.ImageFormat]::Png); $img.Dispose(); $ms.Dispose()
        $hash = -join ($sha.ComputeHash([IO.File]::ReadAllBytes($out)) | ForEach-Object { $_.ToString('X2') })
        "{0:HH:mm:ss.fff}`t{1}`tok`t{2}`t{3}" -f $t, $name, $bytes.Length, $hash | Add-Content -LiteralPath $index -Encoding UTF8
        $ok++
    }
    catch {
        "{0:HH:mm:ss.fff}`t-`terror`t0`t{1}" -f $t, ($_.Exception.Message -replace '\s+', ' ') | Add-Content -LiteralPath $index -Encoding UTF8
        $failed++
    }
    $n++
    $wait = $IntervalMs - ((Get-Date) - $t).TotalMilliseconds
    if ($wait -gt 0) { Start-Sleep -Milliseconds ([int]$wait) }
}
('{0:o} attempts {1} frames {2} failed {3}' -f (Get-Date), $n, $ok, $failed) | Set-Content -LiteralPath (Join-Path $OutDir 'done.txt') -Encoding UTF8
if ($failed -gt 0 -or $ok -eq 0) { exit 1 }
exit 0
