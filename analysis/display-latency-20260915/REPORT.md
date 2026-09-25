# Displayed FPS and input-to-visible — 15 September 2026

Candidate console, two-phone kernel, and both independent receivers stayed up.
C24C and C241 only. Mirror-to-all off. No application performance changes.
No new instrumentation: existing FrameStatus / RateMeter / JitterMeter were
enough once the Activity drawer was open.

## Why FrameStatus was empty

`FrameStatus` lives in `ActivityPane`, which is `Visibility=Collapsed` until
Activity is opened. UI Automation does not see it while collapsed (`exists=False`).
Invoking `ActivityButton` made it appear:

`Live · 19.8 fps · 500 × 1080 · … · 48/78 ms p50/p95`

The ABAB compare harness never opened Activity. That was a probe bug, not a
missing metric. `UpdateFrameStatus` already runs on the UI thread every 8
presented frames (`RateMeter` over 2 s, `JitterMeter` p50/p95, slow > 45 ms).

## Process identities (verified)

| Role | Path | PID |
|---|---|---|
| Console | `release/iMouse2-two-phone-candidate/iMouse2.exe` | 13320 |
| Kernel | `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` | 32328 |
| C24C UxPlay | `tools/airplay/uxplay/build-imouse/uxplay.exe` | 20972, restarts 0 |
| C241 UxPlay | same | 33972, restarts 1 (unchanged) |

## Displayed vs received (~18 s, Home screen)

Received = kernel per-receiver frame counters. Displayed = Activity FrameStatus
(`_rate.Fps` of frames actually presented on the master).

| Master | C24C received | C241 received | Displayed mean (min–max) | Displayed p95 |
|---|---:|---:|---|---|
| C24C | 20.29 | 17.94 | 20.37 (19.8–21.0) | 70–72 ms |
| C241 | 20.03 | **12.62** | **15.48 (3.5–23.6)** | **71–675 ms** |

When C24C is master, displayed ≈ received ≈ 20 FPS. When C241 is master, its
received rate falls to ~12.6 FPS and the on-screen meter swings; C24C’s received
rate stays ~20. The bottleneck is on the C241 master path (full 500×1080 BMP
pump vs JPEG tile), not a global 30 FPS request.

## Input-to-visible (API vs first change vs settled)

Concurrent screenshot polls during the command. Isolation: other-phone MAD
0.02–0.07.

| Phone | Action | API ms | First visible ms | Settled ms |
|---|---|---:|---:|---:|
| C24C | Home (from Spotlight) | 357 | 403 | 584 |
| C24C | Search (after Home) | 2999 | 3159 | 3395 |
| C24C | Swipe left | 3041 | 2043 | 2196 |
| C241 | Home | 340 | 433 | 632 |
| C241 | Search after Home, C241 master | 3014 | *no visual* | *miss* |
| C241 | Swipe left | 3064 | 3369 | 3492 |
| C241 | Search after Home, **C24C master** | 3022 | (spot MAD 49.7) | n/a |

Home is ~340 ms HID + ~60–90 ms until the picture moves + ~180 ms to settle.
That matches the earlier Home-only study. Search/swipe after Home take ~3 s at
the API; the first visible frame tracks the API, so this is **input delivery**,
not a 3 s video lag. Home sets `Known=false`, so the next pointer action resets
and walks. A C241 Search missed while C241 was master (stuttering stream);
the same Search succeeded when C24C was master.

## Recommendation

**Next optimization:** C241’s master-view frame path — keep the UxPlay pipe
reader from stalling while the console copies 500×1080 BMPs (lock/copy/backpressure).
Do not cut click/Home settle delays until that stream is stable as master.

Second, separately, the ~3 s click-after-Home HID walk. Do not paper over it
with a second Home.

This is not vendor speed parity: no matched vendor-console window was run.
Activity must be open to read displayed FPS from the existing UI.

Raw: `results.json`. Methods: `tools/read_ui.ps1`, `tools/measure_display_latency.py`.
