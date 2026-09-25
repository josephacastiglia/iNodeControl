# Candidate console live validation — 15 September 2026

The footer-fix candidate passed the live two-phone basic-control checks and is left open for continued controlled testing. Full speed parity is not established: C24C throughput was unchanged, while C241 received throughput was about 4.2% lower in the candidate window. These short sequential samples cannot attribute that difference to the console.

## Builds and session continuity

- Closed original console PID 2804 (`release/iMouse2-two-phone/iMouse2.exe`) and opened candidate PID 9532 (`release/iMouse2-two-phone-candidate/iMouse2.exe`). Binary hashes are in `build-hashes.json`.
- Kernel PID 32328 (`release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe`) remained running on 9913.
- Modified UxPlay receivers remained PID 20972 (iMouse2-C24C) and 33972 (iMouse2-C241). No recast was needed. Historical restart counts remained 0 and 1 respectively; neither increased.
- C24C / C24CBFBD / 86:1D:4A:04:2F:F6 and C241 / C241BFBD / FE:A9:BC:D7:A0:44 were the only input targets. Mirror-to-all and follower checkboxes stayed off. Other phones and vendor services were untouched.
- No application source or binary changes were made. Only verification tools and notes were added/updated.

## Live candidate controls

The candidate footer now displays `Cast iMouse2-C24C / iMouse2-C241`, including after changing the selected master. Its Activity log records exactly one Tap for each Search check.

| Target | GUI Search | GUI Home | GUI Left then Right | Isolation |
|---|---|---|---|---|
| C24C | One click opened Spotlight | Returned to first Home page | Second page, then first page | C241 stayed on its Home page |
| C241 | One click opened Spotlight | Returned to first Home page | Second page, then first page | C24C stayed on its Home page |

Search was clicked in the displayed phone image; Home and swipes used candidate console buttons. No API input was substituted for these checks. Paired phone PNG captures and `candidate-ui.txt`/`candidate-ui.jpg` provide evidence. `actions.jsonl` entries with null action are read-only captures made after GUI actions: their tiny before/after differences are not a measure of input response or a failed gesture.

The earlier desktop-click automation problem did not recur after maximizing this candidate window and setting the correct preview size. This does not establish its previous cause. No systematic pointer-drift, inactive-window first-click, fan-out, or long-duration test was performed here.

## Matched short comparison

Both runs used the same kernel and receivers, 500×1080 source frames, C24C master, C241 wall tile, first Home pages with animated clock icons, 30 FPS master and wall settings, a maximized 1920×1032 window, approximately 352×760 master image and 54×118 tile, and the Activity drawer open. No input was sent during either telemetry window. Candidate warmed up for several minutes before measurement.

Each run has 46 samples approximately two seconds apart over 91.4 seconds. Baseline: 04:12:24–04:13:56 UTC. Candidate: 04:22:32–04:24:04 UTC. UI readouts are sparse supplemental observations; one candidate observation is just after the telemetry window and another is marked followup. Accessibility readout text can lag the screenshot and should not be treated as precise continuous presentation telemetry.

| Measurement | Original | Candidate |
|---|---:|---:|
| C24C received FPS (kernel counter delta / elapsed time) | 20.11 | 20.13 |
| C241 received FPS | 19.02 | 18.21 |
| Master displayed rate, sampled UI | About 20 | About 20 |
| Master p95 frame gap, sampled UI | 71–72 ms | About 70–72 ms |
| Console average CPU, whole-machine scale | 1.76% | 1.61% |
| Kernel + console + both receivers CPU | 3.02% | 2.74% |
| Console working set, start → end | 207.02 → 207.14 MiB | 207.28 → 207.60 MiB |
| Console private bytes, start → end | 222.96 → 222.99 MiB | 215.37 → 215.83 MiB |
| Offline samples / zero-progress intervals / new restarts | 0 / 0 / 0 | 0 / 0 / 0 |
| Telemetry errors / nonresponding process samples | 0 / 0 | 0 / 0 |

CPU is process CPU-time delta divided by elapsed time and 16 logical processors. This is not total system CPU. Receiver and kernel memory measurements are retained in `summary.json`; no large increase occurred in these short windows. Different process ages mean the smaller candidate private-byte count is not evidence of a memory optimization, and this duration cannot rule out a leak. Two-second sampling cannot exclude shorter frame stalls. Received FPS is distinct from displayed FPS and input latency.

## Decision and next step

Keep this candidate as the console for controlled C24C/C241 testing: the footer fix and basic controls pass, sessions survived the switch, and no restart or sampled stall appeared. Preserve the original build as the comparison baseline. This does not establish 30 FPS delivery, vendor speed parity, or daily-use readiness.

Before further performance edits, repeat alternating original/candidate windows with a repeatable moving workload and the same selected master, preview sizes, and settings. Determine whether the C241 difference repeats and whether it originates in received frames or presentation. Do not assume the software decoder or the console is the bottleneck from this run.

Reproduction: `tools/candidate_benchmark.ps1` records a read-only window; `tools/summarize_candidate_benchmark.py` summarizes the saved phases. No additional automated test suite was run because the application build was unchanged; this session specifically exercised the delivered candidate on live phones.
