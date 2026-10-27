param([Parameter(Mandatory=$true)][string]$ImagePath, [string]$ControlImagePath)
# Windows PowerShell 5.1 WinRT bridge. Reads local images; no desktop/input APIs.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await-Result($Operation, [Type]$ResultType) {
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (-not $task.Wait(15000)) { throw 'Image recognition timed out.' }
    return $task.Result
}
$language = New-Object Windows.Globalization.Language('en-US')
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($language)
if ($null -eq $engine) { throw 'English Windows OCR language is unavailable.' }
function Read-ImageText([string]$InputPath) {
$path = [System.IO.Path]::GetFullPath($InputPath)
if (-not [System.IO.File]::Exists($path)) { throw 'Image file missing.' }
if ((Get-Item -LiteralPath $path).Length -gt 16777216) { throw 'Image exceeds 16 MiB.' }
$lockedFile = $null
$stream = $null
$bitmap = $null
try {
    # Hash and recognize the same file while excluding writers and replacement.
    # FileShare.Read permits the WinRT decoder's second read handle, not modification.
    $lockedFile = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
    if ($lockedFile.Length -gt 16777216) { throw 'Image exceeds 16 MiB.' }
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { $imageHash = ([BitConverter]::ToString($hasher.ComputeHash($lockedFile))).Replace('-', '').ToLowerInvariant() }
    finally { $hasher.Dispose() }
    $file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
    $stream = Await-Result ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $limit = [Windows.Media.Ocr.OcrEngine]::MaxImageDimension
    if ($decoder.PixelWidth -gt $limit -or $decoder.PixelHeight -gt $limit) { throw 'Image dimensions exceed OCR support.' }
    $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, [Windows.Graphics.Imaging.BitmapAlphaMode]::Ignore)) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result = Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
    $lines = @($result.Lines | ForEach-Object {
        $words = @($_.Words | ForEach-Object {
            @{text=$_.Text; x=$_.BoundingRect.X; y=$_.BoundingRect.Y; width=$_.BoundingRect.Width; height=$_.BoundingRect.Height}
        })
        @{text=$_.Text; words=$words}
    })
    return @{provider='windows-ocr'; language='en-US'; imageSha256=$imageHash; width=$bitmap.PixelWidth; height=$bitmap.PixelHeight; textAngle=$result.TextAngle; lines=$lines}
}
finally {
    if ($null -ne $bitmap) { $bitmap.Dispose() }
    if ($null -ne $stream) { $stream.Dispose() }
    if ($null -ne $lockedFile) { $lockedFile.Dispose() }
}
}
$recognized = Read-ImageText $ImagePath
if ($ControlImagePath) { $recognized.control = Read-ImageText $ControlImagePath }
$recognized | ConvertTo-Json -Depth 10 -Compress
