# Footer names, C241 Home delay, speed measurements — 14 September 2026

Tested processes were left running:
- Console `release/iMouse2-two-phone/iMouse2.exe` PID 2804 (unchanged)
- Kernel `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` PID 32328
- UxPlay iMouse2-C24C 20972, iMouse2-C241 33972

Candidate console (footer fix only): `release/iMouse2-two-phone-candidate/iMouse2.exe`.
Kernel was not rebuilt. No vendor service was stopped.

## 1. Footer Cast name

Cause: `_castName` was filled once from `/config/imserver/get` and never
replaced. A previous C214 configuration therefore stayed in the footer while
live routing already used C241.

Fix (candidate console): footer Cast label is rebuilt on every device refresh
from current `receiver_name` values. Stale imserver names are ignored when
devices report live names. Disconnect clears the cache. Selection change keeps
the live pair.

Evidence: UI checks (footer uses C24C/C241, not C214, after selection change).
Live capture of the candidate window footer: `../footer-candidate.png`
(`Cast iMouse2-C24C / iMouse2-C241`).

To use the fix: close the old console and launch
`release/iMouse2-two-phone-candidate/iMouse2.exe` (still `http://127.0.0.1:9913`).

## 2. C241 Home delay

Reproduced with timestamped API send and tight screenshot polls (3 trials each
phone) after opening Spotlight. No second Home was sent.

| Phone | API return | First visual Home | Extra after API |
|---|---:|---:|---:|
| C241 | 289–310 ms | 372–436 ms | 83–132 ms |
| C24C | 293–316 ms | 381–408 ms | 65–115 ms |

HID Home is two programmed key strokes (~280 ms of delays). That matches the
API duration. The picture changes ~80–130 ms later (iOS + AirPlay). The earlier
1.2 s Spotlight screenshot was a late poll of a transition that had already
started; a follow-up frame showed Home *before* any second command.

No HID change. Duplicate Home would hide the timing, not fix it.

Raw polls: `../home-latency/results.json`.

## 3. Speed (measure first, no optimizer this round)

Five-second received counters: C24C 19.92 FPS, C241 18.93 FPS, against a 30 FPS
UxPlay request with software decode. Screenshot fetches are often 1–2 ms on a
duplicate frame and 20–35 ms when a new BMP is copied. Home input-to-visible
is ~370–440 ms, of which ~300 ms is deliberate HID timing.

No settle/click delays were shortened. Click reliability is unchanged.

## Live isolation after the work

| Phone | Search MAD | Other phone MAD | Swipe MAD |
|---|---:|---:|---:|
| C24C | 78.68 | 0.06 | 31.70 |
| C241 | 49.72 | 0.04 | 26.83 |

Shots: `../two-phone-footer-verify/`.

Checks: candidate console 77 self-tests and 102 UI checks (added receiver-name
parse and two footer checks). Kernel not rebuilt.

## Remaining

- Recast after a receiver crash is still manual.
- Spotlight still eats spaces; Notes does not.
- Video ceiling is ~20 received FPS with `-avdec`.
- One UxPlay per phone; not a rack cutover.
- Launch the candidate console for the footer fix; keep using the current
  two-phone kernel.
