# Alternating original vs candidate console — 15 September 2026

Four 90-second windows, same kernel and both independent receivers, Home-screen
workload, C24C selected as master, Mirror-to-all off. Only the console process
was closed when switching builds. No application source was changed.

## Process identities (verified at each sample, not reused from notes)

| Role | Path | PIDs this run |
|---|---|---|
| Kernel | `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` | 32328 throughout |
| C24C UxPlay | `tools/airplay/uxplay/build-imouse/uxplay.exe` | 20972, restarts 0 |
| C241 UxPlay | same UxPlay binary | 33972, restarts stayed 1 |
| Candidate console | `release/iMouse2-two-phone-candidate/iMouse2.exe` | 9532 then 3604 |
| Original console | `release/iMouse2-two-phone/iMouse2.exe` | 31124 then 5240 |

After the last original window the candidate was restored (now PID 13320).
Receivers remained live; no recast.

## Received FPS (kernel frame counters)

| Window | C24C | C241 | Zero-progress intervals | Offline |
|---|---:|---:|---:|---:|
| candidate-a | 20.24 | 19.35 | 0 | 0 |
| original-a | 20.26 | 19.29 | 0 | 0 |
| candidate-b | 20.17 | 18.97 | 0 | 0 |
| original-b | 20.15 | 19.34 | 0 | 0 |
| candidate mean | 20.21 | 19.16 | | |
| original mean | 20.21 | 19.31 | | |

C24C is flat at ~20.2 on both builds. C241 is ~19.0–19.4 on **both** builds.
The earlier candidate-only 19.0 → 18.2 dip **did not repeat** as a console
effect: candidate-a (19.35) was slightly *above* original-a (19.29).
`c241_repeat_lower_on_candidate` is false.

## Displayed FPS

UIA `FrameStatus` was empty in this harness, so presented FPS / p50/p95 gaps
were not recorded here. Do not treat received FPS as displayed FPS. Prior
candidate validation read ~20 fps on the master FrameStatus for the candidate
with 40/72 ms p50/p95; that remains a single-build snapshot, not an ABAB pair.

## CPU / memory

Console CPU (share of the 16-logical-processor machine) was ~0.6–0.8% in all
four windows. Kernel ~0.3%, each UxPlay ~0.3%. No Not Responding samples.
Candidate working set was ~200 MiB on the long-lived first window and ~164–168
MiB on the fresh relaunch, overlapping the original’s ~159–170 MiB. Different
process ages; not a leak test.

## Recommendation

**Do not optimize for the C241 18.2 figure.** It did not reproduce as a
candidate regression under matched alternating windows. C241 sits a little
below C24C on both consoles (~19 vs ~20 received FPS), which is consistent
with the phone/stream, not with the footer-fix binary.

This ABAB still does not establish 30 FPS delivery or vendor speed parity.
Next performance work, if any, should instrument displayed FPS in-process
(FrameStatus / present intervals) rather than chasing sub-1 FPS received
noise.

Keep using `release/iMouse2-two-phone-candidate/iMouse2.exe` against the
current two-phone kernel. Raw logs: `*-telemetry.jsonl`, `summary.json`.
