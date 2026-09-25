# Kill only UxPlay. Kernel and console must stay up. C24C only.
$ErrorActionPreference = 'Stop'
$Id = '86:1D:4A:04:2F:F6'
$Base = 'http://127.0.0.1:9913/api'
function Status() { (Invoke-WebRequest -UseBasicParsing "$Base/kernel/status" -TimeoutSec 5).Content | ConvertFrom-Json }
function Shot($name) {
    $r = Invoke-WebRequest -UseBasicParsing "$Base/pic/screenshot?id=$Id&binary=true" -TimeoutSec 5
    $path = Join-Path $PSScriptRoot "..\analysis\$name"
    if ($r.Headers['Content-Type'] -match 'image/bmp') {
        [IO.File]::WriteAllBytes($path, $r.Content)
        Write-Host "bmp $name"
    } else {
        Set-Content $path $r.Content
        Write-Host "json $name $($r.Content)"
    }
}

$before = Status
$kernel = Get-Process iMouse2.Kernel
$console = Get-Process iMouse2 | Where-Object { $_.Path -like '*iMouse2-independent*' }
$ux = Get-Process uxplay
if (-not $before.data.live) { throw 'Need live video before crash test.' }
$dev = ((Invoke-WebRequest -UseBasicParsing "$Base/device/get").Content | ConvertFrom-Json).data.list[0]
if ($dev.pid -ne 'C24C' -or $dev.deviceid -ne $Id) { throw "bad bind $($dev.pid)" }
Write-Host "kernel=$($kernel.Id) console=$($console.Id) uxplay=$($ux.Id) frames=$($before.data.frames)"

Stop-Process -Id $ux.Id -Force
$sawRestarting = $false
$newPid = 0
$deadline = (Get-Date).AddSeconds(20)
do {
    Start-Sleep -Milliseconds 400
    $s = Status
    if ($s.data.receiver_state -eq 'restarting') { $sawRestarting = $true; Write-Host "restarting pid=$($s.data.receiver_pid) restarts=$($s.data.receiver_restarts)" }
    if ($s.data.receiver_pid -gt 0 -and $s.data.receiver_pid -ne $ux.Id -and $s.data.receiver_state -eq 'running') {
        $newPid = $s.data.receiver_pid
        break
    }
} while ((Get-Date) -lt $deadline)

$kernel2 = Get-Process iMouse2.Kernel
$console2 = Get-Process iMouse2 | Where-Object { $_.Path -like '*iMouse2-independent*' }
if ($kernel2.Id -ne $kernel.Id) { throw "kernel restarted $($kernel.Id) -> $($kernel2.Id)" }
if ($console2.Id -ne $console.Id) { throw "console restarted $($console.Id) -> $($console2.Id)" }
if ($newPid -eq 0) { throw "UxPlay did not come back. last=$($s.data | ConvertTo-Json -Compress)" }
$shot = Invoke-WebRequest -UseBasicParsing "$Base/pic/screenshot?id=$Id&binary=true" -TimeoutSec 5
if ($shot.Headers['Content-Type'] -match 'image/bmp') { throw 'stale BMP after crash' }
Write-Host "PASS crash: kernel $($kernel.Id) console $($console.Id) uxplay $($ux.Id)->$newPid restarting=$sawRestarting"
$s | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $PSScriptRoot '..\analysis\receiver-autorestart-status.json')
Shot 'receiver-autorestart-noframe.json'
Write-Host "Recast 2F:F6 to iMouse2-C24C. Kernel and console were not restarted."
