$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $root 'Open iMouse 2.0.ps1'
$consoleExe = Join-Path $root 'release\iMouse2-two-phone-candidate\iMouse2.exe'
$kernelExe = Join-Path $root 'release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe'
$configRoot = Join-Path $root 'analysis\two-phone-config'
$receiverExe = Join-Path $root 'tools\airplay\uxplay\build-imouse\uxplay.exe'
$runtimeRoot = Join-Path $root 'tools\airplay\msys64\ucrt64'
$settingsPath = Join-Path (Split-Path $consoleExe) 'data\settings.json'
$failed = [System.Collections.Generic.List[string]]::new()
function Expect($ok, $msg) { if (!$ok) { $script:failed.Add($msg) } }
$identityArgs = @{ ExpectedExe = $kernelExe; ProjectRoot = $root; ConfigRoot = $configRoot; ReceiverExe = $receiverExe; RuntimeRoot = $runtimeRoot }
$expectedIds = '86:1D:4A:04:2F:F6,FE:A9:BC:D7:A0:44'

foreach ($path in @($launcher,$consoleExe,$kernelExe,$receiverExe,$runtimeRoot,
    (Join-Path $configRoot 'receivers.json'),(Join-Path $configRoot 'pointer-calibration.json'),$settingsPath)) {
    Expect (Test-Path -LiteralPath $path) "Missing $path"
}
$settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
Expect ($settings.address.TrimEnd('/') -eq 'http://127.0.0.1:9913') "settings.json address is $($settings.address)"

$tokens = $null; $parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$tokens, [ref]$parseErrors)
Expect ($parseErrors.Count -eq 0) "Launcher parse errors: $parseErrors"
$fns = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] }, $true))
$identityAst = $fns | Where-Object Name -eq 'Test-ReleaseKernelIdentity' | Select-Object -First 1
$verifyAst = $fns | Where-Object Name -eq 'Get-VerifiedKernelPids' | Select-Object -First 1
Expect ($null -ne $identityAst) 'Launcher is missing Test-ReleaseKernelIdentity'
Expect ($null -ne $verifyAst) 'Launcher is missing Get-VerifiedKernelPids'
if ($identityAst) { . ([scriptblock]::Create($identityAst.Extent.Text)) }

$goodCmd = "`"$kernelExe`" http://127.0.0.1:9913/api/ --data-dir `"$configRoot`" --input-pid C24C,C241 --receivers `"$(Join-Path $configRoot 'receivers.json')`" --receiver `"$receiverExe`" --receiver-runtime `"$runtimeRoot`""
$relativeCmd = "`"$kernelExe`" http://127.0.0.1:9913/api/ --data-dir analysis\two-phone-config --input-pid C24C,C241 --receivers analysis\two-phone-config\receivers.json --receiver tools\airplay\uxplay\build-imouse\uxplay.exe --receiver-runtime tools\airplay\msys64\ucrt64"
Expect (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine $goodCmd @identityArgs) 'accepted the expected kernel command line'
Expect (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine $relativeCmd @identityArgs) 'accepted relative two-phone-config paths'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine "$goodCmd --precise-movement" @identityArgs)) 'rejected --precise-movement'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine "$goodCmd `"--precise-movement`"" @identityArgs)) 'rejected quoted --precise-movement'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath 'C:\Windows\System32\notepad.exe' -CommandLine $goodCmd @identityArgs)) 'rejected a competing executable'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine '--data-dir x --input-pid C24C,C241' @identityArgs)) 'rejected a command line without 127.0.0.1:9913'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine ($goodCmd -replace [regex]::Escape($configRoot),'analysis\single-phone-config') @identityArgs)) 'rejected a wrong --data-dir'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine "`"$kernelExe`" http://127.0.0.1:9913/api/ --data-dir `"$configRoot`" --input-pid C24C,C241 --receiver `"$receiverExe`" --receiver-runtime `"$runtimeRoot`"" @identityArgs)) 'rejected a command line without --receivers'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine "`"$kernelExe`" http://127.0.0.1:9913/api/ --data-dir `"$configRoot`" --input-pid C24C,C241 --receivers `"$(Join-Path $configRoot 'receivers.json')`" --receiver-runtime `"$runtimeRoot`"" @identityArgs)) 'rejected a command line without --receiver'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine "`"$kernelExe`" http://127.0.0.1:9913/api/ --data-dir `"$configRoot`" --input-pid C24C,C241 --receivers `"$(Join-Path $configRoot 'receivers.json')`" --receiver `"$receiverExe`"" @identityArgs)) 'rejected a command line without --receiver-runtime'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine ($goodCmd -replace '--input-pid C24C,C241','--input-pid C24C') @identityArgs)) 'rejected a command line missing C241'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine "$goodCmd --input-pid C24C,C241" @identityArgs)) 'rejected duplicate --input-pid'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine ($goodCmd -replace '--input-pid C24C,C241','--input-pid C24C,C241 --input-pid C24C') @identityArgs)) 'rejected conflicting --input-pid'
Expect (-not (Test-ReleaseKernelIdentity -ExecutablePath $kernelExe -CommandLine ($goodCmd -replace 'http://127.0.0.1:9913/api/','http://127.0.0.1:80/ http://127.0.0.1:9913/api/') @identityArgs)) 'rejected a wrong first HTTP prefix'

$verify = & {
    . ([scriptblock]::Create($identityAst.Extent.Text))
    . ([scriptblock]::Create($verifyAst.Extent.Text))
    $script:mockPid = 4242
    $script:procs = @{ 4242 = [pscustomobject]@{ ExecutablePath = $kernelExe; CommandLine = $goodCmd; ProcessId = 4242; ParentProcessId = 1 } }
    $script:status = $null
    function Get-NetTCPConnection { param($LocalPort,$State,$ErrorAction) if ($null -ne $script:mockPid) { [pscustomobject]@{ OwningProcess = $script:mockPid } } }
    function Get-CimInstance { param($ClassName,$Filter,$ErrorAction) if ($Filter -match 'ProcessId\s*=\s*(\d+)') { $script:procs[[int]$Matches[1]] } }
    function Invoke-RestMethod { param($Uri,$TimeoutSec) $script:status }
    $accepted = @(Get-VerifiedKernelPids @identityArgs -ExpectedIds $expectedIds)
    $script:procs[4242] = [pscustomobject]@{ ExecutablePath = $kernelExe; CommandLine = "$goodCmd --precise-movement"; ProcessId = 4242; ParentProcessId = 1 }
    $precise = $false
    try { [void](Get-VerifiedKernelPids @identityArgs -ExpectedIds $expectedIds) } catch { $precise = $_.Exception.Message -match 'unverified or competing process \(PID 4242\)' }
    $script:procs[4242] = [pscustomobject]@{ ExecutablePath = 'C:\Windows\System32\notepad.exe'; CommandLine = $goodCmd; ProcessId = 4242; ParentProcessId = 1 }
    $wrongExe = $false
    try { [void](Get-VerifiedKernelPids @identityArgs -ExpectedIds $expectedIds) } catch { $wrongExe = $_.Exception.Message -match 'unverified or competing process \(PID 4242\)' }
    $script:mockPid = 4
    $script:procs = @{
        5001 = [pscustomobject]@{ ProcessId = 5001; ParentProcessId = 7777; ExecutablePath = $receiverExe; CommandLine = 'uxplay' }
        5002 = [pscustomobject]@{ ProcessId = 5002; ParentProcessId = 7777; ExecutablePath = $receiverExe; CommandLine = 'uxplay' }
        7777 = [pscustomobject]@{ ProcessId = 7777; ParentProcessId = 1; ExecutablePath = $kernelExe; CommandLine = $goodCmd }
    }
    $script:status = [pscustomobject]@{ data = [pscustomobject]@{ receivers = @(
        [pscustomobject]@{ deviceid = '86:1D:4A:04:2F:F6'; receiver_pid = 5001 }
        [pscustomobject]@{ deviceid = 'FE:A9:BC:D7:A0:44'; receiver_pid = 5002 }
    ) } }
    $httpAccepted = @(Get-VerifiedKernelPids @identityArgs -ExpectedIds $expectedIds)
    $script:procs[7777] = [pscustomobject]@{ ProcessId = 7777; ParentProcessId = 1; ExecutablePath = $kernelExe; CommandLine = "$goodCmd --precise-movement" }
    $httpPrecise = $false
    try { [void](Get-VerifiedKernelPids @identityArgs -ExpectedIds $expectedIds) } catch { $httpPrecise = $_.Exception.Message -match 'unverified HTTP service or competing kernel build' }
    $script:procs[7777] = [pscustomobject]@{ ProcessId = 7777; ParentProcessId = 1; ExecutablePath = 'C:\Windows\System32\notepad.exe'; CommandLine = $goodCmd }
    $httpWrong = $false
    try { [void](Get-VerifiedKernelPids @identityArgs -ExpectedIds $expectedIds) } catch { $httpWrong = $_.Exception.Message -match 'unverified HTTP service or competing kernel build' }
$httpPair = {
    [pscustomobject]@{ data = [pscustomobject]@{ receivers = @(
        [pscustomobject]@{ deviceid = '86:1D:4A:04:2F:F6'; receiver_pid = 5001 }
        [pscustomobject]@{ deviceid = 'FE:A9:BC:D7:A0:44'; receiver_pid = 5002 }
    ) } }
}
$rejected = {
    $hit = $false
    try { [void](Get-VerifiedKernelPids @identityArgs -ExpectedIds $expectedIds) } catch { $hit = $_.Exception.Message -match 'unverified HTTP service or competing kernel build' }
    $hit
}
$script:procs = @{
    5001 = [pscustomobject]@{ ProcessId = 5001; ParentProcessId = 7777; ExecutablePath = $receiverExe; CommandLine = 'uxplay' }
    5002 = [pscustomobject]@{ ProcessId = 5002; ParentProcessId = 7777; ExecutablePath = $receiverExe; CommandLine = 'uxplay' }
    7777 = [pscustomobject]@{ ProcessId = 7777; ParentProcessId = 1; ExecutablePath = $kernelExe; CommandLine = $goodCmd }
}
$script:status = & $httpPair
$script:status.data.receivers[1].receiver_pid = 0
$zeroPid = & $rejected
$script:status = & $httpPair
$script:status.data.receivers[1] = [pscustomobject]@{ deviceid = 'FE:A9:BC:D7:A0:44' }
$missingPid = & $rejected
$script:status = & $httpPair
$script:procs.Remove(5002)
$missingChild = & $rejected
$script:procs[5002] = [pscustomobject]@{ ProcessId = 5002; ParentProcessId = 7777; ExecutablePath = 'C:\Windows\System32\notepad.exe'; CommandLine = 'uxplay' }
$wrongChild = & $rejected
$script:procs[5002] = [pscustomobject]@{ ProcessId = 5002; ParentProcessId = 8888; ExecutablePath = $receiverExe; CommandLine = 'uxplay' }
$script:procs[8888] = [pscustomobject]@{ ProcessId = 8888; ParentProcessId = 1; ExecutablePath = $kernelExe; CommandLine = "$goodCmd --precise-movement" }
$secondParent = & $rejected
$script:procs[8888] = [pscustomobject]@{ ProcessId = 8888; ParentProcessId = 1; ExecutablePath = $kernelExe; CommandLine = $goodCmd }
$divergent = & $rejected
$script:procs[5002] = [pscustomobject]@{ ProcessId = 5002; ParentProcessId = 7777; ExecutablePath = $receiverExe; CommandLine = 'uxplay' }
$script:procs.Remove(8888)
$script:procs[7777] = [pscustomobject]@{ ProcessId = 7777; ParentProcessId = 1; ExecutablePath = $kernelExe; CommandLine = "$goodCmd `"--precise-movement`"" }
$quotedParent = & $rejected
$script:procs[7777] = [pscustomobject]@{ ProcessId = 7777; ParentProcessId = 1; ExecutablePath = $kernelExe; CommandLine = "$goodCmd --input-pid C24C" }
$dupInput = & $rejected
    $script:mockPid = $null
    $empty = @(Get-VerifiedKernelPids @identityArgs -ExpectedIds $expectedIds)
[pscustomobject]@{ Accepted = $accepted; Precise = $precise; WrongExe = $wrongExe; HttpAccepted = $httpAccepted; HttpPrecise = $httpPrecise; HttpWrong = $httpWrong; ZeroPid = $zeroPid; MissingPid = $missingPid; MissingChild = $missingChild; WrongChild = $wrongChild; SecondParent = $secondParent; Divergent = $divergent; QuotedParent = $quotedParent; DupInput = $dupInput; Empty = $empty }
}
Expect ($verify.Accepted.Count -eq 1 -and $verify.Accepted[0] -eq 4242) "accepted mock listener $($verify.Accepted)"
Expect $verify.Precise 'rejected mock --precise-movement occupant'
Expect $verify.WrongExe 'rejected mock competing executable occupant'
Expect ($verify.HttpAccepted.Count -eq 1 -and $verify.HttpAccepted[0] -eq 7777) "accepted HTTP.sys correlated parent $($verify.HttpAccepted)"
Expect $verify.HttpPrecise 'rejected HTTP.sys --precise-movement parent'
Expect $verify.HttpWrong 'rejected HTTP.sys wrong parent'
Expect $verify.ZeroPid 'rejected HTTP.sys receiver_pid 0'
Expect $verify.MissingPid 'rejected HTTP.sys missing receiver_pid'
Expect $verify.MissingChild 'rejected HTTP.sys child missing from CIM'
Expect $verify.WrongChild 'rejected HTTP.sys wrong child executable'
Expect $verify.SecondParent 'rejected HTTP.sys unverified second parent'
Expect $verify.Divergent 'rejected HTTP.sys divergent parents'
Expect $verify.QuotedParent 'rejected HTTP.sys quoted --precise-movement parent'
Expect $verify.DupInput 'rejected HTTP.sys duplicate --input-pid'
Expect ($verify.Empty.Count -eq 0) 'empty listen list is not occupied'

$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$checkFile = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher -CheckOnly 2>&1 | Out-String
$fileCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
$check = $null
$checkError = $null
try { $check = & $launcher -CheckOnly } catch { $checkError = $_.Exception.Message }
$listeners = @(Get-NetTCPConnection -LocalPort 9913 -State Listen -ErrorAction SilentlyContinue)
$pids = @($listeners | Where-Object { $_.OwningProcess } | ForEach-Object { [int]$_.OwningProcess } | Select-Object -Unique)
$userPids = @($pids | Where-Object { $_ -gt 4 })
if ($userPids.Count -gt 0) {
    Expect ($fileCode -eq 0) "CheckOnly -File failed: $checkFile"
    Expect ([string]::IsNullOrWhiteSpace($checkError)) "CheckOnly failed: $checkError"
    if ($check) {
        Expect ($check.Console -eq $consoleExe) "CheckOnly Console $($check.Console)"
        Expect ($check.Kernel -eq $kernelExe) "CheckOnly Kernel $($check.Kernel)"
        Expect ($check.Address.TrimEnd('/') -eq 'http://127.0.0.1:9913') "CheckOnly Address $($check.Address)"
        Expect ([bool]$check.Occupied) 'CheckOnly Occupied should be true when 9913 has a user-mode listener'
    }
    foreach ($owningPid in $userPids) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $owningPid"
        $ok = $proc -and (Test-ReleaseKernelIdentity -ExecutablePath $proc.ExecutablePath -CommandLine $proc.CommandLine @identityArgs)
        Expect $ok "listening PID $owningPid is not the expected kernel"
        if ($check -and $check.KernelPid) {
            Expect ($check.KernelPid -match [string]$owningPid) "CheckOnly KernelPid $($check.KernelPid) missed $owningPid"
        }
    }
} elseif ($pids -contains 4) {
    Expect ($fileCode -eq 0) "CheckOnly -File failed: $checkFile"
    Expect ([string]::IsNullOrWhiteSpace($checkError)) "CheckOnly failed: $checkError"
    $liveStatus = $null
    $liveParents = [System.Collections.Generic.List[int]]::new()
    $liveOk = $true
    try {
        $liveStatus = Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 2
        $liveReceivers = @($liveStatus.data.receivers)
        $liveIds = @($liveReceivers | ForEach-Object { [string]$_.deviceid } | Sort-Object)
        if ($liveReceivers.Count -lt 1 -or ($liveIds -join ',') -cne $expectedIds) { $liveOk = $false }
        foreach ($recv in $liveReceivers) {
            $rawPid = $recv.receiver_pid
            if ($null -eq $rawPid -or "$rawPid" -notmatch '^\d+$' -or [int]$rawPid -le 0) { $liveOk = $false; break }
            $child = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$rawPid)"
            $childOk = $false
            if ($child -and -not [string]::IsNullOrWhiteSpace([string]$child.ExecutablePath)) {
                try { $childOk = [IO.Path]::GetFullPath([string]$child.ExecutablePath) -ieq [IO.Path]::GetFullPath($receiverExe) } catch {}
            }
            if (!$childOk) { $liveOk = $false; break }
            $rawParent = $child.ParentProcessId
            if ($null -eq $rawParent -or "$rawParent" -notmatch '^\d+$' -or [int]$rawParent -le 0) { $liveOk = $false; break }
            $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$rawParent)"
            if (!$parent -or !(Test-ReleaseKernelIdentity -ExecutablePath $parent.ExecutablePath -CommandLine $parent.CommandLine @identityArgs)) { $liveOk = $false; break }
            $liveParents.Add([int]$rawParent)
        }
    } catch { $liveOk = $false }
    $uniqueParents = @($liveParents | Select-Object -Unique)
    $receiverCount = 0
    if ($liveStatus -and $liveStatus.data) { $receiverCount = @($liveStatus.data.receivers).Count }
    Expect ($liveOk -and $uniqueParents.Count -eq 1 -and $liveParents.Count -eq $receiverCount) 'live HTTP.sys receivers did not converge on one verified parent kernel'
    if ($check -and $uniqueParents.Count -eq 1) {
        $liveParent = [int]$uniqueParents[0]
        Expect ($check.Console -eq $consoleExe) "CheckOnly Console $($check.Console)"
        Expect ($check.Kernel -eq $kernelExe) "CheckOnly Kernel $($check.Kernel)"
        Expect ($check.Address.TrimEnd('/') -eq 'http://127.0.0.1:9913') "CheckOnly Address $($check.Address)"
        Expect ([bool]$check.Occupied) 'CheckOnly Occupied should be true for the HTTP.sys kernel'
        $reportedExact = $false
        try { $reportedExact = [int]$check.KernelPid -eq $liveParent } catch {}
        Expect (($check.KernelPid -contains $liveParent) -or $reportedExact) "CheckOnly KernelPid $($check.KernelPid) should be $liveParent"
    }
} else {
    Expect ($fileCode -eq 0) "CheckOnly -File failed: $checkFile"
    Expect ([string]::IsNullOrWhiteSpace($checkError)) "CheckOnly failed: $checkError"
    if ($check) {
        Expect ($check.Console -eq $consoleExe) "CheckOnly Console $($check.Console)"
        Expect ($check.Kernel -eq $kernelExe) "CheckOnly Kernel $($check.Kernel)"
        Expect ($check.Address.TrimEnd('/') -eq 'http://127.0.0.1:9913') "CheckOnly Address $($check.Address)"
        Expect (-not [bool]$check.Occupied) 'CheckOnly Occupied should be false when 9913 is not listening'
    }
}

if ($failed.Count) {
    $failed | ForEach-Object { Write-Error $_ }
    exit 1
}
[pscustomobject]@{
    Result='pass'
    Console=$consoleExe
    Kernel=$kernelExe
    Occupied=[bool]$check.Occupied
    KernelPid=$check.KernelPid
}
