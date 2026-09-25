$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Get-ChildItem (Join-Path $PSScriptRoot '*.bmp') | ForEach-Object {
  $fs = [System.IO.File]::Open($_.FullName, 'Open', 'Read', 'Read')
  try {
    $img = New-Object System.Drawing.Bitmap $fs
    $png = [System.IO.Path]::ChangeExtension($_.FullName, '.png')
    $img.Save($png, [System.Drawing.Imaging.ImageFormat]::Png)
    $img.Dispose()
    Write-Output $png
  } finally { $fs.Dispose() }
}
