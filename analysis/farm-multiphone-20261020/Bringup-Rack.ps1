# Reconnects the rack's phones in the order that works (bringup-plan.json; see rack_recovery.py): rack B
# from B20, rack A's small phones, then A20 and the XRs. Wakes Home-button phones, retries once, resumes
# input only on boards our own stop or bring-up left stopped (input-stops.jsonl), never an operator's
# stop. Writes bringup-<time>\report.json beside the preparation. Drives phones (taps, Home): run it
# only when no lane is on a phone.
#   .\Bringup-Rack.ps1 [-Stage slots | -Rack A|B] [-PlanOnly] [-Plan <file>]
param([ValidateSet('','held','slots')][string]$Stage='',[ValidateSet('','A','B')][string]$Rack='',[switch]$PlanOnly,[string]$Plan='')
$ErrorActionPreference='Stop'
if($Stage -and $Rack){throw 'Choose -Stage or -Rack, not both.'}
$taskPy=if($env:IMOUSE_FARM_PYTHON){$env:IMOUSE_FARM_PYTHON}else{'python'}
$taskArgs=@('bringup')+$(if($Rack){@('--rack',$Rack)}else{@('--stage',$(if($Stage){$Stage}else{'slots'}))})
if($Plan){$taskArgs+=@('--plan',$Plan)}
if($PlanOnly){$taskArgs+='--plan-only'}
& $taskPy (Join-Path $PSScriptRoot 'rack_recovery.py') @taskArgs
if($LASTEXITCODE){throw "Bring-up failed (exit $LASTEXITCODE)."}
