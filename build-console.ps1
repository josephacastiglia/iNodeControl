<#
.SYNOPSIS
  Builds the canonical SDK console and its apphost into the chosen output folder.
  Does not launch the console, connect to a service, or change shortcuts.
#>
param([string]$OutputDirectory = (Join-Path $PSScriptRoot 'release\iMouse2'))
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($OutputDirectory)) { throw 'OutputDirectory must name a build folder.' }
$output = [IO.Path]::GetFullPath($OutputDirectory)
$projectFile = Join-Path $PSScriptRoot 'src\iMouse.Console\iMouse.Console.csproj'
$dotnet = Get-Command dotnet -CommandType Application -ErrorAction Stop

# The SDK apphost forwards every argument unchanged. The old custom launcher dropped
# --data-dir/--print-data-path and used a separately generated XAML implementation.
# Building the authored project keeps its markup, startup behavior and tests identical.
& $dotnet.Source build $projectFile -c Release -p:UseSharedCompilation=false -o $output --nologo
if ($LASTEXITCODE -ne 0) { throw "Console build failed (exit $LASTEXITCODE). No application was started." }
if (-not (Test-Path -LiteralPath (Join-Path $output 'iMouse2.exe') -PathType Leaf)) {
    throw 'The SDK build did not produce iMouse2.exe.'
}
Write-Output "Built $output\iMouse2.exe using the project SDK apphost. Nothing was started."
