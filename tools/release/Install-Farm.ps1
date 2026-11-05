# Install or update the Marketing Farm from this package folder.
# 1. Runs the read-only preflight and stops if a check fails (it prints the operator steps).
# 2. Verifies every file against release.json, copies the package to <root>\versions\<version>,
#    and switches current.json in one step. The previous version stays for Rollback.
# Needs no administrator and changes nothing outside the install root and the data folder.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File Install-Farm.ps1 [-InstallRoot DIR] [-DataRoot DIR] [-Python EXE]
#   ... -Update            update an existing install to this package
#   ... -Rollback          switch back to the previous version (no package needed)
#   ... -PreflightOnly     only report
#   ... -IgnorePreflight   install although the preflight failed (the farm will not run until it passes)
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\iMouseFarm'),
    [string]$DataRoot = (Join-Path $env:LOCALAPPDATA 'iMouseFarm'),
    [string]$Python = '',
    [switch]$Update, [switch]$Rollback, [switch]$PreflightOnly, [switch]$IgnorePreflight
)
$ErrorActionPreference = 'Stop'
$package = $PSScriptRoot
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'install\Preflight-Farm.ps1') -InstallRoot $InstallRoot -DataRoot $DataRoot -Python $Python -Package $package
$preflight = $LASTEXITCODE
if ($PreflightOnly) { exit $preflight }
if ($preflight -ne 0 -and !$IgnorePreflight) { Write-Host 'Preflight failed: nothing was installed. Do the operator steps above, then run this again.'; exit 1 }
if (!$Python) {
    $launcher = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    $Python = if ($launcher) { (& $launcher -3.11 -c "import sys; print(sys.executable)" 2>$null) } else { (Get-Command python.exe -ErrorAction SilentlyContinue).Source }
}
if (!$Python -or $Python -like '*\WindowsApps\*') { throw 'Python 3.11 was not found; pass -Python <path to python.exe>.' }
$tool = Join-Path $package 'install\farm_install.py'
if ($Rollback) { & $Python -E $tool rollback --root $InstallRoot }
elseif ($Update) { & $Python -E $tool update --package $package --root $InstallRoot }
else { & $Python -E $tool install --package $package --root $InstallRoot --data $DataRoot --python $Python }
exit $LASTEXITCODE
