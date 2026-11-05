# Scale gate on rack B home screens, 4–5 Nov 2026

Scale gate lane, branch `sb/chat-scale-gate`. Evidence for release gates 8 (predictable group
control) and 11 (full-rack operation) at the 8-phone stage and at the largest stage rack B could
offer today. Every phone was on its home screen throughout, and nothing this harness sends can
open an app.

## Result

| Gate stage | Verdict |
|---|---|
| **8 phones** (one kernel, 13 phones leased: 8 in the group, 5 as isolation controls) | **Pass** for mirroring, per-phone and group input delivery, landing accuracy, isolation, leases and stop/cancel. Still open under gate 8: an unreachable group member not blocking the others, and the console's visible group/mode indicator. Neither was in this lane's scope |
| **19 phones** | **Not run: 13 of 19.** B6 and B19 mirrors were stalled before the lane started; B3, B7, B10 and B17 are not connected; B5 belongs to the Small phone lane. On the 13 live phones: 0 isolation failures, every command acknowledged, every landing confirmed except one unexplained single-phone landing ~40 px off |

Line for the tracker: **Scale gate: 8-phone stage passed on rack B home screens (pointer input,
group dispatch, isolation, leases, stop: 0 misses, 0 isolation failures in 442 checks, frame age
≤ 0.62 s). 13 of 19 run (B6/B19 mirrors stalled; B3/B7/B10/B17 not connected): 0 isolation
failures, 1 unexplained landing ~40 px off in 234. The 19-phone run needs those 6 phones live.**

## Setup

- Kernel `http://127.0.0.1:9916` (direct HID, input leases required), shared with the
  Repeatability (A17, A20), Scheduler (A18) and Small phone (B5) lanes, all live throughout. That
  is realistic load, not a fault. Other receivers live during every run: 6 (A17, A18, A20, B5,
  plus B6/B19, which report "live" but have stalled frames).
- Phones: rack B, 4.7-inch (iPhone 6s/7/8/SE 2nd), frame 500×1080 letterboxed from y 95,
  calibration 5.61 px per unit. Slots used: B1, B2, B4, B8, B9, B11, B12, B13, B14, B15, B16,
  B18, B20. The receiver name and board for each slot are checked against `rack-b-slots.json` and
  the kernel's device list before anything is sent.
- **Input used**: `/mouse/reset`, `/mouse/move` (pointer moves with no button) and Home (vendor
  sequence, at most once per phone per 3 s, two per run). The client refuses clicks, button
  down/up, swipes and every other key, and refuses any target outside the named slots
  (`test_scale_gate.py`). Before and after each phase every phone's frame is compared with its
  preflight home-screen frame. The largest change seen was 0.13% of the screen (threshold 4%).
  **No app, App Switcher, Control Center or Spotlight opened on any phone.**
- Measured: frame age (`X-iMouse-Frame-Age-Ms`) on every capture; the pointer dot found in fresh
  frames (round blob ~25 px; clock hands and the status bar are masked); the PC's CPU and
  `/kernel/status` response time every 2 s; lease renewals every 6 s (30 s leases).
- Captures stay in `output/scale-gate-20261104/` (not committed). `results/*.json` are the
  committed summaries: slots, codes, timings, landing errors. They hold no frames and no device IDs.

## Preflight (read-only, 4 Nov 21:0x local)

16 of rack B's 20 receivers report mirroring. With B5 excluded, that leaves 15. **B6 and B19 are
stalled**: the receiver says "mirroring/live", but frame delivery is "quiet", the newest frame was
~3.0 h (B6) and ~3.5 h (B19) old, and the sequence did not advance over 2 s while the other 13
advanced at ~30 frames/s. Both were left alone with no input, per the lane rules. They were still
"quiet" after the last run. The other 13 were all on home page 1 (checked by eye on a contact sheet).

## 8-phone stage

Group = B1, B2, B4, B8, B9, B11, B12, B13. Controls = B14, B15, B16, B18, B20. Every run: one
atomic acquire for all 13, lease tests, group Home, reset, then 13 single-phone moves (each
watched on all 12 other phones), then 13 group moves (8 phones, one command each, 5 controls
watched), group Home, release.

| | run 2 | run 3 |
|---|---|---|
| Single-phone moves: acknowledged / landed | 13/13 / 13/13 | 13/13 / 13/13 |
| Group deliveries (13 commands × 8): acknowledged / landed | 104/104 / 104/104 | 104/104 / 103 + 1 by eye |
| Landing error, settled frame (px): median / p95 / max | 3.6 / 5.0 / 5.8 | 3.6 / 5.4 / 8.5 |
| Isolation checks (single-phone + group controls) / failures | 221 / **0** | 221 / **0** |
| Group command round trip (ms): median / max | 479 / 1112 | 467 / 2161 |
| Move complete → first frame with the dot (ms), group: median / p95 | 589 / 1216 ¹ | 156 / 453 |
| Move complete → first frame with the dot (ms), single: median / p95 | 188 / 490 | 74 / 315 |
| Arrival spread across the 8 (ms): median / max | 339 / 856 ¹ | 317 / 1226 |
| Frame age at capture (ms): median / p95 / max; over 1.5 s | 23 / 65 / 598; 0 | 23 / 65 / 622; 0 |
| PC CPU %: median / max | 39 / 81 | 62 / 85 |
| `/kernel/status` (ms): median / p95 / max | 12 / 27 / 330 | 21 / 481 / 1369 |
| Lease renewals: ok / min remaining before renew | 7/7 / 23.9 s | 7/7 / 23.6 s |

¹ In run 2 each phone was polled to its settled frame before the next phone was polled, so later
phones' arrival times include that wait. Run 3 polls round-robin, so its spread and arrival times
are bounded by one sweep of 8 screenshots (~0.3–0.4 s). Treat the spread as an upper bound.

The one group landing in run 3 that the detector could not confirm (B9, round 9) shows the dot on
target in its frame, over a pale icon label where it has little contrast.

**Lease behaviour under load** (every run): acquiring 13 phones atomically took 2–9 ms. A second
acquire on a held phone was refused (409, "owned"). A move with a wrong token was refused (409)
and left the lease, generation and stop state unchanged. Release revoked all 13 tokens, nothing
stayed owned, and a move on a released token was refused (409).

**Stop/cancel** (`results/gate8-cancel1.json`): a group move of the 8 phones from the top-left
corner to (390, 880) was stopped 251 ms in. `/input/stop` returned in 11.5 ms with "Input
released; previous tokens revoked". All 8 walks returned 499 "Input cancelled" 12 ms after the
stop. Every pointer halted at the same point on the walk line, (78, 252), well short of the target,
and nothing moved in the following 2 s (no replay). `/input/resume` then a new lease and a group
move all succeeded, and the screens were unchanged.

Run 1 (`results/gate8-run1.json`) is kept for completeness but is not counted. Its detector took
the first frame showing the dot near the target, which caught pointers still walking in (errors
up to 42 px on the approach side). Landing is now measured on a frame at least 250 ms after the
move completes. That change was made before runs 2 and 3. Run 1 also had 0 isolation failures
and 117/117 acknowledgements.

## Largest stage: 13 of 19

All 13 live phones in the group (no controls inside the set, so isolation here comes from the
single-phone phase: each move watched on the other 12). 8 group rounds per run.

| | all13 run 1 | all13 run 2 |
|---|---|---|
| Single-phone moves: acknowledged / landed (detector) | 13/13 / 12 + 1 by eye | 13/13 / 11 + 1 by eye + **1 unexplained** |
| Group deliveries (8 commands × 13): acknowledged / landed (detector) | 104/104 / 101 + 3 by eye | 104/104 / 102 + 2 by eye |
| Landing error, settled frame (px): median / p95 / max | 3.6 / 5.0 / 9.0 | 3.6 / 5.0 / 9.0 |
| Isolation checks / failures | 156 / **0** | 156 / **0** |
| Group command round trip (ms): median / max | 542 / 1823 | 534 / 1115 |
| Move complete → first frame with the dot (ms), group: median / p95 | 164 / 1071 | 123 / 445 |
| Arrival spread across the 13 (ms): median / max | 447 / 2476 | 422 / 1640 |
| Frame age at capture (ms): max; over 1.5 s | 943; 0 | 507; 0 |
| PC CPU %: median / max | 60 / 69 | 63 / 82 |
| `/kernel/status` (ms): median / p95 / max | 13 / 513 / 1374 | 13 / 38 / 199 |
| Lease renewals ok | 7/7 | 8/8 |

"By eye": the detector found no dot on the settled frame. The saved frame shows the dot on
target with low contrast: B18's grey-purple dock and pale folder label, B4's dark wallpaper. These
were B18 ×5 and B4 ×2 across both runs.

**Unexplained**: in all13 run 2 the single move to B12 at (250, 190) settled with the dot at
(214, 173), ~40 px off, and never came within 15 px in 18 polls. Its frame was not kept: the
harness saved frames only when no dot was found. It now saves every frame whose landing it cannot
confirm. B12 landed within 5 px at the same target in every other run. Treat this as one
unconfirmed landing until it is reproduced or ruled out.

A sweep of 13 screenshots takes ~0.5 s, so the 13-phone spread and arrival times are coarser
than the 8-phone ones. The kernel's screenshot limiter is shared with the other lanes, and this
lane polled from a single thread.

## What the 19-phone run still needs

1. **Six more rack B phones mirroring with fresh frames.** B6 and B19 need their stalled mirrors
   recovered (a recast or receiver restart: Rack lane or orchestrator), and B3, B7, B10, B17 need
   connecting. With B5 kept for the Small phone lane, that makes exactly 19 (B1–B20 without B5).
2. Run `scale_gate.py run --slots <19> --group <19>`, and the 8-phone group with the other 11 as
   controls. No code change is needed. The sweep resolution grows to ~0.75 s at 19, so add a
   second polling thread only if the kernel's screenshot limiter has room (other lanes share it).
3. Still out of this lane's scope: clicks (the gate 6 500 ms figure is click-to-visible, from
   the console), an unreachable member not blocking a group, the console's group UI, and endurance
   at 19 phones.

## Files

- `scale_gate.py`: the harness (`preflight` read-only, `run` group test, `cancel` stop test).
- `test_scale_gate.py`: 17 offline tests (slot and command guards, Home spacing, per-phone
  tokens, dot detection, sweep polling).
- `summarize.py`, `show_run.py`: turn a run under `output/` into `results/<run>.json` / print it.
- `results/`: preflight, gate8 runs 1–3, gate8-cancel1, all13 runs 1–2.
