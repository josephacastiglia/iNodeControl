<#
.SYNOPSIS
  Starts a candidate iMouse 2.0 console on its own settings folder, pointed at an explicitly
  chosen and verified service, optionally through the input fault proxy. Test tooling only:
  it does not touch "Open iMouse 2.0.ps1", the installed shortcuts, release\ or %APPDATA%\iMouse2.

.EXAMPLE
  .\Start-iMouse2Candidate.ps1 -ConsoleExe "C:\...\imouse-candidate-integrated-2\iMouse2.exe" -DataDir "C:\...\candidate data" -ViaProxy -ProxyExe "C:\...\proxy\InputFaultProxy.exe"
#>
param(
    [Parameter(Mandatory)][string]$ConsoleExe,
    [Parameter(Mandatory)][string]$DataDir,
    [string]$Address = 'http://127.0.0.1:9913',
    [switch]$ViaProxy,
    [string]$ProxyExe = '',
    [string]$ProxyListen = 'http://localhost:9923/',
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
function Test-FullPath([string]$path) { $path -match '^[A-Za-z]:\\' -or $path -match '^\\\\[^\\]+\\' }

function Fail([string]$message) { Write-Error $message; exit 2 }

# The console and its folder.
if (-not (Test-FullPath $ConsoleExe) -or -not (Test-Path -LiteralPath $ConsoleExe -PathType Leaf)) { Fail "ConsoleExe must be the full path of an existing iMouse2.exe: $ConsoleExe" }
$ConsoleExe = [IO.Path]::GetFullPath($ConsoleExe)
$consoleDir = Split-Path -LiteralPath $ConsoleExe

# The isolated settings folder: absolute, not the shared operator folder, not inside release\.
if (-not (Test-FullPath $DataDir)) { Fail "DataDir must be a full path: $DataDir" }
$DataDir = [IO.Path]::GetFullPath($DataDir).TrimEnd('\')
$shared = [IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'iMouse2')).TrimEnd('\')
if ($DataDir -ieq $shared) { Fail "DataDir is the shared operator folder $shared. Choose a folder of the candidate's own." }
if ($DataDir -match '(?i)\\release(\\|$)') { Fail "DataDir must not be inside a release folder: $DataDir" }

# Operator settings: record metadata only, never contents, so a later check can show they did not change.
$operatorSettings = Join-Path $shared 'settings.json'
function OperatorStamp {
    if (-not (Test-Path -LiteralPath $operatorSettings)) { return 'absent' }
    $f = Get-Item -LiteralPath $operatorSettings
    '{0:o} {1} bytes sha256 {2}' -f $f.LastWriteTimeUtc, $f.Length, (Get-FileHash -LiteralPath $operatorSettings).Hash
}

# The service: it must answer as the ownership kernel before the console may connect.
$Address = $Address.TrimEnd('/')
function Assert-Kernel([string]$base, [string]$label) {
    try { $status = Invoke-RestMethod -Uri ($base + '/api/kernel/status') -TimeoutSec 5 }
    catch { Fail "$label $base did not answer /api/kernel/status: $($_.Exception.Message)" }
    if ($status.data.input_protocol -ne 1 -or $status.data.input_leases_required -ne $true) { Fail "$label $base is not the ownership-enabled kernel (input_protocol=$($status.data.input_protocol))." }
}
Assert-Kernel $Address 'Service'

$effective = $Address
$proxy = $null
if ($ViaProxy) {
    if (-not $ProxyExe -or -not (Test-Path -LiteralPath $ProxyExe -PathType Leaf)) { Fail "-ViaProxy needs -ProxyExe, the full path of InputFaultProxy.exe." }
    $effective = $ProxyListen.TrimEnd('/')
    if (-not $CheckOnly) {
        New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
        $proxy = Start-Process -FilePath $ProxyExe -ArgumentList @('--listen', $ProxyListen, '--upstream', $Address, '--log', "`"$(Join-Path $DataDir 'proxy-log.jsonl')`"") -WindowStyle Hidden -PassThru
        Start-Sleep -Milliseconds 800
        if ($proxy.HasExited) { Fail "The fault proxy exited at once (exit code $($proxy.ExitCode))." }
        Assert-Kernel $effective 'Proxy'
    }
}

# The console reports which folder it will use, without connecting.
$probe = Join-Path $consoleDir 'data-path.txt'
Remove-Item -LiteralPath $probe -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $ConsoleExe -ArgumentList @('--print-data-path', "--data-dir=`"$DataDir`"") -WorkingDirectory $consoleDir -PassThru -Wait
if ($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $probe)) { Fail "The console did not accept --data-dir (exit $($p.ExitCode)); see data-path-failure.txt beside it." }
$reported = (Get-Content -LiteralPath $probe -Raw).Trim()
if ($reported -ine $DataDir) { Fail "The console would use '$reported', not '$DataDir'." }

[pscustomobject]@{
    Console = $ConsoleExe
    DataDir = $DataDir
    Service = $Address
    ConsoleAddress = $effective
    ProxyPid = if ($proxy) { $proxy.Id } else { $null }
    OperatorSettings = OperatorStamp
} | Format-List | Out-String | Write-Host
if ($CheckOnly) { exit 0 }

# The address is passed explicitly; the console does not fall back to a saved or built-in one.
$console = Start-Process -FilePath $ConsoleExe -ArgumentList @("--data-dir=`"$DataDir`"", "--address=$effective") -WorkingDirectory $consoleDir -PassThru
Write-Host "Candidate console PID $($console.Id) on $effective with data in $DataDir"
