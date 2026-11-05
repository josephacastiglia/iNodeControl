# Marketing Farm launcher. Installed at <install root>\Farm.ps1 by farm_install.py.
# Runs one command from the CURRENT version (current.json), with the per-machine data folder as the
# working directory and these variables set for the farm tools:
#   IMOUSE_FARM_HOME              <root>\versions\<v>\farm (code; never written)
#   IMOUSE_FARM_DATA              the data folder from install.json (all private state)
#   IMOUSE_FARM_VERSION           <v>
#   IMOUSE_FARM_KERNEL            <root>\versions\<v>\kernel\iMouse2.Kernel.exe
#   IMOUSE_FARM_RECEIVER          <root>\versions\<v>\receiver\uxplay.exe
#   IMOUSE_FARM_RECEIVER_RUNTIME  <root>\versions\<v>\receiver\runtime
#   IMOUSE_FARM_PYTHON            the Python recorded at install
# A command whose code still reads the dev folder or keeps state inside the install is refused
# (release.json "ready": false) until the shared fixes land.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File Farm.ps1 status
#   powershell -NoProfile -ExecutionPolicy Bypass -File Farm.ps1 preflight
#   powershell -NoProfile -ExecutionPolicy Bypass -File Farm.ps1 <command> [arguments]
param([Parameter(Position = 0)][string]$Command = 'status', [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest = @())
$ErrorActionPreference = 'Stop'
function Read-JsonFile([string]$Path) { [IO.File]::ReadAllText($Path, [Text.Encoding]::UTF8) | ConvertFrom-Json }
$root = $PSScriptRoot
$install = Read-JsonFile (Join-Path $root 'install.json')
$current = Read-JsonFile (Join-Path $root 'current.json')
if ($current.version -notmatch '^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$') { throw 'current.json names an invalid version.' }
$version = Join-Path $root ('versions\' + $current.version)
$release = Read-JsonFile (Join-Path $version 'release.json')
$data = [string]$install.data_root
if (!(Test-Path -LiteralPath (Join-Path $data 'data.json'))) { throw "The data folder $data has no data.json; run farm_install.py init-data or reinstall." }
$python = if ($install.python) { [string]$install.python } else { (Get-Command python.exe -ErrorAction SilentlyContinue).Source }

if ($Command -eq 'status') {
    [pscustomobject][ordered]@{ version = $current.version; previous = $current.previous; data = $data; python = $python
        ready = (@($release.commands.PSObject.Properties | Where-Object { $_.Value.ready } | ForEach-Object Name) -join ', ')
        blocked = (@($release.commands.PSObject.Properties | Where-Object { !$_.Value.ready } | ForEach-Object Name) -join ', ') } | Format-List
    exit 0
}
if ($Command -eq 'preflight') {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $version 'install\Preflight-Farm.ps1') -InstallRoot $root -DataRoot $data -Python $python -Package $version @Rest
    exit $LASTEXITCODE
}
$spec = $release.commands.$Command
if (!$spec) { throw "Unknown command '$Command'. Known: status, preflight, " + (($release.commands.PSObject.Properties | ForEach-Object Name) -join ', ') }
if (!$spec.ready) { throw "'$Command' is not ready in version $($current.version): its code still reads the dev folder or keeps state in the install (" + (@($spec.blocked_by) -join ', ') + '). Nothing was started.' }
$entry = Join-Path $version ($spec.entry -replace '/', '\')
$env:IMOUSE_FARM_HOME = Join-Path $version 'farm'
$env:IMOUSE_FARM_DATA = $data
$env:IMOUSE_FARM_VERSION = [string]$current.version
$env:IMOUSE_FARM_KERNEL = Join-Path $version 'kernel\iMouse2.Kernel.exe'
$env:IMOUSE_FARM_RECEIVER = Join-Path $version 'receiver\uxplay.exe'
$env:IMOUSE_FARM_RECEIVER_RUNTIME = Join-Path $version 'receiver\runtime'
$env:IMOUSE_FARM_PYTHON = $python
$extra = @($spec.args | Where-Object { $_ })
Push-Location -LiteralPath $data
try {
    switch ($spec.kind) {
        'python' { if (!$python) { throw 'No Python recorded; reinstall with --python.' }; & $python -E $entry @extra @Rest }
        'powershell' { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $entry @extra @Rest }
        'exe' { & $entry --data-dir (Join-Path $data 'console') @extra @Rest }
        default { throw "Unknown command kind '$($spec.kind)'." }
    }
    $code = $LASTEXITCODE
} finally { Pop-Location }
exit $code
