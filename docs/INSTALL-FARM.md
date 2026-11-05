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

5. Prepare the rack and windows on this PC. Preparations name this PC's paths, so ones copied from
   another PC do not work. Then run the farm through `Farm.ps1`: `start-rack`, `release-receiver`,
   `restart-receiver`, `start-window`, `run-window`, `verify-window`, `stop-window`, `stop-rack`,
   `schedule`.

## 3. Update to a new version

1. Stop the farm:

   `powershell -NoProfile -ExecutionPolicy Bypass -File $farm stop-window -Window <name>`, once per window

   `powershell -NoProfile -ExecutionPolicy Bypass -File $farm stop-rack -Stage slots`, or `-Rack A` / `-Rack B` for
   per-rack kernels

2. Unzip the new release, then from its folder run:

   `powershell -NoProfile -ExecutionPolicy Bypass -File .\Install-Farm.ps1 -Update`

   It refuses while any farm program is still running.
3. Prepare every window again: a new version changes the backend's fingerprint. Prepare the rack again
   too if the release notes say the kernel changed.

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
