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
