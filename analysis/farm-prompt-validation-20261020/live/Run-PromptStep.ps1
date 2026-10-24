# One prompt-validation step through tools/farm_prompt_validation.py with the prepared Python.
# Part A runs observe and trials; part B runs the probe; confirm and promote need no kernel.
# A label is used once: a step is never replayed. See ../README.md for the window order.
param(
    [Parameter(Mandatory)][ValidateSet('observe','trial','probe','confirm','promote')][string]$Step,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9][a-z0-9-]{1,47}$')][string]$Label,
    [ValidateSet('A','B')][string]$Part,
    [ValidateSet('pointer_tap','keyboard_escape','long_press','keyboard_focus')][string]$Method,
    [switch]$NoActivate,
    [ValidateSet('safe','other','unclear')][string]$Answer,
    [string]$Observed
)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$taskPrep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw | ConvertFrom-Json
$taskArgs=@((Join-Path $taskRoot 'tools/farm_prompt_validation.py'),$Step,'--preparation',(Join-Path $PSScriptRoot 'preparation.json'),'--label',$Label)
if($Step -in @('observe','trial','probe')){
    if(!$Part){throw '-Part is required for this step.'}
    if(($Step -eq 'probe') -ne ($Part -eq 'B')){throw 'The probe runs on part B; observe and trials run on part A.'}
    if(Test-Path -LiteralPath (Join-Path $PSScriptRoot ('restoration-'+$Part+'.json'))){throw ('Part '+$Part+' has been stopped.')}
    $taskProcesses=Get-Content -LiteralPath (Join-Path $PSScriptRoot ('processes-'+$Part+'.json')) -Raw | ConvertFrom-Json
    $taskActual=Get-CimInstance Win32_Process -Filter ('ProcessId='+$taskProcesses.kernel.pid)
    if(!$taskActual -or $taskActual.ExecutablePath -cne $taskPrep.kernel){throw 'The private kernel process changed. Nothing was sent.'}
    $taskArgs+=@('--part',$Part)
}
if($Step -eq 'trial'){
    if(!$Method){throw '-Method is required for a trial.'}
    $taskArgs+=@('--method',$Method)
    if($NoActivate){$taskArgs+='--no-activate'}
}
if($Step -eq 'confirm'){
    if(!$Answer -or !$Observed){throw '-Answer and -Observed are required to confirm.'}
    if($Observed.Contains('"')){throw 'Use no double quotes inside -Observed.'}
    $taskArgs+=@(('--'+$Answer),'--observed',$Observed)
}
& $taskPrep.python @taskArgs
exit $LASTEXITCODE
