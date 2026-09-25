# Alternating original vs candidate console comparison. Closes only iMouse2.exe.
# Kernel and UxPlay stay up. C24C/C241 only. Mirror-to-all is not used.
param(
    [int]$Seconds = 90,
    [int]$WarmupSeconds = 30,
    [int]$SampleMs = 2000
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $root 'analysis\console-compare-20260915'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$orig = Join-Path $root 'release\iMouse2-two-phone\iMouse2.exe'
$cand = Join-Path $root 'release\iMouse2-two-phone-candidate\iMouse2.exe'
$kernelWant = Join-Path $root 'release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe'
$C24C = '86:1D:4A:04:2F:F6'
$C241 = 'FE:A9:BC:D7:A0:44'

function Get-Status {
    (Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 5).data
}
function Assert-Kernel {
    $k = Get-Process iMouse2.Kernel -ErrorAction Stop
    if ($k.Count -ne 1) { throw "expected 1 kernel, got $($k.Count)" }
    if ($k.Path -ne $kernelWant) { throw "kernel path $($k.Path)" }
    $st = Get-Status
    $allow = ($st.allowed | Sort-Object) -join ','
    if ($allow -ne 'C241,C24C') { throw "allow $allow" }
    $names = $st.receivers | ForEach-Object { $_.name }
    if ($names -notcontains 'iMouse2-C24C' -or $names -notcontains 'iMouse2-C241') { throw "receivers $names" }
    $ux = @(Get-Process uxplay -ErrorAction Stop)
    if ($ux.Count -ne 2) { throw "expected 2 uxplay, got $($ux.Count)" }
    return @{ kernel = $k; status = $st; uxplay = $ux }
}
function Get-Console {
    $c = @(Get-Process iMouse2 -ErrorAction SilentlyContinue)
    return $c
}
function Send-Home([string]$id) {
    $body = @{ fun = '/key/sendkey'; data = @{ id = $id; fn_key = 'Home' } } | ConvertTo-Json -Compress
    $r = Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:9913/api/' -ContentType 'application/json' -Body $body -TimeoutSec 20
    if ($r.status -ne 200 -or $r.data.code -ne 0) { throw "Home $id $($r | ConvertTo-Json -Compress)" }
}
function Save-Shot([string]$id, [string]$name) {
    $dest = Join-Path $out $name
    Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:9913/api/pic/screenshot?id=$id&binary=true" -TimeoutSec 8 -OutFile $dest
}
function Read-Ui([int]$processId) {
    try {
        Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes -ErrorAction Stop
        $p = Get-Process -Id $processId
        $root = [System.Windows.Automation.AutomationElement]::FromHandle($p.MainWindowHandle)
        if ($null -eq $root) { return @{ error = 'no hwnd' } }
        function TextId($id) {
            $c = New-Object System.Windows.Automation.PropertyCondition ([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
            $el = $root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $c)
            if ($null -eq $el) { return '' }
            $el.Current.Name
        }
        return @{
            selected = TextId 'SelectedTitle'
            frame = TextId 'FrameStatus'
            status = TextId 'StatusInfo'
            totals = TextId 'Totals'
        }
    } catch { return @{ error = $_.Exception.Message } }
}
function Set-Maximized([int]$processId) {
    Add-Type -TypeDefinition @"
using System; using System.Runtime.InteropServices;
public class WinMax {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
}
"@ -ErrorAction SilentlyContinue
    $h = (Get-Process -Id $processId).MainWindowHandle
    [WinMax]::ShowWindow($h, 3) | Out-Null
}
function Switch-Console([string]$exe) {
    $alive = Get-Console
    foreach ($p in $alive) {
        if ($p.Path -notlike '*iMouse2.exe') { throw "refusing to kill $($p.Path)" }
        Stop-Process -Id $p.Id -Force
    }
    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Console).Count -gt 0 -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200 }
    if ((Get-Console).Count -gt 0) { throw 'console did not exit' }
    Assert-Kernel | Out-Null
    $wd = Split-Path $exe
    $proc = Start-Process -FilePath $exe -WorkingDirectory $wd -PassThru
    $ready = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 400
        $p = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
        if ($p -and $p.MainWindowHandle -ne [IntPtr]::Zero) { break }
    } while ((Get-Date) -lt $ready)
    if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) { throw "failed to start $exe" }
    Set-Maximized $proc.Id
    Start-Sleep -Seconds 2
    return $proc
}
function Record-Phase([string]$phase, [int]$consoleId, [string]$exePath) {
    $log = Join-Path $out "$phase-telemetry.jsonl"
    $uiLog = Join-Path $out "$phase-ui.jsonl"
    if (Test-Path $log) { throw "exists $log" }
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $uiEvery = 0
    do {
        try {
            $k = Assert-Kernel
            $con = Get-Process -Id $consoleId -ErrorAction Stop
            if ($con.Path -ne $exePath) { throw "console path $($con.Path) != $exePath" }
            $ids = @($consoleId, $k.kernel.Id) + @($k.status.receivers | ForEach-Object { $_.receiver_pid })
            $processes = @(Get-Process -Id $ids -ErrorAction Stop | ForEach-Object {
                @{ id = $_.Id; name = $_.ProcessName; path = $_.Path; working_set = $_.WorkingSet64; private_bytes = $_.PrivateMemorySize64; cpu_s = $_.CPU; responding = $_.Responding }
            })
            $row = @{
                at = [DateTime]::UtcNow.ToString('o')
                elapsed_s = $watch.Elapsed.TotalSeconds
                logical_cpus = [Environment]::ProcessorCount
                console_id = $consoleId
                console_path = $exePath
                kernel_id = $k.kernel.Id
                kernel_path = $k.kernel.Path
                phase = $phase
                receivers = $k.status.receivers
                processes = $processes
            }
        } catch {
            $row = @{ at = [DateTime]::UtcNow.ToString('o'); elapsed_s = $watch.Elapsed.TotalSeconds; phase = $phase; error = $_.Exception.Message }
        }
        ($row | ConvertTo-Json -Depth 8 -Compress) | Add-Content -LiteralPath $log
        if ($uiEvery % 5 -eq 0) {
            $ui = Read-Ui -processId $consoleId
            $ui.at = [DateTime]::UtcNow.ToString('o')
            $ui.phase = $phase
            ($ui | ConvertTo-Json -Compress) | Add-Content -LiteralPath $uiLog
        }
        $uiEvery++
        if ($watch.Elapsed.TotalSeconds -ge $Seconds) { break }
        Start-Sleep -Milliseconds $SampleMs
    } while ($true)
}

$ident = Assert-Kernel
Write-Host "kernel $($ident.kernel.Id) $($ident.kernel.Path)"
$ident.status.receivers | ForEach-Object { Write-Host "receiver $($_.name) pid=$($_.receiver_pid) live=$($_.live) frames=$($_.frames) restarts=$($_.receiver_restarts)" }

# Workload: both phones on first Home page (animated clock). Isolated Homes, no Mirror-to-all.
Send-Home $C24C
Start-Sleep -Milliseconds 400
Send-Home $C241
Start-Sleep -Seconds 1
Save-Shot $C24C 'pre-C24C.bmp'
Save-Shot $C241 'pre-C241.bmp'

$order = @(
    @{ name = 'candidate-a'; exe = $cand },
    @{ name = 'original-a'; exe = $orig },
    @{ name = 'candidate-b'; exe = $cand },
    @{ name = 'original-b'; exe = $orig }
)
$run = @()
foreach ($step in $order) {
    Write-Host "=== $($step.name) $($step.exe) ==="
    Send-Home $C24C
    Start-Sleep -Milliseconds 350
    Send-Home $C241
    $cur = Get-Console
    $needStart = $true
    if ($cur.Count -eq 1 -and $cur[0].Path -eq $step.exe) {
        $needStart = $false
        $proc = $cur[0]
        Write-Host "already running pid $($proc.Id)"
    }
    if ($needStart) {
        $proc = Switch-Console $step.exe
        Write-Host "started pid $($proc.Id)"
    }
    Set-Maximized $proc.Id
    Save-Shot $C24C "$($step.name)-home-C24C.bmp"
    Save-Shot $C241 "$($step.name)-home-C241.bmp"
    Write-Host "warmup ${WarmupSeconds}s"
    Start-Sleep -Seconds $WarmupSeconds
    Assert-Kernel | Out-Null
    $p = Get-Process -Id $proc.Id
    Record-Phase $step.name $p.Id $step.exe
    $run += @{ phase = $step.name; console_id = $p.Id; console_path = $p.Path }
    Write-Host "finished $($step.name)"
}
$run | ConvertTo-Json | Set-Content (Join-Path $out 'run-order.json')
Write-Host 'Restoring candidate console'
$null = Switch-Console $cand
$run | ConvertTo-Json | Set-Content (Join-Path $out 'run-order.json')
Write-Host "DONE compare $out"
