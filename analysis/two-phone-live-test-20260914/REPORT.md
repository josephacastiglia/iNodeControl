# Controlled two-phone test — 14 September 2026

## Result

Core two-phone video and isolated input checks passed on the current build.
The monitoring run lasted 12 minutes: 22:26:17–22:38:16 EDT, 144 samples spanning
718.85 seconds. The final read-only snapshot at 22:38:55 still showed both live.
The user subsequently confirmed that one desktop image click opens Search on
each selected phone, with the other phone unchanged, and both respond only
when Mirror-to-all is enabled. This completes the manual GUI click/isolation
check. One Home transition appeared later than the initial screenshot check,
so longer-term daily-use readiness still needs follow-up. No application
source, production executable, receiver configuration, or firewall rule changed.

## Exact configuration

- Console: `release/iMouse2-two-phone/iMouse2.exe`, PID 2804.
- Kernel: `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe`, PID 32328,
  `http://127.0.0.1:9913/api/`.
- C24C / C24CBFBD: phone `86:1D:4A:04:2F:F6`, receiver `iMouse2-C24C`, PID 20972.
- C241 / C241BFBD: phone `FE:A9:BC:D7:A0:44`, receiver `iMouse2-C241`, PID 33972.
- Both receivers were our modified UxPlay, with separate ports, pipes, and
  exact-device restrictions. Both streams were 500 × 1080 BMP.
- Mirror-to-all and following were off. Commands contained exactly one of these
  two phone IDs. Other phones and vendor processes were untouched.

Executable hashes are in `build-hashes.json`. The API helper rechecked both
phone/board bindings, live receiver identities, and the exact two-board allowlist
before every action. It checked the returned target ID after each command.

## Functional results

- Five single Search clicks through the kernel opened Spotlight: one on C24C
  and four on C241. Each was one click, without a second activation click.
- Six horizontal swipes were visually verified: left/right on C24C and two
  left/right cycles on C241. One C241 left swipe used the console's Controls
  button; the remaining five used the kernel API.
- Home transitions were verified on both phones. C241's console Home button
  also worked. The five API Home calls include a redundant follow-up discussed
  below; five successful API responses do not mean five independently observed
  transitions.
- The non-target screen remained in its expected view during each action.
  Before/after image differences on that phone were small clock/compression
  changes. No cross-phone input or swapped video feed was observed.
- Repeated C241 Search clicks still landed after horizontal movement. No
  functional pointer drift was observed at that target. This was not a new
  calibration across the entire screen.
- All 15 logged API commands returned code 0 for the intended single phone.
- User-reported follow-up: one console image click opens Search on C24C and
  C241 individually; both respond only when Mirror-to-all is enabled. This
  manual result is separate from the automated measurements above.

## Performance and pauses

The receiver counters normally advanced at about 20 FPS per phone. The console
Activity panel showed C24C at 20.5 presented FPS with approximately 39/71 ms
p50/p95 presentation spacing at one observation; the other phone's tile was
usually around 18–20 FPS. This is a snapshot of the console's rolling/cumulative
meters, not a continuous rendering benchmark or measured input latency.

There were no receiver restarts, offline status samples, lost test processes,
or unresponsive-process samples during the monitoring window. Final exact
statistics and memory/CPU measurements are in `summary.json` and the table below.
CPU percentages are normalized across 16 logical processors. Short-run memory
measurements cannot establish the absence of a long-term leak.

Six five-second sampling intervals had no frame-counter advance: one on C24C
and five on C241. Every such interval occurred while the affected phone was on
its static second Home page. Its other phone kept advancing. C241 was deliberately
left there for about 40 seconds to reproduce the behavior; a right swipe restored
the animated first page and continuing frames without reconnecting. This is
consistent with static-screen transmission suppression. It does not prove a
decoder freeze or a network failure. Counts alone cannot distinguish those causes.
Receiver logs also contain intermittent missing-client-feedback warnings.

API completion times were approximately 290–314 ms for Home, 538–1068 ms for
Search, and 692–1225 ms for swipes. These include the kernel's programmed motion
and settling time; they are not end-to-end human input latency. Two sampled Home
transitions first showed a large visual change at 480 and 466 ms from API send.
One sampled Search transition changed by 737 ms. Those samples were taken only
after the API returned and include polling overhead, so they are upper bounds
for when that visual change was first present, not precise latency measurements.

## Final measurements

| Receiver | Frames received | Average received FPS | Median five-second FPS | New restarts | Offline samples |
|---|---:|---:|---:|---:|---:|
| C24C | 14,211 | 19.77 | 20.10 | 0 | 0 |
| C241 | 13,948 | 19.40 | 20.10 | 0 | 0 |

Static-page periods are included in the averages. These are received-frame
counters, not continuous measurements of the console's displayed frames.

| Process | Working set start → end (MiB) | Peak working set (MiB) | Private memory start → end (MiB) | Average machine CPU |
|---|---:|---:|---:|---:|
| Console 2804 | 193.91 → 201.60 | 204.75 | 207.57 → 208.84 | 1.88% |
| Kernel 32328 | 77.20 → 77.54 | 78.46 | 40.60 → 40.73 | 0.49% |
| C24C receiver 20972 | 84.25 → 86.93 | 86.93 | 65.05 → 67.89 | 0.37% |
| C241 receiver 33972 | 83.70 → 86.23 | 86.23 | 64.49 → 67.20 | 0.36% |

Combined average CPU was 3.10% of this 16-logical-processor machine. No rapid
memory growth was observed. Receiver memory increased modestly over the run;
a longer soak is needed to assess whether that increase levels off.

## Remaining uncertainties

1. At 22:31:53, C241's Home API response succeeded, but the screenshot taken
   roughly 1.2 seconds afterward still showed Spotlight. The next capture,
   taken **before** a subsequent Home command, already showed Home. Therefore
   it recovered before the redundant command; this is an observed delay, not
   proof that a second press was required. Its exact delay/cause was not captured.
   Two later watched Home checks were prompt.
2. Desktop automation attempted one image click on each phone. Neither produced
   a Tap entry in the console Activity log. The user subsequently verified both
   manual image clicks and correct Mirror-to-all behavior. The product's manual
   GUI check therefore passes; the desktop automation limitation remains
   unexplained. Do not count the automated attempts as successful GUI clicks.
3. The footer still displays a cached `iMouse2-C214` name from the previous
   configuration. Live device status, active receiver processes, and actual
   frames correctly identify C241. This cosmetic issue makes hardware selection
   confusing and should be corrected before broader use.

Keep the scope to these two phones. Investigate the delayed Home observation
before claiming full replacement readiness or
expanding to the rack. Then measure speed parity under matched workloads.

## Evidence

- `telemetry.jsonl`: five-second status, frame-counter, process memory, CPU samples.
- `actions.jsonl`: verified identity, one-phone requests/results, API timing,
  paired screenshots, and selected visual-response samples.
- Numbered PNGs: before/after views for both phones, including the delayed Home
  check and the Home screen present before the redundant follow-up command.
- `console-observations.json`: Activity panel rendering and input log snapshot.
- `summary.json`: computed statistics; static intervals are retained, not hidden.

The receiver and console were left running. No forced crash/recast test was
performed during this baseline run.
