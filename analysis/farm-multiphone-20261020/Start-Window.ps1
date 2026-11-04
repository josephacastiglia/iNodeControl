# Starts one window's backend against the running multi-phone kernel. Never starts or stops the
# kernel or a receiver, and sends no phone input. Refuses if the kernel is not the prepared one,
# if this window already runs, or if its own ports are taken.
param([Parameter(Mandatory)][ValidatePattern('^[a-z]+(-[a-z]+)?-slot\d+$')][string]$Window)
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$taskPython='C:\Users\joey_\AppData\Local\Programs\Python\Python311\python.exe'
$taskDir=Join-Path $PSScriptRoot "windows\$Window"
$taskProcessFile=Join-Path $taskDir 'processes.json'
if(Test-Path -LiteralPath $taskProcessFile){throw 'This window already has a process record. Do not start duplicates.'}
$taskPrep=Get-Content -LiteralPath (Join-Path $taskDir 'preparation.json') -Raw | ConvertFrom-Json
if((Get-FileHash -LiteralPath $taskPrep.config -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.configSha256){throw 'Window config changed.'}
# The shared kernel: the one the multi-phone preparation started, still the same process and build.
# Its record is the main folder's, also from a lane's worktree (<main>.worktrees\<lane>, tools/farm_paths.py).
$taskLanes=Split-Path $taskRoot -Parent
$taskMain=if((Split-Path $taskLanes -Leaf).EndsWith('.worktrees')){$taskLanes.Substring(0,$taskLanes.Length-'.worktrees'.Length)}else{$taskRoot}
$taskRack=Get-Content -LiteralPath (Join-Path $taskMain 'analysis\farm-multiphone-20261020\slots\processes.json') -Raw | ConvertFrom-Json
$taskKernel=Get-CimInstance Win32_Process -Filter "ProcessId=$($taskRack.kernel.pid)"
if(!$taskKernel -or $taskKernel.ExecutablePath -ne $taskPrep.kernel){throw 'The multi-phone kernel is not running.'}
$taskStatus=(Invoke-RestMethod 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 4).data
if($taskStatus.process.pid -ne $taskRack.kernel.pid -or $taskStatus.build_identity.sha256 -cne $taskPrep.kernelSha256){throw 'Kernel identity differs from the preparation.'}
$taskOwn=@($taskStatus.receivers | Where-Object {$_.deviceid -ceq $taskPrep.phone.deviceId})
if($taskOwn.Count -ne 1 -or $taskOwn[0].name -cne $taskPrep.phone.receiver){throw 'The kernel does not map this window''s phone to its receiver.'}
$taskTcp=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object LocalPort -In @($taskPrep.backendPort,$taskPrep.mediaPort))
if($taskTcp.Count){throw 'This window''s backend or media port is in use. Nothing was started.'}
function Quote-TaskArguments($taskValues){ foreach($v in $taskValues){if($v.Contains('"')){throw 'Unexpected quote.'}}; (($taskValues | ForEach-Object {'"'+$_+'"'}) -join ' ') }
$taskArgs=@('-u',(Join-Path $taskRoot 'tools/imouse_farm_server.py'),'--no-browser','--mode','live','--port',[string]$taskPrep.backendPort,'--data-dir',$taskPrep.backendData,'--draft-creation-config',$taskPrep.config)
$taskBackend=Start-Process -FilePath $taskPython -ArgumentList (Quote-TaskArguments $taskArgs) -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskDir 'backend.stdout.txt') -RedirectStandardError (Join-Path $taskDir 'backend.stderr.txt')
@{utc=[datetime]::UtcNow.ToString('o');backend=@{pid=$taskBackend.Id;path=$taskPython;arguments=$taskArgs};kernelPid=$taskRack.kernel.pid;phoneInput=$false} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $taskProcessFile -Encoding utf8
$taskDeadline=[datetime]::UtcNow.AddSeconds(30)
do{
    Start-Sleep -Milliseconds 300
    try{$taskHealth=Invoke-RestMethod "http://127.0.0.1:$($taskPrep.backendPort)/health" -TimeoutSec 2}catch{$taskHealth=$null}
    if($taskBackend.HasExited){throw 'Window backend exited; preserve its logs.'}
}while(!$taskHealth -and [datetime]::UtcNow -lt $taskDeadline)
$taskCap=$taskHealth.($taskPrep.capability)
if(!$taskHealth -or $taskHealth.sourceHash -cne $taskPrep.backendSourceHash -or $taskHealth.executionMode -cne 'live' -or !$taskCap.enabled -or $taskCap.device -cne $taskPrep.phone.board -or $taskCap.publishing -or $taskCap.messaging){throw 'Backend identity or draft-only scope differs.'}
$taskHealth | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $taskDir 'backend-ready.json') -Encoding utf8
[ordered]@{window=$Window;backendPid=$taskBackend.Id;port=$taskPrep.backendPort;device=$taskCap.device;receiver=$taskOwn[0].name;live=$taskOwn[0].live;phoneInput=$false} | ConvertTo-Json -Compress
