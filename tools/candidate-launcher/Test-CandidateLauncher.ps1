param([string]$ReportPath='')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'CandidateLaunch.ps1')
$readServiceImplementation=(Get-Command Read-CandidateService).ScriptBlock
$stopProxyImplementation=(Get-Command Stop-CandidateProxy).ScriptBlock
Add-Type -AssemblyName System.Net.Http
$compilerOptions=@{}
if ($PSVersionTable.PSEdition -eq 'Desktop') { $compilerOptions.ReferencedAssemblies='System.Net.Http' }
Add-Type @compilerOptions -TypeDefinition @'
using System; using System.Net; using System.Net.Http; using System.Threading; using System.Threading.Tasks;
public sealed class OfflineCandidateHttp : HttpMessageHandler {
    public int Count; public string LastUri; public int Status = 200; public string ProxyPid = "102"; public bool IncludeProxyHeader = true;
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token) {
        Count++; LastUri=request.RequestUri.AbsoluteUri;
        var result=new HttpResponseMessage((HttpStatusCode)Status);
        result.Content=new StringContent("{\"status\":200,\"data\":{\"code\":0,\"input_protocol\":1,\"input_leases_required\":true}}");
        if (IncludeProxyHeader) result.Headers.TryAddWithoutValidation("X-iMouse-FaultProxy-Pid",ProxyPid);
        return Task.FromResult(result);
    }
}
'@
$passed=[Collections.Generic.List[string]]::new()
function Check([string]$Name,[bool]$OK) { if (!$OK) { throw "Failed: $Name" }; $passed.Add($Name) }
function Reject([string]$Name,[scriptblock]$Action,[string]$Pattern) {
    $rejected=$false
    try { & $Action | Out-Null } catch { if ($_.Exception.Message -notmatch $Pattern) { throw }; $rejected=$true }
    Check $Name $rejected
}
# These sentinels make accidental fallback to real network/process adapters a test failure.
function Start-Process { throw 'A test attempted to start a real process.' }
function Invoke-RestMethod { throw 'A test attempted to contact a real service.' }
$root=Join-Path ([IO.Path]::GetTempPath()) ('imouse-launcher-test-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($root)
$source=Join-Path $root 'repo with spaces'; [void][IO.Directory]::CreateDirectory($source)
function Record-File([string]$Path) { @{sha256=(Get-FileHash -LiteralPath $Path).Hash.ToLowerInvariant(); bytes=(Get-Item -LiteralPath $Path).Length} }
function Fixture-Build([string]$Name,[string]$Project,[string]$SourceName,[string]$Content) {
    $folder=Join-Path $root ($Name+' build'); [void][IO.Directory]::CreateDirectory($folder)
    $projectPath=Join-Path $source $Project; [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($projectPath))
    [IO.File]::WriteAllText($projectPath,'<Project/>')
    $codePath=Join-Path $source $SourceName; [IO.File]::WriteAllText($codePath,$Content)
    $artifacts=[ordered]@{}
    foreach ($suffix in @('.exe','.dll','.deps.json','.runtimeconfig.json','.pdb')) {
        $path=Join-Path $folder ($Name+$suffix); [IO.File]::WriteAllText($path,'SYNTHETIC: NEVER EXECUTE '+$suffix)
        $artifacts[$Name+$suffix]=Record-File $path
    }
    $sources=[ordered]@{}; $sources[$Project]=Record-File $projectPath; $sources[$SourceName]=Record-File $codePath
    $manifest=Join-Path $root ($Name+'-manifest.json')
    Write-CandidateJson $manifest @{schema_version=1; project=$Project; sources=$sources; artifacts=$artifacts}
    @{Exe=(Join-Path $folder ($Name+'.exe')); Manifest=$manifest; Code=$codePath; Folder=$folder}
}
$c=Fixture-Build 'iMouse2' 'src/iMouse.Console/iMouse.Console.csproj' 'src/iMouse.Console/App.xaml.cs' 'e.Args.Contains("--validate-startup")'
$sourceExeHash=(Get-FileHash -LiteralPath $c.Exe).Hash
$p=Fixture-Build 'InputFaultProxy' 'tools/input-fault-proxy/InputFaultProxy.csproj' 'tools/input-fault-proxy/Program.cs' '"--ready-file"'
function New-TestPlan([switch]$Proxy) {
    $planOptions=@{ConsoleExe=$c.Exe; BuildManifest=$c.Manifest; SourceRoot=$source; RunDir=(Join-Path $root ('run '+[Guid]::NewGuid().ToString('N'))); Address='http://127.0.0.1:9913/api/'}
    if ($Proxy) { $planOptions.ViaProxy=$true; $planOptions.ProxyExe=$p.Exe; $planOptions.ProxyManifest=$p.Manifest; $planOptions.ProxyListen='http://localhost:9923/' }
    New-CandidatePlan @planOptions
}
$script:events=[Collections.Generic.List[string]]::new()
$script:failProbe=$false; $script:failService=$false; $script:failConsole=$false; $script:badProxy=$false; $script:badReceipt=$false; $script:failCleanup=$false; $script:portBusy=$false; $script:wrongProxyHeader=$false
function Start-CandidateProcess([string]$Exe,[string[]]$Arguments,[string]$Directory,[bool]$Hidden) {
    if ($Arguments -contains '--validate-startup') {
        $script:events.Add('probe')
        if (!$Hidden) { throw 'Probe must be hidden.' }
        $digest=@($script:plan.Files | Where-Object Relative -ceq 'bin/iMouse2.dll')[0].Sha256
        Write-CandidateJson (Join-Path $Directory 'startup-validation.json') @{valid=$true; connected=$false; settingsWritten=$false; dataDirectory=$script:plan.DataDir; address=$script:plan.ConsoleAddress; build=@{Sha256=$digest}}
        return [pscustomobject]@{Id=101; HasExited=$true; ExitCode=0}
    }
    if ($Exe.EndsWith('InputFaultProxy.exe')) {
        $script:events.Add('proxy'); if (!$Hidden) { throw 'Proxy must be hidden.' }
        Write-CandidateJson (Join-Path $script:plan.RunDir 'proxy-ready.json') @{pid=$(if ($script:badReceipt) { 900 } else { 102 }); listen=$script:plan.ConsoleAddress; upstream=$script:plan.Service}
        return [pscustomobject]@{Id=102; HasExited=$false; ExitCode=0}
    }
    $script:events.Add('console')
    if ($script:failConsole) { throw 'Synthetic console launch failure.' }
    if ($Hidden -or $Arguments -notcontains ('--data-dir="'+$script:plan.DataDir+'"') -or $Arguments -notcontains ('--address='+$script:plan.ConsoleAddress)) { throw 'Incorrect console command line.' }
    [pscustomobject]@{Id=103; HasExited=$false; ExitCode=0}
}
function Wait-CandidateProbe($Process) { if ($script:failProbe) { throw 'Synthetic validation failure.' } }
function Read-CandidateService([string]$Base) {
    $script:events.Add('read '+$Base)
    if ($script:failService) { throw 'Synthetic unavailable service.' }
    @{Body=@{status=200; data=@{code=0; input_protocol=1; input_leases_required=$true; receivers=@(@{deviceid='TEST:01'});
        process=@{pid=$(if ($script:badProxy -and $Base -eq $script:plan.ConsoleAddress) { 999 } else { 200 })}; build_identity=@{sha256='KERNEL-BYTES'}}};
        ProxyPid=$(if ($script:plan.ViaProxy -and $Base -eq $script:plan.ConsoleAddress -and !$script:wrongProxyHeader) { 102 } else { $null })}
}
function Assert-CandidateProxyPortFree([string]$Address) { $script:events.Add('port check'); if ($script:portBusy) { throw 'Synthetic port already in use.' } }
function Stop-CandidateProxy($Process,[string]$Exe) {
    $script:events.Add('cleanup '+$Process.Id)
    if ($script:failCleanup) { throw 'Synthetic cleanup unconfirmed.' }
}
try {
    $httpHandler=[OfflineCandidateHttp]::new(); $http=[Net.Http.HttpClient]::new($httpHandler)
    try {
        $reply=& $readServiceImplementation 'http://localhost:9923' $http
        Check 'HTTP reader captures the proxy response header separately from service JSON' ($reply.ProxyPid -eq 102 -and $reply.Body.data.input_leases_required -ceq $true -and $httpHandler.Count -eq 1 -and $httpHandler.LastUri -eq 'http://localhost:9923/api/kernel/status')
        $httpHandler.ProxyPid='bad'
        Reject 'HTTP reader refuses malformed proxy identity headers' { & $readServiceImplementation 'http://localhost:9923' $http } 'Invalid proxy'
        $httpHandler.IncludeProxyHeader=$false; $httpHandler.Status=302
        Reject 'HTTP redirect responses are refused rather than treated as status' { & $readServiceImplementation 'http://localhost:9923' $http } '302'
        $httpHandler.Status=200
        Check 'Direct-kernel response has no fabricated proxy identity' ($null -eq (& $readServiceImplementation 'http://localhost:9913' $http).ProxyPid)
    } finally { $http.Dispose() }
    & {
        $script:cleanupCall=$null
        function Start-Process($FilePath,$ArgumentList,$WindowStyle,[switch]$PassThru) {
            $script:cleanupCall=@{exe=$FilePath; args=$ArgumentList; style=$WindowStyle}
            $child=[pscustomobject]@{ExitCode=0}
            $child | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value { param($ms) $true }
            $child
        }
        & $stopProxyImplementation ([pscustomobject]@{Id=102;HasExited=$false}) $p.Exe
        $args=$script:cleanupCall.args
        Check 'Cleanup invokes the scoped helper hidden with script permission and the exact owned process' ($script:cleanupCall.exe -ceq 'powershell.exe' -and $script:cleanupCall.style -ceq 'Hidden' -and $args[$args.IndexOf('-ExecutionPolicy')+1] -ceq 'Bypass' -and $args[$args.IndexOf('-ProcessId')+1] -eq 102 -and $args[$args.IndexOf('-ExpectedPath')+1] -ceq ('"'+$p.Exe+'"'))
    }
    $script:plan=New-TestPlan
    Check 'Checking performs no process or service calls and creates no run folder' ($events.Count -eq 0 -and !(Test-Path -LiteralPath $plan.RunDir))
    Check 'Default profile uses the explicit endpoint and hover tracking off' (($plan.Profile | ConvertFrom-Json).trackPointer -ceq $false -and $plan.ConsoleAddress -ceq 'http://127.0.0.1:9913')
    foreach ($endpoint in @('http://localhost','http://user:secret@localhost:9913','http://localhost:9913/?key=x','http://localhost:9913/else','http://localhost:0','http://localhost:99999999999','file:///C:/data')) {
        Reject ('Reject endpoint '+$endpoint) { Get-CandidateEndpoint $endpoint } 'HTTP|port'
    }
    Check 'Explicit standard ports and IPv6 are preserved' ((Get-CandidateEndpoint 'http://[::1]:80/api') -ceq 'http://[::1]:80' -and (Get-CandidateEndpoint 'https://localhost:443') -ceq 'https://localhost:443')
    Reject 'Reject drive roots' { Get-CandidatePath 'C:\' } 'dedicated'
    Reject 'Reject relative paths' { Get-CandidatePath 'relative' } 'absolute'
    Reject 'Reject reserved device names' { Get-CandidatePath (Join-Path $root 'NUL') } 'Invalid'
    Reject 'Reject traversal in manifest entries' { Get-CandidateRelative $source '../outside' } 'relative'
    $bytes=[IO.File]::ReadAllBytes($c.Exe); [IO.File]::WriteAllText($c.Exe,'changed')
    Reject 'Changed candidate is refused before anything starts' { New-TestPlan } 'changed'
    [IO.File]::WriteAllBytes($c.Exe,$bytes)
    $code=[IO.File]::ReadAllText($c.Code); [IO.File]::WriteAllText($c.Code,'changed source')
    Reject 'Changed source provenance is refused' { New-TestPlan } 'changed'
    [IO.File]::WriteAllText($c.Code,$code)
    $manifestText=[IO.File]::ReadAllText($c.Manifest)
    [IO.File]::WriteAllText($c.Code,'old console without validation mode')
    $oldRecord=$manifestText | ConvertFrom-Json; $oldRecord.sources.'src/iMouse.Console/App.xaml.cs'=Record-File $c.Code
    Write-CandidateJson $c.Manifest $oldRecord
    Reject 'An intact old build without startup-validation support is never executed' { New-TestPlan } 'no-window'
    [IO.File]::WriteAllText($c.Code,$code); [IO.File]::WriteAllText($c.Manifest,$manifestText)
    $unmarked=Join-Path $root 'existing'; [void][IO.Directory]::CreateDirectory($unmarked)
    Reject 'Existing unrecorded folders are preserved' { New-CandidatePlan $c.Exe $c.Manifest $source $unmarked 'http://localhost:9913' } 'without'
    Reject 'Release output is refused' { New-CandidatePlan $c.Exe $c.Manifest $source (Join-Path $root 'release/new') 'http://localhost:9913' } 'release'
    Reject 'Build folder overlap is refused' { New-CandidatePlan $c.Exe $c.Manifest $source (Join-Path $c.Folder 'run') 'http://localhost:9913' } 'separate'
    $operator=Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'iMouse2/candidate'
    Reject 'Operator settings descendants are refused before writes' { New-CandidatePlan $c.Exe $c.Manifest $source $operator 'http://localhost:9913' } 'operator settings'
    Initialize-CandidateRun $plan
    Check 'Preparation only copies recorded binaries and writes an isolated profile' ($events.Count -eq 0 -and (Get-ChildItem -LiteralPath $plan.RunDir -Recurse -File).Count -eq 7 -and (Get-Content -LiteralPath (Join-Path $plan.DataDir 'settings.json') -Raw | ConvertFrom-Json).trackPointer -ceq $false)
    $profilePath=Join-Path $plan.DataDir 'settings.json'; $stamp=(Get-Item -LiteralPath $profilePath).LastWriteTimeUtc
    Initialize-CandidateRun $plan
    Check 'Repeated preparation preserves the existing verified profile bytes and timestamp' ((Get-Item -LiteralPath $profilePath).LastWriteTimeUtc -eq $stamp)
    [IO.File]::WriteAllText($profilePath,'{"trackPointer":true}')
    Reject 'Altered prepared preferences are refused rather than overwritten' { Initialize-CandidateRun $plan } 'settings changed'
    [IO.File]::WriteAllText($profilePath,$plan.Profile)
    [IO.File]::WriteAllText((Join-Path $plan.RunDir 'bin/unexpected.dll'),'extra')
    Reject 'Unexpected prepared binary is refused' { Assert-CandidatePrepared $plan } 'Unexpected'
    $script:plan=New-TestPlan; $events.Clear(); $result=Invoke-CandidateLaunch $plan
    Check 'Direct launch validates before contacting the service and opening the console' (($events -join '|') -ceq 'probe|read http://127.0.0.1:9913|console' -and $result.ConsolePid -eq 103)
    Reject 'A launched run is never silently reused' { Invoke-CandidateLaunch $plan } 'already attempted'
    $script:plan=New-TestPlan -Proxy; $events.Clear(); $script:failProbe=$true
    Reject 'Failed startup validation leaves the proxy unstarted' { Invoke-CandidateLaunch $plan } 'validation failure'
    Check 'Failed validation sent no service request' (($events -join '|') -ceq 'probe')
    $script:failProbe=$false; $script:plan=New-TestPlan -Proxy; $events.Clear(); $script:failService=$true
    Reject 'An unavailable kernel prevents proxy and console startup' { Invoke-CandidateLaunch $plan } 'unavailable service'
    Check 'Unavailable service leaves no background process to clean up' (($events -join '|') -ceq 'probe|read http://127.0.0.1:9913')
    $script:failService=$false; $script:plan=New-TestPlan -Proxy; $events.Clear(); $result=Invoke-CandidateLaunch $plan
    Check 'Proxy launch verifies the owning process and matching kernel before console launch' (($events -join '|') -ceq 'probe|read http://127.0.0.1:9913|port check|proxy|read http://localhost:9923|console' -and $result.ProxyPid -eq 102)
    $script:plan=New-TestPlan -Proxy; $events.Clear(); $script:portBusy=$true
    Reject 'An occupied proxy port is refused before creating a proxy' { Invoke-CandidateLaunch $plan } 'already in use'
    Check 'Port collision never starts or stops another process' ($events -notcontains 'proxy' -and $events -notcontains 'console' -and @($events | Where-Object { $_ -like 'cleanup*' }).Count -eq 0)
    $script:portBusy=$false; $script:plan=New-TestPlan -Proxy; $events.Clear(); $script:wrongProxyHeader=$true
    Reject 'A shared-prefix answer bypassing this proxy is refused' { Invoke-CandidateLaunch $plan } 'did not pass through'
    Check 'Bypassed proxy is cleaned up without opening the console' ($events[-1] -ceq 'cleanup 102' -and $events -notcontains 'console')
    $script:wrongProxyHeader=$false
    $script:plan=New-TestPlan -Proxy; $events.Clear(); $script:badReceipt=$true
    Reject 'Wrong proxy startup PID is refused' { Invoke-CandidateLaunch $plan } 'receipt'
    Check 'Wrong proxy receipt cleans up only the proxy this launcher started' ($events[-1] -ceq 'cleanup 102' -and $events -notcontains 'console')
    $script:badReceipt=$false; $script:plan=New-TestPlan -Proxy; $events.Clear(); $script:badProxy=$true
    Reject 'A proxy pointing to another kernel is refused' { Invoke-CandidateLaunch $plan } 'does not match'
    Check 'Wrong upstream identity prevents the console and cleans up the owned proxy' ($events[-1] -ceq 'cleanup 102' -and $events -notcontains 'console')
    $script:badProxy=$false; $script:plan=New-TestPlan -Proxy; $events.Clear(); $script:failConsole=$true; $script:failCleanup=$true
    Reject 'Console failure reports unconfirmed proxy cleanup' { Invoke-CandidateLaunch $plan } 'cleanup unconfirmed'
    $failed=Get-Content -LiteralPath (Join-Path $plan.RunDir 'launch.json') -Raw | ConvertFrom-Json
    Check 'Failed launch records the exact owned proxy PID and cleanup error' ($failed.state -eq 'failed' -and $failed.proxy_pid -eq 102 -and $failed.cleanup_error -like '*unconfirmed*')
    Reject 'Malformed ownership flags are not accepted' { Assert-CandidateService @{status=200; data=@{code=0; input_protocol=1; input_leases_required='true'}} } 'ownership-kernel'
    Check 'Synthetic source executable was preserved through preparation and launch tests' ((Get-FileHash -LiteralPath $c.Exe).Hash -eq $sourceExeHash)
    $report=[ordered]@{passed=$passed.Count; tests=$passed; all_processes_and_network_mocked=$true; at_utc=[DateTime]::UtcNow.ToString('o')}
    if ($ReportPath) { Write-CandidateJson ([IO.Path]::GetFullPath($ReportPath)) $report }
    "$($passed.Count) candidate launcher checks passed; no real process or network calls."
} finally {
    $resolved=[IO.Path]::GetFullPath($root)
    $temp=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\'
    if (!$resolved.StartsWith($temp,[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notmatch '^imouse-launcher-test-[0-9a-f]{32}$') { throw 'Test cleanup path verification failed.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
