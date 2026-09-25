# Click-candidate validation B — 15 September 2026 — **not promoted**

Preserving `Known` across Home caused **reproducible C241 targeting misses**.
Previous behavior restored: running kernel is again
`release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` (PID 28896). Recast both
phones to iMouse2-C24C / iMouse2-C241.

## Builds

| Role | Path |
|---|---|
| Failed candidate (do not use) | `release/iMouse2-kernel-click-candidate/iMouse2.Kernel.exe` |
| Restored kernel (running) | `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` |
| Console | `release/iMouse2-two-phone-candidate/iMouse2.exe` PID 13320 |

Source `InputRouter` Home again sets `Known=false`. Timing logs remain in
source (`ClickAsync`) for diagnosis; 34 self-tests passed after the revert.

## Same-spot Home → Search → Home (visual Spotlight)

| Phone | Spotlight | Miss | API ms |
|---|---|---|---|
| C24C | **10/10** | 0 | 232–262 (pointer already at Search) |
| C241 | **7/10** | **3** (cycles 00, 04, 06 — FaceTime selected) | 206–237 on 0-step clicks |

C241 misses were 0-step clicks (`Known=true`, believed at 250,900) while the
iOS pointer was on FaceTime. That is exactly the failure mode of not
invalidating after Home / a missed tap.

Isolation: other phone stayed on Home (`*-cycle00-other.bmp`).

## Off-location then Home then Search

| From | C24C | C241 |
|---|---|---|
| 80,140 | Spotlight | Spotlight |
| 400,200 | Spotlight | Spotlight |
| 120,500 | Spotlight | **miss FaceTime** |
| 360,760 | Spotlight | **miss FaceTime** |

Together with run A’s C241 loc3 FaceTime miss, this is **reproducible**.

## Video during the candidate run

Both live, restarts 0, until we stopped the candidate to roll back.

## Rollback (already applied)

1. Stopped click-candidate kernel 24780.
2. Started `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` (28896) with
   the two-phone `--data-dir` / `--receivers` / UxPlay args.
3. Recast **iMouse2-C24C** and **iMouse2-C241**.

Long-distance 1-unit walks remain ~2.5 s; that is separate. Fast same-spot
Search is not worth C241 clicking FaceTime.

Shots: this folder. Prior run A: `../click-candidate-validate-20260915/`.
