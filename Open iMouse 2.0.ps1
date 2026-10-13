param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$consoleExe = Join-Path $projectRoot 'release\iMouse2-two-phone-candidate\iMouse2.exe'
$kernelExe = Join-Path $projectRoot 'release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe'
$configRoot = Join-Path $projectRoot 'analysis\two-phone-config'
$receiverExe = Join-Path $projectRoot 'tools\airplay\uxplay\build-imouse\uxplay.exe'
$runtimeRoot = Join-Path $projectRoot 'tools\airplay\msys64\ucrt64'
$expectedIds = '86:1D:4A:04:2F:F6,FE:A9:BC:D7:A0:44'

function Test-ReleaseKernelIdentity {
    param([string]$ExecutablePath,[string]$CommandLine,[string]$ExpectedExe,[string]$ProjectRoot,[string]$ConfigRoot,[string]$ReceiverExe,[string]$RuntimeRoot)
    if ([string]::IsNullOrWhiteSpace($ExecutablePath) -or [string]::IsNullOrWhiteSpace($CommandLine)) { return $false }
    if ([IO.Path]::GetFullPath($ExecutablePath) -ine [IO.Path]::GetFullPath($ExpectedExe)) { return $false }
    if ($CommandLine -match '(?i)--precise-movement') { return $false }
    $httpArg = [regex]::Match($CommandLine, '(?<=^|\s)(http\S+)').Groups[1].Value.Trim('"')
    if ($httpArg -cne 'http://127.0.0.1:9913/api/') { return $false }
    $inputFlags = [regex]::Matches($CommandLine, '(?i)(?:^|\s)"?--input-pid')
    if ($inputFlags.Count -ne 1) { return $false }
    $inputVal = [regex]::Match($CommandLine, '(?i)(?:^|\s)"?--input-pid"?\s+(?:"([^"]*)"|(\S+))')
    $inputPid = $(if ($inputVal.Groups[1].Value) { $inputVal.Groups[1].Value } else { $inputVal.Groups[2].Value })
    if ($inputPid -cne 'C24C,C241') { return $false }
    $resolve = {
        param($cmd,$flag)
        $m = [regex]::Match($cmd, [regex]::Escape($flag) + '\s+(?:"([^"]+)"|(\S+))')
        if (-not $m.Success) { return '' }
        $v = $(if ($m.Groups[1].Value) { $m.Groups[1].Value } else { $m.Groups[2].Value })
        if ([string]::IsNullOrWhiteSpace($v)) { return '' }
        if ([IO.Path]::IsPathRooted($v)) { return [IO.Path]::GetFullPath($v) }
        [IO.Path]::GetFullPath((Join-Path $ProjectRoot $v))
    }
    $dataDir = & $resolve $CommandLine '--data-dir'
    $receivers = & $resolve $CommandLine '--receivers'
    $receiver = & $resolve $CommandLine '--receiver'
    $runtime = & $resolve $CommandLine '--receiver-runtime'
    if (!$dataDir -or !$receivers -or !$receiver -or !$runtime) { return $false }
    if ($dataDir -ine [IO.Path]::GetFullPath($ConfigRoot)) { return $false }
    if ($receivers -ine [IO.Path]::GetFullPath((Join-Path $ConfigRoot 'receivers.json'))) { return $false }
    if ($receiver -ine [IO.Path]::GetFullPath($ReceiverExe)) { return $false }
    if ($runtime -ine [IO.Path]::GetFullPath($RuntimeRoot)) { return $false }
    $true
}
function Get-VerifiedKernelPids {
    param([string]$ExpectedExe,[string]$ProjectRoot,[string]$ConfigRoot,[string]$ReceiverExe,[string]$RuntimeRoot,[string]$ExpectedIds)
    $listeners = @(Get-NetTCPConnection -LocalPort 9913 -State Listen -ErrorAction SilentlyContinue)
    $verified = @()
    $httpSys = $false
    foreach ($owningPid in @($listeners | Where-Object { $_.OwningProcess } | ForEach-Object { [int]$_.OwningProcess } | Select-Object -Unique)) {
        if ($owningPid -eq 4) { $httpSys = $true; continue }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $owningPid"
        $exe = if ($proc) { [string]$proc.ExecutablePath } else { '' }
        $cmd = if ($proc) { [string]$proc.CommandLine } else { '' }
        if (!(Test-ReleaseKernelIdentity -ExecutablePath $exe -CommandLine $cmd -ExpectedExe $ExpectedExe -ProjectRoot $ProjectRoot -ConfigRoot $ConfigRoot -ReceiverExe $ReceiverExe -RuntimeRoot $RuntimeRoot)) {
            throw "Port 9913 is occupied by an unverified or competing process (PID $owningPid)"
        }
        $verified += $owningPid
    }
    if ($httpSys) {
        $status = $null
        try { $status = Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 2 } catch {}
        $receivers = @()
        if ($status -and $status.data -and $null -ne $status.data.receivers) { $receivers = @($status.data.receivers) }
        $ids = @($receivers | ForEach-Object { [string]$_.deviceid } | Sort-Object)
        $kernelPid = $null
        $ok = ($ids.Count -eq @($ExpectedIds -split ',').Count) -and (($ids -join ',') -ceq $ExpectedIds)
        if ($ok) {
            foreach ($recv in $receivers) {
                $rawPid = $recv.receiver_pid
                if ($null -eq $rawPid -or "$rawPid" -notmatch '^\d+$' -or [int]$rawPid -le 0) { $ok = $false; break }
                $child = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$rawPid)"
                $childOk = $false
                if ($child -and -not [string]::IsNullOrWhiteSpace([string]$child.ExecutablePath)) {
                    try { $childOk = [IO.Path]::GetFullPath([string]$child.ExecutablePath) -ieq [IO.Path]::GetFullPath($ReceiverExe) } catch {}
                }
                if (!$childOk) { $ok = $false; break }
                $rawParent = $child.ParentProcessId
                if ($null -eq $rawParent -or "$rawParent" -notmatch '^\d+$' -or [int]$rawParent -le 0) { $ok = $false; break }
                $parentPid = [int]$rawParent
                $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $parentPid"
                if (!$parent -or !(Test-ReleaseKernelIdentity -ExecutablePath ([string]$parent.ExecutablePath) -CommandLine ([string]$parent.CommandLine) -ExpectedExe $ExpectedExe -ProjectRoot $ProjectRoot -ConfigRoot $ConfigRoot -ReceiverExe $ReceiverExe -RuntimeRoot $RuntimeRoot)) { $ok = $false; break }
                if ($null -eq $kernelPid) { $kernelPid = $parentPid }
                elseif ($kernelPid -ne $parentPid) { throw 'Port 9913 is occupied by an unverified HTTP service or competing kernel build' }
            }
        }
        if ($ok -and $kernelPid -gt 0) { $verified += $kernelPid }
        else { throw 'Port 9913 is occupied by an unverified HTTP service or competing kernel build' }
    }
    @($verified | Select-Object -Unique)
}

function Start-ReleaseKernel {
    param([string]$Exe,[string[]]$Arguments,[string]$WorkingDirectory)
    # One file per attempt: never confuse an earlier refusal with this start.
    $logDir = Join-Path $WorkingDirectory 'launch-logs'
    [void][IO.Directory]::CreateDirectory($logDir)
    $errorLog = Join-Path $logDir ('kernel-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N') + '.stderr.txt')
    $process = Start-Process -FilePath $Exe -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -RedirectStandardError $errorLog -PassThru
    [pscustomobject]@{ Process=$process; ErrorLog=$errorLog }
}

function Read-ReleaseStartupError {
    param([string]$Path)
    if (!$Path) { return '' }
    $stream = $null
    try {
        $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        # Keep a large crash report out of the dialog; the full file is preserved.
        $count = [int][Math]::Min(8192, $stream.Length)
        [void]$stream.Seek(-$count, [IO.SeekOrigin]::End)
        $bytes = New-Object byte[] $count
        $read = $stream.Read($bytes, 0, $count)
        $detail = [Text.Encoding]::UTF8.GetString($bytes, 0, $read).Trim()
        if ($stream.Length -gt $count) { return "[Last 8 KiB of startup error]`r`n$detail" }
        $detail
    } catch {
        "Startup error log could not be read: $($_.Exception.Message)"
    } finally { if ($stream) { $stream.Dispose() } }
}

function Wait-ReleaseKernel {
    param($Start)
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try { return Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 2 }
        catch {
            if (!$Start) { throw 'The existing AirPlay service is not responding. No additional service was started. See OPEN-THIS-APP.md.' }
            if ($Start.Process.HasExited) {
                [void]$Start.Process.WaitForExit(1000)
                $reason = Read-ReleaseStartupError $Start.ErrorLog
                $exitDetail = if ($null -eq $Start.Process.ExitCode) { 'exit code unavailable' } else { "exit $($Start.Process.ExitCode)" }
                $message = "Our AirPlay service exited before it was ready ($exitDetail)."
                if ($reason) { $message += "`r`n`r`n$reason" }
                else { $message += "`r`nNo startup error was written. See OPEN-THIS-APP.md." }
                $message += "`r`n`r`nStartup log: $($Start.ErrorLog)"
                throw $message
            }
            if ($attempt -lt 19) { Start-Sleep -Milliseconds 300 }
        }
    }
    throw "Our AirPlay service did not finish starting. It may still be running (PID $($Start.Process.Id)); it was not stopped or restarted. See OPEN-THIS-APP.md. Startup log: $($Start.ErrorLog)"
}

try {
    foreach ($required in @($consoleExe,$kernelExe,$receiverExe,$runtimeRoot,
        (Join-Path $configRoot 'receivers.json'),(Join-Path $configRoot 'pointer-calibration.json'))) {
        if (!(Test-Path -LiteralPath $required)) { throw "Missing required file: $required" }
    }
    $settingsPath = Join-Path (Split-Path $consoleExe) 'data\settings.json'
    $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($settings.address.TrimEnd('/') -ne 'http://127.0.0.1:9913') {
        throw 'This app must use http://127.0.0.1:9913. Check its saved connection settings.'
    }
    $kernelPids = @(Get-VerifiedKernelPids -ExpectedExe $kernelExe -ProjectRoot $projectRoot -ConfigRoot $configRoot -ReceiverExe $receiverExe -RuntimeRoot $runtimeRoot -ExpectedIds $expectedIds)
    $occupied = $kernelPids.Count -gt 0
    if (!$occupied) {
        $probe = [Net.Sockets.TcpClient]::new()
        try { $tcpBusy = $probe.ConnectAsync('127.0.0.1',9913).Wait(500) -and $probe.Connected }
        catch { $tcpBusy = $false } finally { $probe.Dispose() }
        if ($tcpBusy) {
            throw 'Port 9913 is occupied by an unverified or competing process. No process was stopped.'
        }
    }
    if ($CheckOnly) {
        [pscustomobject]@{ Name='iMouse 2.0 - Independent AirPlay'; Console=$consoleExe;
            Kernel=$kernelExe; Address=$settings.address; Receivers='iMouse2-C24C / iMouse2-C241';
            Occupied=$occupied; KernelPid=($kernelPids -join ',') }
        return
    }

    if (!$occupied) {
        $kernelArgs = @('http://127.0.0.1:9913/api/','--data-dir',('"'+$configRoot+'"'),
            '--input-pid','C24C,C241','--receivers',('"'+(Join-Path $configRoot 'receivers.json')+'"'),
            '--receiver',('"'+$receiverExe+'"'),'--receiver-runtime',('"'+$runtimeRoot+'"'))
        $started = Start-ReleaseKernel -Exe $kernelExe -Arguments $kernelArgs -WorkingDirectory $projectRoot
    }
    $status = Wait-ReleaseKernel -Start $(if ($occupied) { $null } else { $started })
    $ids = @($status.data.receivers.deviceid | Sort-Object)
    if (($ids -join ',') -ne $expectedIds) {
        throw 'Port 9913 belongs to a different phone configuration. No console was opened and no process was stopped.'
    }

    # Resolve the exact executable; Windows name-based app lookup can open an old build.
    $existingConsole = Get-Process -Name iMouse2 -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $consoleExe } | Select-Object -First 1
    if (!$existingConsole) {
        Start-Process -FilePath $consoleExe -WorkingDirectory (Split-Path $consoleExe)
    }
} catch {
    if ($CheckOnly) { throw }
    $message = $_.Exception.Message
    try { [IO.File]::WriteAllText((Join-Path $projectRoot 'launch-error.txt'), $message, [Text.UTF8Encoding]::new($false)) }
    catch { $message += "`r`n`r`nThe failure report could not be saved: $($_.Exception.Message)" }
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($message, 'iMouse 2.0 - Independent AirPlay') | Out-Null
    exit 1
}
