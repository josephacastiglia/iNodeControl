# Live checks for the authorized iPhone XR only. Refuses any other id/board.
$ErrorActionPreference = 'Stop'
$Id = '86:1D:4A:04:2F:F6'
$TestBoardPid = 'C24C'
$Uid = 'C24CBFBD'
$Base = 'http://127.0.0.1:9913/api'
$Out = Join-Path $PSScriptRoot '..\analysis'
function Get-Json($path) {
    $r = Invoke-WebRequest -UseBasicParsing "$Base$path" -TimeoutSec 5
    $r.Content | ConvertFrom-Json
}
function Send-Fun($fun, $data) {
    $body = @{ fun = $fun; data = $data } | ConvertTo-Json -Compress
    $r = Invoke-WebRequest -UseBasicParsing -Method POST -Uri "$Base/" -ContentType 'application/json' -Body $body -TimeoutSec 30
    $j = $r.Content | ConvertFrom-Json
    if ($j.status -ne 200 -or $j.data.code -ne 0) { throw "$fun failed: $($r.Content)" }
    $j
}
function Save-Shot($name) {
    $r = Invoke-WebRequest -UseBasicParsing "$Base/pic/screenshot?id=$Id&binary=true" -TimeoutSec 5
    if ($r.Headers['Content-Type'] -notmatch 'image/bmp') { throw "Not a BMP for $name : $($r.Content)" }
    $path = Join-Path $Out $name
    [IO.File]::WriteAllBytes($path, $r.Content)
    $path
}

$st = Get-Json '/kernel/status'
if (-not $st.data.live) { throw "Video is not live. Recast this phone to $($st.data.receiver)." }
$dev = (Get-Json '/device/get').data.list | Where-Object { $_.deviceid -eq $Id }
if ($null -eq $dev) { throw "Test phone missing from device list." }
if ($dev.pid -ne $TestBoardPid -or $dev.uid -ne $Uid) { throw "Binding is $($dev.pid)/$($dev.uid), expected $TestBoardPid/$Uid. Do not send input." }
Write-Host "identity ok pid=$($dev.pid) uid=$($dev.uid) live=$($st.data.live) frames=$($st.data.frames)"

Send-Fun '/mouse/reset' @{ id = $Id } | Out-Null
Start-Sleep -Milliseconds 200
Save-Shot 'live-reset.bmp' | Out-Null
Send-Fun '/key/sendkey' @{ id = $Id; fn_key = 'Home' } | Out-Null
Start-Sleep -Seconds 1
Save-Shot 'live-home.bmp' | Out-Null
Send-Fun '/mouse/click' @{ id = $Id; x = 250; y = 900; button = 1 } | Out-Null
Start-Sleep -Seconds 1
Save-Shot 'live-click-search.bmp' | Out-Null
Write-Host 'reset, Home, single Search click sent. Inspect analysis/live-*.bmp'
