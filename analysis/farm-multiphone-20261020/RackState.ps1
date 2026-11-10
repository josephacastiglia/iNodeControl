# Where the rack keeps its state, for every rack script (dot-source this file):
#   Get-RackState                    the state root: beside these scripts in a checkout; installed, Farm.ps1
#                                    sets IMOUSE_FARM_DATA and it is <data>\analysis\farm-multiphone-20261020
#   Get-RackState 'slots'            the kernel's one folder: preparation, process record, logs, ledgers
#   Get-RackState 'windows\<name>'   one window's folder
# Python reads the same places through tools/farm_paths.py (rack_state) and rack_kernels.py (kernel_folder).
function Get-RackState([string]$Child='') {
    $rackRoot=if($env:IMOUSE_FARM_DATA){Join-Path $env:IMOUSE_FARM_DATA 'analysis\farm-multiphone-20261020'}else{$PSScriptRoot}
    if($Child){Join-Path $rackRoot $Child}else{$rackRoot}
}
# The Python that runs the rack's helpers: IMOUSE_FARM_PYTHON when installed, else python on PATH.
function Get-RackPython { if($env:IMOUSE_FARM_PYTHON){$env:IMOUSE_FARM_PYTHON}else{'python'} }
