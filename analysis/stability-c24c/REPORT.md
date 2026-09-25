# C24C 45-minute stability — 14 September 2026

Build: `release/iMouse2-kernel-verified` (kernel 39096) +
`release/iMouse2-independent` (console 16672) + UxPlay 13412.
Phone `86:1D:4A:04:2F:F6` / board C24C / UID C24CBFBD only.
Duration 2710 s (45.2 min), 16 cycles at ~3 min. No code changes during the run.

## Result

All 16 cycles passed. No input failures, no frame stalls, no receiver restarts,
no PID changes, no other boards addressed.

| Signal | Observation |
|---|---|
| Live video | `live:true` every cycle; frames 14285 → 70145 (~3700 / 3 min, ~20.5 fps) |
| Home | Returned to page 1 each cycle |
| Single Search click (250,900) | Spotlight every cycle (MAD 76.6–78.7) |
| Swipe left / right | Page 2 then back (left MAD ~30.8; back MAD 1.3–1.8) |
| Pointer drift | Search still hits Spotlight on cycle 15; swipe restores page 1 |
| Receiver restarts | Stayed at 1 (from the earlier crash test) |
| Kernel WS | 74.1 → 78.9 MB |
| Console WS | 190 → 180 MB |
| UxPlay WS | 85.3 → 94.7 MB (slow climb, no leak spike) |

Shots: `analysis/stability-c24c/shots/`. Raw log: `run.jsonl`. Numbers: `summary.json`.
Spot-check of cycle 15: Home Screen, Spotlight, and the second Home page match the
gestures. Clock 2:31 → 3:16, so the stream was not frozen.

## Two-phone readiness

**Yes, for a controlled two-phone test of HID + bind/calibration — not a rack
cutover.**

This build is stable on one portrait phone for 45 minutes. A second phone still
needs its own calibration, its own allowed PID, and (for video) a second
receiver/pipe: this kernel still has one UxPlay session. Recast after a helper
crash remains manual. Do not enable Mirror-to-all or the other 17 boards yet.
