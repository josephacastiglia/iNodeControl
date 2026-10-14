# iMouse candidate: offline review bundle

13 October 2026. This bundle combines the preserved receiver fleet shutdown kernel with the
latest console: bounded image downloads, opt-in response timing, active-service
connection hints and the earlier input/recovery repairs.
It is **not installed or approved for release**. The native receiver/runtime
retain their previously recorded bytes. Both managed components have offline
evidence; this combined package has no physical acceptance.

## Verify without launching

From this folder, using Python 3.11 or later:

```powershell
python verify_package.py verify --bundle .
python dependencies/receiver-runtime/verify_runtime.py verify --bundle dependencies/receiver-runtime
```

Both commands inspect files only. Neither starts a window, service or receiver.
Checksums establish consistency with the embedded records, not a signature or
proof of physical behavior. Keep this package immutable; generate reports and
runtime settings only in separate copies. Rebuild under a new name after any
integrity failure rather than repairing a package in place.

## Contents

| Folder/file | Purpose |
|---|---|
| `payload/console` and `payload/kernel` | Recorded .NET executable/assembly/symbol/runtime files, without operator settings |
| `payload/receiver/uxplay.exe` | Preserved native receiver build |
| `dependencies/receiver-runtime` | Audited libraries, scanner/plugins, package receipts and available notices for local tests |
| `source` and `provenance` | Exact project/native source and build records |
| `source/launcher/Open iMouse 2.0.ps1.txt` | Launcher source as inert text; not a runnable entry point or an isolated candidate launcher |
| `package.json` | Complete inventory and unresolved release requirements |
| [OPERATOR-GUIDE.md](OPERATOR-GUIDE.md) | Candidate behavior and recovery instructions; these do not authorize a test window |

The launcher source retains the startup-refusal reporting repair. Its fixed paths
refer to a future reviewed release layout; they must not be treated as a way to
start this package. No executable start script or live phone configuration is
included. Source fixtures and symbols are evidence, not live settings. Review
local paths/device identifiers before publishing any of these files.

## Separate preparation

The source checkout's `analysis/combined-timing-package-20261013/prepare_candidate.py`
records a separate C24C-only kernel configuration and a console profile with
explicit endpoint, isolated settings and hover tracking off. It copies from this
verified package and runs only the binaries' no-window `--validate-startup`
modes. Console validation uses a separate disposable copy so its generated
report cannot invalidate the intended prepared run. A final launcher `-CheckOnly`
must pass. This source script is intentionally not an executable in the bundle.

The adjacent preparation report records exact paths and hashes. It does not
establish free ports, current process identity, phone ownership, physical binding,
mirroring, native compatibility on a clean PC or UI behavior. Recheck those in a
coordinated window before starting anything. C241 is not in that candidate.

## Acceptance and restoration remain required

The managed components require .NET 8; the console requires Windows Desktop.
Native notices/source obligations and clean-PC redistribution checks remain
open. The included runtime is for local tests, not a cleared installer.

Startup file validation is distinct from loading native libraries and receiving
real video. No offline test here closes Home/typing/App Switcher defects,
varied-target accuracy, actual console latency/video, receiver recasting,
19-phone scale or final endurance. Typing remains deferred.

A future kernel swap needs its agreed interruption/restoration window. Preserve
the installed binaries, configuration, settings and exact launch commands first.
Stop only verified candidate processes, restore through the original launcher,
and confirm both phones are usable afterward. Receiver rediscovery can require
operator help. Do not alter installed shortcuts, restart the rack, or promote
this bundle as part of integrity verification or preparation.

## Timing preparation is a separate workload

The prepared run is a C24C-only smoke profile; it is not the two-stream Gate 6
workload. The Gate 6 runner now requires both declared streams and explicit
candidate path, PID, DLL hash and isolated settings. Its UIA and bitmap timeline
measure components of the response, not physical-click-to-correct-display
acceptance. The timeline stays off unless IMOUSE_RESPONSE_TIMING=1 is supplied
to a future candidate process; no system-wide environment change was made.
