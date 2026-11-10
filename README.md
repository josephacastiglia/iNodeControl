# iMouse 2.0 and the Marketing Farm

A Windows system that drives racks of iPhones from one PC. A kernel sends each phone's input through its
own USB board and shows its screen through its own AirPlay receiver. A desktop console lets an operator
watch and control the phones. The Marketing Farm, on top of both, prepares social-post **drafts** on the
phones and checks them read-only. It never posts, publishes, sends or messages.

## Start here

| If you want | Read |
|---|---|
| What is done and what is left | [MARKETING-SUITE-TRACKER.md](MARKETING-SUITE-TRACKER.md) |
| The rules for working here in parallel, and who has which phone | [LANES.md](LANES.md) |
| When the product counts as finished (the release gates) | [FINISH-CRITERIA.md](FINISH-CRITERIA.md) |
| To start the rack, connect phones, run a window, stop | [the rack runbook](rack/README.md) |
| To install the farm on a PC, update it, roll back | [docs/INSTALL-FARM.md](docs/INSTALL-FARM.md) |
| To open and use the desktop console | [OPEN-THIS-APP.md](OPEN-THIS-APP.md), [docs/OPERATOR-GUIDE.md](docs/OPERATOR-GUIDE.md) |
| What typing and keys do on a phone, and what is still open | [KEYBOARD-SPEC.md](KEYBOARD-SPEC.md) |
| Something that used to be here: old documents, evidence, other branches, private folders | [docs/EVIDENCE.md](docs/EVIDENCE.md) |

## What is where

| Path | What |
|---|---|
| `src/iMouse.Kernel/` | The kernel (C#, .NET 8): loopback HTTP API, input leases per phone, the HID boards, the AirPlay receivers and their frames |
| `src/iMouse.Console/` | The operator's console (WPF) |
| `tools/imouse_farm_server.py`, `tools/farm_*.py` | The farm (Python 3.11): one backend per window, a draft flow and a read-only verifier per format, the scheduler |
| `rack/` | The rack scripts: start and stop the kernel, connect phones, prepare and run windows |
| `tools/farm_release.py`, `tools/farm_install.py`, `tools/release/` | Building a release package and installing it in versioned folders |
| `tools/airplay/` | The receiver's source: UxPlay with three changes ([UPSTREAM.md](tools/airplay/UPSTREAM.md)) |
| the C# projects under `tools/` (`*.csproj`) | Test projects and harnesses for the kernel and console |
| `tools/gate4_1000_tap_suite.py`, `tools/endurance_soak.py`, `tools/export_diagnostics.py` and their tests | Harnesses for release gates 4 and 10 and the diagnostics export |
| [analysis/HARDWARE.md](analysis/HARDWARE.md), [analysis/HID-PROTOCOL.md](analysis/HID-PROTOCOL.md) | The boards and hubs, and the protocol the kernel speaks to them |
| `analysis/` (the rest) | Test fixtures, the configurations the launchers read, and the evidence the release gates cite |
| `AGENT-MANUAL.pdf`, `API-CAPABILITIES.pdf`, `NODE-THEORY-ACTION-PLAN.pdf` | The owner's documents (sources in `analysis/*.html`) |

## Build and test

Nothing here needs a phone. The farm's own tests want the private fixtures of the development PC for some
cases and skip those elsewhere.

```powershell
dotnet build src/iMouse.Kernel/iMouse.Kernel.csproj -c Release -o <new folder>
dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o <new folder>
<kernel folder>\iMouse2.Kernel.exe --self-test
<console folder>\iMouse2.exe --self-test

cd tools; python -m unittest discover -p "test_farm*.py"         # the farm
cd rack; python -m pytest -q                                     # the rack scripts
python tools\farm_release.py lint                                # nothing packaged reads the dev folder
```

Build into a new folder, never over the build the rack or the desktop shortcut is running. The rack
runbook lists the off-rack trials, which run the real rack scripts against a sandbox kernel;
`tools/farm_release_rehearsal.py` installs, updates, rolls back and uninstalls a package in a temporary
folder.

## What is not in the repository

Phone and receiver data, rack and window state, run output, captures, databases, account names and built
binaries stay on the PC that runs the rack. `.gitignore` keeps them out, and
`python tools/privacy_scan_staged.py` runs before every commit (`LANES.md`).
