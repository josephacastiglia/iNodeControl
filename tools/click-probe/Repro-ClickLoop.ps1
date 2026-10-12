<#
.SYNOPSIS
  Repeats the console click sequence that intermittently failed on 27 Sep and detects a click that
  does nothing: close the drawer, Reset, tap the preview, wait, click Controls, then check through
  UI Automation that the Controls drawer opened. Clicks are ordinary OS mouse input (SendInput).

.DESCRIPTION
  Use only against a candidate connected to the mock kernel (input-cleanup-harness --serve).
  UI Automation is used to read state, never to click. Coordinates are in the 1456-wide
  computer-use frame of a maximized console on the primary display.
  Stops at the first failure and prints the window's GUI-thread state; exit code 1 if one occurred.

  CAVEAT (27 Sep): from the Claude Code agent's shell, SendInput returns success but injects
  nothing (a relative move leaves the cursor still; Watch-MouseButtons sees no event). Every
  "failure" this script reports from that shell is that artifact, not the console. Run it from an
  ordinary interactive session, and confirm with Watch-MouseButtons that its clicks are seen.
#>
param(
    [Parameter(Mandatory)][int]$ProcessId,
    [int]$Iterations = 30,
    [int[]]$WaitAfterTapMs = @(0, 150, 400, 1500, 3000),
    [string]$Log
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
Add-Type -Namespace RL -Name U -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx, dy; public uint mouseData, dwFlags, time; public IntPtr extra; }
[StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public MOUSEINPUT mi; }
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
[StructLayout(LayoutKind.Sequential)] public struct GUITHREADINFO { public int cbSize; public uint flags; public IntPtr hwndActive, hwndFocus, hwndCapture, hwndMenuOwner, hwndMoveSize, hwndCaret; public RECT rcCaret; }
[DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] inputs, int size);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v);
[DllImport("user32.dll")] public static extern bool GetGUIThreadInfo(uint tid, ref GUITHREADINFO info);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
[DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint flags);
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
'@
[void][RL.U]::SetProcessDpiAwarenessContext([IntPtr](-4))
$scale = 3840 / 1456.0
$size = [Runtime.InteropServices.Marshal]::SizeOf([type][RL.U+INPUT])
function Note([string]$text) { $line = '{0:HH:mm:ss.fff} {1}' -f (Get-Date), $text; $line; if ($Log) { Add-Content -LiteralPath $Log -Value $line } }
function Click([double]$x, [double]$y, [string]$what) {
    # Refuse to click unless the window under the point belongs to the target process: another
    # console (the installed one on the real rack) may be on top.
    $pt = New-Object RL.U+POINT; $pt.X = [int]($x * $scale); $pt.Y = [int]($y * $scale)
    $owner = [uint32]0; [void][RL.U]::GetWindowThreadProcessId([RL.U]::GetAncestor([RL.U]::WindowFromPoint($pt), 2), [ref]$owner)
    if ($owner -ne $ProcessId) { Note "ABORT: $what at ($x,$y) would land on PID $owner, not $ProcessId"; exit 2 }
    [void][RL.U]::SetCursorPos($pt.X, $pt.Y); Start-Sleep -Milliseconds 40
    $down = New-Object RL.U+INPUT; $down.mi.dwFlags = 2; $up = New-Object RL.U+INPUT; $up.mi.dwFlags = 4
    $a = [RL.U]::SendInput(1, @($down), $size); Start-Sleep -Milliseconds 50; $b = [RL.U]::SendInput(1, @($up), $size)
    if ($a -ne 1 -or $b -ne 1) { throw "SendInput failed for $what" }
}
$window = [Windows.Automation.AutomationElement]::RootElement.FindFirst([Windows.Automation.TreeScope]::Children,
    (New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::ProcessIdProperty, $ProcessId)))
$sendText = New-Object Windows.Automation.PropertyCondition([Windows.Automation.AutomationElement]::NameProperty, 'Send text')
function DrawerOpen { $b = $window.FindFirst([Windows.Automation.TreeScope]::Descendants, $sendText); [bool]($b -and -not $b.Current.IsOffscreen) }
function ThreadState {
    $p = Get-Process -Id $ProcessId; $owner = [uint32]0; $tid = [RL.U]::GetWindowThreadProcessId($p.MainWindowHandle, [ref]$owner)
    $i = New-Object RL.U+GUITHREADINFO; $i.cbSize = [Runtime.InteropServices.Marshal]::SizeOf($i); [void][RL.U]::GetGUIThreadInfo($tid, [ref]$i)
    $fg = [uint32]0; [void][RL.U]::GetWindowThreadProcessId([RL.U]::GetForegroundWindow(), [ref]$fg)
    'main={0} active={1} focus={2} capture={3} flags=0x{4:X} foregroundPid={5} responding={6}' -f $p.MainWindowHandle, $i.hwndActive, $i.hwndFocus, $i.hwndCapture, $i.flags, $fg, $p.Responding
}
$failures = 0
for ($n = 1; $n -le $Iterations; $n++) {
    foreach ($wait in $WaitAfterTapMs) {
        if (DrawerOpen) { Click 1432 63 'drawer Close'; Start-Sleep -Milliseconds 500 }
        Click 353 85 'Reset'; Start-Sleep -Milliseconds 700
        Click 214 151 'preview tap'; Start-Sleep -Milliseconds $wait
        Click 82 30 'Controls'; Start-Sleep -Milliseconds 800
        if (DrawerOpen) { continue }
        Start-Sleep -Milliseconds 1200
        if (DrawerOpen) { Note "iteration $n wait $wait ms: drawer opened late (over 800 ms)"; continue }
        $failures++
        Note "FAILURE iteration $n wait $wait ms: Controls click did not open the drawer. $(ThreadState)"
        exit 1
    }
    Note "iteration $n passed ($($WaitAfterTapMs -join '/') ms waits)"
}
Note "no failure in $Iterations iterations"
exit 0
