# iMouse 2.0 - local console host
#
# Serves console/index.html and proxies /api/* through to the iMouse kernel on
# 127.0.0.1:9911. The proxy exists for one reason: the kernel sends no CORS
# headers, so a browser page loaded from disk cannot read its JSON. Serving the
# page and the API from one origin removes the problem entirely.
#
# Windows PowerShell 5.1 compatible. No admin rights and no installs required.
# Nothing is sent to any phone except the commands the page itself issues.

[CmdletBinding()]
param(
    [int]$Port = 8777,
    [string]$Kernel = 'http://127.0.0.1:9911',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$page = Join-Path $root 'index.html'
if (-not (Test-Path -LiteralPath $page)) { throw "index.html was not found next to serve.ps1 ($page)." }

# Fail early and clearly if the kernel is not up, rather than showing an empty console.
try {
    $probe = [System.Net.WebRequest]::Create("$Kernel/api/config/usb/get")
    $probe.Timeout = 5000
    $probe.GetResponse().Close()
    Write-Host "Kernel reachable at $Kernel" -ForegroundColor Green
}
catch {
    Write-Host "WARNING: could not reach the iMouse kernel at $Kernel." -ForegroundColor Yellow
    Write-Host "         Start iMouse XP (the iMouseService kernel) and reload the page." -ForegroundColor Yellow
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://127.0.0.1:$Port/")
try { $listener.Start() }
catch { throw "Could not listen on port $Port. Another program may be using it. Try -Port 8778." }

$url = "http://127.0.0.1:$Port/"
Write-Host ""
Write-Host "  iMouse 2.0 console  ->  $url" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C in this window to stop." -ForegroundColor DarkGray
Write-Host ""
if (-not $NoBrowser) { Start-Process $url | Out-Null }

function Write-Bytes {
    param($Response, [byte[]]$Bytes, [string]$ContentType, [int]$Status = 200)
    $Response.StatusCode = $Status
    $Response.ContentType = $ContentType
    # The live view refetches constantly; caching would freeze the picture.
    $Response.Headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    $Response.ContentLength64 = $Bytes.Length
    $Response.OutputStream.Write($Bytes, 0, $Bytes.Length)
}

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response
        try {
            $path = $request.Url.AbsolutePath
            if ($path -eq '/' -or $path -eq '/index.html') {
                $bytes = [System.IO.File]::ReadAllBytes($page)
                Write-Bytes $response $bytes 'text/html; charset=utf-8'
            }
            elseif ($path -like '/api/*') {
                $target = $Kernel + $request.Url.PathAndQuery
                $upstream = [System.Net.HttpWebRequest]::Create($target)
                $upstream.Method = $request.HttpMethod
                $upstream.Timeout = 15000
                $upstream.ReadWriteTimeout = 15000
                $upstream.Proxy = $null
                if ($request.HttpMethod -eq 'POST') {
                    $upstream.ContentType = $request.ContentType
                    $body = New-Object System.IO.MemoryStream
                    $request.InputStream.CopyTo($body)
                    $payload = $body.ToArray()
                    $upstream.ContentLength = $payload.Length
                    $stream = $upstream.GetRequestStream()
                    $stream.Write($payload, 0, $payload.Length)
                    $stream.Close()
                }
                $reply = $upstream.GetResponse()
                $buffer = New-Object System.IO.MemoryStream
                $reply.GetResponseStream().CopyTo($buffer)
                $reply.Close()
                Write-Bytes $response $buffer.ToArray() $reply.ContentType
            }
            else {
                Write-Bytes $response ([Text.Encoding]::UTF8.GetBytes('Not found')) 'text/plain; charset=utf-8' 404
            }
        }
        catch {
            $message = "Proxy error: " + $_.Exception.Message
            try { Write-Bytes $response ([Text.Encoding]::UTF8.GetBytes($message)) 'text/plain; charset=utf-8' 502 } catch { }
        }
        finally { try { $response.OutputStream.Close() } catch { } }
    }
}
finally {
    try { $listener.Stop(); $listener.Close() } catch { }
    Write-Host "Console host stopped. iMouse XP and the phones were left running." -ForegroundColor DarkGray
}
