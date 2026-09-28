# Lower-screen taps stopping at y ≈ 783: offline investigation, 27 Sep 2026

**Result.** The software path is not where the cut-off happened. In the 27 Sep FKA session (`analysis/fka-space-loss-20260927`, finding 2):
- the kernel was asked for y ≈ 783 each time, and the pointer went exactly there;
- the console computed y ≈ 783 from where the Windows cursor actually was;
- the cursor, positioned by the agent's desktop-automation tool, never got below one fixed screen line after the first tap.

**No product defect was found, and no product change is made.**
- What held the automation cursor at that line is not established.
- Physical accuracy at the bottom of the screen has not been re-tested since.

Nothing live was touched for this: no phone, kernel, receiver, console or setting.

## Coordinate path (code as built)

1. **Console preview to image pixels.**
   - `MainWindow.MapPreview` → `CoordinateMapper.Map` (`src/iMouse.Console/ApiClient.cs`).
   - Uniform-scaled `Image`, letterbox margins excluded. Default space "image pixels" (`CoordSpace` index 0), so the target is 500 × 1080.
   - A press outside the picture is rejected, not clamped. `MapClamped` is used only for a drag in progress.
   - The tap uses the **mouse-down** point (`EndGestureAsync` → `/mouse/click`).
   - The hover readout uses the same `MapPreview`, so the readout is the coordinate a click at that point sends.
2. **Kernel validation.** `InputRouter.ValidatePoint` rejects x ≥ 500 or y ≥ 1080 with an error. It never clamps; every short tap in the session returned code 0.
3. **Calibration** (`analysis/two-phone-config/pointer-calibration.json`, C24C): origin 14, 14; 5.12 / 5.09 px per unit.
   - `tx = round((x − 14) / 5.12)`, `ty = round((y − 14) / 5.09)`, floored at 0, with no upper clamp.
   - y 1079 → 209 units; y 783 → 151 units.
4. **HID movement.**
   - When the position is unknown (after Home, AppSwitch, ControlBar, any failure, or the first command), the kernel resets first: 4 × `A1 00 81 81`, that is (−127, −127) each, 508 units toward the top-left corner.
   - It then walks one unit per report, `max(|dx|, |dy|)` reports, with no speed or distance limit.
   - `/mouse/reset` does the same corner reset.
   - The position is an estimate of transmitted steps, not an acknowledgement from iOS.
5. **Orientation and size.**
   - Both phones report 500 × 1080 image and 414 × 896 points, rotate 0. Portrait throughout the session.
   - The console refuses a tap if the orientation changed between press and release.

## Evidence review (FKA session, 15:48–16:02 EDT)

- **Sources:** `iMouseXP-2.0-evidence-archive/20260927-fka-space-loss-b0708e3/` (`proxy-log.jsonl`, `frames/`) and the agent's session transcript (desktop-automation click coordinates and console readouts).
- **Pointer positions** were found by locating the pointer dot (grey disc, about 22 px) in every saved frame.
- **Step counts** come from click durations. The proxy log records timing, not coordinates.
  - Per-step time was derived from the one tap whose target is certain: 15:48:26, the dock at (310, 1002) after Home. It took 2003 ms, which is reset about 50 + 194 steps + settle/button about 205, so about 9.0 ms per step.
  - A click with no movement takes 205–207 ms in the same log.

| Click (EDT) | ms | Steps implied | Implied target y | Automation click, preview y (image y it maps to) | Pointer in next frame |
|---|---|---|---|---|---|
| 15:48:26 (after Home) | 2003 | 194 (reset + move) | 1002 | 458 (≈ 1000) | (310, 1002), `nav-01` |
| 15:49:19 (from 10, 14) | 1438.6 | 137 | 783 | 428 (≈ 921, Accessibility) | (163, 783), `nav-03` |
| 15:49:55 (after Reset) | 1566.5 | 151 | 783 | 428 (≈ 921) | (163, 783), `nav-05` |
| 15:54:33 (after Reset) | 1568.9 | 151 | 783 | 462 (≈ 1010, compose) | (458, 783), `on-notes1-c-new` |
| 15:55:46 (from 10, 14) | 1440.7 | 137 | 783 | 462 (≈ 1010) | (249, 783), `probe-01-bottom` |
| 16:01:10 (after Reset) | 1565.7 | 151 | 783 | Settings dock icon (≈ 1002, per the session notes) | (310, 783), `on-S1-a-open` |

Observed:
- **The kernel was sent y ≈ 783 for every short tap.** Independent clicks, with and without a preceding Reset, all imply ty = 151 units: 783 ± 2.5 px. None implies 178 (y 922), 194 (y 1002) or 196 (y 1012).
- **The pointer landed exactly on the sent coordinate** each time, in both axes. The x values (163, 249, 310, 458) match the intended targets.
- **The cut-off was on the Windows cursor.**
  - When the automation tool placed the cursor over the compose icon (preview y 462), the console's own readout said "x 457, y 784 — click to tap here".
  - Minutes later, `hover-map.ps1` placed the cursor at the same preview y with `SetCursorPos` and the readout said image y 1009.
  - So the console mapped correctly both times; the cursor was not where the automation tool was asked to put it.
- **The line is fixed on screen.** Image y 783 is preview y ≈ 375 in the tool's screenshot frame, about 989 physical pixels at the 2.637 scale. It held from about 15:48:46 onward; the first click at 15:48:23 was not affected.
- **Nothing in the console confines the cursor.** There is no `ClipCursor` or `SetCursorPos` in `src/`; `CaptureMouse` does not clip.

Not established:
- What held the automation cursor at that line. Candidates are a cursor clip set by another process, or the tool's coordinate handling. The console had no input trace running then (`IMOUSE_INPUT_TRACE`).
- Whether a person's physical mouse, or the API directly, reaches the bottom rows now. Only the first automated tap and the 7 Sep / 10 Sep hardware checks (`analysis/HARDWARE.md`) show bottom-area landings.
- Whether iOS pointer acceleration or an edge limit matters near y 1079. The session never delivered a coordinate below 1002 to the kernel.

## Mock checks

Added to the kernel self-tests (`src/iMouse.Kernel/SelfTests.cs`, recording transport, no HID opened):
- **"Clicks down to the bottom row emit the full calibrated movement after a reset":** targets (310, 1002), (163, 922), (458, 1012), (249, 1079), (163, 783). The summed relative steps after the corner reset equal the calibrated units exactly: y 1079 gives 209 units.
- **"Chained lower-screen clicks from a known position end at the last target's units":** the same targets in sequence after one reset, so the estimate stays consistent.

All 98 self-tests pass (built to `%TEMP%\claude\imouse-kernel-selftest-lower`, not the release). **This shows the emitted reports only. It is not evidence of where iOS puts the pointer.**

## Proposed short test (C24C only, current release, no restart; not approved)

This uses the running release kernel and receivers as they are. It takes about 5 minutes and is move-only, so nothing is tapped.
1. Preflight, read-only: kernel and receiver PIDs, C24C unowned, `live` true.
2. Acquire C24C's lease through the API.
3. `/mouse/reset`, then `/mouse/move` (no click) to (250, 922), (250, 1012) and (250, 1070). Take one frame after each move and locate the pointer dot.
4. Release the lease. C241 is not addressed.

This separates the software and phone path from the desktop-automation path:
- Pointer at the requested y each time: the kernel and phone reach the bottom rows. The 27 Sep stop was purely the automation cursor.
- Pointer short of it: the phone or calibration is implicated.

An optional second part is read-only on the console:
- The desktop-automation tool hovers over the preview's lower area, with no click, and the console readout is read.
- This would show whether the automation cursor is still held at a line.
- It needs desktop control of a console, so it is listed separately.
