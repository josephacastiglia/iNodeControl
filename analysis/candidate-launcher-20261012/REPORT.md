# Recorded candidate launcher

12 October 2026. Offline preparation only. No desktop control, live console
launch, rack service request, phone input, kernel/receiver restart or deployment.

## Result

The existing candidate launcher now defaults to a read-only build/configuration
check. Preparation copies only recorded runtime files into a new run folder and
writes an isolated profile with explicit endpoint and hover tracking off. It
preserves changed or previously used folders instead of overwriting them. The
installed console, shortcuts and operator profile remain separate.

Explicit launch first validates the copied console with its no-window mode,
then checks the existing kernel's ownership protocol before opening a window.
Optional proxy startup requires a free port, atomic readiness receipt, exact
proxy PID response header and matching upstream status. This rejects the shared
HTTP.sys-prefix bypass previously encountered in testing. Failure records keep
process identities; only this attempt's proxy is eligible for graceful cleanup.
No force-kill, retry, automatic kernel start or receiver start was added.

The fault proxy publishes its receipt only after listener registration. Its
header identifies the responding proxy; it is not authentication against hostile
local software. The launcher does not constrain which phone a later operator
chooses, or grant approval for input. See `tools/candidate-launcher/README.md`.

## Validation

| Check | Result and scope |
|---|---|
| Windows PowerShell 5.1 launcher suite | 49 passed, all process/network adapters simulated |
| PowerShell 7 launcher suite | Same 49 passed, independent runtime |
| Real HTTP response parsing | Fake HttpClient handler; exact route, PID header, missing/malformed header and redirect handling |
| Proxy startup receipt tests | 2 passed; atomic creation and existing-record preservation, no listener |
| Proxy Release build | Zero warnings/errors; 4 source inputs and 5 build files recorded/verified |
| Actual combined console no-window probe | Exit 0, valid, disconnected, settingsWritten false; DLL hash/profile/address match |
| Fresh direct and proxy preparations | 7 and 12 files respectively; repeated read-only verification passed; neither launched |
| Existing console/kernel build manifests | All recorded source/artifact bytes still match |
| Installed kernel, console and receiver | Recorded SHA-256 unchanged |
| Operator settings during final preparations | Content hash unchanged |

Regression coverage includes changed source/binary bytes, old builds lacking the
probe, unsafe/overlapping paths, altered profiles, extra DLLs, reuse after launch,
occupied ports, wrong proxy identity/routing, service failure, startup refusal
and unconfirmed cleanup. The cleanup adapter verifies exact PID/path, a hidden
helper and explicit script execution policy; it does not signal a real process.

The PowerShell 5.1 IPv6 representation differed from PowerShell 7; endpoint
normalization now uses `IPAddress` for both. The added HTTP fixture initially
assigned null to a C# string property, which PowerShell converted to empty text,
accidentally testing an empty header instead of an absent one. An explicit
include-header flag corrected the fixture. PowerShell 7 also required its default
compiler reference set instead of the .NET Framework-specific reference list.
These failures were offline; no live request escaped the test adapter.

## Exact prepared copies

`prepared-runs.json` identifies the fresh folders under `output/candidate-runs/`:

- `combined-ready-20261012`: direct endpoint `http://127.0.0.1:9913`.
- `combined-proxy-ready-20261012`: proxy endpoint `http://localhost:9923`, upstream
  `http://127.0.0.1:9913`.

Both contain console DLL `620093229ac345c640b3d5173d7b1000fc82887435b16a88ecf30c19830d82b7`.
Their source/build records are the preceding console-diagnostics manifests, not
newly compiled product binaries. The proxy has its own `proxy-manifest.json`.

The separate `offline validation 20261012` copy ran only `--validate-startup`.
Its generated report makes it evidence, not a reusable pristine run folder.
`actual-validation.json` preserves that result. No prepared copy was promoted.

## Remaining limits

Live launch and graceful cleanup still require their coordinated test window.
This work does not prove actual console clicks, receiver configuration, phone
selection, exact typing, displayed video/latency, or full-rack acceptance. The
optional proxy does not provide a physical video acceptance path. Checksum
validation establishes consistency with a trusted local record, not independent
build attestation or a signature. No release gate is newly signed off.

Next offline work is the combined kernel's candidate configuration and readiness
checks using existing tools. The deferred first-space investigation stays deferred.
