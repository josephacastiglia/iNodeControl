<#
.SYNOPSIS
  Sends one ordinary left click (SendInput) at a frame point while a low-level mouse hook
  (WH_MOUSE_LL, own thread) records what the system input stream carries. Read-only observation
  plus the one click; it never blocks input (always calls the next hook).
#>
param([double]$X = -1, [double]$Y = -1, [int]$ExpectPid = 0, [int]$WatchSeconds = 0, [string]$Out)
Add-Type -TypeDefinition @'
using System; using System.Collections.Concurrent; using System.Runtime.InteropServices; using System.Threading;
public static class MouseSpy {
  delegate IntPtr Proc(int code, IntPtr w, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] struct MSLL { public int x, y; public uint data, flags, time; public IntPtr extra; }
  [StructLayout(LayoutKind.Sequential)] struct MSG { public IntPtr h; public uint m; public IntPtr w, l; public uint t; public int x, y; }
  [DllImport("user32.dll")] static extern IntPtr SetWindowsHookEx(int id, Proc p, IntPtr mod, uint tid);
  [DllImport("user32.dll")] static extern bool UnhookWindowsHookEx(IntPtr h);
  [DllImport("user32.dll")] static extern IntPtr CallNextHookEx(IntPtr h, int c, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] static extern int GetMessage(out MSG m, IntPtr h, uint a, uint b);
  [DllImport("user32.dll")] static extern bool PostThreadMessage(uint tid, uint m, IntPtr w, IntPtr l);
  [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
  [DllImport("kernel32.dll")] static extern IntPtr GetModuleHandle(string n);
  public static readonly ConcurrentQueue<string> Events = new ConcurrentQueue<string>();
  static Proc _keep; static uint _tid; static IntPtr _hook;
  public static void Start() {
    var ready = new ManualResetEventSlim();
    var t = new Thread(() => {
      _tid = GetCurrentThreadId();
      _keep = (c, w, l) => {
        if (c >= 0) { int m = w.ToInt32(); if (m == 0x201 || m == 0x202) { var s = (MSLL)Marshal.PtrToStructure(l, typeof(MSLL));
          Events.Enqueue(DateTime.Now.ToString("HH:mm:ss.fff") + (m == 0x201 ? " LL LBUTTONDOWN" : " LL LBUTTONUP") + " at (" + s.x + "," + s.y + ") injected=" + ((s.flags & 1) != 0)); } }
        return CallNextHookEx(IntPtr.Zero, c, w, l); };
      _hook = SetWindowsHookEx(14, _keep, GetModuleHandle(null), 0);
      ready.Set(); MSG msg; while (GetMessage(out msg, IntPtr.Zero, 0, 0) > 0) { }
      UnhookWindowsHookEx(_hook);
    }) { IsBackground = true };
    t.Start(); ready.Wait();
  }
  public static void Stop() { PostThreadMessage(_tid, 0x12, IntPtr.Zero, IntPtr.Zero); }
}
'@
Add-Type -Namespace WM -Name U -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx, dy; public uint mouseData, dwFlags, time; public IntPtr extra; }
[StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public MOUSEINPUT mi; }
[StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
[DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] inputs, int size);
[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
[DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v);
[DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
[DllImport("user32.dll")] public static extern IntPtr GetAncestor(IntPtr h, uint f);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
'@
[void][WM.U]::SetProcessDpiAwarenessContext([IntPtr](-4))
if ($WatchSeconds -gt 0) {
    # Watch only: record every button event in the system stream for a while, click nothing.
    [MouseSpy]::Start(); "{0:HH:mm:ss.fff} watching {1} s" -f (Get-Date), $WatchSeconds
    $end = (Get-Date).AddSeconds($WatchSeconds); $e = $null
    while ((Get-Date) -lt $end) { while ([MouseSpy]::Events.TryDequeue([ref]$e)) { $e; if ($Out) { Add-Content -LiteralPath $Out -Value $e } }; Start-Sleep -Milliseconds 100 }
    [MouseSpy]::Stop(); "{0:HH:mm:ss.fff} done" -f (Get-Date); exit 0
}
$s = 3840 / 1456.0; $pt = New-Object WM.U+POINT; $pt.X = [int]($X * $s); $pt.Y = [int]($Y * $s)
$owner = [uint32]0; [void][WM.U]::GetWindowThreadProcessId([WM.U]::GetAncestor([WM.U]::WindowFromPoint($pt), 2), [ref]$owner)
if ($ExpectPid -and $owner -ne $ExpectPid) { "ABORT: point is over PID $owner, not $ExpectPid"; exit 2 }
[MouseSpy]::Start()
[void][WM.U]::SetCursorPos($pt.X, $pt.Y); Start-Sleep -Milliseconds 60
$size = [Runtime.InteropServices.Marshal]::SizeOf([type][WM.U+INPUT])
$down = New-Object WM.U+INPUT; $down.mi.dwFlags = 2; $up = New-Object WM.U+INPUT; $up.mi.dwFlags = 4
"{0:HH:mm:ss.fff} SendInput down={1}" -f (Get-Date), [WM.U]::SendInput(1, @($down), $size)
Start-Sleep -Milliseconds 60
"{0:HH:mm:ss.fff} SendInput up={1}" -f (Get-Date), [WM.U]::SendInput(1, @($up), $size)
Start-Sleep -Milliseconds 400
[MouseSpy]::Stop()
$e = $null; while ([MouseSpy]::Events.TryDequeue([ref]$e)) { $e }
