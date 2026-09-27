# Reports what is under a screenshot-frame point before it is clicked: the top-level window and
# its process (Win32 hit test, which is what a real click follows), the UI Automation element at
# that point, and the cursor position. Frame coordinates are the 1456-wide computer-use frame.
param([double]$X, [double]$Y, [string]$Log)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms, WindowsBase
Add-Type -Namespace P -Name U -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
[DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
[DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint flags);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
[DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
[DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT p);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern IntPtr GetCapture();
[DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v);
'@
# Physical pixels throughout, as UI Automation reports them.
[void][P.U]::SetProcessDpiAwarenessContext([IntPtr](-4))
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$scale = $screen.Width / 1456.0
$pt = New-Object P.U+POINT; $pt.X = [int]($X * $scale); $pt.Y = [int]($Y * $scale)
$h = [P.U]::WindowFromPoint($pt); $root = [P.U]::GetAncestor($h, 2)
$procId = 0; [void][P.U]::GetWindowThreadProcessId($root, [ref]$procId)
$cls = New-Object System.Text.StringBuilder 256; [void][P.U]::GetClassName($root, $cls, 256)
$fgPid = 0; [void][P.U]::GetWindowThreadProcessId([P.U]::GetForegroundWindow(), [ref]$fgPid)
$uia = try { $e = [Windows.Automation.AutomationElement]::FromPoint((New-Object Windows.Point $pt.X, $pt.Y)); "$($e.Current.ControlType.ProgrammaticName) '$($e.Current.Name)' enabled=$($e.Current.IsEnabled) pid=$($e.Current.ProcessId)" } catch { "uia error: $($_.Exception.Message)" }
$line = '{0:HH:mm:ss.fff} frame({1},{2}) phys({3},{4}) top-level pid={5} ({6}) class={7} | foreground pid={8} | uia: {9}' -f (Get-Date), $X, $Y, $pt.X, $pt.Y, $procId, (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName, $cls, $fgPid, $uia
$line
if ($Log) { Add-Content -LiteralPath $Log -Value $line }
