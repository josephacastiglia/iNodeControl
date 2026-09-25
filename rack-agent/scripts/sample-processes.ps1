<#
.SYNOPSIS
  Samples CPU and memory of chosen processes to a CSV file. Read-only: it changes nothing.
  Works in Windows PowerShell 5.1 and PowerShell 7.

.DESCRIPTION
  CPU is the process's processor-time increase between samples, divided by the wall time.
  CpuPercentOfOneCore can exceed 100 on multi-core use; CpuPercentOfMachine divides by the
  logical processor count (what Task Manager shows). WorkingSetMB is physical memory in use;
  PrivateMB is memory committed to the process alone. Processes started elevated may need an
  elevated shell to read their CPU time; such rows are marked "access denied".

.EXAMPLE
  # PIDs come from the portal/agent startup lines and from Get-Process for the kernel/receiver.
  .\sample-processes.ps1 -ProcessIds 1234,5678,9012 -Seconds 5 -Minutes 10 `
      -OutFile ..\..\analysis\portal-m1-windows-20260926\processes.csv
#>
param(
  [Parameter(Mandatory = $true)][int[]]$ProcessIds,
  [int]$Seconds = 5,
  [double]$Minutes = 10,
  [Parameter(Mandatory = $true)][string]$OutFile
)
$ErrorActionPreference = 'Stop'
$cores = [Environment]::ProcessorCount
$previous = @{}
$rows = New-Object System.Collections.Generic.List[object]
$end = (Get-Date).AddMinutes($Minutes)

function Read-Sample([int]$id) {
  $p = Get-Process -Id $id -ErrorAction SilentlyContinue
  if (-not $p) { return $null }
  try { $cpu = $p.TotalProcessorTime.TotalSeconds } catch { $cpu = $null }
  return @{ Process = $p; Cpu = $cpu; At = Get-Date }
}

foreach ($id in $ProcessIds) {
  $s = Read-Sample $id
  if ($s) { $previous[$id] = $s } else { Write-Warning "Process $id not found." }
}
Write-Host "Sampling $($ProcessIds -join ', ') every $Seconds s for $Minutes min -> $OutFile"
while ((Get-Date) -lt $end) {
  Start-Sleep -Seconds $Seconds
  foreach ($id in $ProcessIds) {
    $s = Read-Sample $id
    $row = [ordered]@{ Time = (Get-Date).ToString('o'); Pid = $id; Name = ''; CpuPercentOfMachine = ''; CpuPercentOfOneCore = ''; WorkingSetMB = ''; PrivateMB = ''; Note = '' }
    if (-not $s) { $row.Note = 'not running'; $rows.Add([pscustomobject]$row); continue }
    $p = $s.Process
    $row.Name = $p.ProcessName
    $row.WorkingSetMB = [math]::Round($p.WorkingSet64 / 1MB, 1)
    $row.PrivateMB = [math]::Round($p.PrivateMemorySize64 / 1MB, 1)
    $prev = $previous[$id]
    if ($null -eq $s.Cpu) { $row.Note = 'access denied (run elevated for CPU)' }
    elseif ($prev -and $null -ne $prev.Cpu) {
      $elapsed = ($s.At - $prev.At).TotalSeconds
      if ($elapsed -gt 0) {
        $oneCore = 100 * ($s.Cpu - $prev.Cpu) / $elapsed
        $row.CpuPercentOfOneCore = [math]::Round($oneCore, 2)
        $row.CpuPercentOfMachine = [math]::Round($oneCore / $cores, 2)
      }
    }
    $previous[$id] = $s
    $rows.Add([pscustomobject]$row)
  }
  # Rewritten every round so an interrupted run still leaves its samples.
  $rows | Export-Csv -Path $OutFile -NoTypeInformation
}
Write-Host "Wrote $($rows.Count) samples to $OutFile"
