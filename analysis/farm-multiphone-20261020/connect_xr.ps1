# Connects rack A's iPhone XRs one at a time: advertise the receiver, read the Screen Mirroring list
# on a mirroring XR (C214, slot 20), then auto-connect from the board. With rack B and the small
# phones listed, the XR card fills the screen; going from 19 down, each new name sorts just after
# iMouse2-8, in row 6 (30 Oct).
param([string[]]$Pairs = @('C241=192.168.4.85','C24C=192.168.4.57','724E=192.168.4.65','F215=192.168.4.69','9515=192.168.4.35',
                           '764E=192.168.4.34','C415=192.168.4.66','3523=192.168.4.28','E414=192.168.4.37','374C=192.168.4.68'),
      [string]$SurveyBoard = 'C214')
Set-Location $PSScriptRoot
foreach ($pair in $Pairs) {
    $board, $ip = $pair -split '='
    try { .\Release-Receiver.ps1 -Board $board -Stage slots | Out-Null } catch { }
    Start-Sleep 3
    $survey = (cmd /c "python card_survey.py --board $SurveyBoard 2>&1" | Select-Object -Last 1 | ConvertFrom-Json).folder
    $result = ''
    foreach ($try in 1..2) {
        $out = cmd /c "python auto_connect.py --board $board --phone-ip $ip --survey `"$(Join-Path $PSScriptRoot "$survey\record.json")`" 2>&1"
        $result = if ("$out" -match 'Traceback') { ($out | Select-Object -Last 3) -join ' | ' } else { "$($out | Select-Object -Last 1)" }
        if ($result -notmatch 'no AirPlay query') { break }
    }
    $state = if ($result -match '"result": "([^"]*)"') { $Matches[1] } else { $result }
    [pscustomobject]@{board=$board; result=$state} | ConvertTo-Json -Compress
}
