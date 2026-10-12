<#
.SYNOPSIS
  Saves a timestamped JPEG of one window's content (PrintWindow, works while the window is
  covered, not while minimized) at a fixed interval until a stop time, optionally cropped.
  Used to record the Camera app's webcam view of the phones. Read-only: clicks nothing.
#>
param([string]$ProcessName = 'ApplicationFrameHost', [string]$Title = 'Camera', [int]$IntervalSeconds = 10,
      [datetime]$Until, [string]$OutDir, [int]$CropX = 0, [int]$CropY = 0, [int]$CropW = 0, [int]$CropH = 0)
Add-Type -AssemblyName System.Drawing
Add-Type -Namespace WC -Name U -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
[StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
[DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
[DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v);
'@
[void][WC.U]::SetProcessDpiAwarenessContext([IntPtr](-4))
New-Item -ItemType Directory -Force $OutDir | Out-Null
$codec = [Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object MimeType -eq 'image/jpeg'
$params = New-Object Drawing.Imaging.EncoderParameters 1
$params.Param[0] = New-Object Drawing.Imaging.EncoderParameter ([Drawing.Imaging.Encoder]::Quality), 85L
while ((Get-Date) -lt $Until) {
    $t = Get-Date
    $w = Get-Process $ProcessName -ErrorAction SilentlyContinue | Where-Object MainWindowTitle -eq $Title | Select-Object -First 1
    if (-not $w -or [WC.U]::IsIconic($w.MainWindowHandle)) {
        Add-Content (Join-Path $OutDir 'gaps.txt') ('{0:HH:mm:ss} window {1}' -f $t, $(if ($w) { 'minimized' } else { 'not found' }))
    } else {
        $r = New-Object WC.U+RECT; [void][WC.U]::GetWindowRect($w.MainWindowHandle, [ref]$r)
        $full = New-Object Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
        $g = [Drawing.Graphics]::FromImage($full); $hdc = $g.GetHdc()
        [void][WC.U]::PrintWindow($w.MainWindowHandle, $hdc, 2)
        $g.ReleaseHdc($hdc); $g.Dispose()
        $img = $full
        if ($CropW -gt 0 -and $CropH -gt 0) { $img = $full.Clone((New-Object Drawing.Rectangle $CropX, $CropY, $CropW, $CropH), $full.PixelFormat); $full.Dispose() }
        $img.Save((Join-Path $OutDir ('{0:HHmmss}.jpg' -f $t)), $codec, $params); $img.Dispose()
    }
    $wait = $IntervalSeconds * 1000 - ((Get-Date) - $t).TotalMilliseconds
    if ($wait -gt 0) { Start-Sleep -Milliseconds ([int]$wait) }
}
