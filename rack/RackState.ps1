# Where the rack keeps its state, for every rack script (dot-source this file):
#   Get-RackState                    the state root: beside these scripts in a checkout; installed, Farm.ps1
#                                    sets IMOUSE_FARM_DATA and it is <data>\rack
#   Get-RackKernelFolder             the kernel's one folder: preparation, process record, logs, ledgers
#   Get-RackState 'windows\<name>'   one window's folder
# Python reads the same places through tools/farm_paths.py (rack_state) and rack_kernels.py (kernel_folder).
function Get-RackState([string]$Child='') {
    $rackRoot=if($env:IMOUSE_FARM_DATA){Join-Path $env:IMOUSE_FARM_DATA 'rack'}else{$PSScriptRoot}
    if($Child){Join-Path $rackRoot $Child}else{$rackRoot}
}
# The folder keeps the name of the stage it once was ('slots'): live state on the rack PC sits there.
function Get-RackKernelFolder { Get-RackState 'slots' }
# Why a kernel that was just launched does not count as started yet, or '' when it does: it must be the
# prepared build with the prepared allow-list, hold exactly the receivers the preparation holds, and run
# every other one. $Status is its /kernel/status data ($null while the API does not answer).
function Get-RackStartProblem($Status,$Prep,[bool]$Exited) {
    if($Exited){return 'The kernel exited during startup.'}
    if(!$Status){return 'The kernel API did not answer.'}
    if($Status.build_identity.sha256 -cne $Prep.kernelSha256 -or @($Status.allowed).Count -ne @($Prep.inputEnabled).Count){return 'Kernel identity or allow-list differs from the preparation.'}
    $rackHeld=@($Prep.held | Where-Object {$_}).Count
    $rackNowHeld=@($Status.receivers | Where-Object {$_.receiver_state -eq 'held'}).Count
    if($rackNowHeld -ne $rackHeld){return "Held receivers differ from the preparation ($rackNowHeld held, $rackHeld prepared)."}
    $rackExpected=@($Prep.receivers).Count-$rackHeld
    $rackRunning=@($Status.receivers | Where-Object {$_.receiver_pid -gt 0}).Count
    if($rackRunning -ne $rackExpected){return "$rackRunning of $rackExpected receivers that should run have started."}
    return ''
}
# The Python that runs the rack's helpers: IMOUSE_FARM_PYTHON when installed, else python on PATH.
function Get-RackPython { if($env:IMOUSE_FARM_PYTHON){$env:IMOUSE_FARM_PYTHON}else{'python'} }
