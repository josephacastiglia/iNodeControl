# Rack B, one board at a time: advertise its placeholder receiver, read the Screen Mirroring list's
# order on rack A slot 2 (a mirroring 6s), then auto-connect from the board. The receiver refuses
# the phone but logs its device ID and model, which prepare_rack_b.py's bound step reads (30 Oct).
# Boards go in descending name order so each new name tends to sort near the top of the list.
param([string[]]$Boards)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$prep = Get-Content slots\preparation.json -Raw | ConvertFrom-Json
$data = Join-Path $prep.runDirectory 'data'
if (-not $Boards) { $Boards = (Get-Content rack-b-boards.json -Raw | ConvertFrom-Json).boards.board | Sort-Object -Descending }
foreach ($b in $Boards) {
    $log = Join-Path $data "receiver-$b.log"
    $count = { if (Test-Path $log) { [regex]::Matches((Get-Content $log -Raw), 'connection request from .*? \((iPhone[\d,]+)\)').Count } else { 0 } }
    if ((& $count) -gt 0) { [pscustomobject]@{board=$b; result='already logged'} | ConvertTo-Json -Compress; continue }
    # Release unconditionally (a state check skipped 636D on 30 Oct); an already advertised receiver is refused harmlessly.
    try { .\Release-Receiver.ps1 -Board $b -Stage slots | Out-Null } catch { }
    Start-Sleep 3
    $survey = (python card_survey.py --board 1814 --small | ConvertFrom-Json).folder
    $result = ''
    foreach ($try in 1..2) {
        # cmd keeps Python's stderr (a traceback) as text instead of a terminating PowerShell error.
        $out = cmd /c "python auto_connect.py --board $b --survey `"$(Join-Path $PSScriptRoot "$survey\record.json")`" --small 2>&1"
        $result = if ("$out" -match 'Traceback') { ($out | Select-Object -Last 3) -join ' | ' } else { $out | Select-Object -Last 1 }
        if ((& $count) -gt 0 -or "$result" -notmatch 'no AirPlay query') { break }
    }
    $models = if (Test-Path $log) { ([regex]::Matches((Get-Content $log -Raw), 'connection request from .*? \((iPhone[\d,]+)\)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique) -join ',' } else { '' }
    [pscustomobject]@{board=$b; logged=(& $count); model=$models; last="$result"} | ConvertTo-Json -Compress
}
