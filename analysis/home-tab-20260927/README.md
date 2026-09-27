# Home inserts a Tab into an active text field: 27 Sep 2026

## Second testing window, 27 Sep 18:34–18:46: discovery failed again; release restored; Home not tested

**Outcome.** With a 10-minute discovery allowance, the test receiver was still never connected. The window ended and the release was restored. **No Home trial ran, and no input went to any phone. No firewall, network or receiver code was changed.**

| Time | Step |
|---|---|
| 18:34:58 | Preflight. Installed console 9044; release kernel 33912 (command line identical to the snapshot); receivers 36508 = C24C and 36856 = C241, both mirroring. C24C = XR C24C (board C24C, uid C24CBFBD). Both phones unowned, no active work. Release files unchanged since the snapshot; operator settings `72F51CC0…`. Test kernel and candidate hashes re-verified |
| 18:35:12 | Installed console closed normally |
| 18:35:14 | Release kernel stopped gracefully (exit 0); both receivers exited; port 9913 free |
| 18:35:23 | Test kernel 32464 started (`command-h`, C24C only); receiver `iMouse2-C24C` 15144 |
| 18:35–18:45:24 | Receiver checked every 5 s, read-only. The process stayed alive, and its log shows only startup up to "Initialized server socket(s)". No client connected and no frames arrived. The user watched C24C's Screen Mirroring list to select it |
| 18:45:34 | Test kernel stopped gracefully (exit 0); its receiver exited; port 9913 free |
| 18:45:52 | Release restored with `Open iMouse 2.0.ps1` after `-CheckOnly`. Kernel 30652, receivers 35448 (iMouse2-C24C) and 6100 (iMouse2-C241), console 30604. Kernel and receiver command lines identical to the snapshot; no release file changed; both phones unowned; operator settings unchanged |

**What this shows (AirPlay compatibility, not Home).** Two test runs of about 2.5 and 10 minutes were never discovered or connected. In both windows the release receivers, started by the release kernel with identical uxplay arguments, were listed and connected within minutes. So the test build's receiver management most likely differs in a way that matters. It uses the repository's `AirplayProcess.cs` and `ReceiverFleet.cs`, whose release versions are unrecorded. This is not proven, and it was not investigated during the window, as instructed.

**Home result: none.** V1 remains untested on a phone. V2 was not run because V1 was never observed.

**After the second restore (18:45–18:51): this weakens the receiver-code explanation.**
- The **release** receivers, started at 18:45:46, had still not been listed by C24C or C241 five minutes later. Both phones' Screen Mirroring was searching (user photo, `user-photo-after-window2.webp`).
- Two **other** rack phones could see them and tried to connect. Both were refused by `-restrict -allow`, as designed, so no video flowed:
  - `8A:23:B5:71:35:8D` (192.168.4.27) tried both iMouse2-C24C and iMouse2-C241 at 18:48:43–46;
  - `3A:DC:15:FB:DD:EC` (192.168.4.65) tried iMouse2-C241 at 18:48:58, and iMouse2-C24C at 18:49:39.
- Earlier today C241 took about 3 minutes to list a restarted release receiver.
- So slow or failed discovery on **C24C and C241 themselves** after a receiver restart is at least as likely a cause as the test build's receiver code. It is unknown whether other phones could see the test receiver. Neither explanation is established.

## Testing window, 27 Sep 18:24–18:31: stopped at mirroring; release restored; Home not tested

**Outcome.** The test kernel started correctly, but C24C's Screen Mirroring list never showed its receiver. Following the agreed rule, the experiment stopped and the release was restored. **No Home trial ran, and no input went to any phone. V1 is still untested.**

| Time | Step |
|---|---|
| 18:24:51 | Preflight. Installed console 9044 was not yet running; the console at the time was 25728. Release kernel 28776 (release path, full command line recorded). Receivers **36456 = iMouse2-C24C** and **13616 = iMouse2-C241**; the "Interruption" section below had these two PIDs swapped. C24C was leased by the installed console but not active; no active work on either phone |
| 18:25 | **Release snapshot.** Kernel folder, `devices.json`, `pointer-calibration.json`, `receivers.json` and the launcher copied to the evidence archive, plus the exact kernel and receiver command lines and `ORIGINALS-SHA256.txt`. Every copy was verified. `uxplay.exe` was used in place; its hash was recorded |
| 18:25 | **Test build provenance** (`test-build-provenance.txt`). All 16 kernel sources equal commit `068bb68`. Compared with release (line endings normalised), 9 are identical. The 7 that differ are this change's 5 files and the 2 unrecorded AirPlay files (release PDB SHA-256: `AirplayProcess.cs` `1881E2DE…79DF`, `ReceiverFleet.cs` `E86091FF…69E5BD`) |
| 18:26:02 | Installed console closed normally; C24C's lease released (generation 9) |
| 18:26:11 | **Release kernel stopped gracefully** (Ctrl+C helper, exit 0). Both receivers and the console host exited; port 9913 was free |
| 18:26:22 | **Test kernel 30912 started.** `home_sequence: command-h`, input allowed for C24C only, one receiver `iMouse2-C24C` (35768) with arguments identical to the release C24C receiver |
| 18:26–18:28 | **Mirroring failed.** On both phones Screen Mirroring searched and listed nothing (user photo). The test receiver logged startup up to "Initialized server socket(s)", the same lines as the release receiver at 14:37, and then no client. The console has no role in mirroring: the kernel's `/device/airplay/*` only returns a message |
| 18:29:03 | **Test kernel stopped gracefully** (exit 0). Its receiver exited, port 9913 was free, and no test process remained |
| 18:29:22 | **Release restored** with `Open iMouse 2.0.ps1` after a `-CheckOnly` dry run. Kernel 33912, receivers 36508 (iMouse2-C24C) and 36856 (iMouse2-C241), installed console 9044. The kernel and receiver command lines are identical to the pre-window ones, all release files match the snapshot, and operator settings are unchanged |
| 18:29:55 | **C24C recast by the user through the release receiver: mirroring works.** C24C's list shows both iMouse2-C24C and iMouse2-C241 |
| 18:31 | **C241's list shows no receivers at all**, although its receiver is running and C24C can see it advertised. No connection attempt has reached it. This looks phone-side and was not changed |

**Why the test receiver was not listed: undetermined.** Candidates, none tested:
- **the test build's receiver handling:** `AirplayProcess.cs` and `ReceiverFleet.cs` differ from release's unrecorded versions;
- **Bonjour/mDNS timing:** the test receiver re-registered the same service name and MAC seconds after the release instance was stopped;
- **phone discovery state:** C241 is not discovering any receivers even now.

**Later observation (18:32).** C241 listed and connected to the **release** C241 receiver at 18:32:38, about 3 minutes after that receiver started (18:29:22); both phones then mirrored through release. The test receiver was up for only about 2.5 minutes (18:26:22–18:29:03). So slow discovery on the phones after a receiver restart is a plausible explanation for the failed window, alongside the test build's receiver code. This is not proven either way.

A future attempt should first show that the test build's receiver can be discovered before any input, allowing at least 5 minutes for the phones to list it. That attempt needs its own approval.

**Scope.** This window tested nothing about the Home sequence. It does not authorise promoting the test kernel or its AirPlay implementation.

Evidence: `iMouseXP-2.0-evidence-archive/20260927-home-window/` (the release snapshot and the test build provenance).

**Status: traced and reproduced in HID reports on the mock. A test-only kernel option is prepared. The phone test has not run; it needs a coordinated window.** The release kernel's behaviour is unchanged: the option defaults to the current sequence. The candidate is not promoted. App Switcher, Control Centre, pointer movement, keyboard settings and the missing-space behaviour are untouched.

## Why Tab precedes Command+H

- **Where Home is sent.** `InputRouter` sends `fn_key == "Home"` as `Stroke(0, 43)` (Tab), then `Stroke(8, 11)` (Left GUI+H).
- **Where it came from.** It is the vendor's Home, copied byte for byte from IMService's `WriteFile` calls observed on 14 Sep (`analysis/HID-PROTOCOL.md`; raw data in `analysis/hid-keys-20260914.jsonl` in the main checkout). All three vendor Home presses in that capture were: release, `A2 00 2B` (Tab), release, `A2 08 0B` (GUI+H), release. AppSwitch and ControlBar start with the same Tab.
- **No record explains the Tab.** It arrived with the source import (`ee445d7`).
- **Context on C24C.** Full Keyboard Access is On, and its help lists Tab as "move forward".
  - AppSwitch (flag `02` + Up) and ControlBar (flag `02` + C) match FKA commands.
  - Command+H is a system shortcut, not an FKA command.
- **Hypotheses (untested):**
  - (a) the Tab wakes FKA's hidden focus ring, so the next key is not swallowed;
  - (b) it is an unneeded artefact.
- **Observed once live.** On 27 Sep at 15:48, Home typed a Tab into the open test note.

## Reproducible check: S9 (mock)

**What it is.** S9 (`tools/input-cleanup-harness`) validates **the HID reports the kernel emits** for the console's Home button (`/key/sendkey fn_key=Home`). It decodes them under a **simplified text-field model** (`HidText`, the kernel's `HidProtocol.Ascii` inverted): unmodified keys type, and keys with GUI are shortcuts. It uses the console's `ApiClient` and the real kernel code on a simulated board.

**What it is not.** It is not evidence of how iOS responds, whether it goes Home, or what a real field does.

| `--home-sequence` | Model field receives for `ab`, Home, `c` |
|---|---|
| `vendor` (default, release behaviour) | `ab\t[GUI+h]c`: the emitted Home includes a Tab |
| `command-h` (V1) | `ab[GUI+h]c` |
| `command-wake` (V2) | `ab[GUI+h]c` |
| AppSwitch / ControlBar (unchanged) | `\t[flag02+0x52]` / `\t[flag02+c]` (recorded for later) |

## Kernel option (test only; release default unchanged)

- **`--home-sequence vendor|command-h|command-wake`**, default `vendor`.
  - It is parsed before anything else. An invalid value exits with code 2 before any board is enumerated or opened (checked).
  - It changes only what `fn_key=Home` emits.
- **Every option still goes through the kernel's per-phone lease, its per-board write gate, Stop, and key and button release.**
- **No new endpoint.** There is no arbitrary-HID endpoint; `--hid-replay` is not used.
- **Status.** `/kernel/status` reports `home_sequence`, so a preflight can prove which Home a running kernel uses.
- **Kernel self-tests:** 96 pass, including 17 new ones:
  - the default is `vendor`, and invalid values are rejected;
  - each option emits exactly its reports;
  - Home without the phone's lease sends nothing, for each option;
  - a second command during Home is refused, not interleaved;
  - Stop cancels a `command-h` Home in progress and releases the mouse and keyboard.
- The original "Home reproduces observed Tab and GUI+H sequence" test still passes.

## Revised live method

The replay method proposed earlier is withdrawn. A console holding C24C's lease blocks other lease-aware controllers only. It would not serialise raw `--hid-replay` writes with kernel writes, and Stop could not cancel a replay.

### Why a test kernel, and exactly what differs from the release kernel

The release kernel's API cannot emit Command+H except through `fn_key=Home`, so V1 needs a kernel started with `--home-sequence command-h`.

The release kernel's PDB records a SHA-256 for every source file it was built from:
- 14 of its 16 kernel source files match this repository byte for byte (LF), `InputRouter.cs` included.
- The two receiver-management files, `AirplayProcess.cs` and `ReceiverFleet.cs`, match **no recorded version** in any branch or on disk. The test kernel therefore uses the repository's version of those two files.
- The test kernel's other differences are only this change: the Home option in `InputRouter`, its parsing in `Program`, and the `home_sequence` status field in `ApiServer`.

**Test kernel build:** `%TEMP%\claude\imouse-test-kernel-home\`. Hashes: `iMouse2.Kernel.dll` `83BBF441C5A6516C4B0C8EAAA5D998835F31ACDC0DE14CAD87D8D688C132843B`, `iMouse2.Kernel.exe` `162993B5504F00D7282866BC91E9BE4B3BCCA4A990DE41A37AD51E82302A45AF`. Self-test: 96 passed.

**Test kernel scope:**
- **C24C only:** `--input-pid C24C`.
- **Own data folder:** `%TEMP%\claude\imouse-test-kernel-home data\` holds copies of `devices.json` and `pointer-calibration.json`, and a `receivers.json` with only C24C (`iMouse2-C24C`, port 7110, the same name and port as release). The release configuration and its receiver logs are not touched.
- **Same address, 9913.** The release launcher then sees an unverified service on 9913 and refuses to start a second kernel or console. It stops nothing.

### The interruption, exactly

1. **Before:**
   - you stop using the PC;
   - a read-only preflight covers PIDs and paths, C24C identity, leases, and the operator settings hash;
   - the installed console is closed normally.
2. **Stop the release kernel (PID verified; currently 28776)** with `tools/kernel-window/Stop-ConsoleProcessGracefully.ps1`. It sends Ctrl+C to the kernel's hidden console; it was validated offline against a mock, including refusing a wrong path.
   - The kernel cancels input, releases keys and buttons, and ends both receivers it started (currently 13616 for C24C and 36456 for C241).
   - **Mirroring ends on both phones.** C24C's is already offline since about 16:59; C241's ends here.
   - If the kernel does not exit within 20 s, nothing is killed. The window stops there and the state is reported.
3. **Start the test kernel** (C24C only, `--home-sequence command-h`, same receiver executable and runtime). Verify that `/kernel/status` shows `home_sequence: command-h`, `allowed: [C24C]` and one receiver `iMouse2-C24C`.
4. **You re-select mirroring on C24C:** Control Center, Screen Mirroring, iMouse2-C24C.
5. **C241 has no kernel, receiver or input** for the rest of the window. It is untouched but unavailable.
6. **Trials** (below), through candidate console `b0708e3`:
   - launched by PID with isolated settings (`"trackPointer": false`), via the logging proxy;
   - C24C only.
7. **Restore:**
   - close the candidate;
   - stop the test kernel with the same helper, so its receiver ends;
   - run the release launcher (`Open iMouse 2.0.ps1`, `-CheckOnly` first). It starts the release kernel with its usual arguments (both phones and both receivers) and the installed console, which is not used;
   - verify the release kernel path, `home_sequence: vendor`, both receivers, both phones unowned, and the operator settings hash;
   - **you re-select mirroring on both phones.**

Estimated at 25–35 minutes. C241 is without service for about that long.

### Acceptance protocol (V1 = `command-h` first)

- **Dedicated disposable note.** Create it once, titled `Home test 27 Sep`, with a known body of `HomeTest line`. Record its baseline frame. Use no other note.
- **Home is pressed only with the console's Home button**, the real path. Frames are captured every 0.5 s around each press. The proxy logs each command's timing and result.

| Situation | Trial | Pass when |
|---|---|---|
| (a) Active text field | Open the note and put the caret at the end of the body, then press Home. Return to Notes | The Home screen shows within 2 s. On return, the note text is unchanged (crop compared with the baseline, and read visually) |
| (b) Settings | From a Settings list page, press Home | The Home screen shows within 2 s |
| (c) First press after idle | No input for 60 s or more with the note field active, then press Home once. Repeat from Settings | The first press goes Home, with (a)'s text check where the field was active |

- **Each situation runs at least 3 times.**
- **V1 is accepted only if every trial passes** and the repeated trials agree. A single success per situation would count only as preliminary.
- **Any failure stops V1:** record it and report.
- **V2 (`command-wake`) is tested only if V1 fails**, or if V1 gives a concrete reason. For example, V1 failing only after idle would point to hypothesis (a). Testing V2 means restarting the test kernel with `--home-sequence command-wake`, a C24C-only restart inside the same window. C24C's mirroring would need re-selecting once more.
- **After acceptance:** the release default changes in a separate reviewed step. S9 and the kernel self-test would then assert that Home emits no Tab.
