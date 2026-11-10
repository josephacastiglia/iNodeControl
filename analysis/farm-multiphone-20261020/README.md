# The rack: start, bring up, run a window, stop

One kernel on `127.0.0.1:9916` drives both racks: each phone has a USB input board and an AirPlay
receiver that shows its screen. A *window* is one platform on one phone, with its own backend, and
makes drafts only. This folder holds the scripts and, on the PC that runs the rack, its state.
The history of how this was built is in Git (tag `evidence-20261109`, this file's earlier versions).

Only the orchestrator or the Rack lane runs the kernel commands, and only when no lane is on a phone:
a restart drops every phone's mirror (`LANES.md`).

## State

| Where | What |
|---|---|
| `slots\` | the kernel's one folder: `preparation.json` (what to start), `processes.json` (what is running), logs, `releases.jsonl`, `restarts.jsonl`, `input-stops.jsonl`, `bringup-<time>\report.json`, `watchdog.jsonl` |
| `windows\<platform>-slot<N>\` | one window: its preparation, config, process record, attempts and checks |
| `phone-slots.json`, `rack-b-slots.json`, `rack-b-boards.json` | which board sits in which slot; `bringup-plan.json`: the connect order |

Installed (`docs/INSTALL-FARM.md`) the same layout sits in the data folder; `RackState.ps1` and
`tools/farm_paths.py` are the only places that decide. State is never committed: it names this PC's
paths and phones.

## 1. Start the kernel

```powershell
.\Start-Multiphone.ps1
```

It refuses if a kernel, receiver, console or window backend is already running or one of their ports is
taken, and if the kernel build or its data changed since the preparation. The kernel starts detached, so
it outlives the session that started it; every receiver starts held (not advertised). Do not pipe this
script or `Start-Window.ps1` into another command: the process they start inherits the pipe and the
pipeline never ends.

## 2. Bring the phones up

```powershell
python rack_recovery.py bringup --plan-only     # the order, nothing sent
python rack_recovery.py bringup                 # connects every phone in the plan
```

The bring-up sends input (Home, Control Center, taps). Per phone it advertises the receiver, wakes a
Home-button phone, reads where the receiver's row is on the Screen Mirroring card and taps it. A phone
whose input someone else stopped is skipped; it resumes only boards its own ledger says the rack
scripts stopped. Read `slots\bringup-<time>\report.json` afterwards.

One phone by hand: `.\Release-Receiver.ps1 -Board <board>` advertises its receiver;
`.\Restart-Receiver.ps1 -Board <board>` restarts it without touching the others (the phone must choose
the receiver again; `-Hold` leaves it withdrawn).

Leave `python rack_recovery.py watch` running to have a dead kernel restarted and the phones brought
up again. It never touches a running kernel and never restarts one stopped on purpose. A file named
`slots\watchdog-pause` pauses it.

## 3. Run a window

```powershell
python prepare_window.py --platform reel --slot 18 --phone-ip <phone address> --account <handle>
.\Start-Window.ps1 -Window reel-slot18                  # the backend only; the kernel keeps running
python run_window.py --window reel-slot18 --attempt 1   # one draft; follows the run to its end
python verify_window.py --window reel-slot18 --attempt 1 --check 1   # only if the verifier stopped
.\Stop-Window.ps1 -Window reel-slot18
```

An attempt or check number is never reused, and a new attempt is refused unless every earlier one
ended as a confirmed stop before media import. Verifiers are read-only. A code change alters the
backend's fingerprint, so the window is prepared again. `relaunch_check.py` proves a verified draft
survives closing the app; `close_app.py`, `discard_leftover.py` and `one_tap.py` leave a screen a
stopped run left behind (never 'Save draft' for a leftover).

## 4. Stop

```powershell
.\Stop-Window.ps1 -Window <name>     # each window first
.\Stop-Multiphone.ps1
```

The kernel shuts down through its stop file, ends its receivers and the script withdraws their
AirPlay names (a killed receiver never says goodbye, and phones would list it for 75 more minutes).
Nothing is ever force-killed: if the stop fails, inspect before doing anything else.

## Preparing the rack

`slots\preparation.json` names the kernel build, the run folder with this PC's device, receiver and
calibration data, and the kernel's arguments. `rack_kernels.py rekernel` moves it to another kernel
build. A new one is derived by `prepare_rack_a.py` and `prepare_rack_b.py` from earlier preparations
on this PC; there is no way yet to prepare a rack from nothing on another PC.
`pointer_identify.py` shows which phone a board drives; `pointer_measure.py` measures its calibration.

## Tests

```powershell
python -m pytest -q                                              # unit tests: no kernel, no phone
python offrack\offrack_trial.py --kernel <iMouse2.Kernel.exe>    # the real scripts on a sandbox kernel (:9936)
python offrack\offrack_recovery_trial.py --kernel <iMouse2.Kernel.exe>
```

The off-rack trials use stand-in receivers and board IDs no board has; they are safe beside the live
rack and only read it.
