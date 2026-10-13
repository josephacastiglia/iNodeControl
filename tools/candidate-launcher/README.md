# Prepare and launch a recorded console candidate

This developer tool prepares an isolated copy of a console build. It never starts
the kernel or receivers, modifies the installed app, or changes a shortcut.
Normal use requires PowerShell 5.1 or 7 and the console's .NET 8 Desktop runtime.

## Check and prepare offline

Use absolute paths to the exact build, its `tools/build_manifest.py` record, the
matching source checkout, and a new run folder. The address requires an explicit
port. A profile is generated with pointer hover tracking off; operator settings
are never copied into it.

```powershell
$candidate = @{
    ConsoleExe = 'C:\review\console\iMouse2.exe'
    BuildManifest = 'C:\review\console-manifest.json'
    SourceRoot = 'C:\review\source-checkout'
    RunDir = 'C:\review\runs\candidate 01'
    Address = 'http://127.0.0.1:9913'
}
.\tools\candidate-launcher\Start-iMouse2Candidate.ps1 @candidate -CheckOnly
.\tools\candidate-launcher\Start-iMouse2Candidate.ps1 @candidate -PrepareOnly
```

Paths above are examples. `-CheckOnly` is also the default. It reads and checks
files without creating a folder, contacting services, or starting a process.
`-PrepareOnly` copies the five recorded console runtime files into `RunDir\bin`,
writes `RunDir\data\settings.json`, and creates `prepared.json`. It also stays
offline. Keep immutable review packages intact; the copies receive later logs.

Existing unrecorded folders, release paths, shared operator-settings paths,
changed binaries/source, reparse points, and altered prepared profiles are
refused. Rechecking/repreparing an intact prepared run does not rewrite settings.
After any launch attempt, preserve that run and prepare a new one. Do not remove
`launch.json` to bypass this rule. The legacy `-DataDir` spelling is an alias for
**RunDir**: settings now live in its **data** child, not at the supplied path.

Checksums establish consistency with the trusted local record, not a signature
or independent proof of how the binary was compiled. The recorded source must
support `--validate-startup`, so an older app cannot accidentally open normally
when asked to run a capability it does not have.

## Start only during the agreed window

Add `-Launch` to the same parameters only when the console test window is
authorized and the intended service is already running. The launcher first runs
the copied console's no-window startup check, verifying its DLL, data folder and
address, then reads kernel status before opening the actual console.

Starting a console can affect focus. The launch result means a process was
started; it does not establish GUI usability, correct phone selection, lease
ownership, live video, or acceptance. Check those separately before input. This
launcher does not enforce a C24C-only input policy: keep other phones unchecked
and follow the authorized scope. Hover tracking off prevents hover acquisition;
it does not prevent deliberate control actions.

`launch.json` records the probe, proxy and console PIDs, outcome and any cleanup
failure. A failed launch is never automatically retried. A probe that fails to
exit is reported by PID; it is not force-killed. Closing the console normally and
restoring the working app remain part of the coordinated test/restoration plan.

## Optional fault proxy

Add `ViaProxy = $true`, `ProxyExe`, `ProxyManifest`, and an explicit loopback HTTP
`ProxyListen` (for example `http://localhost:9923/`) to the parameters. `Address`
remains the actual upstream kernel. Preparation copies five proxy runtime files
into the run folder and puts the proxy address in the isolated console profile.
The proxy must have the new `--ready-file` support recorded in its source/build.

At launch, any listener on the proxy port is a conflict. After starting its own
proxy, the launcher requires its atomic readiness record and PID response header,
then compares the returned receiver IDs and available kernel build/process
identity with upstream. The PID check also rejects an HTTP.sys prefix answering
directly while bypassing the proxy. It is a local routing check, not authentication
against a malicious process.

If startup fails before the console opens, only the proxy started by this attempt
is sent to the existing path-checked graceful-stop helper. No force-kill is used;
unconfirmed cleanup leaves its identity in the failure record. A successful
launch leaves the proxy available for the test; stop that recorded process as
part of restoration. The proxy starts unarmed. Using its fault controls requires
the relevant test authorization. It is not a video-latency acceptance route.

## Offline validation

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/candidate-launcher/Test-CandidateLauncher.ps1
pwsh.exe -NoProfile -File tools/candidate-launcher/Test-CandidateLauncher.ps1
dotnet C:\review\proxy\InputFaultProxy.dll --self-test
```

Launcher tests use synthetic files and fake process/HTTP adapters. They do not
execute the fixture binaries or connect to a service. The proxy self-test writes
only temporary readiness files; it opens no listener. Physical launch, cleanup
and acceptance remain separate checks.
