# Start only the isolated candidate when the rack is stopped. Never stop a process.
$ErrorActionPreference = 'Stop'
$record = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'preparation.json') -Encoding UTF8 | ConvertFrom-Json
$protected = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'protected-files.json') -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in $protected.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.sha256) {
        throw "Protected file changed since preparation: $($entry.Name)"
    }
}
if ($record.validation.allowed.Count -ne 1 -or $record.validation.allowed[0] -ne 'C24C' -or
    $record.validation.receiver_count -ne 1 -or $record.arguments[0] -ne 'http://127.0.0.1:9916/api/') {
    throw 'Prepared scope is not the isolated C24C kernel.'
}
if ((Get-FileHash -LiteralPath ([IO.Path]::ChangeExtension($record.kernel, '.dll')) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.validation.build.sha256) {
    throw 'Candidate bytes changed.'
}
foreach ($entry in $record.runtimeFiles.PSObject.Properties) {
    $file = Join-Path $record.runDirectory $entry.Name
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value.sha256) {
        throw "Candidate configuration or dependency changed: $($entry.Name)"
    }
}
$sourceRecord = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'validation-sources.json') -Encoding UTF8 | ConvertFrom-Json
if (@($sourceRecord.files.PSObject.Properties).Count -eq 0) { throw 'Validation source inventory is missing.' }
foreach ($entry in $sourceRecord.files.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath $entry.Name -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) {
        throw "Validation source changed after preparation: $($entry.Name)"
    }
}
$existing = @(Get-CimInstance Win32_Process -Filter "Name='iMouse2.exe' OR Name='iMouse2.Kernel.exe' OR Name='uxplay.exe'")
if ($existing.Count) { throw 'Rack processes are now running. Nothing was stopped or replaced.' }
$ports = @(9913, 9916, 7110, 7111, 7112)
if (@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -In $ports).Count -or
    @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object LocalPort -In $ports).Count) {
    throw 'A required rack/test port is occupied. Nothing was stopped.'
}
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'started.json')) { throw 'This run already has a process record; inspect it rather than relaunching.' }
$quoted = @($record.arguments | ForEach-Object {
    if ($_ -match '["\r\n]') { throw 'Unsupported quoted argument.' }
    '"' + $_ + '"'
})
$process = Start-Process -FilePath $record.kernel -ArgumentList $quoted -WorkingDirectory $record.runDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'kernel-live.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'kernel-live.stderr.txt')
[ordered]@{ pid=$process.Id; startedUtc=$process.StartTime.ToUniversalTime().ToString('o'); path=$record.kernel;
    sha256=$record.validation.build.sha256; address=$record.arguments[0]; initialRackStopped=$true;
    phoneInput=$false; consoleStarted=$false } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'started.json') -Encoding UTF8
$ready = $null
for ($attempt=0; $attempt -lt 10; $attempt++) {
    if ($process.HasExited) { throw "Candidate exited with code $($process.ExitCode). See retained logs." }
    try {
        $response = Invoke-RestMethod -Uri 'http://127.0.0.1:9916/api/kernel/status' -TimeoutSec 2
        if ($response.data.process.pid -eq $process.Id -and $response.data.build_identity.sha256 -eq $record.validation.build.sha256) { $ready=$response; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) { throw 'No verified candidate response. Process record retained; do not start a second copy.' }
$ready | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'started-status.json') -Encoding UTF8
$ready | ConvertTo-Json -Depth 12
