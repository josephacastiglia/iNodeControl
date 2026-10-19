$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$p=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'processes.json') -Raw -Encoding UTF8|ConvertFrom-Json
$prep=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Raw -Encoding UTF8|ConvertFrom-Json
$acceptance=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'acceptance-attempt-15.json') -Raw -Encoding UTF8|ConvertFrom-Json
if(!$acceptance.accepted){throw 'Live acceptance has not completed.'}
$kernel=Invoke-RestMethod 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 5
if($kernel.data){$kernel=$kernel.data}
$state=Invoke-RestMethod -Uri 'http://127.0.0.1:9916/api/' -Method Post -ContentType 'application/json' -Body '{"fun":"/input/status","data":{}}' -TimeoutSec 5
if($state.data){$state=$state.data}
$phone=@($state.phones)
if($kernel.process.pid -ne $p.kernel.pid -or $kernel.build_identity.sha256 -cne $prep.kernelSha256 -or $phone.Count -ne 1 -or $phone[0].id -cne $prep.expectedDeviceId -or $phone[0].owned -or $phone[0].active -or $phone[0].stopped -or $phone[0].releasing -or $phone[0].release_failed){throw 'Candidate identity or free-input state changed.'}
@{kernel=$kernel;input=$state;utc=[datetime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 15|Set-Content -LiteralPath (Join-Path $PSScriptRoot 'final-live-state.json') -Encoding UTF8
$helper=Join-Path $root 'tools/kernel-window/Stop-ConsoleProcessGracefully.ps1'
foreach($target in @(@{name='backend';pid=$p.backend.pid;path=$p.backend.path},@{name='kernel';pid=$p.kernel.pid;path=$prep.kernel})){
    $actual=Get-CimInstance Win32_Process -Filter ('ProcessId='+$target.pid)
    if(!$actual -or [IO.Path]::GetFullPath($actual.ExecutablePath) -cne [IO.Path]::GetFullPath($target.path)){throw ('Process changed: '+$target.name)}
    $stopper=Start-Process -FilePath powershell.exe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "'+$helper+'" -ProcessId '+$target.pid+' -ExpectedPath "'+$target.path+'" -TimeoutSeconds 20') -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput (Join-Path $PSScriptRoot ('final-stop-'+$target.name+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ('final-stop-'+$target.name+'.stderr.txt'))
    if($stopper.ExitCode -ne 0){throw ('Graceful stop unconfirmed: '+$target.name+'. Nothing is force-killed.')}
}
$remaining=@(Get-CimInstance Win32_Process|Where-Object {$_.Name -in @('iMouse2.exe','iMouse2.Kernel.exe','uxplay.exe','NativeProbe.exe') -or ($_.Name -like 'python*' -and $_.CommandLine -like '*imouse_farm_server.py*')})
$tcp=@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue|Where-Object {$_.LocalPort -in @(9913,9914,9915,9916,9917,7110,7111,7120,7121)})
$udp=@(Get-NetUDPEndpoint -ErrorAction SilentlyContinue|Where-Object {$_.LocalPort -in @(7110,7111,7112,7120,7121,7122)})
$protected=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'protected-files.json') -Raw -Encoding UTF8|ConvertFrom-Json
$files=@(foreach($entry in $protected.PSObject.Properties){
    $hash=(Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant()
    @{path=$entry.Name;sha256=$hash;unchanged=($hash -ceq $entry.Value.sha256)}
})
$accepted=$remaining.Count -eq 0 -and $tcp.Count -eq 0 -and $udp.Count -eq 0 -and @($files|Where-Object {!$_.unchanged}).Count -eq 0
@{restored=$accepted;utc=[datetime]::UtcNow.ToString('o');processes=$remaining|Select-Object ProcessId,Name;tcp=$tcp;udp=$udp;protectedFiles=$files;installedReleaseStarted=$false;phoneInput=$false}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath (Join-Path $PSScriptRoot 'restoration.json') -Encoding UTF8
if(!$accepted){throw 'Restoration checks require review; see restoration.json.'}
Write-Output ('Restored stopped state; '+$files.Count+' protected files unchanged.')
