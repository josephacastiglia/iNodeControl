<#
.SYNOPSIS
  Check or prepare a recorded candidate offline; only -Launch starts the console.
  Installed files, shortcuts, kernel and receivers are never modified or started.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ConsoleExe,
    [Parameter(Mandatory)][string]$BuildManifest,
    [Parameter(Mandatory)][string]$SourceRoot,
    [Parameter(Mandatory)][Alias('DataDir')][string]$RunDir,
    [Parameter(Mandatory)][string]$Address,
    [switch]$ViaProxy, [string]$ProxyExe='', [string]$ProxyManifest='',
    [string]$ProxyListen='http://localhost:9923/',
    [switch]$CheckOnly, [switch]$PrepareOnly, [switch]$Launch
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'CandidateLaunch.ps1')
try {
    if (@($CheckOnly,$PrepareOnly,$Launch | Where-Object { $_ }).Count -gt 1) { throw 'Choose one of CheckOnly, PrepareOnly or Launch.' }
    $plan=New-CandidatePlan -ConsoleExe $ConsoleExe -BuildManifest $BuildManifest -SourceRoot $SourceRoot -RunDir $RunDir -Address $Address -ViaProxy:$ViaProxy -ProxyExe $ProxyExe -ProxyManifest $ProxyManifest -ProxyListen $ProxyListen
    if ($Launch) { Invoke-CandidateLaunch $plan }
    elseif ($PrepareOnly) { Initialize-CandidateRun $plan; $plan }
    else { $plan }
} catch { Write-Error -ErrorAction Continue $_.Exception.Message; exit 2 }
