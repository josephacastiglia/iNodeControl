# Click-candidate validation — 15 September 2026

**Do not promote.** Rollback remains the two-phone kernel.

| | Path | PID this run |
|---|---|---|
| Candidate kernel | `release/iMouse2-kernel-click-candidate/iMouse2.Kernel.exe` | 24780 |
| Rollback kernel | `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` | (not running) |
| Console | `release/iMouse2-two-phone-candidate/iMouse2.exe` | 13320 |
| C24C UxPlay | `tools/airplay/uxplay/build-imouse/uxplay.exe` | 9936, restarts **0** |
| C241 UxPlay | same | 29764, restarts **0** |

Change: Home no longer sets `Known=false`. Calibration, 3 ms step delay, 120 ms
settle, 80 ms hold, and HID packets are unchanged. Video path unchanged.

## Before (old kernel 32328)

Home → Search 250,900: **C24C 3014 ms Spotlight**, **C241 3041 ms miss (Home)**.
Search again without Home: **259 / 221 ms**.

Kernel logs on the candidate show why: first click after a cold start is
`known=False reset≈70ms steps=174 send≈187ms delay≈2350ms settle≈125ms button≈95ms total≈3000ms`.
Later same-spot clicks are `steps=0 settle≈125 button≈95 total≈220ms`.

## 10× Home → Search → Home (visual Spotlight)

| Phone | Spotlight | API ms (cycle 0 / cycles 1–9) | Shot after click |
|---|---|---|---|
| C24C | **10/10** | 2947 / **234–262** | ~750 ms |
| C241 | **10/10** | 3036 / **234–266** | ~740–790 ms |

No double-click pattern (Spotlight once per click, then Home). Isolation:
other phone stayed on Home (`C24C-cycle00-other.bmp` is C241 Home,
`C241-cycle00-other.bmp` is C24C Home). Inspected cycles 00,01,02,03,05,07,08,09
on both phones: Siri Suggestions + Search field.

## Home → Search after other locations

Click a different Home-screen point, Home, then Search 250,900.

| From | C24C Search | C241 Search | API ms (walk) |
|---|---|---|---|
| 80,140 | Spotlight | Spotlight | ~2540 |
| 400,200 | Spotlight | Spotlight | ~2380 |
| 120,500 | Spotlight | Spotlight | ~1450 |
| 360,760 | Spotlight | **miss — FaceTime selected** | ~670 |

C241 loc3: after-move pointer was already near Search; kernel still believed
(360,760). Home then a relative walk to (250,900) from the wrong origin landed
on FaceTime. That is one targeting error after a missed intermediate click, not
a 10-cycle Home→Search failure.

## Video

Both receivers stayed `live:true`. Restarts stayed 0. Frames C24C 2297→6349,
C241 2057→5576 during the run.

## Promotion

Not promoted. Reasons: (1) user asked not to until these checks pass as a
set; (2) one C241 off-location miss; (3) long-distance walks still ~2.5 s
(`delay≈13.5 ms/step` × N, separate from this fix).

Rollback: stop the candidate kernel, run `Start Two Phone Test.ps1` so
`release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` owns 9913, recast both
phones to iMouse2-C24C / iMouse2-C241.

To keep testing the candidate: leave 24780 running; recast is already done.

Shots: `analysis/click-candidate-validate-20260915/`. Timing lines:
`analysis/click-after-home-20260915/kernel.out.log`.
