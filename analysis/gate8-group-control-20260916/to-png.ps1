$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$n = 0
Get-ChildItem (Join-Path $PSScriptRoot '*.bmp') | ForEach-Object {
  $img = [System.Drawing.Image]::FromFile($_.FullName)
  $png = [System.IO.Path]::ChangeExtension($_.FullName, '.png')
  $img.Save($png, [System.Drawing.Imaging.ImageFormat]::Png)
  $img.Dispose()
  $n++
}
"converted=$n"
