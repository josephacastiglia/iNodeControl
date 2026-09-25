$ErrorActionPreference = 'Stop'
$Out = Split-Path -Parent $MyInvocation.MyCommand.Path
$Base = 'http://127.0.0.1:9913/api'
$KernelPid = 31944
$C24C = '86:1D:4A:04:2F:F6'
$C241 = 'FE:A9:BC:D7:A0:44'
Add-Type -AssemblyName System.Net.Http
$client = [System.Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromSeconds(8)

function Now() { [DateTimeOffset]::Now.ToString('o') }
function Round($n) { [math]::Round([double]$n, 1) }

function Get-Status {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $text = $client.GetStringAsync("$Base/kernel/status").GetAwaiter().GetResult()
    $sw.Stop()
    $obj = $text | ConvertFrom-Json
    @{ at = (Now); elapsed_ms = (Round $sw.Elapsed.TotalMilliseconds); text = $text; obj = $obj }
}

function Pick($status, $id) {
    @($status.obj.data.receivers | Where-Object { $_.deviceid -eq $id })[0]
}

function Slim($r) {
    if (-not $r) { return $null }
    @{
        deviceid = [string]$r.deviceid
        name = [string]$r.name
        live = [bool]$r.live
        frames = [int]$r.frames
        receiver_state = [string]$r.receiver_state
        receiver_pid = [int]$r.receiver_pid
        receiver_restarts = [int]$r.receiver_restarts
    }
}

function Get-Shot($id) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $resp = $client.GetAsync("$Base/pic/screenshot?id=$id&binary=true").GetAwaiter().GetResult()
    $bytes = $resp.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
    $sw.Stop()
    $isBmp = ($bytes.Length -ge 2 -and $bytes[0] -eq 0x42 -and $bytes[1] -eq 0x4D)
    $prefix = ''
    if ($bytes.Length -gt 0 -and -not $isBmp) {
        $n = [Math]::Min(500, $bytes.Length)
        $prefix = [Text.Encoding]::UTF8.GetString($bytes, 0, $n)
    }
    $sha = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($bytes)).Replace('-', '').ToLowerInvariant()
    @{
        at = (Now)
        elapsed_ms = (Round $sw.Elapsed.TotalMilliseconds)
        http = [int]$resp.StatusCode
        content_type = [string]$resp.Content.Headers.ContentType
        length = $bytes.Length
        is_bmp = $isBmp
        sha256 = $sha
        json_prefix = $prefix
        bytes = $bytes
    }
}

function Save-Shot($shot, $stem) {
    if ($shot.is_bmp) {
        $path = Join-Path $Out "$stem.bmp"
        [IO.File]::WriteAllBytes($path, $shot.bytes)
    } else {
        $path = Join-Path $Out "$stem.json"
        $text = if ($shot.json_prefix) { $shot.json_prefix } else { '' }
        [IO.File]::WriteAllText($path, $text)
    }
    $shot.path = $path
    $shot.Remove('bytes')
    $shot
}

function Proc($procId) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction SilentlyContinue
    if (-not $p) { return $null }
    @{
        pid = [int]$p.ProcessId
        name = [string]$p.Name
        parent = [int]$p.ParentProcessId
        command = [string]$p.CommandLine
    }
}

function KernelSnap() {
    $p = Get-Process -Id $KernelPid -ErrorAction SilentlyContinue
    if (-not $p) { return @{ alive = $false; pid = $KernelPid } }
    @{
        alive = $true
        pid = $p.Id
        name = $p.ProcessName
        start_time = $p.StartTime.ToString('o')
    }
}

function MirrorSnap() {
    $consoles = @(Get-Process | Where-Object { $_.MainWindowTitle -match 'iMouse' })
    if ($consoles.Count -lt 1) { return @{ found = $false; mirror_to_all = 'no-console' } }
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes -ErrorAction SilentlyContinue
    $boxes = @()
    foreach ($c in $consoles) {
        $root = [System.Windows.Automation.AutomationElement]::FromHandle($c.MainWindowHandle)
        $cond = New-Object System.Windows.Automation.PropertyCondition (
            [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
            [System.Windows.Automation.ControlType]::CheckBox)
        foreach ($el in $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)) {
            $tog = 'n/a'
            try { $tog = $el.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState.ToString() } catch {}
            $boxes += @{ name = [string]$el.Current.Name; id = [string]$el.Current.AutomationId; toggle = $tog; console_pid = $c.Id }
        }
    }
    $mirror = @($boxes | Where-Object { $_.id -eq 'SelectAllBox' -or $_.name -match 'Mirror' })
    $on = @($mirror | Where-Object { $_.toggle -eq 'On' })
    @{
        found = $true
        console_pid = $consoles[0].Id
        window = $consoles[0].MainWindowTitle
        mirror_on_count = $on.Count
        mirror_to_all = $(if ($on.Count -gt 0) { 'On' } else { 'Off' })
        boxes = $mirror
    }
}

$abort = $null
$kernelBefore = KernelSnap
if (-not $kernelBefore.alive -or $kernelBefore.name -ne 'iMouse2.Kernel') {
    $abort = "kernel $KernelPid is not the live iMouse2.Kernel"
}

$mirrorBefore = $null
if (-not $abort) {
    try { $mirrorBefore = MirrorSnap } catch { $abort = "mirror check failed: $($_.Exception.Message)" }
    if (-not $abort -and $mirrorBefore.mirror_to_all -eq 'On') { $abort = 'Mirror-to-all is ON; refusing to crash' }
}

$s0 = $null; $s1 = $null
if (-not $abort) {
    $s0 = Get-Status
    Start-Sleep -Milliseconds 1000
    $s1 = Get-Status
    $a0 = Pick $s0 $C24C; $b0 = Pick $s0 $C241
    $a1 = Pick $s1 $C24C; $b1 = Pick $s1 $C241
    if (-not $a1 -or -not $b1) { $abort = 'status missing C24C or C241' }
    elseif (-not $a1.live -or -not $b1.live) { $abort = 'baseline not live' }
    elseif ([string]$a1.receiver_state -ne 'mirroring' -or [string]$b1.receiver_state -ne 'mirroring') { $abort = 'baseline not mirroring' }
    elseif ([int]$a1.frames -le [int]$a0.frames -or [int]$b1.frames -le [int]$b0.frames) { $abort = 'baseline frames not advancing' }
    elseif ([int]$a1.receiver_pid -le 0 -or [int]$b1.receiver_pid -le 0) { $abort = 'baseline receiver pid missing' }
    elseif ([int]$a1.receiver_pid -eq [int]$b1.receiver_pid) { $abort = 'C24C and C241 share a receiver pid' }
    elseif ([int]$a1.receiver_pid -eq $KernelPid -or [int]$b1.receiver_pid -eq $KernelPid) { $abort = 'receiver pid is the kernel' }
}

$c24cProc = $null; $c241Proc = $null
if (-not $abort) {
    $c24cPid = [int]$a1.receiver_pid
    $c241Pid = [int]$b1.receiver_pid
    $c24cProc = Proc $c24cPid
    $c241Proc = Proc $c241Pid
    if (-not $c24cProc -or $c24cProc.name -notmatch 'uxplay') { $abort = "C24C pid $c24cPid is not uxplay" }
    elseif ($c24cProc.parent -ne $KernelPid) { $abort = "C24C pid $c24cPid parent is $($c24cProc.parent), not kernel $KernelPid" }
    elseif ($c24cProc.command -notmatch 'iMouse2-C24C') { $abort = 'C24C command line missing iMouse2-C24C' }
    elseif ($c24cProc.command -match 'iMouse2-C241') { $abort = 'C24C command line looks like C241' }
    elseif ($c24cProc.command -notmatch '(^|\s)-p\s+7110(\s|$)') { $abort = 'C24C command line is not port 7110' }
    elseif (-not $c241Proc -or $c241Proc.name -notmatch 'uxplay') { $abort = 'C241 uxplay missing before crash' }
    elseif ($c241Proc.parent -ne $KernelPid) { $abort = 'C241 parent is not the kernel' }
    elseif ($c241Proc.command -notmatch 'iMouse2-C241') { $abort = 'C241 command line missing iMouse2-C241' }
}

$baseShots = $null
if (-not $abort) {
    $baseShots = @{
        c24c = (Save-Shot (Get-Shot $C24C) 'baseline-c24c')
        c241 = (Save-Shot (Get-Shot $C241) 'baseline-c241')
    }
    if (-not $baseShots.c24c.is_bmp -or -not $baseShots.c241.is_bmp) { $abort = 'baseline screenshot was not a BMP' }
}

$crashAt = $null
$killReturnedMs = $null
$samples = @()
$immediate = $null
$relaunch = $null
$shots = @{}
$newProc = $null
$killedGone = $null

if (-not $abort) {
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $crashAt = Now
    Stop-Process -Id $c24cPid -Force
    $killReturnedMs = Round $clock.Elapsed.TotalMilliseconds
    $killedGone = -not [bool](Get-Process -Id $c24cPid -ErrorAction SilentlyContinue)

    $deadlineMs = 8000
    $shotImmediate = $false
    $shotRelaunch = $false
    $downRestarts = [int]$a1.receiver_restarts + 1
    while ($clock.Elapsed.TotalMilliseconds -lt $deadlineMs) {
        $st = Get-Status
        $elapsed = Round $clock.Elapsed.TotalMilliseconds
        $ca = Slim (Pick $st $C24C)
        $cb = Slim (Pick $st $C241)
        $sample = @{ elapsed_ms = $elapsed; status_ms = $st.elapsed_ms; at = $st.at; c24c = $ca; c241 = $cb }
        $samples += $sample
        $downNow = (-not $ca.live) -and ([int]$ca.receiver_restarts -ge $downRestarts)
        if (-not $shotImmediate -and ($downNow -or $elapsed -ge 1400)) {
            $immediate = $sample
            $immediate.within_1_5s = ($elapsed -lt 1500)
            $immediate.down_observed = $downNow
            [IO.File]::WriteAllText((Join-Path $Out 'status-immediate.json'), $st.text)
            $shots.immediate_c24c = Save-Shot (Get-Shot $C24C) 'immediate-c24c'
            $shots.immediate_c241 = Save-Shot (Get-Shot $C241) 'immediate-c241'
            $shotImmediate = $true
            $immediate.shot_elapsed_ms = Round $clock.Elapsed.TotalMilliseconds
        }

        $newPid = [int]$ca.receiver_pid
        $ready = ($newPid -gt 0 -and $newPid -ne $c24cPid -and [string]$ca.receiver_state -eq 'offline')
        if ($shotImmediate -and $ready -and -not $shotRelaunch) {
            $relaunch = $sample
            [IO.File]::WriteAllText((Join-Path $Out 'status-relaunch.json'), $st.text)
            $shots.relaunch_c24c = Save-Shot (Get-Shot $C24C) 'relaunch-c24c'
            $shots.relaunch_c241 = Save-Shot (Get-Shot $C241) 'relaunch-c241'
            $shotRelaunch = $true
            $relaunch.shot_elapsed_ms = Round $clock.Elapsed.TotalMilliseconds
            $newProc = Proc $newPid
            break
        }
        Start-Sleep -Milliseconds 80
    }
    if (-not $shotRelaunch) {
        $st = Get-Status
        $relaunch = @{
            elapsed_ms = (Round $clock.Elapsed.TotalMilliseconds)
            status_ms = $st.elapsed_ms
            c24c = (Slim (Pick $st $C24C))
            c241 = (Slim (Pick $st $C241))
            timed_out = $true
        }
        $shots.relaunch_c24c = Save-Shot (Get-Shot $C24C) 'relaunch-c24c'
        $shots.relaunch_c241 = Save-Shot (Get-Shot $C241) 'relaunch-c241'
        $np = [int]$relaunch.c24c.receiver_pid
        if ($np -gt 0) { $newProc = Proc $np }
    }
}

Start-Sleep -Milliseconds 1000
$final = $null
$kernelAfter = KernelSnap
$mirrorAfter = $null
try { $mirrorAfter = MirrorSnap } catch { $mirrorAfter = @{ error = $_.Exception.Message } }
if (-not $abort) {
    $sf = Get-Status
    $final = @{ at = $sf.at; c24c = (Slim (Pick $sf $C24C)); c241 = (Slim (Pick $sf $C241)) }
    [IO.File]::WriteAllText((Join-Path $Out 'status-final.json'), $sf.text)
}

$downJson = $null
if ($shots.immediate_c24c -and $shots.immediate_c24c.json_prefix) {
    try { $downJson = $shots.immediate_c24c.json_prefix | ConvertFrom-Json } catch {}
}
$upJson = $null
if ($shots.relaunch_c24c -and $shots.relaunch_c24c.json_prefix) {
    try { $upJson = $shots.relaunch_c24c.json_prefix | ConvertFrom-Json } catch {}
}

$c241Frames = @()
if ($s0) { $c241Frames += [int](Pick $s0 $C241).frames }
if ($s1) { $c241Frames += [int](Pick $s1 $C241).frames }
foreach ($sm in $samples) { $c241Frames += [int]$sm.c241.frames }
if ($final) { $c241Frames += [int]$final.c241.frames }
$c241Advanced = $true
for ($i = 1; $i -lt $c241Frames.Count; $i++) {
    if ($c241Frames[$i] -lt $c241Frames[$i - 1]) { $c241Advanced = $false }
}
$c241Net = 0
if ($c241Frames.Count -ge 2) { $c241Net = $c241Frames[-1] - $c241Frames[0] }

$newPid = 0
if ($relaunch) { $newPid = [int]$relaunch.c24c.receiver_pid }
$restartMs = $null
if ($relaunch -and $newPid -gt 0 -and $newPid -ne $c24cPid) { $restartMs = $relaunch.elapsed_ms }

$acceptRestart = [bool]($restartMs -ne $null -and $restartMs -le 4000 -and $newProc -and $newProc.parent -eq $KernelPid -and $newProc.command -match 'iMouse2-C24C' -and $newProc.command -notmatch 'iMouse2-C241')
$acceptNoStale = [bool]($shots.immediate_c24c -and -not $shots.immediate_c24c.is_bmp -and $downJson -and [int]$downJson.data.code -ne 0)
$acceptSibling = [bool]($immediate -and $relaunch -and $final -and $c241Advanced -and $c241Net -gt 0 -and
    $immediate.c241.live -and $relaunch.c241.live -and $final.c241.live -and
    [string]$immediate.c241.receiver_state -eq 'mirroring' -and
    [string]$relaunch.c241.receiver_state -eq 'mirroring' -and
    [string]$final.c241.receiver_state -eq 'mirroring' -and
    [int]$immediate.c241.receiver_restarts -eq [int]$b1.receiver_restarts -and
    [int]$relaunch.c241.receiver_restarts -eq [int]$b1.receiver_restarts -and
    [int]$final.c241.receiver_restarts -eq [int]$b1.receiver_restarts -and
    [int]$immediate.c241.receiver_pid -eq $c241Pid -and
    [int]$relaunch.c241.receiver_pid -eq $c241Pid -and
    [int]$final.c241.receiver_pid -eq $c241Pid -and
    $shots.immediate_c241.is_bmp -and $shots.relaunch_c241.is_bmp)
$acceptKernel = [bool]($kernelAfter.alive -and $kernelAfter.pid -eq $KernelPid -and $kernelAfter.start_time -eq $kernelBefore.start_time)

$result = @{
    model = 'Grok 4.7'
    model_id = 'xai-oauth/grok-4.7'
    at = (Now)
    kernel_url = $Base
    target = @{ name = 'iMouse2-C24C'; deviceid = $C24C }
    sibling = @{ name = 'iMouse2-C241'; deviceid = $C241 }
    aborted = [bool]$abort
    abort_reason = $abort
    kernel_before = $kernelBefore
    kernel_after = $kernelAfter
    mirror_before = $mirrorBefore
    mirror_after = $mirrorAfter
    baseline = @{
        t0 = $(if ($s0) { @{ at = $s0.at; c24c = (Slim (Pick $s0 $C24C)); c241 = (Slim (Pick $s0 $C241)) } } else { $null })
        t1 = $(if ($s1) { @{ at = $s1.at; c24c = (Slim (Pick $s1 $C24C)); c241 = (Slim (Pick $s1 $C241)) } } else { $null })
        screenshots = $baseShots
    }
    crash = @{
        at = $crashAt
        command = $(if ($c24cPid) { "Stop-Process -Id $c24cPid -Force" } else { $null })
        killed_pid = $c24cPid
        kill_returned_ms = $killReturnedMs
        process_gone = $killedGone
        verified_process = $c24cProc
        sibling_process_before = $c241Proc
    }
    immediate = $immediate
    relaunch = $relaunch
    new_process = $newProc
    screenshots = $shots
    final = $final
    sample_count = $samples.Count
    samples = $samples
    c241_frame_series = $c241Frames
    acceptance = @{
        c24c_restarted_new_pid_within_about_3s = $acceptRestart
        restart_observed_ms = $restartMs
        c24c_restarts_became_1 = $(if ($immediate) { [int]$immediate.c24c.receiver_restarts -eq 1 } else { $false })
        c24c_live_false_within_1_5s = $(if ($immediate) { [bool]$immediate.within_1_5s -and -not $immediate.c24c.live -and [bool]$immediate.down_observed } else { $false })
        c24c_zero_stale_frames_while_down = $acceptNoStale
        immediate_screenshot_code = $(if ($downJson) { $downJson.data.code } else { $null })
        immediate_screenshot_message = $(if ($downJson) { [string]$downJson.data.message } else { $null })
        relaunch_state_offline = $(if ($relaunch) { [string]$relaunch.c24c.receiver_state -eq 'offline' } else { $false })
        relaunch_restarts = $(if ($relaunch) { [int]$relaunch.c24c.receiver_restarts } else { $null })
        relaunch_screenshot_message = $(if ($upJson) { [string]$upJson.data.message } else { $null })
        relaunch_screenshot_names_c24c = $(if ($upJson) { [string]$upJson.data.message -match 'iMouse2-C24C' } else { $false })
        c241_uninterrupted_live_mirroring_0_restart_delta = $acceptSibling
        c241_restart_count = $(if ($b1) { [int]$b1.receiver_restarts } else { $null })
        c241_frames_net = $c241Net
        kernel_pid_unchanged = $acceptKernel
        mirror_stayed_off = $(if ($mirrorBefore -and $mirrorAfter) { $mirrorBefore.mirror_to_all -eq 'Off' -and $mirrorAfter.mirror_to_all -eq 'Off' } else { $false })
    }
}

$json = $result | ConvertTo-Json -Depth 12
[IO.File]::WriteAllText((Join-Path $Out 'results.json'), $json)
Write-Output $json
if ($abort) { exit 2 }
if (-not ($acceptRestart -and $acceptNoStale -and $acceptSibling -and $acceptKernel)) { exit 3 }
exit 0
