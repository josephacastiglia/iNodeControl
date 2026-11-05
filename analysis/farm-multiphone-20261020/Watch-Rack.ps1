# Watchdog for the rack kernel, for the operator to leave running. Every -IntervalSeconds it checks the
# kernel in processes.json. If that kernel has died: it stops the receivers the dead kernel left (they
# hold its ports and are useless without it), withdraws their AirPlay names, starts the kernel again
# (Start-Multiphone.ps1, detached) and runs Bringup-Rack (unless -NoBringup). It never touches a
# kernel that is running, even one whose API is silent (it reports that), and never restarts a kernel
# stopped on purpose (Stop-Multiphone.ps1 renames its record). At most -MaxRestarts per hour, then it
# stops and says so. Pause it without stopping it: create watchdog-pause beside the preparation.
# Log: watchdog.jsonl beside the preparation.
#   .\Watch-Rack.ps1 [-Stage slots | -Rack A|B] [-IntervalSeconds 30] [-NoBringup] [-Once] [-MaxRestarts 3]
param([ValidateSet('','held','slots')][string]$Stage='',[ValidateSet('','A','B')][string]$Rack='',[int]$IntervalSeconds=30,
    [switch]$NoBringup,[switch]$Once,[int]$MaxRestarts=3)
$ErrorActionPreference='Stop'
if($Stage -and $Rack){throw 'Choose -Stage or -Rack, not both.'}
$taskPy=if($env:IMOUSE_FARM_PYTHON){$env:IMOUSE_FARM_PYTHON}else{'python'}
$taskArgs=@('watch','--interval',$IntervalSeconds,'--max-restarts',$MaxRestarts)+$(if($Rack){@('--rack',$Rack)}else{@('--stage',$(if($Stage){$Stage}else{'slots'}))})
if($NoBringup){$taskArgs+='--no-bringup'}
if($Once){$taskArgs+='--once'}
& $taskPy (Join-Path $PSScriptRoot 'rack_recovery.py') @taskArgs
exit $LASTEXITCODE
