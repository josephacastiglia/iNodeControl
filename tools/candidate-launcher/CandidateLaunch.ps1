# Dot-sourcing defines functions only; no file, network or process operation runs here.
function Get-CandidatePath([string]$Path) {
    if ($Path -notmatch '^[A-Za-z]:[\\/]') { throw 'Candidate paths must be absolute local-drive paths.' }
    $full=[IO.Path]::GetFullPath($Path).TrimEnd('\','/')
    if ($full.Length -le 2) { throw 'Use a dedicated folder below the drive root.' }
    foreach ($part in $full.Substring(3).Split([char[]]'\/')) {
        if (!$part -or $part.EndsWith('.') -or $part.EndsWith(' ') -or $part.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)') { throw 'Invalid candidate path component.' }
    }
    for ($parent=$full; $parent; $parent=[IO.Path]::GetDirectoryName($parent)) {
        if ((Test-Path -LiteralPath $parent) -and ((Get-Item -LiteralPath $parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Candidate path contains a reparse point: $parent" }
    }
    $full
}
function Test-CandidateUnder([string]$Path,[string]$Root) { $Path -ieq $Root -or $Path.StartsWith($Root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase) }
function Get-CandidateEndpoint([string]$Address) {
    if ($Address -notmatch '^(https?)://(\[[^\]]+\]|[^/:?#@\s]+):([0-9]+)(/api/?)?/?$') { throw 'Use HTTP(S) with an explicit port and no credentials, query or unrelated path.' }
    $scheme=$Matches[1]; $hostPart=$Matches[2]; $number=0
    if (![int]::TryParse($Matches[3],[ref]$number) -or $number -lt 1 -or $number -gt 65535) { throw 'Invalid service port.' }
    $uri=[Uri]($scheme+'://'+$hostPart+':'+$number)
    if (!$uri.IsAbsoluteUri -or !$uri.Host -or $uri.UserInfo -or $uri.Query -or $uri.Fragment) { throw 'Invalid service address.' }
    $normalizedHost=$uri.Host.ToLowerInvariant()
    if ($hostPart.StartsWith('[')) { $normalizedHost='['+[Net.IPAddress]::Parse($hostPart.Trim('[',']')).ToString()+']' }
    $scheme.ToLowerInvariant()+'://'+$normalizedHost+':'+$number
}
function Assert-CandidateHash([string]$Path,$Record) {
    if (!$Record -or [string]$Record.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or $null -eq $Record.bytes) { throw 'Missing or invalid build hash record.' }
    $safe=Get-CandidatePath $Path
    if (!(Test-Path -LiteralPath $safe -PathType Leaf)) { throw "Recorded file missing: $safe" }
    if ((Get-Item -LiteralPath $safe).Length -ne $Record.bytes -or (Get-FileHash -LiteralPath $safe -Algorithm SHA256).Hash -ine $Record.sha256) { throw "Recorded file changed: $safe" }
}
function Get-CandidateRelative([string]$Root,[string]$Name) {
    if (!$Name -or $Name.Contains('\') -or $Name.Contains(':') -or $Name.StartsWith('/') -or @($Name.Split('/') | Where-Object { $_ -in @('','..','.') }).Count) { throw 'Invalid relative build-record path.' }
    $path=Get-CandidatePath ([IO.Path]::Combine($Root,$Name.Replace('/','\')))
    if (!(Test-CandidateUnder $path $Root)) { throw 'Build record escapes its root.' }
    $path
}
function Get-CandidateBuild([string]$Exe,[string]$Manifest,[string]$SourceRoot,[string]$Name,[string]$Project) {
    $exePath=Get-CandidatePath $Exe; $manifestPath=Get-CandidatePath $Manifest
    if ([IO.Path]::GetFileName($exePath) -cne ($Name+'.exe')) { throw "Expected $Name.exe." }
    $build=[IO.Path]::GetDirectoryName($exePath)
    $record=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($record.schema_version -ne 1 -or $record.project -cne $Project -or !$record.sources -or !$record.artifacts) { throw 'Wrong or incomplete build manifest.' }
    foreach ($item in $record.sources.PSObject.Properties) { Assert-CandidateHash (Get-CandidateRelative $SourceRoot $item.Name) $item.Value }
    $files=@()
    foreach ($suffix in @('.exe','.dll','.deps.json','.runtimeconfig.json','.pdb')) {
        $nameOnDisk=$Name+$suffix; $entry=$record.artifacts.PSObject.Properties[$nameOnDisk]
        if (!$entry) { throw "Build manifest does not identify $nameOnDisk." }
        $path=Get-CandidateRelative $build $nameOnDisk; Assert-CandidateHash $path $entry.Value
        $files += [pscustomobject]@{ Name=$nameOnDisk; Source=$path; Sha256=[string]$entry.Value.sha256; Bytes=[long]$entry.Value.bytes }
    }
    [pscustomobject]@{ Exe=$exePath; Directory=$build; Files=$files; Manifest=$manifestPath; ManifestHash=(Get-FileHash -LiteralPath $manifestPath).Hash; Record=$record }
}
function Get-CandidateTextHash([string]$Value) {
    $sha=[Security.Cryptography.SHA256]::Create()
    try { ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-','').ToLowerInvariant() } finally { $sha.Dispose() }
}
function Write-CandidateJson([string]$Path,$Value) { [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 16),[Text.UTF8Encoding]::new($false)) }
function Write-CandidateNew([string]$Path,[string]$Text) {
    $stream=[IO.File]::Open($Path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try { $bytes=[Text.Encoding]::UTF8.GetBytes($Text); $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
}
function New-CandidatePlan {
    param([string]$ConsoleExe,[string]$BuildManifest,[string]$SourceRoot,[string]$RunDir,[string]$Address,
        [switch]$ViaProxy,[string]$ProxyExe='',[string]$ProxyManifest='',[string]$ProxyListen='http://localhost:9923/')
    $source=Get-CandidatePath $SourceRoot; $run=Get-CandidatePath $RunDir
    $endpoint=Get-CandidateEndpoint $Address; $effective=$endpoint
    $shared=Get-CandidatePath (Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'iMouse2')
    if (Test-CandidateUnder $run $shared) { throw 'RunDir must not be inside operator settings.' }
    if ($run -match '(?i)\\release(?:\\|$)') { throw 'RunDir must not be in release.' }
    $console=Get-CandidateBuild $ConsoleExe $BuildManifest $source 'iMouse2' 'src/iMouse.Console/iMouse.Console.csproj'
    if ((Test-CandidateUnder $run $console.Directory) -or (Test-CandidateUnder $run (Join-Path $source 'src'))) { throw 'RunDir must be separate from build and source folders.' }
    $startupName='src/iMouse.Console/App.xaml.cs'
    if (!$console.Record.sources.PSObject.Properties[$startupName]) { throw 'Build lacks startup capability evidence.' }
    $startup=Get-Content -LiteralPath (Get-CandidateRelative $source $startupName) -Raw -Encoding UTF8
    if (!$startup.Contains('e.Args.Contains("--validate-startup")')) { throw 'Recorded source does not support no-window startup validation.' }
    $files=@($console.Files | ForEach-Object { [pscustomobject]@{ Relative=('bin/'+$_.Name); Source=$_.Source; Sha256=$_.Sha256; Bytes=$_.Bytes } })
    $proxy=$null
    if ($ViaProxy) {
        $effective=Get-CandidateEndpoint $ProxyListen
        if (!([Uri]$effective).IsLoopback -or ([Uri]$effective).Scheme -ne 'http') { throw 'Fault proxy must listen on loopback HTTP.' }
        if ($effective -ieq $endpoint -or (([Uri]$endpoint).IsLoopback -and ([Uri]$effective).Port -eq ([Uri]$endpoint).Port)) { throw 'Proxy and upstream must use different ports.' }
        $proxy=Get-CandidateBuild $ProxyExe $ProxyManifest $source 'InputFaultProxy' 'tools/input-fault-proxy/InputFaultProxy.csproj'
        if (Test-CandidateUnder $run $proxy.Directory) { throw 'RunDir overlaps the proxy build.' }
        $proxySource='tools/input-fault-proxy/Program.cs'
        if (!$proxy.Record.sources.PSObject.Properties[$proxySource] -or !(Get-Content -LiteralPath (Get-CandidateRelative $source $proxySource) -Raw -Encoding UTF8).Contains('"--ready-file"')) { throw 'Recorded proxy lacks a startup receipt.' }
        $files+=@($proxy.Files | ForEach-Object { [pscustomobject]@{ Relative=('proxy/'+$_.Name); Source=$_.Source; Sha256=$_.Sha256; Bytes=$_.Bytes } })
    } elseif ($ProxyExe -or $ProxyManifest) { throw 'Proxy parameters require ViaProxy.' }
    $settings=[ordered]@{ address=$effective; theme='light'; trackPointer=$false }
    $profile=($settings | ConvertTo-Json -Compress)
    $identity=[ordered]@{ schema_version=1; source_root=$source; run_dir=$run; service=$endpoint; console_address=$effective;
        console_manifest_sha256=$console.ManifestHash; proxy_manifest_sha256=$(if ($proxy) { $proxy.ManifestHash } else { $null }); files=$files; settings=$settings }
    $plan=[pscustomobject]@{ RunDir=$run; DataDir=(Join-Path $run 'data'); ConsoleExe=(Join-Path $run 'bin/iMouse2.exe');
        Service=$endpoint; ConsoleAddress=$effective; ViaProxy=[bool]$ViaProxy; ProxyExe=$(if ($proxy) { Join-Path $run 'proxy/InputFaultProxy.exe' } else { $null });
        Files=$files; Profile=$profile; Identity=$identity; Fingerprint=(Get-CandidateTextHash ($identity | ConvertTo-Json -Depth 12 -Compress));
        OfflineOnly=$true; Prepared=(Test-Path -LiteralPath $run) }
    if ($plan.Prepared) { Assert-CandidatePrepared $plan }
    $plan
}
function Assert-CandidatePrepared($Plan) {
    if (Test-Path -LiteralPath (Join-Path $Plan.RunDir 'launch.json')) { throw 'This run already attempted launch. Keep its evidence and use a new RunDir.' }
    $marker=Join-Path $Plan.RunDir 'prepared.json'
    if (!(Test-Path -LiteralPath $marker -PathType Leaf)) { throw 'RunDir exists without a completed preparation record; choose a new folder.' }
    $saved=Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($saved.fingerprint -cne $Plan.Fingerprint) { throw 'Prepared run belongs to a different build or configuration.' }
    foreach ($file in $Plan.Files) { Assert-CandidateHash (Get-CandidateRelative $Plan.RunDir $file.Relative) $file }
    if ([IO.File]::ReadAllText((Get-CandidateRelative $Plan.RunDir 'data/settings.json')) -cne $Plan.Profile) { throw 'Prepared settings changed; keep them and prepare a new run.' }
    $allowed=@('prepared.json','data/settings.json')+@($Plan.Files.Relative)
    foreach ($file in Get-ChildItem -LiteralPath $Plan.RunDir -Recurse -Force) {
        if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Prepared run contains a reparse point.' }
        if (!$file.PSIsContainer) {
            $relative=$file.FullName.Substring($Plan.RunDir.Length+1).Replace('\','/')
            if ($relative -cnotin $allowed) { throw "Unexpected prepared-run file: $relative" }
        }
    }
}
function Initialize-CandidateRun($Plan) {
    if (Test-Path -LiteralPath $Plan.RunDir) { Assert-CandidatePrepared $Plan; $Plan.Prepared=$true; return }
    [void][IO.Directory]::CreateDirectory($Plan.RunDir)
    foreach ($file in $Plan.Files) {
        Assert-CandidateHash $file.Source $file
        $target=Get-CandidateRelative $Plan.RunDir $file.Relative
        [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
        [IO.File]::Copy($file.Source,$target,$false); Assert-CandidateHash $target $file
    }
    [void][IO.Directory]::CreateDirectory($Plan.DataDir)
    Write-CandidateNew (Join-Path $Plan.DataDir 'settings.json') $Plan.Profile
    Write-CandidateNew (Join-Path $Plan.RunDir 'prepared.json') (@{ fingerprint=$Plan.Fingerprint; prepared_utc=[DateTime]::UtcNow.ToString('o'); configuration=$Plan.Identity } | ConvertTo-Json -Depth 16)
    Assert-CandidatePrepared $Plan
    $Plan.Prepared=$true
}
function Read-CandidateService([string]$Base,$Client=$null) {
    Add-Type -AssemblyName System.Net.Http
    $ownsClient=$null -eq $Client; $http=$Client
    if ($ownsClient) {
        $handler=[Net.Http.HttpClientHandler]::new(); $handler.UseProxy=$false; $handler.AllowAutoRedirect=$false
        $http=[Net.Http.HttpClient]::new($handler); $http.Timeout=[TimeSpan]::FromSeconds(5); $http.MaxResponseContentBufferSize=1048576
    }
    try {
        $response=$http.GetAsync($Base+'/api/kernel/status').GetAwaiter().GetResult()
        try {
            if ([int]$response.StatusCode -ne 200) { throw "Status returned HTTP $([int]$response.StatusCode); redirect/error refused." }
            $body=$response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
            [Collections.Generic.IEnumerable[string]]$values=$null; $proxyIdentity=$null
            if ($response.Headers.TryGetValues('X-iMouse-FaultProxy-Pid',[ref]$values)) {
                $identities=@($values); $identity=0
                if ($identities.Count -ne 1 -or ![int]::TryParse($identities[0],[ref]$identity) -or $identity -lt 1) { throw 'Invalid proxy process header.' }
                $proxyIdentity=$identity
            }
            [pscustomobject]@{Body=$body; ProxyPid=$proxyIdentity}
        } finally { $response.Dispose() }
    } finally { if ($ownsClient) { $http.Dispose() } }
}
function Assert-CandidateService($Status) {
    if ($Status.status -ne 200 -or $Status.data.code -ne 0 -or $Status.data.input_protocol -ne 1 -or $Status.data.input_leases_required -isnot [bool] -or !$Status.data.input_leases_required) { throw 'Endpoint is not a successful ownership-kernel response.' }
}
function Assert-CandidateProxyPortFree([string]$Address) {
    $port=([Uri]$Address).Port
    # HTTP.sys permits different URL prefixes on one port. Any existing listener is a
    # collision for this test proxy, even when its root prefix could still be registered.
    $listeners=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq $port)
    if ($listeners.Count) { throw "Proxy port $port is already in use; no process was stopped." }
}
function Start-CandidateProcess([string]$Exe,[string[]]$Arguments,[string]$Directory,[bool]$Hidden) {
    $options=@{FilePath=$Exe; ArgumentList=$Arguments; WorkingDirectory=$Directory; PassThru=$true}
    if ($Hidden) { $options.WindowStyle='Hidden' }
    Start-Process @options
}
function Wait-CandidateProbe($Process) {
    if (!$Process.WaitForExit(15000)) { throw "Startup validation did not exit; PID $($Process.Id) needs inspection. It was not force-killed." }
    if ($Process.ExitCode -ne 0) { throw "Startup validation failed (exit $($Process.ExitCode))." }
}
function Wait-CandidateProxy($Process,$Plan) {
    $receipt=Join-Path $Plan.RunDir 'proxy-ready.json'; $clock=[Diagnostics.Stopwatch]::StartNew()
    while (!(Test-Path -LiteralPath $receipt)) {
        if ($Process.HasExited) { throw 'Candidate proxy exited before becoming ready.' }
        if ($clock.Elapsed.TotalSeconds -ge 5) { throw 'Candidate proxy did not become ready within five seconds.' }
        Start-Sleep -Milliseconds 50
    }
    $ready=Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Process.HasExited -or $ready.pid -ne $Process.Id -or (Get-CandidateEndpoint $ready.listen) -ine $Plan.ConsoleAddress -or (Get-CandidateEndpoint $ready.upstream) -ine $Plan.Service) { throw 'Proxy receipt does not match this process and route.' }
}
function Stop-CandidateProxy($Process,[string]$Exe) {
    if ($Process.HasExited) { return }
    $helper=Join-Path $PSScriptRoot '../kernel-window/Stop-ConsoleProcessGracefully.ps1'
    $stop=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$helper+'"'),'-ProcessId',$Process.Id,'-ExpectedPath',('"'+$Exe+'"'),'-TimeoutSeconds','10') -WindowStyle Hidden -PassThru
    if (!$stop.WaitForExit(15000) -or $stop.ExitCode -ne 0) { throw "Proxy cleanup unconfirmed: PID $($Process.Id), $Exe. No force-kill was attempted." }
}
function Invoke-CandidateLaunch($Plan) {
    Initialize-CandidateRun $Plan
    $state=@{ started_utc=[DateTime]::UtcNow.ToString('o'); state='checking'; console_pid=$null; proxy_pid=$null; probe_pid=$null; error=$null; cleanup_error=$null }
    $record=Join-Path $Plan.RunDir 'launch.json'; Write-CandidateNew $record ($state | ConvertTo-Json -Depth 16)
    $proxy=$null; $console=$null
    try {
        $quotedData='--data-dir="'+$Plan.DataDir+'"'; $address='--address='+$Plan.ConsoleAddress
        $probe=Start-CandidateProcess $Plan.ConsoleExe @('--validate-startup',$quotedData,$address) ([IO.Path]::GetDirectoryName($Plan.ConsoleExe)) $true
        $state.probe_pid=$probe.Id; Write-CandidateJson $record $state; Wait-CandidateProbe $probe
        $proof=Get-Content -LiteralPath (Join-Path $Plan.RunDir 'bin/startup-validation.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $dll=@($Plan.Files | Where-Object Relative -ceq 'bin/iMouse2.dll')[0]
        if ($proof.valid -cne $true -or $proof.connected -cne $false -or $proof.settingsWritten -cne $false -or $proof.dataDirectory -ine $Plan.DataDir -or (Get-CandidateEndpoint $proof.address) -ine $Plan.ConsoleAddress -or $proof.build.Sha256 -ine $dll.Sha256) { throw 'Startup validation did not confirm this exact build, profile and address.' }
        $upstreamRead=Read-CandidateService $Plan.Service; $upstream=$upstreamRead.Body; Assert-CandidateService $upstream
        if ($Plan.ViaProxy) {
            Assert-CandidateProxyPortFree $Plan.ConsoleAddress
            $proxy=Start-CandidateProcess $Plan.ProxyExe @('--listen',($Plan.ConsoleAddress+'/'),'--upstream',$Plan.Service,'--log',('"'+(Join-Path $Plan.RunDir 'proxy-log.jsonl')+'"'),'--ready-file',('"'+(Join-Path $Plan.RunDir 'proxy-ready.json')+'"')) ([IO.Path]::GetDirectoryName($Plan.ProxyExe)) $true
            $state.proxy_pid=$proxy.Id; Write-CandidateJson $record $state; Wait-CandidateProxy $proxy $Plan
            $proxyRead=Read-CandidateService $Plan.ConsoleAddress; $through=$proxyRead.Body; Assert-CandidateService $through
            if ($proxyRead.ProxyPid -ne $proxy.Id) { throw 'The status answer did not pass through the proxy this launcher started.' }
            $ids=@($upstream.data.receivers | ForEach-Object { $_.deviceid } | Sort-Object)
            $proxiedIds=@($through.data.receivers | ForEach-Object { $_.deviceid } | Sort-Object)
            if (!$ids.Count -or ($ids -join ',') -cne ($proxiedIds -join ',') -or $upstream.data.build_identity.sha256 -cne $through.data.build_identity.sha256 -or $upstream.data.process.pid -cne $through.data.process.pid) { throw 'Proxy status does not match the selected kernel.' }
        }
        foreach ($file in $Plan.Files) { Assert-CandidateHash (Get-CandidateRelative $Plan.RunDir $file.Relative) $file }
        if ([IO.File]::ReadAllText((Join-Path $Plan.DataDir 'settings.json')) -cne $Plan.Profile) { throw 'Candidate preferences changed during validation.' }
        $console=Start-CandidateProcess $Plan.ConsoleExe @($quotedData,$address) ([IO.Path]::GetDirectoryName($Plan.ConsoleExe)) $false
        $state.console_pid=$console.Id; $state.state='started'; Write-CandidateJson $record $state
        [pscustomobject]@{ ConsolePid=$console.Id; ProxyPid=$state.proxy_pid; RunDir=$Plan.RunDir; DataDir=$Plan.DataDir; Address=$Plan.ConsoleAddress; Note='Process started; GUI usability and phone ownership are not established.' }
    } catch {
        $state.state='failed'; $state.error=$_.Exception.Message
        if ($proxy -and !$console) { try { Stop-CandidateProxy $proxy $Plan.ProxyExe } catch { $state.cleanup_error=$_.Exception.Message } }
        Write-CandidateJson $record $state
        if ($state.cleanup_error) { throw ($state.error+' '+$state.cleanup_error) }
        throw
    }
}
