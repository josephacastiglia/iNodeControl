# Open Marketing Farm.ps1
# Starts the iMouse 2.0 7-Layer Marketing Farm Command Center on http://localhost:9914
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python (Join-Path $scriptDir "tools\imouse_farm_server.py")
