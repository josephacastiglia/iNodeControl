# C241 as master — follow-up measurement — 15 September 2026

Hypothesis from the previous report: selecting C241 as master stalls its UxPlay
pipe because `FrameStore.WriteFrame` holds `_gate` for the whole ~1.6 MB BMP
HTTP write. That remains a **code-level risk**, not a confirmed cause of the
earlier 12.6 received-FPS drop. This run repeated matched video-only windows
and did **not** reproduce that collapse. No kernel or console binary was
changed. HID calibration and settle delays were left alone.

## Conditions

Kernel 32328, candidate console 13320, UxPlay 20972 (C24C) and 33972 (C241)
stayed running. Activity was opened at the start. Preview sizes and 30 fps
presets were not changed. Mirror-to-all off. Video windows had **no input**.
Search tests were a separate phase.

Displayed FPS (`RateMeter`) is unique `Present()` marks in a **~2 s** window.
It does **not** count duplicate BMPs (the master pump skips `SameAsPrevious`).
Received FPS is **every** pipe frame over the **whole ~20 s** window. Instant
FrameStatus samples must not be compared with whole-window received averages
as if they were the same quantity.

## Video-only alternating masters (~20 s each)

| Seq | Master | C24C received | C241 received | Displayed samples |
|---|---|---:|---:|---|
| 0 | C24C | 19.95 | 18.81 | 14× 28.9 fps (stale/identical UIA text) |
| 1 | C241 | 20.07 | **19.10** | none (FrameStatus empty after selection) |
| 2 | C24C | 20.20 | 18.20 | none |
| 3 | C241 | 20.11 | **17.24** | none |

C24C stays ~20.0–20.2 as master or tile. C241 stays ~17.2–19.1 in **both**
roles. The previous C241-master **12.62** did not repeat. C241-as-master was
once *higher* (19.10) than C241-as-tile (18.81).

UIA `FrameStatus` went empty after the first master change, so displayed FPS
after seq 0 is missing. Seq 0’s 28.9 fps (all 14 samples identical) is not
trustworthy against 20 received: likely a stuck Automation Name, not 29 unique
presents.

## Screenshot fetch times (10 GETs, extra load, after video windows)

| Master | Target | mean ms | max ms |
|---|---|---:|---:|
| C24C | C24C | 8.8 | 15.3 |
| C24C | C241 | 13.8 | 30.9 |
| C241 | C24C | 11.5 | 28.3 |
| C241 | C241 | 14.4 | 18.7 |

Loopback copies are typically 1–16 ms, not hundreds. That is compatible with
short lock holds, not with a seconds-long stall. It does **not** prove the
pipe is or is not blocked; it only bounds HTTP write time.

## Trace (code, not timers)

1. UxPlay writes BMP + 4-byte length on a named pipe.
2. `FrameStore` reads into `_incoming`, then under `_gate` swaps with `_current`
   and increments `Frames` (microseconds).
3. `WriteFrame` takes `_gate` and **writes `_current` to HTTP inside the lock**.
   A concurrent swap cannot proceed until that write finishes. Without the lock,
   the next swap would reuse `_current` as `_incoming` and corrupt the write.
   Copy-out or a third buffer would shorten the lock; that is a FrameStore-local
   change, not done here because the 12.6 FPS event was not reproduced.
4. Console master pump: raw BMP, skip identical payloads, `Prepare` off UI
   thread, `Present` on UI thread. `RateMeter` only marks unique presents.

## Search (visual Spotlight, not MAD)

API duration is HID completion after Home (`Known=false` reset+walk), ~3.0 s.
A later screenshot is not “first visible.” Eyes on the BMP:

| Trial | API ms | After image |
|---|---:|---|
| C24C Search | 2996 | Spotlight (Maps/Notes/Fitness/Measure, Search field) |
| C241 Search, C24C master | 3009 | Spotlight (Clock/Settings/Messages/Watch) |
| C241 Search, C241 master | 2991 | Spotlight (same C241 Spotlight) |

All three opened Spotlight. Before/after for the last trial is Home → Spotlight.

## Recommendation

Do **not** ship a BMP-path change on this evidence. Keep the two-phone kernel
as-is. If C241-as-master received FPS falls to ~12 again, then add timers
around `_gate` wait/hold and pipe `ReadExactly` in a **diagnostic** kernel
build; a copy-out `WriteFrame` is the smallest fix if hold time tracks the
drop. That is still FrameStore-local, not a Codex-scale redesign.

Separately, the ~3 s Search/swipe-after-Home is input delivery (API), not
video. Do not hide it with a second Home. Do not claim vendor speed parity.

Raw: `results.json`, `search-*-after.bmp`.
