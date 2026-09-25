# Home → Search ~3 s — 15 September 2026

Video path unchanged. Running two-phone kernel was left on disk as rollback
(`release/iMouse2-kernel-two-phone`). Candidate:
`release/iMouse2-kernel-click-candidate/iMouse2.Kernel.exe`.

## Before (kernel 32328, two-phone build)

Process identities at measurement: console 13320, kernel 32328, UxPlay 20972 /
33972. Mirror-to-all off. C24C and C241 only.

| Phone | Action | API ms | Notes |
|---|---|---:|---|
| C24C | Home | 354 | Tab + GUI+H |
| C24C | Home then click 20,20 | 334 | reset + ~0 steps + settle 120 + hold 80 |
| C24C | Home then Search 250,900 | **3014** | Spotlight **opened** |
| C24C | Search again, no Home | **259** | pointer already there |
| C24C | Move 80,140, no Home | 2549 | ~150 HID units from Search |
| C241 | Home | 324 | |
| C241 | Home then click 20,20 | 310 | |
| C241 | Home then Search 250,900 | **3041** | **Home screen — miss** |
| C241 | Search again, no Home | 221 | still Home |
| C241 | Move 80,140, no Home | 2546 | |

Home sets `Known=false`. The next click corner-resets and walks 1 HID unit per
report with `Task.Delay(3)` plus `WriteAsync`+`FlushAsync`. Search is ~173 units
from origin → ~3 s. Queue wait is not the cost (Home-only is 350 ms). Settle
and button-down are the 220–260 ms leftover when `steps=0`.

Home does not need to forget the pointer: AssistiveTouch stays put. Invalidating
`Known` was avoidable. Calibration, 120 ms settle, 80 ms hold, and 3 ms step
delay were not changed. HID packets unchanged.

## Candidate

`release/iMouse2-kernel-click-candidate` — Home no longer clears `Known`.
Stage log line: `click pid=… known= reset= steps= send= delay= settle= button= total=`.
36 kernel self-tests passed.

Kernel swap dropped AirPlay. Recast both phones to **iMouse2-C24C** and
**iMouse2-C241**, then run `python tools/verify_click_candidate.py`.
Current candidate kernel PID 24780, UxPlay 9936 / 29764, `live:false` until recast.
The previous two-phone kernel remains at `release/iMouse2-kernel-two-phone`.
