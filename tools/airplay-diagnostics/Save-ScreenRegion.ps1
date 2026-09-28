<#
.SYNOPSIS
  Saves a timestamped JPEG of one screen region at a fixed interval until a stop time. Used to
  record a webcam view of the phones' Screen Mirroring lists during a trial. Read-only: it only
  copies screen pixels; it clicks nothing.
  Region is in physical pixels (X, Y, Width, Height).
#>
param([int]$X, [int]$Y, [int]$Width, [int]$Height, [int]$IntervalSeconds = 10, [datetime]$Until, [string]$OutDir)
Add-Type -AssemblyName System.Drawing
Add-Type -Namespace SR -Name U -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr v);'
[void][SR.U]::SetProcessDpiAwarenessContext([IntPtr](-4))
New-Item -ItemType Directory -Force $OutDir | Out-Null
$codec = [Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object MimeType -eq 'image/jpeg'
$params = New-Object Drawing.Imaging.EncoderParameters 1
$params.Param[0] = New-Object Drawing.Imaging.EncoderParameter ([Drawing.Imaging.Encoder]::Quality), 80L
while ((Get-Date) -lt $Until) {
    $t = Get-Date
    $bmp = New-Object Drawing.Bitmap $Width, $Height
    $g = [Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($X, $Y, 0, 0, $bmp.Size)
    $g.Dispose()
    $bmp.Save((Join-Path $OutDir ('{0:HHmmss}.jpg' -f $t)), $codec, $params)
    $bmp.Dispose()
    $wait = $IntervalSeconds * 1000 - ((Get-Date) - $t).TotalMilliseconds
    if ($wait -gt 0) { Start-Sleep -Milliseconds ([int]$wait) }
}
