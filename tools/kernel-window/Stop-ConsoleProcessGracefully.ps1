<#
.SYNOPSIS
  Sends Ctrl+C to one console process (for example the kernel, started hidden by the release
  launcher) so it runs its own shutdown, then waits for it and its child processes to exit.

.DESCRIPTION
  The kernel stops cleanly only on Ctrl+C: that cancels input, drains key and button releases and
  disposes its receiver fleet, which ends each uxplay receiver it started. A hard kill would leave
  the receivers running, still holding their AirPlay names and ports.

  Refuses unless the process's executable path equals -ExpectedPath. Never kills anything: if the
  process has not exited within -TimeoutSeconds it reports that and exits 3. Children that remain
  are listed, not stopped. Run it in its own PowerShell process (it detaches from its console).

  Exit codes: 0 stopped (children gone), 1 refused, 2 could not attach/signal, 3 still running,
  4 stopped but children remain.
#>
param(
    [Parameter(Mandatory)][int]$ProcessId,
    [Parameter(Mandatory)][string]$ExpectedPath,
    [int]$TimeoutSeconds = 20
)
$ErrorActionPreference = 'Stop'
Add-Type -Namespace KW -Name U -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint pid);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool FreeConsole();
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetConsoleCtrlHandler(IntPtr handler, bool add);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool GenerateConsoleCtrlEvent(uint ctrlEvent, uint groupId);
'@
$target = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId"
if (-not $target) { "PID $ProcessId is not running."; exit 1 }
if (-not $target.ExecutablePath -or ([IO.Path]::GetFullPath($target.ExecutablePath) -ine [IO.Path]::GetFullPath($ExpectedPath))) {
    "Refused: PID $ProcessId is $($target.ExecutablePath), not $ExpectedPath."; exit 1
}
$children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" | Select-Object ProcessId, Name, ExecutablePath)
"{0:HH:mm:ss.fff} stopping PID {1} ({2}); children: {3}" -f (Get-Date), $ProcessId, $target.Name, (($children | ForEach-Object { "$($_.ProcessId) $($_.Name)" }) -join ', ')

[void][KW.U]::FreeConsole()
if (-not [KW.U]::AttachConsole([uint32]$ProcessId)) { "Could not attach to the console of PID $ProcessId (error $([Runtime.InteropServices.Marshal]::GetLastWin32Error()))."; exit 2 }
[void][KW.U]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)       # this helper ignores the Ctrl+C it sends
$sent = [KW.U]::GenerateConsoleCtrlEvent(0, 0)
[void][KW.U]::FreeConsole()
if (-not $sent) { "Ctrl+C could not be sent (error $([Runtime.InteropServices.Marshal]::GetLastWin32Error()))."; exit 2 }

$process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
if ($process -and -not $process.WaitForExit($TimeoutSeconds * 1000)) {
    "{0:HH:mm:ss.fff} PID {1} is still running after {2} s. Nothing was killed." -f (Get-Date), $ProcessId, $TimeoutSeconds; exit 3
}
Start-Sleep -Milliseconds 500
$left = @($children | Where-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
"{0:HH:mm:ss.fff} PID {1} exited; children still running: {2}" -f (Get-Date), $ProcessId, $(if ($left.Count) { ($left | ForEach-Object { "$($_.ProcessId) $($_.Name)" }) -join ', ' } else { 'none' })
if ($left.Count) { exit 4 }
exit 0
