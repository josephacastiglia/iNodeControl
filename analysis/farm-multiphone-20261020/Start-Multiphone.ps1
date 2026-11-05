# Starts a private multi-phone kernel so each prepared phone can mirror. Starts no backend and sends no input.
#   -Stage held|slots  the single kernel for every prepared receiver ('slots' = racks A and B on :9916).
#                      Refuses if any rack/test service, kernel, receiver or listener exists (unchanged rule).
#   -Rack A|B          one rack's own kernel (rack-a/ or rack-b/preparation.json, from rack_kernels.py prepare),
#                      on its own port. Refuses only what would collide with this rack: its own kernel, its
#                      receivers' names or ports, its listeners, the single kernel (and, for rack A, the farm
#                      console/backends). The other rack's kernel and phones are left alone.
# Prepared receivers start held; Release-Receiver.ps1 advertises one at a time.
param([ValidateSet('','held','slots')][string]$Stage='',[ValidateSet('','A','B')][string]$Rack='')
$ErrorActionPreference='Stop'
if($Stage -and $Rack){throw 'Choose -Stage or -Rack, not both.'}
$taskDir=if($Rack){Join-Path $PSScriptRoot ('rack-'+$Rack.ToLowerInvariant())}elseif($Stage){Join-Path $PSScriptRoot $Stage}else{$PSScriptRoot}
$taskProcessFile=Join-Path $taskDir 'processes.json'
if(Test-Path -LiteralPath $taskProcessFile){throw 'This multi-phone kernel already has a process record. Do not start duplicates.'}
$taskPrepFile=Join-Path $taskDir 'preparation.json'
$taskPrep=Get-Content -LiteralPath $taskPrepFile -Raw | ConvertFrom-Json
$taskApi=([string]$taskPrep.arguments[0]).TrimEnd('/')
if($taskApi -notmatch '^http://127\.0\.0\.1:\d+/api$'){throw 'The preparation does not start a loopback kernel.'}
if([string]$taskPrep.rack -cne $Rack){throw "The preparation's rack ('$($taskPrep.rack)') is not -Rack '$Rack'."}
$taskHeld=@($taskPrep.held | Where-Object {$_})
$taskExpected=@($taskPrep.receivers).Count-$taskHeld.Count
# What is running, for rack_kernels.py to judge (command lines go to it on stdin only, never to a file).
$taskNames=@('iMouse2.exe','iMouse2.Kernel.exe','uxplay.exe','ReelProbe.exe','TikTokProbe.exe','XProbe.exe')
$taskSnap=@{
    processes=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in $taskNames -or ($_.CommandLine -and $_.CommandLine -match 'python[^\r\n]*imouse_farm_server\.py') } | ForEach-Object { @{Name=$_.Name;ProcessId=$_.ProcessId;CommandLine=$_.CommandLine} })
    listeners=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ForEach-Object LocalPort | Sort-Object -Unique)
} | ConvertTo-Json -Depth 4 -Compress
$taskRackArgs=if($Rack){@('--rack',$Rack)}else{@()}
$taskVerdict=$taskSnap | & python (Join-Path $PSScriptRoot 'rack_kernels.py') check-start --prep $taskPrepFile @taskRackArgs
if($LASTEXITCODE -eq 3){throw "Nothing was stopped or started: $taskVerdict"}elseif($LASTEXITCODE){throw "Start check failed (exit $LASTEXITCODE); nothing was started."}
if((Get-FileHash -LiteralPath ([IO.Path]::ChangeExtension($taskPrep.kernel,'.dll')) -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.kernelSha256){throw 'Kernel changed.'}
foreach($taskName in 'devices.json','receivers.json','pointer-calibration.json'){
    if((Get-FileHash -LiteralPath (Join-Path $taskPrep.runDirectory "data\$taskName") -Algorithm SHA256).Hash.ToLowerInvariant() -cne $taskPrep.dataSha256.$taskName){throw "Prepared $taskName changed."}
}
function Quote-TaskArguments($taskValues){ foreach($v in $taskValues){if($v.Contains('"')){throw 'Unexpected quote.'}}; (($taskValues | ForEach-Object {'"'+$_+'"'}) -join ' ') }
$taskValidator=Start-Process -FilePath $taskPrep.kernel -ArgumentList (Quote-TaskArguments (@($taskPrep.arguments)+@('--validate-startup'))) -WorkingDirectory ([IO.Path]::GetDirectoryName($taskPrep.kernel)) -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $taskDir 'kernel-validation.stdout.txt') -RedirectStandardError (Join-Path $taskDir 'kernel-validation.stderr.txt')
if($taskValidator.ExitCode -ne 0){throw 'Offline kernel startup validation failed; nothing was started.'}
$taskKernel=Start-Process -FilePath $taskPrep.kernel -ArgumentList (Quote-TaskArguments $taskPrep.arguments) -WorkingDirectory ([IO.Path]::GetDirectoryName($taskPrep.kernel)) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskDir 'kernel.stdout.txt') -RedirectStandardError (Join-Path $taskDir 'kernel.stderr.txt')
@{utc=[datetime]::UtcNow.ToString('o');kernel=@{pid=$taskKernel.Id;path=$taskPrep.kernel};rack=$Rack;api=$taskApi;phoneInput=$false} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $taskProcessFile -Encoding utf8
$taskDeadline=[datetime]::UtcNow.AddSeconds(40)
do{
    Start-Sleep -Milliseconds 500
    try{$taskStatus=(Invoke-RestMethod "$taskApi/kernel/status" -TimeoutSec 3).data}catch{$taskStatus=$null}
    if($taskKernel.HasExited){throw 'Kernel exited. Preserve its logs.'}
}while((!$taskStatus -or @($taskStatus.receivers | Where-Object {$_.receiver_pid -gt 0}).Count -ne $taskExpected -or @($taskStatus.receivers | Where-Object {$_.receiver_state -eq 'held'}).Count -ne $taskHeld.Count) -and [datetime]::UtcNow -lt $taskDeadline)
$taskStatus | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $taskDir 'receivers-ready.json') -Encoding utf8
if(!$taskStatus -or $taskStatus.build_identity.sha256 -cne $taskPrep.kernelSha256 -or @($taskStatus.allowed).Count -ne @($taskPrep.inputEnabled).Count){throw 'Kernel identity or allow-list differs.'}
if($Rack -and [string]$taskStatus.rack -cne $Rack){throw "The kernel on $taskApi is not rack $Rack."}
if(@($taskStatus.receivers | Where-Object {$_.receiver_state -eq 'held'}).Count -ne $taskHeld.Count){throw 'Held receivers differ from the preparation.'}
$taskStatus.receivers | ForEach-Object { [pscustomobject]@{receiver=$_.name; state=$_.receiver_state; pid=$_.receiver_pid; live=$_.live} } | Format-Table -AutoSize | Out-String
