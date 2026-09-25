# Independent two-phone test build

The currently validated console is `release/iMouse2-two-phone-candidate/iMouse2.exe`, connected to
our kernel at `http://127.0.0.1:9913`. The kernel is
`release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe`. Both use our modified
UxPlay receiver, not vendor AirPlay forwarding.

| Phone | Board / UID | Receiver | Ports | Address |
|---|---|---|---|---|
| 86:1D:4A:04:2F:F6 | C24C / C24CBFBD | iMouse2-C24C | 7110–7112 | 192.168.4.28 |
| FE:A9:BC:D7:A0:44 | C241 / C241BFBD | iMouse2-C241 | 7120–7122 | 192.168.4.68 |

The second target was changed from C214 to C241 after the phone the user was
trying to connect identified itself in both receiver logs as FE:A9:BC:D7:A0:44.
Vendor hardware status confirmed C241 / C241BFBD attached. C214's temporary
firewall rules were disabled; it is no longer an enabled test target.

Each receiver has its own MAC identity, pipe, BMP buffers, and restart supervisor.
The API routes screenshot requests and device video status by exact phone ID.
Unknown screenshot IDs are rejected. Configuration validation rejects shared
ports, pipes, names, MAC identities, and mismatched phone/board assignments.
Legacy top-level kernel status describes the first receiver; use the `receivers`
array for independent status of both phones.

Configuration and per-receiver logs: `analysis/two-phone-config/`.
The original C24C calibration is copied. C241 was calibrated with direct HID
mouse movement observed on its independent stream: reset origin approximately
(15,14), after 40 diagonal unit steps (219,218), after 80 (423,422). Its saved
scale is 5.1 pixels per unit on each axis. These commands affected the C241
stream, confirming the hardware association. C24C remained on its Home Screen.
Evidence: `analysis/two-phone-config/C241-reset.bmp`, `C241-diagonal.bmp`, and
`C241-diagonal-second.bmp`. Pointer input had been disabled due to the missing
calibration; the console's “No phone on board” label was misleading.

Validation: 34 kernel checks, 77 console self-checks, 100 UI mock checks passed.
Added checks cover receiver configuration collisions, input isolation in both
directions, and losing one frame pipe while the other remains live.

Both phones have established independent live video. A 12-minute live baseline
was completed on 14 September, with the kernel and console left running.
Home, single Search clicks, horizontal swipes, and isolation between the two
phones were visually verified through direct input; console Home and Left
buttons were also verified on C241. Average received rates were 19.77 FPS on
C24C and 19.40 FPS on C241, with no new receiver restarts or offline samples.

The user subsequently confirmed that a single console image click opens Search
on each selected phone and affects both only when Mirror-to-all is enabled.
Manual GUI click and isolation checks pass. Earlier desktop automation clicks did not
register in Activity; the cause remains unexplained. The 15 September candidate
validation recorded single GUI Taps successfully on both phones. One
Home transition appeared after the initial screenshot check. The footer C214 cache is fixed in `release/iMouse2-two-phone-candidate/iMouse2.exe`.
C241 Home API returned in ~300 ms in later trials, with the first detected
visual change around 370–440 ms. Those trials did not reproduce or establish
the cause of the earlier 1.2 s Spotlight observation.
See `analysis/two-phone-live-test-20260914/REPORT.md`,
`analysis/footer-home-speed-20260914/REPORT.md`, and
`analysis/console-compare-20260915/REPORT.md`. An ABAB original/candidate
window did not repeat the C241 18.2 received-FPS dip as a console effect.
Displayed FPS requires the Activity drawer. A follow-up C24C/C241 master ABAB
did **not** reproduce the 12.6 received-FPS drop (`analysis/c241-master-20260915/REPORT.md`).
BMP-lock remains a hypothesis. Search opened Spotlight on both phones (visual).
No forced receiver interruption was performed during this baseline. Do not
claim daily-use readiness from this short run or the mock checks. Mirror-to-all
was off during the automated run; its behavior was confirmed separately by the
user. Other boards were outside the test. No vendor service was stopped.

On 15 September the candidate replaced the original console without restarting
the kernel or receivers. Its footer correctly lists C24C and C241; GUI Home,
single-click Search, horizontal swipes, and isolation passed on both phones.
Matched 91-second windows measured C24C 20.11 vs 20.13 received FPS and C241
19.02 vs 18.21; no offline samples, zero-progress intervals, or new restarts.
The candidate is suitable for continued controlled two-phone testing; full
speed parity remains unproven. See `analysis/candidate-validation-20260915/REPORT.md`.

The later keep-Known-across-Home kernel was rejected after repeated C241 misses.
Home invalidation remains required. On 15 September Codex implemented a separate
opt-in `--precise-movement` candidate that retains reset and all one-unit packets,
but uses a high-resolution timer for unheld movement. Isolated InputRouter checks
passed 14 live Home-to-Search checks per phone (~1.17 s vs ~3.02 s). On 16 September
the candidate (PID 12516) was deployed on port 9913: C24C passed 9/9, but C241
regressed (3/5 cycle, 2/4 location, 0/5 targeted rerun). Step 5 rollback restored
`release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` (PID 31472, legacy pacing).
C241 recovered to 5/5 Spotlight hits, C24C passed 2/2, with 100% reciprocal isolation.
See `analysis/pointer-reliability-20260915/REPORT.md` and its `HANDOFF.md`.
