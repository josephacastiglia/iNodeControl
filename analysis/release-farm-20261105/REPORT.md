# Marketing Farm release: package, install, update, rollback (Release lane, 5 Nov 2026)

Branch `sb/chat-release`. Off the rack throughout: no kernel, receiver, backend or phone was started,
stopped or called; nothing was installed system-wide. The rehearsal ran in a temporary folder tree.

## Update, 5 Nov late: strict privacy, the real zip, the operator guide

- **No handle ships.** `farm_start_screen.py:187` now reads the Instagram profile's account through
  `farm_paths.account_label()`, the same private `farm-accounts.json`. That file is not in the server's
  `sourceHash`, so prepared windows stay valid. The Small phone tests pass (`test_farm_small_shared`,
  `test_farm_small_layout`, `test_farm_safari_start`: 104 OK).
- **Strict privacy is the default.** Any handle in a packaged file refuses the build. The handles come
  from `farm-accounts.json` and the retained X OCR, with no exemption. `--no-strict-privacy` makes a
  review build that only lists them.
- **The real package** is `farm-2026.11.05-406e13c.zip`: 237 files, 69.6 MB, SHA-256 `323f73e0…`. Its
  record is `package-20261105-406e13c.json`. It was built from tip 406e13c with no tracked changes,
  0 dev-path blockers and 0 handles. Inputs:
  - the kernel: `rack-kernel-20261104`, the live build;
  - the console: built from 8b43548 (its source is unchanged since);
  - the receiver and runtime: `farm-new-draft-20261019`.

  The zip stays out of Git (over 50 MB).
- **The rehearsal from that zip passed 26/26** (`rehearsal-zip-20261105.json`).
  - Version A is the extracted zip: CRC checked, safe names, verify passed, no handle.
  - Then the guarded imports and self-check, then the sandbox rack through the installed `Farm.ps1`
    (:9956, stand-ins, :9916 untouched).
  - Then update, rollback, tamper refusal and uninstall, with a strict verify of the version folder.
- **Fixed:** the zip had been named `farm-2026.11.zip`, because `with_suffix` cut the dotted version;
  it is now tested.
- **Operator guide:** `docs/INSTALL-FARM.md`, one page, admin steps marked. It ships at the package
  root as `INSTALL-FARM.md`.

## Update, 5 Nov evening: dev-path blockers removed

**Lint: 56 blocker lines before (2f26ed8), 0 after.** Every launcher command is now ready from an
install, including the console. The rule is one variable, `IMOUSE_FARM_DATA`, which `Farm.ps1` sets.
When it is unset, every path is today's, and that is tested:
- `test_farm_paths` checks the paths against the 27 Oct definitions, from the main folder and from a
  lane;
- `test_rack_state` imports the 12 edited rack scripts both ways;
- `test_rack_ps_state` runs sandbox copies of the 6 rack PowerShell scripts both ways, and evaluates
  the API lines on their own;
- the four live window preparations resolve to the same `http://127.0.0.1:9916/api` as before.

| Item | Change |
|---|---|
| 1 `tools/farm_paths.py` | Set: `MAIN` = data folder, `ARCHIVE` = `<data>/evidence-archive`, new `STATE`; helpers `rack_state`, `run_root`, `installed`, `source_option`, `lan_address`, `machine_config`. The schedule tools and Photos cleanup follow through `MAIN`. `farm_schedule_runner.py`'s window state uses `rack_state`. |
| 2 Rack Python | `run_window`, `verify_window`, `watch_run`, `relaunch_check`, `auto_connect`, `card_survey`, `pointer_identify`, `pointer_measure`, `rack_kernels`, `prepare_window` (window, run and print lines only), `prepare_rack_a`, `prepare_rack_b`. State goes through `STATE`, runs through `RUNS`. `prepare_rack_b` names the installed kernel, receiver and runtime. `prepare_rack_a --source DIR` replaces the sibling-repo input; it is required when installed. |
| 3 Rack PowerShell | All six take state from `$taskState` (data folder when installed, `$PSScriptRoot` otherwise) and Python from `IMOUSE_FARM_PYTHON`, else `python`. `Start-Window` finds Python by `IMOUSE_FARM_PYTHON`, then this user's Python 3.11 (the same path as before on this PC), then PATH. `Start-Window` and `Stop-Window` take the kernel API from the window's rack preparation, falling back to :9916, so rack B windows on :9926 now work. |
| 4 LAN address | One line in `prepare_window.py`. A checkout keeps the same address. Installed: `IMOUSE_FARM_LAN`, else `<data>/machine.json` `lanAddress`, else the PC's single private IPv4. This PC has three, so installed it stops and lists them. |
| 5 Account handle | `farm_draft_runs.ACCOUNT` now reads `<archive>/privacy/farm-accounts.json`. I wrote that file in the main folder's evidence archive with the same value; it is `''` where absent. `farm_format_coverage.py`'s note no longer names the handle. |
| 6 Console | New `InstallLayout.cs`. Installed: run, failure and QA files go to `<data>\console`, the farm server comes from `IMOUSE_FARM_HOME`, Python from `IMOUSE_FARM_PYTHON`, and the data folder is the server's working folder; no settings mirror beside the exe. **625 self-tests pass** (8 new), both unset and set; set, the build folder stayed unwritten. |

The 20 Oct one-shots `prepare_multiphone.py` and `prepare_slots.py` were not changed. They use fixed
run names and refuse to run again, so they are left out of the package.

**Rehearsal with the sandbox rack: 24/24** (`rehearsal-sandbox-20261105.json`).
- The installed farm modules and server self-check ran with `IMOUSE_FARM_DATA` set, and `farm_paths`
  pointed at the data folder.
- Then, only through the installed `Farm.ps1`, against an off-rack kernel. That kernel was the
  *installed* build, on :9956, with three stand-in receivers, board IDs absent from USB and names
  `iMouse2-Y1..3`:
  - `start-rack -Rack B` refused beside the live single kernel and started nothing;
  - `restart-receiver` restarted one stand-in (generation 2, others unchanged);
  - `release-receiver` started the held stand-in;
  - `stop-rack` stopped the kernel gracefully and sent goodbyes for the Y names.
- All records landed in `<data>/analysis/farm-multiphone-20261020/rack-b/`. A **strict** verify of the
  installed version afterwards found no new file, and nothing of the sandbox remained.
- :9916 was never read or called.

**Found by the rehearsal and fixed:**
- Python wrote `__pycache__` into the version folder. `Farm.ps1` now sets `PYTHONPYCACHEPREFIX` and
  `-X pycache_prefix` to `<data>\cache\pycache`.

**Learned:**
- Processes started under an agent session inherit "ignore Ctrl+C". A kernel started that way does not
  stop with `Stop-Multiphone`'s graceful Ctrl+C. This reproduces with the dev helper too, so it is not
  a script regression; the sandbox kernel is now created through WMI.
- The kernel *lists* every WCH board (it logged 19) but opens one only for input to an allowed board,
  so the sandbox could not grab rack A's boards.

**Before merging:**
- `farm_draft_runs.py` and `farm_format_coverage.py` are in the farm server's `sourceHash` list. After
  the merge, Start-Window refuses every window prepared before it until it is prepared again. Merge
  between runs.
- `tools/farm_start_screen.py:187` (Small phone lane) still names the account handle. The package build
  lists it under `account_labels_in` for review.
- New operator steps on a clean PC:
  - write `<data>\machine.json` `{"lanAddress": "<farm Wi-Fi IPv4>"}`;
  - copy `farm-accounts.json` and the privacy lists into `<data>\evidence-archive\privacy\`;
  - prepare racks with `prepare_rack_a.py --source <full-rack config>`.

## Result

- **Builder** `tools/farm_release.py`: builds a verified package folder (optional zip) from a kernel
  build, a console build, the receiver and its runtime, and the farm's Python/PowerShell. It refuses
  private paths and private content, and it lints the farm code for dev-folder assumptions.
- **Installer** `tools/farm_install.py` (stdlib only): installs into `<root>\versions\<version>`,
  switches `current.json` in one `os.replace`, updates, rolls back, prunes and uninstalls. The data
  folder is always outside the install, and uninstall leaves it in place.
- **Preflight** `tools/release/Preflight-Farm.ps1`: read-only. It checks prerequisites and prints the
  exact operator steps; admin steps are marked "(admin)".
- **Launcher** `tools/release/Farm.ps1`: copied to the install root. It runs a command from the current
  version, with the data folder as working directory and `IMOUSE_FARM_*` variables set. It refuses a
  command whose code still depends on the dev folder.
- **Operator entry** `tools/release/Install-Farm.ps1`: runs the preflight, then install, `-Update` or
  `-Rollback`.
- **Tests**: 34 pass (`test_farm_release.py` 14, `test_farm_install.py` 20). The existing
  `test_stage_release` and `test_build_manifest` still pass.
- **Clean-machine rehearsal** with the real kernel, console and receiver bytes: **16 of 16 checks
  passed**, three runs in a row. Evidence: `rehearsal-20261105.json`, with paths replaced by
  placeholders.

**Not yet installable for rack work.** Only `server` and `server-self-check` are ready from an install.
The rack, window, schedule and console commands are blocked by 56 dev-path lines in shared files,
listed below. The orchestrator owns those changes; this lane did not make them.

## What the package contains

237 files, about 182 MB. `release.json` records every file's SHA-256 and size.

| Folder | Contents |
|---|---|
| `kernel/` | `iMouse2.Kernel.{exe,dll,deps.json,runtimeconfig.json,pdb}`, from `output/rack-kernel-20261104` in the rehearsal. The manifest carries the DLL's SHA-256, which preparations check. |
| `console/` | `iMouse2.{exe,dll,deps.json,runtimeconfig.json,pdb}`. Both runtimeconfigs are checked for .NET 8; the console also needs WindowsDesktop.App. |
| `receiver/` | `uxplay.exe` and `runtime/**` (132 GStreamer/MSYS2 files). Marked `redistribution_cleared: false`: for the operator's own PCs only. |
| `farm/tools/`, `farm/analysis/farm-multiphone-20261020/` | 89 files in the same relative layout as the dev folder, so the scripts' `$PSScriptRoot\..\..` and `parents[1]` still resolve. See the selection rules below. |
| `install/` | `farm_install.py`, `farm_release.py` (to verify on the target PC), `Preflight-Farm.ps1`, `Farm.ps1` |
| `Install-Farm.ps1` | Operator entry point |

How the 89 farm files are chosen:
- **Entry points:** the farm server, the schedule CLI and runner, Photos cleanup, `mdns_goodbye`, and
  the rack scripts.
- **What they pull in:** local imports, string constants that name a module (catches the importlib
  lane table that loads `farm_tiktok_photo_runs`), and files named in code (catches
  `kernel-window\Stop-ConsoleProcessGracefully.ps1` and `farm_start_screen.py`). Mentions in
  comments or docstrings do not count.
- **Server hash check:** all 48 files in the server's `sourceHash` list are present, so the build
  refuses if one is missing.
- **Left out:** tests, and the one-off probes with machine-specific values (`identify_rack_b.py`,
  `connect_xr.ps1`, `connect_small.ps1`, `learn_rack_b.ps1`, `board_probe.py`, `one_tap.py`,
  `switcher_probe.py`, `open_app_look.py`).

**Pinned Python:** Python 3.11 x64 with `requirements-farm.txt`, which must use `==` pins (Pillow
9.5.0, numpy 2.3.1, opencv-python-headless 5.0.0.93). The preflight checks the exact versions. No
interpreter is bundled.

## What it excludes, and where that state lives

**Never packaged,** by path pattern:
- rack preparations and process records;
- `phone-slots.json`, `rack-b-boards.json`, `rack-*-slots.json`;
- the `slots/`, `held/`, `rack-a/`, `rack-b/`, `windows*/`, `identify/`, `autoconnect/`, `measure/` and
  `look/` folders;
- any `data/` or `output/` folder;
- `devices.json`, `receivers.json`, `pointer-calibration.json`, `settings.json`, `startup-state.json`,
  `ui-boxes.json`, `IMService.json`;
- databases, logs, jsonl files, captures (png, jpg, bmp, mp4 and the like), keys and tokens, the
  evidence archive and its privacy lists.

**Content scan:** every text file in the package is also checked for UDID-shaped device IDs, the
evidence archive's withheld values and the handles to keep out of Git. A match refuses the build
before anything is written. The build only appears complete through a final rename (`.partial` →
final name).

The farm code names six private files. They were not packaged; they belong in the data folder: the
rack preparation, the held preparation, `slots/preparation-4phone-20261020.json`, `phone-slots.json`,
`rack-b-boards.json` and `rack-b-slots.json`.

**Data folder** (default `%LOCALAPPDATA%\iMouseFarm`, created by `farm_install.py init-data`). It
mirrors today's state layout, so `farm_paths.MAIN = <data>` is the only switch the tools need:
- `analysis/farm-multiphone-20261020/{slots,held,rack-a,rack-b,windows}`
- `output/{candidate-runs,farm-data,media-stage,farm-schedule}`
- `evidence-archive/privacy`
- `logs`
- `data.json`, holding the data schema and the last version that used the folder

An older version refuses to open data at a newer schema, so a rollback cannot open data a later
version changed.

## Install, update, rollback

- **Layout:** `<root>` (default `%LOCALAPPDATA%\Programs\iMouseFarm`) holds `install.json` (data
  folder, Python), `current.json` (version, previous, history), `versions\<v>\` and `Farm.ps1`.
- **Install and update:** verify the package against `release.json`; copy it to
  `versions\.<v>.partial-*`; verify again; rename. Then claim the data folder and replace
  `current.json` atomically. A failed copy removes its partial folder and leaves `current.json` as it
  was (tested).
- **Update and rollback** refuse while any process runs from the install root, matched by executable
  path or command line. Stop the farm first.
- **Rollback** switches to `previous` after re-verifying it. A version whose recorded bytes changed is
  refused. Files the apps wrote beside themselves (the console's `startup-state.json`) are allowed.
- **Uninstall** removes only what the installer wrote (versions, json files, `Farm.ps1`). It refuses if
  foreign files are in the root, and keeps the data folder.
- **Install refuses** an install root or data folder inside a git checkout, the two inside each
  other, or either overlapping the package.

## Preflight (read-only)

What it checks:
- Windows 10 2004+/11 x64, PowerShell 5.1 and the execution policy;
- .NET 8 NETCore.App and WindowsDesktop.App;
- Python 3.11 x64 (not the Store stub) and the exact pins;
- ffmpeg and ffprobe with libx264;
- Windows OCR with English;
- the Bonjour service and `dns-sd.exe`, which `auto_connect`/`card_survey` use to browse (the
  receivers use their own mDNS);
- WCH boards (VID_720A) present and OK on the built-in HID driver; no vendor driver is needed;
- vendor `iMouseService` not running;
- an inbound firewall **port** rule for TCP and UDP 7100-7599 (receivers) and TCP 9917/9927/9937/9947
  (window media). Per-program `uxplay` rules do not survive an update, because each version has its
  own path.
- no Public network profile;
- install and data folders outside checkouts and apart from each other;
- disk space, and the farm ports.

The tests parse the script with PowerShell's own parser and fail if it calls any changing command
(firewall, service, registry, item, process, policy, PnP or download cmdlets).

On this PC it passes with two warnings (the Ethernet network is Public; 9916 is in use by the live
kernel). It takes about 3 s; the firewall read is two bulk queries, where a per-rule lookup took about
54 s.

## Rehearsal (`tools/farm_release_rehearsal.py`), 5 Nov, real bytes, below-normal priority

The tree was built in the session scratch folder:
- `packages/` held package A, built from this checkout, and package B, built from a temporary copy
  with one changed file;
- the fake `LocalAppData/Programs/iMouseFarm` was the install root;
- the fake `LocalAppData/iMouseFarm` was the data folder, seeded with a fake rack preparation, slot map
  and privacy list.

| Check | Result |
|---|---|
| Both packages verify | PASS |
| Every installed `farm/tools` module imported, run from the install with cwd = data folder, under the runtime guard: no file opened, module loaded or `sys.path` entry under `Desktop\Claude Code` | PASS (466 opens) |
| Installed farm server `--self-check` (simulate) under the guard: no dev-folder read; the guard refused nothing (no process, no connection except its own port) | PASS |
| Self-check output `OK - Simulated routes ... passed` | PASS |
| `Farm.ps1 status`; `Farm.ps1 preflight` (read-only) | PASS |
| `Farm.ps1 start-rack` refuses ("not ready ... Nothing was started") | PASS |
| Update A → B: current B, previous A, B's change present, B's modules guarded clean, launcher follows | PASS |
| Rollback B → A, with a console-written file in A: switched, launcher follows | PASS |
| Rollback to a tampered B refused; current stays A | PASS |
| Uninstall removes the root; the data folder is byte-identical except `data.json` (`last_version`) | PASS |
| No private path in the package | PASS |

**The runtime guard** (`tools/release/runtime_guard.py`, with its own test) is a Python audit hook. It
records every opened path and refuses any process start. It refuses every socket connection except to
a loopback port the same process bound, and never to 9911-9949 or 7100-7599. So the guarded code could
not reach the live kernel even by mistake.

The guard also shows the core problem. The installed `farm_paths` resolves `MAIN` and `RACK` **inside
the versioned install** (`versions\rehearsal-a\farm\...`) and `ARCHIVE` to
`versions\iMouseXP-2.0-evidence-archive`. State would be written into the install and lost on update.

**What the rehearsal does not prove:**
- PowerShell rack scripts have no runtime guard. They are linted, and the launcher keeps them blocked.
- The kernel and console binaries were copied, hashed and checked for frameworks, but never started.
- The pinned packages were checked in this PC's Python; no fresh pip install was done (it would need a
  download).

## Dev-path list, and the shared changes needed (for the orchestrator)

`python tools/farm_release.py lint` lists these as file:line; it is the gate. A command becomes ready by
itself once its files lint clean; nothing in the release code needs to change.

**The anchors are mixed.** Tools find state three ways:
- their own folder (`HERE`);
- the checkout root (`parents[1]`, `$PSScriptRoot\..\..`);
- the main folder found by its `.worktrees` name (`farm_paths.MAIN`).

The proposed contract is one variable, `IMOUSE_FARM_DATA`, which `Farm.ps1` already sets. When it is
set, state goes there; code stays where it is.

1. **`tools/farm_paths.py`** (lines 4-15; blocks `schedule` and everything that imports it). When
   `IMOUSE_FARM_DATA` is set:
   - `MAIN = Path(env)`
   - `ARCHIVE = MAIN / 'evidence-archive'`
   - new `STATE = MAIN / 'analysis/farm-multiphone-20261020'`
   - `RACK = STATE / 'slots'`

   Otherwise keep today's discovery, with `STATE = MAIN / 'analysis/farm-multiphone-20261020'`. This
   one change also fixes `farm_schedule_cli.py:31,92` and `farm_photos_cleanup.py:45`.
2. **Rack PowerShell.** Add
   `$taskState = if($env:IMOUSE_FARM_DATA){Join-Path $env:IMOUSE_FARM_DATA 'analysis\farm-multiphone-20261020'}else{$PSScriptRoot}`.
   Use it for `held`/`slots`/`rack-*`/`windows`; keep `$PSScriptRoot` for code.
   - `Start-Multiphone.ps1:12`, `Stop-Multiphone.ps1:9`, `Release-Receiver.ps1:8`,
     `Restart-Receiver.ps1:14`, `Stop-Window.ps1:4`: the state folder only.
   - `Start-Window.ps1:7`: hard-coded `...\Python311\python.exe`. Use
     `$env:IMOUSE_FARM_PYTHON`, else `(Get-Command python.exe).Source`.
   - `Start-Window.ps1:8,16-17`: the `.worktrees` main discovery becomes `$taskState`.
   - `Start-Window.ps1`/`Stop-Window.ps1`: the hard-coded `127.0.0.1:9916` becomes the preparation's
     `api`, which also unblocks rack B windows on 9926.
3. **Rack Python state beside the scripts** (`HERE / 'windows'` and friends) moves to
   `farm_paths.STATE`:
   - `run_window.py:40`, `verify_window.py:123`, `watch_run.py:18`, `relaunch_check.py:52`,
     `prepare_window.py:84`
   - `auto_connect.py:145`, `pointer_identify.py:60,80,137`, `pointer_measure.py:67`
   - `prepare_slots.py:17,19`, `prepare_rack_a.py:30,64,76`, `prepare_rack_b.py:28`,
     `prepare_multiphone.py:29`
   - `tools/farm_schedule_runner.py:39,110,128` (`FOLDER/windows`, `windows-archive`)
   - `tools/farm_schedule_cli.py:112,116`
4. **Rack Python state under the checkout** (`ROOT/'output/...'`) moves to `farm_paths.MAIN/'output/...'`:
   `prepare_window.py:85-86`, `prepare_slots.py:18,24`, `prepare_rack_a.py:99`,
   `prepare_rack_b.py:29,105`, `prepare_multiphone.py:20,26,28`.
5. **Inputs from the sibling repo** (`iMouseXP-2.0/analysis/five-phone-config`, `full-rack-config`) in
   `prepare_multiphone.py:21` and `prepare_rack_a.py:29` become explicit `--source` arguments. The
   kernel, receiver and runtime paths in new preparations come from `IMOUSE_FARM_KERNEL`,
   `IMOUSE_FARM_RECEIVER` and `IMOUSE_FARM_RECEIVER_RUNTIME`, not `ROOT/output/...`
   (`prepare_rack_b.py:29`, `prepare_multiphone.py`).
6. **Console** (C#; listed by hand in `MANUAL_BLOCKERS`, which the lint cannot read):
   - `App.xaml.cs`/`MainWindow.xaml.cs` write `startup-state.json`, `startup-validation.json`,
     failure files and `qa\` into `AppContext.BaseDirectory`, i.e. into the installed version. They
     should write to `--data-dir`.
   - `FarmAutomationWindow.cs:76-97` looks for `tools\imouse_farm_server.py` above its own folder and
     starts `python` from PATH. It should take `IMOUSE_FARM_HOME` and `IMOUSE_FARM_PYTHON`, and run
     the server with `--data-dir`.
   - `MainWindow.FarmJobs.cs:244` (`..\..\output\media-stage`) should likewise use the data folder.
7. **Kernel:** no change. Every path arrives by argument, and the default `BaseDirectory\data` is only
   used without `--data-dir`.
8. **Machine-specific values in code** that belong in the data folder:
   - `prepare_window.py:39` (`PC_LAN`, the PC's LAN address);
   - `tools/farm_draft_runs.py:25` (an account handle constant, which the privacy scan exempts by name;
     it ships in the package);
   - `connect_xr.ps1:5-6` (phone LAN addresses; kept out of the package).
9. **Preparations bind absolute paths and hashes.** `kernel`, `runDirectory`, `--receiver*`,
   `backendData` and `config` are absolute; `kernelSha256`, `dataSha256`, `configSha256` and
   `backendSourceHash` are checked.
   - After an install, the operator re-runs the rack and window preparations, so they name the
     installed paths.
   - After an update, every prepared window must be prepared again: the server's `sourceHash` changes.
     The rack must be prepared again too if the kernel changed. That is the existing safety, kept.
   - The tracked `analysis/farm-multiphone-20261020/preparation.json`, `held/preparation.json`,
     `slots/preparation-*.json` and `processes-stopped-*.json` hold absolute dev paths. They are
     history; they are not packaged.

**Information only (not blockers):**
- hard-coded kernel ports in many tools;
- the server's and engine's cwd-relative `output/...` defaults, which land in the data folder because
  `Farm.ps1` runs there;
- `parents[1]` used to find code.

## Operator steps for a real clean-PC install

On the dev PC (Claude can do this; it reads the builds and writes only under `output/`):

1. Build:
   `python tools/farm_release.py build --out output/release/farm-<version> --kernel output/rack-kernel-20261104 --console output/multiphone-console-20261020 --receiver-exe output/candidate-runs/farm-new-draft-20261019/receiver/uxplay.exe --receiver-runtime output/candidate-runs/farm-new-draft-20261019/runtime --version <version> --zip`
2. Copy the zip to the new PC (USB stick or network share), outside any synced or Git folder.

On the new PC, signed in as the operator:

3. **(admin) Install the prerequisites.** Re-run the preflight to confirm each one:
   - .NET 8 Desktop Runtime x64;
   - Python 3.11 x64 (install for the current user);
   - an ffmpeg build with libx264, with its `bin` on the user PATH;
   - Bonjour for Windows;
   - the English language with OCR.
4. **Python packages:** `"<python.exe>" -m pip install --user -r <package>\farm\tools\requirements-farm.txt`.
   This needs internet, or a wheel folder with `--no-index --find-links`.
5. **Preflight:** unzip, then run
   `powershell -NoProfile -ExecutionPolicy Bypass -File <package>\Install-Farm.ps1 -PreflightOnly`.
   Do every printed step. The admin ones are:
   - the two receiver firewall port rules and the media port rule (exact `New-NetFirewallRule` lines
     are printed);
   - the farm network set to Private;
   - the Bonjour service running;
   - the vendor `iMouseService` stopped and set to Disabled.
6. **Hardware:** plug the rack hubs in. Each board shows as a HID device with no warning; install no
   vendor driver.
7. **Install:** run `Install-Farm.ps1` with no switch. It installs to
   `%LOCALAPPDATA%\Programs\iMouseFarm` with data in `%LOCALAPPDATA%\iMouseFarm`, and needs no admin.
8. **Check:**
   `powershell -NoProfile -ExecutionPolicy Bypass -File %LOCALAPPDATA%\Programs\iMouseFarm\Farm.ps1 status`,
   then the same with `server-self-check`.
9. **Rack work** waits until the shared changes above land and `Farm.ps1 status` lists the commands as
   ready. Then:
   - copy the private state (rack slot maps, rack-B board maps, privacy lists) into the data folder by
     hand, never through Git;
   - prepare the rack and windows again on that PC.

Later:
- **Update:** stop the farm (`Stop-Window`, `Stop-Multiphone`), run `Install-Farm.ps1 -Update` from the
  new package, then prepare windows again.
- **Rollback:** `Install-Farm.ps1 -Rollback`.
- **Uninstall:** `python <root>\versions\<v>\install\farm_install.py uninstall --root <root>`. The data
  folder stays; deleting it is the operator's choice.

## Open (not done in this lane)

- The shared changes above, then a lint with 0 blockers, then the rehearsal again.
- A real install on a second PC.
- A Python environment per version (venv from a wheel folder), so requirement changes roll back too.
  Today the pins are per-user and checked by the preflight.
- A data migration helper from the dev folder, once item 9's re-prepare rule is agreed.
- Receiver runtime redistribution clearance, before the package goes to anyone else.
- Signing: checksums are integrity records only, not signatures.
