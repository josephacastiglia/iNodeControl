# C24C live draft windows, 20 October 2026

The operator was present and approved running the three prepared windows (Reel,
TikTok, X) one at a time, stopping after any failure for review. C24C only: no
C241 input, desktop control, publishing, messaging, FKA change or
installed-release change. Raw evidence (frames, OCR, journals, logs, binaries'
outputs) is in the private archive
`iMouseXP-2.0-evidence-archive/20261020-farm-live-windows`, outside Git; this
folder holds summaries without OCR text, frames or handles.

## 1. Reel attempt 1: stopped safely before any import

- Window started on the committed sources (`71b3b35`, backend fingerprint
  `c5784346…`). A read-only start-screen check (one screenshot, no input)
  recognized the exact @xs.halle.xo Instagram profile.
- The run answered five actions (Home → Safari → address → transfer URL → *Copy
  caption*). Then it stopped: *The pointer challenge did not produce a new
  frame.* State `review_required`, lease cleanup confirmed, video requested 0
  times. No download, Photos save or Instagram input happened; no draft exists.
  The phone was left in Safari on the transfer page, with the test caption on the
  clipboard.
- Stop script: initial stopped state restored, 25 protected files unchanged.
- [Summary](reel-attempt-1-summary.json); 76 archived files, manifest SHA-256
  `44adec8b0b5458bb43710c4507c4bc9bb8ea7360f692aca62f030e2f129bd678`.

### Root cause

Before each screen capture the workflow moves the pointer (never a tap) so the
phone sends a fresh frame, and the capture must carry a newer frame sequence.
After every answered action the pointer is parked at (480, 300). The challenge
chose x = 480 or 450 by the *count* of observations, so it could target the park
point itself. That happened after *Copy caption*: the pointer did not move, the
page had already finished drawing *Caption copied*, the phone sent no frame, and
the run correctly refused to act on an old one. The receiver stayed live; its
frame counter simply stopped (1,671 unchanged over 2 s afterwards).

The offline fixtures could not catch it: their screenshots and moves always
advanced the frame counter.

### Fix

- `tools/farm_draft_workflow.py`: the challenge reads the last answered pointer
  position from the run's own journal (`pointer_position()`) and always moves
  somewhere else (450 if the pointer is at (480, 300), otherwise 480). A move
  refused before transport does not count; an uncertain one makes the position
  unknown. This is shared by the carousel, Reel, TikTok and X workflows.
- The Reel, TikTok and X fixture kernels now behave like the phone: a screenshot
  returns the latest frame, and only a real pointer change delivers a new one.
  With the old code the X happy path then stops with the exact live reason; with
  the fix it passes.

### Verification and re-preparation

- Complete Python farm suite, all 45 modules in five parallel shards
  (`run_suite_shards.py`, `python-shard-*.txt`): **556 tests; 555 passed**. The
  X (8), TikTok (11) and Reel (9) protocol suites pass on the realistic fixtures.
  One timing test failed only under the 5× parallel load:
  `test_farm_rehearsal_http`, which waits 4 s for a simulated save and does not
  use the changed capture code. It passed when rerun alone
  (four reruns alone, all passing; the last is logged in
  `python-rerun-rehearsal-http.txt`).
- All three windows were re-prepared on the fixed sources: new tokens and run
  folders, dry native probes 3/3, `verify_preparation.py` ready (including the
  fingerprint check), one backend fingerprint
  `16e7c437c0bc80ac71ce7fa9ae325f7e1728c2ff89b6250995052e0862ac20c9`. Each
  window's `live/preparation.json` is authoritative:

  | Window | Token | Colour code | Download name | Video SHA-256 |
  |---|---|---|---|---|
  | Reel | `4f7e0356e411` | `[2,0,5,6,0,2]` | `imouse-reel-nxrevk` | `08930f4f7393489c8e195c038b3e44945a142c6d4281ab5ce387ea4cb3b06b9a` |
  | TikTok | `8c3052f5abe5` | `[6,4,6,5,7,3]` | `imouse-tt-muafmn` | `dd922d9c76bf032493d355452719306d07ab1622ce8eafae59d9c25f25c8582e` |
  | X | `aa8ab2a6d80b` | `[2,1,7,6,3,4]` | `imouse-x-utremp` | `94dc71a7134581e7a955ee9d7a28600e2fed15d6b4aa42c43476659b0f228ebb` |

## 2. Reel attempt 2: the pointer fix worked; stopped at the copy confirmation

- Started on `06f7a44`; the read-only check again recognized the exact profile.
- The same five actions were answered. After *Copy caption* the park was at
  (480, 300) and the challenge moved to (450, 300); a new frame arrived. The
  pointer fix held on the phone.
- It then stopped: *The transfer page did not confirm copying. No paste is
  permitted.* The page **did** show the confirmation, but the phone wrapped it
  onto two rows (`Caption copied. Verify the pasted text in` / `Instagram.`).
  The Reel and TikTok/X checks compared the sentence with each OCR row
  separately. The carousel check, which passed live on 19 Oct, joins the rows
  first. The offline fixtures had drawn the sentence on one row.
- State `review_required`, cleanup confirmed, video requested 0 times, nothing
  imported. Stopped state restored, 25 protected files unchanged.
  [Summary](reel-attempt-2-summary.json); 76 archived files, manifest
  `16fb86279c12a08d078f8013659f1c25effbf59335f00b36cf6d048ad5d95774`.
- Not affected by the selection highlight: after copying, the page selects the
  caption, and OCR then clips its first and last letters (`resh reel
  acceptanc`). No check reads that row after copying.

### Fix

- `farm_reel_layout.caption_copied` and `farm_tiktok_layout.caption_copied`
  (TikTok and X) require the exact sentence in the page's rows joined with
  single spaces, so wrapping is allowed but nothing is repaired or guessed.
- The Reel, TikTok and X protocol fixtures now wrap the sentence like the phone.
  The layout tests add the real wrapped rows, a missing second row and a wrong
  app name across rows.
- Before this window: layout tests 27/27, the three protocol happy paths, and 47
  service/package tests pass. The complete suite is run after the windows,
  because it would compete with a live window for CPU.
- All three windows re-prepared on this fix (dry probes 3/3, ready), backend
  fingerprint `9c9c6fc8fb0af695f737945861a96853c17fc7e1d5162fbe55ad89b7b23a2902`:

  | Window | Token | Colour code | Download name | Video SHA-256 |
  |---|---|---|---|---|
  | Reel | `41fcf02910fe` | `[1,0,5,2,5,0]` | `imouse-reel-uaercv` | `c21e145d9b45a78a81028c8218779e83a9bd0c2da35b8def0466fc32ad330963` |
  | TikTok | `ec8f0dab0e24` | `[6,1,6,7,0,5]` | `imouse-tt-mwdvff` | `6b118768564f78a542bd183f5f5a1eb59caaa94e37ce1b9cb8e5c453596fc86b` |
  | X | `c6d980f9a79c` | `[0,4,5,1,0,2]` | `imouse-x-vtyxck` | `fc41754b57c6ccafd02ee2d907ee61741e4cd4a5f8c90b69554e1e4e05162a14` |
