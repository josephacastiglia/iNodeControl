# Gate 4 1,000-Tap Suite — Isolation Audit Report

- **Date:** 2026-09-25
- **Auditor / Workhorse Role:** GPT-6 Sol (`openai-codex/gpt-6-sol`, verified in `~/.omp/agent/config.yml` and `~/.omp/agent/RULES.md` for `task`, `smol`, `advisor`, `simplify`, `review`, `complex_review`)
- **Dataset:** `analysis/gate4-1000-tap/results.jsonl` (1,000 trials), `analysis/gate4-1000-tap/status.json`, `analysis/gate4-1000-tap/shots/*.bmp` / `*.png`, `analysis/gate4-1000-tap/probe/*.bmp` / `*.png`
- **Harness:** `tools/gate4_1000_tap_suite.py`

---

## 1. Executive Verdict

1. **Target Accuracy:** **1,000 / 1,000 (100.0%)** intended Spotlight hits within the 5.0 s ceiling (`C24C`: 500/500, `C241`: 500/500; `home_search`: 250/250, `off_location`: 250/250, `app_switch`: 250/250, `swipe`: 250/250).
2. **Stuck Inputs / Accidental Double-Clicks:** **0 / 1,000** stuck keys or buttons; **0 / 1,000** accidental double-clicks.
3. **Latency:** Visible-effect `p50 = 2216.6 ms`, `p95 = 2419.2 ms`, `max = 3865.7 ms` (all 1,000 $\le 5000\text{ ms}$). HTTP click dispatch `p50 = 1839.8 ms` (`C24C`) / `1838.9 ms` (`C241`).
4. **Audit of All 18 `isolated == false` Flags:** **0 / 18 are unintended cross-phone actions.** All 18 flags are **harness `other_before` baseline-capture races** where the non-target phone (`other`) had just been the target of Trial $N-1$, received `sendkey("Home")` at the end of Trial $N-1$, and had not finished (or had not yet begun rendering) its Spotlight-to-Home dismiss transition when `other_before = settled(base, oid)` ran 0.35 s later at the start of Trial $N$. By the time `other_after` was captured 3.4–6.6 s later, the non-target phone had settled onto its **clean Home screen**, causing `mad(other_before, other_after)` to measure the previous trial's **Spotlight $\to$ Home recovery** (`~77.2` MAD on `C24C`, `~48.8` MAD on `C241`) instead of cross-phone leakage.
5. **True Cross-Phone Isolation:** **1,000 / 1,000 (100.0%)** trials had zero unintended actions on the non-target phone (`unintended_phone_actions = 0`).

---

## 2. Root-Cause Mechanism in `tools/gate4_1000_tap_suite.py`

The suite alternates strictly between `C24C` (even trials `n = 0, 2, 4, ...`) and `C241` (odd trials `n = 1, 3, 5, ...`).
At the end of Trial $N-1$ on Phone A (`spec["id"]`), `trial()` dismisses Spotlight with `Home` and sleeps only **350 ms** (lines 343–346):

```python
send_timed(base, spec["id"], token, "/key/sendkey", fn_key="Home")
time.sleep(0.35)
return row
```

Immediately at the start of Trial $N$ on Phone B, Phone A becomes `oid` (`other`), and `trial()` captures `other_before = settled(base, oid)` (lines 283–293, 306):

```python
def settled(base: str, pid: str, budget: float = 1.2) -> bytes:
    prev = shot(base, pid)
    deadline = time.perf_counter() + budget
    while time.perf_counter() < deadline:
        time.sleep(0.25)
        frame = shot(base, pid)
        if mad(prev, frame) < 3:
            return frame
        prev = frame
    return prev
```

This creates two deterministic false-flag modes whenever iOS + UxPlay takes longer than `350 ms` to begin rendering the Home transition (or longer than `1.2 s` to finish):
- **Mode 1 — Pre-transition static lock (15 / 18 flags):** At `t = 0.35 s` and `t = 0.60 s` after `sendkey("Home")`, Phone A's AirPlay frame buffer is still showing static Spotlight from Trial $N-1$. Because both frames are static Spotlight, `mad(prev, frame) < 3` succeeds immediately on the first poll (`t = 0.60 s`) and locks in **full Spotlight** as `other_before`. During Trial $N$'s setup + click (`3.4–6.6 s`), Phone A finishes dismissing to the clean Home screen. When `other_after = shot(base, oid)` runs at line 312, `mad(other_before [Spotlight], other_after [Clean Home])` equals the exact full `Spotlight <-> Home` delta of Phone A (`~77.1–77.9` on `C24C`; `~47.8–49.0` on `C241`).
- **Mode 2 — Mid-transition capture (3 / 18 flags: `#56`, `#237`, `#397`):** `other_before` captures Phone A mid-dismiss (partially dimmed wallpaper / retreating keyboard) when `settled()` returns at `budget = 1.2 s` or across a brief two-frame pause, and `other_after` captures Phone A on the clean Home screen (`isolation_mad = 35.44` on `C241` in `#56`; `19.49` and `49.89` on `C24C` in `#237` and `#397`).

Across the remaining **982 trials** where `other_before` caught Phone A after Home dismiss completed:
- `isolation_mad` `min = 0.03`, `p50 = 0.61`, `p95 = 0.90`, `p99 = 1.33`, `max = 5.19` (all well below `ISO_MAX = 8.0`).

---

## 3. Complete 18-Trial Evidence Table

Across all 500 `C24C` target trials, `C24C`'s `Home -> Spotlight` MAD is **`median = 76.12`, `mean = 76.24`, `max = 78.16`** (`probe/c24c-home.bmp` vs `probe/c24c-after.bmp` = **`77.72`**).
Across all 500 `C241` target trials, `C241`'s `Home -> Spotlight` MAD is **`median = 48.66`, `mean = 48.75`, `max = 49.75`**.

| Trial `n` | Block | Target Phone | `other` Phone | Category | Preceding Trial (`n-1`) on `other` | `n-1` Target MAD (`Home -> Spotlight` on `other`) | Trial `n` `isolation_mad` (`other_before -> other_after`) | Ratio (`IsoMAD / PrevTargetMAD`) | Capture Mode & Audit Verdict |
|---:|---:|---|---|---|---:|---:|---:|---:|---|
| **10** | 1 | `C24C` | `C241` | `off_location` | 9 (`C241`) | `48.25` | **`47.82`** | `0.9911` | Mode 1: Full `C241` Spotlight $\to$ Clean Home (`99.1%` of `C241` delta) |
| **56** | 1 | `C24C` | `C241` | `home_search` | 55 (`C241`) | `48.85` | **`35.44`** | `0.7255` | Mode 2: Mid-dismiss `C241` Spotlight $\to$ Clean Home (`72.6%` of `C241` delta) |
| **58** | 1 | `C24C` | `C241` | `off_location` | 57 (`C241`) | `48.05` | **`48.71`** | `1.0137` | Mode 1: Full `C241` Spotlight $\to$ Clean Home (`101.4%` of `C241` delta) |
| **64** | 1 | `C24C` | `C241` | `home_search` | 63 (`C241`) | `49.26` | **`48.97`** | `0.9941` | Mode 1: Full `C241` Spotlight $\to$ Clean Home (`99.4%` of `C241` delta) |
| **70** | 1 | `C24C` | `C241` | `swipe` | 69 (`C241`) | `49.22` | **`48.85`** | `0.9925` | Mode 1: Full `C241` Spotlight $\to$ Clean Home (`99.3%` of `C241` delta) |
| **80** | 1 | `C24C` | `C241` | `home_search` | 79 (`C241`) | `48.37` | **`48.92`** | `1.0114` | Mode 1: Full `C241` Spotlight $\to$ Clean Home (`101.1%` of `C241` delta) |
| **84** | 1 | `C24C` | `C241` | `app_switch` | 83 (`C241`) | `49.25` | **`48.93`** | `0.9935` | Mode 1: Full `C241` Spotlight $\to$ Clean Home (`99.4%` of `C241` delta) |
| **86** | 1 | `C24C` | `C241` | `swipe` | 85 (`C241`) | `48.02` | **`48.89`** | `1.0181` | Mode 1: Full `C241` Spotlight $\to$ Clean Home (`101.8%` of `C241` delta) |
| **94** | 1 | `C24C` | `C241` | `swipe` | 93 (`C241`) | `49.41` | **`48.94`** | `0.9905` | Mode 1: Full `C241` Spotlight $\to$ Clean Home (`99.1%` of `C241` delta) |
| **237** | 3 | `C241` | `C24C` | `app_switch` | 236 (`C24C`) | `75.75` | **`19.49`** | `0.2573` | Mode 2: Mid-dismiss `C24C` $\to$ Clean Home (`0237-C24C-other.png` verified Home) |
| **397** | 4 | `C241` | `C24C` | `app_switch` | 396 (`C24C`) | `77.62` | **`49.89`** | `0.6427` | Mode 2: Mid-dismiss `C24C` $\to$ Clean Home (`0397-C24C-other.png` verified Home) |
| **405** | 5 | `C241` | `C24C` | `app_switch` | 404 (`C24C`) | `77.67` | **`77.86`** | `1.0024` | Mode 1: Full `C24C` Spotlight $\to$ Clean Home (`0405-C24C-other.png` verified Home) |
| **817** | 9 | `C241` | `C24C` | `home_search` | 816 (`C24C`) | `75.48` | **`77.14`** | `1.0220` | Mode 1: Full `C24C` Spotlight $\to$ Clean Home (`0817-C24C-other.png` verified Home) |
| **841** | 9 | `C241` | `C24C` | `home_search` | 840 (`C24C`) | `77.37` | **`77.20`** | `0.9978` | Mode 1: Full `C24C` Spotlight $\to$ Clean Home (`0841-C24C-other.png` verified Home) |
| **843** | 9 | `C241` | `C24C` | `off_location` | 842 (`C24C`) | `77.41` | **`77.10`** | `0.9960` | Mode 1: Full `C24C` Spotlight $\to$ Clean Home (`0843-C24C-other.png` verified Home) |
| **847** | 9 | `C241` | `C24C` | `swipe` | 846 (`C24C`) | `77.48` | **`77.17`** | `0.9960` | Mode 1: Full `C24C` Spotlight $\to$ Clean Home (`0847-C24C-other.png` verified Home) |
| **883** | 9 | `C241` | `C24C` | `off_location` | 882 (`C24C`) | `75.76` | **`77.33`** | `1.0207` | Mode 1: Full `C24C` Spotlight $\to$ Clean Home (`0883-C24C-other.png` verified Home) |
| **893** | 9 | `C241` | `C24C` | `app_switch` | 892 (`C24C`) | `75.01` | **`77.36`** | `1.0313` | Mode 1: Full `C24C` Spotlight $\to$ Clean Home (`0893-C24C-other.png` verified Home) |

---

## 4. Pixel & Visual Verification of Saved `*-C24C-other` Captures

After Block 1 (`0000`–`0099`), `tools/gate4_1000_tap_suite.py` (line 340–341) was updated to write `other_after` to `analysis/gate4-1000-tap/shots/{n:04d}-{otag}-other.bmp` on every trial with `isolated == false`. All 9 flags in Blocks 2–10 (`0237`, `0397`, `0405`, `0817`, `0841`, `0843`, `0847`, `0883`, `0893`) have their exact `other_after` frame saved on disk.

Every single saved `*-C24C-other` image was compared against:
1. `analysis/gate4-1000-tap/probe/c24c-home.bmp` (known clean `C24C` Home screen baseline, captured pre-midnight `THU 24`),
2. `analysis/gate4-1000-tap/shots/0405-C24C-other.bmp` (post-midnight `FRI 25` clean `C24C` Home screen),
3. `analysis/gate4-1000-tap/probe/c24c-after.bmp` (known `C24C` Spotlight open state, `mid_mean = 96.53`).

| Saved `other_after` File | Status-Bar Time / Calendar Icon | Harness `mad()` vs `c24c-home.bmp` | Full-Frame MAD vs `c24c-home.bmp` | Masked MAD (`y >= 300`, below Clock/Calendar) vs `c24c-home.bmp` | Harness `mad()` vs `0405-C24C-other.bmp` | Harness `mad()` vs `c24c-after.bmp` (Spotlight) | Mid-Band Mean (`y=400..700`, Home=`156.82`, Spot=`96.53`) | Visual Inspection Verdict |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `0237-C24C-other.png` | `11:53` / `THU 24` | **`1.91`** | `1.4636` | `1.0605` | `1.64` | `77.52` | `156.83` | Clean `C24C` Home screen; cursor resting on Search pill |
| `0397-C24C-other.png` | `12:08` / `FRI 25` | **`2.21`** | `1.7521` | `1.0715` | `1.24` | `77.60` | `156.85` | Clean `C24C` Home screen; cursor resting on Search pill |
| `0405-C24C-other.png` | `12:09` / `FRI 25` | **`2.19`** | `1.7527` | `1.0751` | `0.00` | `77.64` | `156.88` | Clean `C24C` Home screen; cursor resting on Search pill |
| `0817-C24C-other.png` | `12:49` / `FRI 25` | **`2.23`** | `1.7585` | `1.0728` | `0.98` | `77.68` | `156.89` | Clean `C24C` Home screen; cursor resting on Search pill |
| `0841-C24C-other.png` | `12:52` / `FRI 25` | **`2.19`** | `1.7501` | `1.0743` | `0.76` | `77.66` | `156.88` | Clean `C24C` Home screen; cursor resting on Search pill |
| `0843-C24C-other.png` | `12:52` / `FRI 25` | **`2.21`** | `1.7527` | `1.0792` | `0.58` | `77.63` | `156.89` | Clean `C24C` Home screen; cursor resting on Search pill |
| `0847-C24C-other.png` | `12:53` / `FRI 25` | **`2.21`** | `1.7557` | `1.0796` | `0.54` | `77.65` | `156.89` | Clean `C24C` Home screen; cursor resting on Search pill |
| `0883-C24C-other.png` | `12:56` / `FRI 25` | **`2.18`** | `1.7237` | `1.0778` | `0.51` | `77.64` | `156.88` | Clean `C24C` Home screen; cursor resting on Search pill |
| `0893-C24C-other.png` | `12:57` / `FRI 25` | **`2.19`** | `1.7308` | `1.0798` | `0.56` | `77.65` | `156.89` | Clean `C24C` Home screen; cursor resting on Search pill |

### Key Takeaways from the Pixel & Visual Proof
1. **Every `other_after` capture is indisputably on the clean Home screen:** All 9 `*-C24C-other` images have a harness `mad()` of **`1.91`–`2.23`** against `probe/c24c-home.bmp` (well below `ISO_MAX = 8.0`) and **`0.51`–`0.98`** against `0405-C24C-other.bmp`. The tiny `0.30` step between `0237` (`1.91`) and `0397`–`0893` (`2.18`–`2.23`) is caused solely by local midnight crossing between `11:53 PM` (`THU 24` on the Calendar icon) and `12:08 AM` (`FRI 25` on the Calendar icon), plus the moving hands of the Clock icon.
2. **Since `other_after` is Clean Home and `mad(other_before, other_after)` is `77.10`–`77.86`, `other_before` was mathematically and visually in Spotlight:** On `C24C`, the only state at distance `~77.6` from Clean Home is Spotlight (`mad(c24c-home, c24c-after) = 77.72`). Therefore, during Trials `405`, `817`, `841`, `843`, `847`, `883`, and `893` (and partially during `237` and `397`), `C24C` was **returning from Spotlight to Home** from the preceding even-numbered trial (`236, 396, 404, 816, 840, 842, 846, 882, 892`), **not** leaving Home.
3. **Identical proof holds for the 9 Block-1 flags on `C241`:** In Trials `10, 56, 58, 64, 70, 80, 84, 86, 94`, `C241` had just opened Spotlight in the immediately preceding odd-numbered trial (`9, 55, 57, 63, 69, 79, 83, 85, 93` with `Home -> Spotlight` MAD `48.02`–`49.41`). Eight of the 9 flags recorded `isolation_mad` between **`47.82` and `48.97`** (`Ratio = 0.9905`–`1.0181`), and `#56` recorded **`35.44`** (`Ratio = 0.7255`, mid-dismiss) — proving `C241` was likewise finishing its `Spotlight -> Home` transition from the prior trial.
