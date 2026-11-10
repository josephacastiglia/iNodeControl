# Install the Marketing Farm on a clean PC

One page for the operator. **(admin)** marks a step that needs an administrator; everything else runs as you.
Run commands in **Windows PowerShell**. Nothing here posts or publishes; the farm makes drafts only.

The farm installs in two places:
- the program at `%LOCALAPPDATA%\Programs\iMouseFarm`, one folder per version;
- your private data at `%LOCALAPPDATA%\iMouseFarm`: rack maps, preparations, runs, evidence.

Updates and rollbacks touch only the program. Uninstall leaves your data.

## 1. Before the first install

1. **(admin)** Install the prerequisites:
   - the **.NET 8 Desktop Runtime x64** (dotnet.microsoft.com/download/dotnet/8.0);
   - **Bonjour for Windows**;
   - in Settings > Time & language > Language, the **English** language with its OCR features.
2. Install **Python 3.11 x64** for your user (python.org), and an **ffmpeg** build with libx264. Put
   ffmpeg's `bin` folder on your user PATH, then open a new PowerShell window.
3. Unzip the release (`farm-<version>.zip`) to a folder of its own, for example `Downloads\farm-<version>`.
4. Install the pinned Python packages. This needs internet:

   `py -3.11 -m pip install --user -r .\farm\tools\requirements-farm.txt`

5. Check the PC. This changes nothing; it prints what is missing:

   `powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Farm.ps1 -PreflightOnly`

6. **(admin)** Do every step it prints. On a new PC these are usually:
   - two firewall rules for the receivers (TCP and UDP 7100-7599) and one for the window media ports;
     the preflight prints the exact `New-NetFirewallRule` lines;
   - the farm Wi-Fi set to **Private** (Settings > Network & internet > the network);
   - the vendor **iMouseService** stopped and set to Disabled, if the vendor software is installed.
7. Plug in the rack hubs. Each board appears under Human Interface Devices. Install no driver.

## 2. Install

1. Run, from the unzipped folder:

   `powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Farm.ps1`

2. Copy this PC's private files into the data folder by hand, never through Git or a shared drive:
   - into `%LOCALAPPDATA%\iMouseFarm\evidence-archive\privacy\`: `withheld-candidates.txt`,
     `extra-handles.txt`, `farm-accounts.json`;
   - into `%LOCALAPPDATA%\iMouseFarm\analysis\farm-multiphone-20261020\`: `phone-slots.json`,
     `rack-b-boards.json`, `rack-b-slots.json`.
3. Write `%LOCALAPPDATA%\iMouseFarm\machine.json` with the PC's address on the farm Wi-Fi:

   `{"lanAddress": "192.168.x.y"}`

4. Check the install:

   `$farm = "$env:LOCALAPPDATA\Programs\iMouseFarm\Farm.ps1"`

   `powershell -NoProfile -ExecutionPolicy Bypass -File $farm status`

   `powershell -NoProfile -ExecutionPolicy Bypass -File $farm server-self-check`

   `status` lists the version and every command. The self-check ends with `OK - Simulated routes ...`.

5. The farm runs through `Farm.ps1`: `start-rack`, `release-receiver`, `restart-receiver`,
   `prepare-window`, `start-window`, `run-window`, `verify-window`, `stop-window`, `stop-rack`,
   `schedule`. Every one of them needs a rack preparation in the data folder, and **a new PC has
   none and cannot make one yet**: read the next section before going further.

## What works on a new PC today, and what does not

Works. All of it was rehearsed with a real package in an empty folder tree on the development PC;
none of it has been done on a second PC yet:
- the preflight, install, update, rollback and uninstall;
- `status` and `server-self-check`;
- the rack commands themselves (`start-rack`, `release-receiver`, `restart-receiver`, `stop-rack`),
  against a stand-in kernel with no phones.

Does not work yet:
- **Preparing a rack.** `start-rack` reads `analysis\farm-multiphone-20261020\slots\preparation.json`
  in the data folder: the kernel's arguments, this PC's paths, and each phone's device ID bound to
  its board. The scripts that write one (`prepare_rack_a.py`, `prepare_rack_b.py`) start from
  earlier preparations that exist only on the development PC, and they are not `Farm.ps1` commands.
  A preparation copied from another PC does not work either: it names that PC's paths. Until a
  tool prepares a rack from nothing, the farm can drive phones only on the PC it was developed on.
- **Connecting the phones unattended.** The bring-up and the watchdog (`rack_recovery.py`) are in
  the package but are not `Farm.ps1` commands yet.
- **The receiver on another processor.** The receiver in the packages built so far was compiled for
  the development PC's processor and may stop with an illegal-instruction error on another one. It
  has to be rebuilt first; `receiver\NOTICE.md` in the package says how.

The package is for your own PCs. `uxplay.exe` comes with its licence and source (`receiver\LICENSE`,
`receiver\source`); the GStreamer runtime beside it does not yet, so do not pass the package on.

## 3. Update to a new version

1. Stop the farm:

   `powershell -NoProfile -ExecutionPolicy Bypass -File $farm stop-window -Window <name>`, once per window

   `powershell -NoProfile -ExecutionPolicy Bypass -File $farm stop-rack`

2. Unzip the new release, then from its folder run:

   `powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Farm.ps1 -Update`

   It refuses while any farm program is still running.
3. Prepare every window again: a new version changes the backend's fingerprint. If the release notes
   say the kernel changed, the rack preparation has to name the new build as well (on the development
   PC: `rack_kernels.py rekernel`).

## 4. Roll back

Stop the farm as for an update. Then, from any release folder, run:

`powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Farm.ps1 -Rollback`

This switches to the previous version, which is checked file by file first. Running it again switches
forward. Prepare windows again afterwards.

## 5. Uninstall

Stop the farm, then run:

`py -3.11 "$env:LOCALAPPDATA\Programs\iMouseFarm\versions\<version>\install\farm_install.py" uninstall --root "$env:LOCALAPPDATA\Programs\iMouseFarm"`

This removes the program. Your data folder stays; delete it yourself only if you mean to.

## If something refuses

Every script stops before changing anything and says why. Run the preflight again first. Keep the
message and the files it names, and do not delete preparations or evidence to get past a refusal.
