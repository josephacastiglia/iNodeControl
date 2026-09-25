# Capture WCH board HID traffic using Windows USB ETW.
# No USBPcap, no extra driver. Works on this PC: Windows 11 25H2 (build 26200).
#
# USBPcap's site still says "Windows 7, 8 and 10". Its last signed driver is 1.5.4.0
# (2019). This machine has Secure Boot on and 19 live HID boards; a third-party USB
# filter driver is the wrong tool here. Windows already logs USB interrupt payloads
# via Microsoft-Windows-USB-USBHUB3 FullDataBusTrace (up to 4 KB per transfer, so a
# 9-byte HID report fits whole).
#
# Usage, elevated PowerShell:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\hid-capture.ps1
# Then drive ONE bound phone from iMouse 2.0 (list printed at start). Press Enter to stop.
# Output lands in analysis/hid-captures\ (etl + xml dump).

$ErrorActionPreference = "Stop"
$outDir = Join-Path $PSScriptRoot "..\analysis\hid-captures"
$name = "iMouseHid"

$admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Host "This uses Windows USB tracing (logman). It needs an elevated prompt, not USBPcap."
    Write-Host "Right-click PowerShell -> Run as administrator, then:"
    Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit 1
}

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$etl = Join-Path $outDir "vid720a-$stamp.etl"
$xml = Join-Path $outDir "vid720a-$stamp.xml"

Write-Host "HID capture via Windows USB ETW (no USBPcap)"
Write-Host "Output: $etl"
Write-Host ""
Write-Host "While this runs, send these against ONE bound phone from iMouse 2.0:"
Write-Host "  Reset"
Write-Host "  move the pointer a short way, then a long way (corner to corner)"
Write-Host "  click, then a short drag"
Write-Host "  Home"
Write-Host "  type a single letter a"
Write-Host "  Restart (board)"
Write-Host "Leave the other phones alone so the reports are easy to diff."
Write-Host ""

logman stop $name -ets 2>$null | Out-Null
logman delete $name 2>$null | Out-Null

# USB 3 stack: these boards hang off Terminus 7-port hubs on a USB 3 controller.
# FullDataBusTrace keeps the interrupt payload (HID reports). Rundown records
# which VID/PID is which at the start of the trace.
logman create trace -n $name -o $etl -nb 128 640 -bs 128 | Out-Host
logman update trace -n $name -p Microsoft-Windows-USB-USBXHCI "(Default,FullDataBusTrace,Rundown)" | Out-Host
logman update trace -n $name -p Microsoft-Windows-USB-UCX "(Default,FullDataBusTrace,Rundown)" | Out-Host
logman update trace -n $name -p Microsoft-Windows-USB-USBHUB3 "(Default,FullDataBusTrace,Rundown)" | Out-Host
logman start -n $name | Out-Host

Write-Host ""
Write-Host "Capturing. Press Enter when the actions above are done."
[void][Console]::ReadLine()

logman stop -n $name | Out-Host
logman delete -n $name | Out-Host

$rolled = Get-ChildItem -Path (Split-Path $etl) -Filter ("{0}*" -f [IO.Path]::GetFileNameWithoutExtension($etl)) -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in ".etl", ".etl.bak" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($rolled -and $rolled.FullName -ne $etl) {
    Copy-Item $rolled.FullName $etl -Force
}

if (-not (Test-Path $etl)) {
    $fallback = Get-ChildItem -Path (Split-Path $etl) -Filter "*.etl" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($fallback) { $etl = $fallback.FullName }
}

if (Test-Path $etl) {
    Write-Host "Dumping $etl to XML (this can take a minute)..."
    tracerpt $etl -o $xml -of XML -lr -y | Out-Host
    Write-Host "ETL: $etl"
    Write-Host "XML: $xml"
    Write-Host "Next: diff the 9-byte interrupt payloads around each action into analysis/HID-PROTOCOL.md"
} else {
    Write-Host "No ETL file was produced. The logman start/stop output above is the reason."
    exit 1
}
