# Intermittent console click failures: investigation, 27 Sep 2026

**Status: CLOSED as unreproduced (27 Sep, by the user's decision). Cause undetermined; no fix made.** No further reproduction on the working desktop. Any future attempt belongs in the isolated environment (`analysis/isolated-test-environment-plan-20260927/`). The candidate is not promoted. Physical-phone testing was paused, and the rack was not used for input.

## Binaries

| Build | `iMouse2.dll` SHA-256 | `iMouse2.exe` SHA-256 | Embedded version | Built from |
|---|---|---|---|---|
| **Original candidate** | `E5A51FC6204566FA3B48C650FC239A42B158217D8045D2712850173980303AC3` | `2A0D5CB94AF84226269507C2442BAC3DDAE524DB6E1EED4306B7C2AF79945253` | `2.0.0+b0708e3db09…` | Commit `b0708e3`, clean |
| **Instrumented investigation build** (diagnostic only, never a candidate) | `EAE9D2C3BE8B2DA3E5CA4BF64F524D331FBDA8AEA9A058F6D6C029562FAC028F` | `7C78E3BDBE1D310C11EE7ED66DC1258FE58A33AE3903251936ABD68D22C37F0E` | `2.0.0+afdbba3aa00…` (misleading) | The uncommitted working tree at 21:03:10Z, while HEAD was `afdbba3`. Its `src/` equals `90f7a62`'s |

- Both builds are preserved under `binaries/` in the archive below, with `BINARIES.txt`.
- The instrumented build's version stamp names `afdbba3` only because that was HEAD when it was built. It also contains `InputTrace.cs`.

## What was being investigated

Ordinary clicks on the candidate console sometimes did nothing, in three live episodes:
- `b994de9`, check 3, 15:07–15:08: Activity ×2 and Resume ×3.
- `b0708e3`, FKA session, 16:04:50–16:07:24: Controls, Send text and Activity.
- `b0708e3`, FKA session, 16:08:25: Controls and Send text.
- A fourth, at 15:52, where clicking into the Send text box and typing left the drawer closed.

`afdbba3` concluded "inside the console". Part of its evidence was that plain `SendInput` clicks also failed.

## Correction to the afdbba3 evidence

**`SendInput` from this agent's shell injects nothing.** It returns 1, yet:
- a relative mouse move leaves the cursor where it was;
- a low-level mouse hook (`WH_MOUSE_LL`, `tools/click-probe/Watch-MouseButtons.ps1`) records no event.

In the same watch, the desktop tool's clicks are recorded (injected, down and up in the same millisecond). `SetCursorPos` does work, which is why the probes looked normal.

So the `afdbba3` statement "plain SendInput clicks failed too" does not show anything about the console. With it gone, nothing demonstrates that the failed clicks stopped inside the console.

Ruled out for the shell: integrity level (every process involved is High), and job UI restrictions (the shell's job has none).

## Reproduction attempts (mock kernel, isolated settings)

**Setup.**
- The exact `b0708e3` executable (`imouse-candidate-5`, hashes as recorded), then an instrumented build of the same code.
- Data folders `imouse-candidate-5 data\mock-clicks` and `…\mock-clicks-trace`, each with `"trackPointer": false`.
- The mock is `input-cleanup-harness --serve 9951`. Its board list is answered by a front listener, so nothing enumerates real boards (see Incidents).
- Commands went through the fault proxy on 9955 and are logged.

**Scripted `SendInput` loop.** It "failed" on the first iteration every time: no command ever reached the proxy, and the console received no button message. That is the injection artifact above, not a reproduction.

**Desktop-tool clicks, traced end to end.** An opt-in trace (`IMOUSE_INPUT_TRACE`, `src/iMouse.Console/InputTrace.cs`) logs:
- the window's raw mouse messages;
- every input WPF stages, with `Mouse.Captured` and `DirectlyOver`;
- routed-event receivers and their handled state;
- capture changes, `Click` entries, and the hit-test chain.

A system-level hook ran alongside. The sequences replayed:
- the FKA search-trial rhythm (Close, Reset, Cancel tap, Reset, field tap, a shell command, Controls, Send text), with screenshots and zooms between clicks as live;
- the check-3 sequence (answer to a tap withheld by the proxy, lease expiry, tap while paused, Activity, Resume);
- clicking into the Send text box and typing;
- a 10 fps static mock frame, then 30 fps changing frames like live video.

**Result.** 47 clicks were recorded by the system hook, and 47 `WM_LBUTTONDOWN` reached the console. WPF staged every one, and all 35 clicks on buttons raised `Click` (the other 12 were preview taps). Every drawer opened, Send text was sent, and Resume worked on the first click. **No failure occurred.**

## What remains possible (not tested)

- **Delivery by the desktop tool.** The tool manipulates windows. Observed today:
  - it minimized the diagnostic console while that executable was not granted;
  - when the installed console was frontmost, it delivered a click to that console instead.
  - A live episode could have been a click delivered elsewhere, or not delivered.
- **A console-side condition** not present on the mock (real video timing, the real kernel's latencies). This is still possible but has no evidence.
- **A window-state oddity seen once.** After the candidate was moved between monitors, UIA reported it Maximized while its bounds were still the restored rectangle, and it did not fill the screen until set to Normal and back.

A live episode captured with both the input trace and `Watch-MouseButtons` running would show at which stage the click stops. Run it only once physical testing resumes.

## Incidents during this investigation (no phone input)

1. **The first loop's clicks targeted the installed console.** The candidate had opened on the second monitor, so the points were over the installed console. Those clicks were never injected (the `SendInput` artifact), so they had no effect. The loop now refuses to click unless the window under the point belongs to the target process.
2. **One desktop-tool click opened the installed console's Controls drawer** (17:06:05), because that console was frontmost.
   - That click sent nothing to a phone.
   - C24C stayed at generation 8 and C241 at generation 1, both unowned, throughout.
   - The installed console was then closed normally (17:07:36) for the rest of the mock work, and relaunched from the release folder at the end without being used.
3. **Real boards were enumerated.** The mock's internal ApiServer first took port 9942, which a proxy was also using. http.sys routed `/api/` straight to the ApiServer, so for a few minutes its board list was enumerated from the real USB boards (read-only handle opens; nothing written). The mock now picks a free internal port.
4. **C24C's AirPlay mirroring was found offline** at about 16:59. The receiver (36456) was still running and not restarted. The phone was last seen mirroring at 16:16:12, and auto-lock is the likely cause. It was not touched.

## Changes in this revision

- `src/iMouse.Console/InputTrace.cs`, plus one call in the `MainWindow` constructor: diagnostic only, and inert unless `IMOUSE_INPUT_TRACE` is set.
- `tools/input-cleanup-harness/Serve.cs`:
  - answers `/config/usb/get` with the simulated board;
  - uses a dynamic internal port;
  - `--serve PORT [BOARDPID]`, board `F001` by default;
  - 30 fps changing frames.
- New in `tools/click-probe/`:
  - `Watch-MouseButtons.ps1` (system-level button hook);
  - `Get-IntegrityLevel.ps1`;
  - `Repro-ClickLoop.ps1`, with a target-window guard and the `SendInput` caveat.
- No behaviour change to the console, phone settings, HID, Home or pointer movement.
- Tests on this revision's console: `--self-test` 191 passed, `--ui-test` 151/151, harness S1–S6 passed. The kernel was not changed.

## Evidence

- `iMouseXP-2.0-evidence-archive/20260927-console-click-investigation/`, with `SHA256SUMS.txt` (32 files, verified). It holds the input trace (3,139 lines), the system-hook logs, the proxy logs, the loop logs, the session scripts, and both builds under `binaries/`.
- The `afdbba3` evidence (`20260927-fka-space-loss-b0708e3/`, 217 files) was re-verified intact before starting.
