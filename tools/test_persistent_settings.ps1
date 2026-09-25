$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$source = Join-Path $root 'release\iMouse2-two-phone-candidate'
$appData = Join-Path $env:APPDATA 'iMouse2'
$persistent = Join-Path $appData 'settings.json'
$expected = [System.IO.Path]::GetFullPath($appData)

function Invoke-Resolve([string]$dir) {
    $marker = Join-Path $dir 'data-path.txt'
    $fail = Join-Path $dir 'data-path-failure.txt'
    foreach ($path in @($marker, $fail)) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force } }
    $proc = Start-Process -FilePath (Join-Path $dir 'iMouse2.exe') -ArgumentList '--print-data-path' -WorkingDirectory $dir -PassThru -Wait
    if ($proc.ExitCode -ne 0) {
        $detail = if (Test-Path -LiteralPath $fail) { Get-Content -LiteralPath $fail -Raw } else { '' }
        throw "resolve failed in $dir exit $($proc.ExitCode) $detail"
    }
    if (-not (Test-Path -LiteralPath $marker)) { throw "missing data-path.txt in $dir" }
    return (Get-Content -LiteralPath $marker -Raw).Trim()
}

function Copy-Host([string]$dest) {
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    foreach ($name in @('iMouse2.exe', 'iMouse2.dll', 'iMouse2.deps.json', 'iMouse2.runtimeconfig.json')) {
        Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $dest $name) -Force
    }
}

$installed = Invoke-Resolve $source
if ([System.IO.Path]::GetFullPath($installed) -ne $expected) { throw "candidate resolved to '$installed', expected '$expected'" }
if (-not (Test-Path -LiteralPath $persistent)) { throw "missing $persistent" }
$json = Get-Content -LiteralPath $persistent -Raw | ConvertFrom-Json
if ([string]::IsNullOrWhiteSpace([string]$json.address)) { throw 'settings.json has no address' }
$before = (Get-FileHash -LiteralPath $persistent -Algorithm SHA256).Hash

$scratch = Join-Path $env:TEMP ("imouse2-settings-" + [guid]::NewGuid().ToString('n'))
try {
    foreach ($name in @('build-a', 'build-b')) {
        $dir = Join-Path $scratch $name
        Copy-Host $dir
        New-Item -ItemType Directory -Path (Join-Path $dir 'data') -Force | Out-Null
        $address = if ($name -eq 'build-a') { 'http://127.0.0.1:1' } else { 'http://10.0.0.2:9913' }
        Set-Content -LiteralPath (Join-Path $dir 'data\settings.json') -Value (@{ address = $address; theme = 'light' } | ConvertTo-Json -Compress)
        $resolved = Invoke-Resolve $dir
        if ([System.IO.Path]::GetFullPath($resolved) -ne $expected) { throw "$name resolved to '$resolved', expected '$expected'" }
    }
    $after = (Get-FileHash -LiteralPath $persistent -Algorithm SHA256).Hash
    if ($after -ne $before) { throw 'AppData settings.json changed when resolving from other directories' }
    $again = Get-Content -LiteralPath $persistent -Raw | ConvertFrom-Json
    if ($again.address -ne $json.address) { throw "address changed from $($json.address) to $($again.address)" }
}
finally {
    if (Test-Path -LiteralPath $scratch) { Remove-Item -LiteralPath $scratch -Recurse -Force }
    $marker = Join-Path $source 'data-path.txt'
    if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker -Force }
}

[pscustomobject]@{ Result = 'pass'; Path = $persistent; Address = $json.address }
