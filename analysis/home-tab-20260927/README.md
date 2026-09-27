# Home inserts a Tab into an active text field: 27 Sep 2026

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
