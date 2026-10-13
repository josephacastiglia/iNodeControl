# One explicitly approved, C24C-only API test window. Never stops an existing service.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$evidence = $PSScriptRoot
$preparation = Get-Content (Join-Path $repo 'analysis/scope-release-20261012/preparation.json') -Raw -Encoding utf8 | ConvertFrom-Json
$run = $preparation.run_directory
$package = Join-Path $repo 'output/staging/combined-scope-release-20261012'
function Save-Json($name, $value) { $value | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $evidence $name) -Encoding utf8 }
function Verify-Inventory($root, $entries) {
    foreach ($item in $entries.PSObject.Properties) {
        $path = Join-Path $root $item.Name
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $item.Value.sha256) { throw "Inventory mismatch: $path" }
    }
}
$inventory = Get-Content (Join-Path $repo 'analysis/scope-release-20261012/run-inventory.json') -Raw -Encoding utf8 | ConvertFrom-Json
Verify-Inventory $run $inventory
$manifest = Join-Path $package 'package.json'
if ((Get-FileHash $manifest -Algorithm SHA256).Hash -ine $preparation.package_manifest.sha256) { throw 'Package manifest changed' }
Verify-Inventory $package ((Get-Content $manifest -Raw -Encoding utf8 | ConvertFrom-Json).files)
$processes = @(Get-CimInstance Win32_Process -Filter "Name='iMouse2.exe' OR Name='iMouse2.Kernel.exe' OR Name='uxplay.exe' OR Name='dotnet.exe'" | Where-Object { $_.Name -ne 'dotnet.exe' -or $_.CommandLine -like '*iMouse2.Kernel.dll*' } | Select-Object ProcessId,Name,ExecutablePath,CommandLine,CreationDate)
$ports = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalPort -in @(9913,7110,7111,7112) } | Select-Object LocalAddress,LocalPort,OwningProcess)
Save-Json 'preflight.json' @{ time_utc=[DateTime]::UtcNow.ToString('o'); processes=$processes; ports=$ports; input_scope=@('C24C'); fka_changes=$false; typing=$false; desktop_control=$false; package_verified=$true; prepared_run_verified=$true }
if ($processes.Count -or $ports.Count) { throw 'Rack is no longer stopped; preflight needs review. Nothing started.' }
$protected = @(Get-Content (Join-Path $repo 'analysis/scope-release-20261012/protected-files.json') -Raw -Encoding utf8 | ConvertFrom-Json)
$original = Join-Path (Split-Path $repo) 'iMouseXP-2.0'
$paths = @($protected.path) + @((Join-Path $original 'Open iMouse 2.0.ps1')) + @(Get-ChildItem (Join-Path $original 'analysis/two-phone-config') -File | ForEach-Object FullName)
$snapshot = Join-Path $evidence 'restoration-snapshot'
New-Item -ItemType Directory -Path $snapshot -Force | Out-Null
$saved = @(); $index = 0
foreach ($path in $paths) {
    $copy = Join-Path $snapshot ('{0:D2}-{1}' -f $index, (Split-Path $path -Leaf)); $index++
    Copy-Item -LiteralPath $path -Destination $copy
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ((Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash -ine $hash) { throw 'Snapshot mismatch' }
    $saved += @{ path=$path; copy=$copy; sha256=$hash }
}
Save-Json 'restoration-files.json' $saved
$kernel = Join-Path $run 'kernel/bin/iMouse2.Kernel.exe'
$argsForKernel = @($preparation.kernel_arguments_for_later_review_only | ForEach-Object { if ($_ -match '[\s"]') { if ($_ -match '"') { throw 'Unexpected quote in argument' }; '"' + $_ + '"' } else { $_ } })
$started = Start-Process -FilePath $kernel -ArgumentList $argsForKernel -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $evidence 'kernel-stdout.log') -RedirectStandardError (Join-Path $evidence 'kernel-stderr.log') -PassThru
Save-Json 'started.json' @{ time_utc=[DateTime]::UtcNow.ToString('o'); pid=$started.Id; executable=$kernel; arguments=$preparation.kernel_arguments_for_later_review_only; console_started=$false; human_authorized=$true }
$status = $null
for ($attempt=0; $attempt -lt 25; $attempt++) {
    if ($started.HasExited) { throw "Candidate exited: $($started.ExitCode). Read logs; do not restart automatically." }
    try { $status=Invoke-RestMethod 'http://127.0.0.1:9913/api/kernel/status' -TimeoutSec 2; break } catch { Start-Sleep -Milliseconds 300 }
}
if (!$status) { throw 'Candidate did not respond; retained process/logs for controlled restoration.' }
Save-Json 'startup-status.json' $status
$inputState=Invoke-RestMethod 'http://127.0.0.1:9913/api/input/status' -TimeoutSec 3
Save-Json 'startup-input.json' $inputState
Save-Json 'startup-processes.json' @(Get-CimInstance Win32_Process -Filter "Name='iMouse2.Kernel.exe' OR Name='uxplay.exe'" | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine,CreationDate)
[pscustomobject]@{kernel_pid=$started.Id; receiver_count=@($status.data.receivers).Count; receiver_names=@($status.data.receivers.name); input_state=$inputState; evidence=$evidence} | ConvertTo-Json -Depth 12
