# Connects 4.7-inch phones (6s/7/8/SE) one at a time by receiver name: advertise it, read the
# Screen Mirroring list on rack A slot 2 (a mirroring 6s), then auto-connect from its board.
# Their card shows three rows, so names go in an order that puts each new one in rows 1-3
# (rack B from B20 down: each sorts just after iMouse2-2). 30 Oct.
param([Parameter(Mandatory)][string[]]$Receivers, [string]$SurveyBoard = '1814')
Set-Location $PSScriptRoot
$prep = Get-Content slots\preparation.json -Raw | ConvertFrom-Json
foreach ($name in $Receivers) {
    $board = [string](@($prep.receivers | Where-Object name -eq $name)[0].board)
    if (-not $board) { [pscustomobject]@{receiver=$name; result='not in the preparation'} | ConvertTo-Json -Compress; continue }
    $row = @((Invoke-RestMethod http://127.0.0.1:9916/api/kernel/status).data.receivers | Where-Object name -eq $name)[0]
    if ($row.live) { [pscustomobject]@{receiver=$name; result='already mirroring'} | ConvertTo-Json -Compress; continue }
    try { .\Release-Receiver.ps1 -Board $board -Stage slots | Out-Null } catch { }
    Start-Sleep 3
    $survey = (cmd /c "python card_survey.py --board $SurveyBoard --small 2>&1" | Select-Object -Last 1 | ConvertFrom-Json).folder
    $result = ''
    foreach ($try in 1..2) {
        $out = cmd /c "python auto_connect.py --board $board --survey `"$(Join-Path $PSScriptRoot "$survey\record.json")`" --small 2>&1"
        $result = if ("$out" -match 'Traceback') { ($out | Select-Object -Last 3) -join ' | ' } else { "$($out | Select-Object -Last 1)" }
        if ($result -notmatch 'no AirPlay query') { break }
    }
    $state = if ($result -match '"result": "([^"]*)"') { $Matches[1] } else { $result }
    [pscustomobject]@{receiver=$name; board=$board; result=$state} | ConvertTo-Json -Compress
}
