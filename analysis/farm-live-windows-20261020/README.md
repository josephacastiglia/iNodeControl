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

## 3. Reel attempt 3: the copy fix worked; stopped at Safari's link menu

- Started on `805bcd6`; the read-only check recognized the exact profile.
- Six actions were answered. The wrapped *Caption copied* confirmation now passed
  on the phone, and the long press on *Download video* opened Safari's link menu
  with the video preview playing. The preview fetched the video 3 times, but no
  download was chosen.
- It stopped before tapping anything in the menu: *Exact visible label missing:
  Open.* The menu rows were exactly the 17 Oct rows (y 773–1005), but iOS drew
  the column about 85 px further right (labels at x 139 instead of about 60), and
  it also listed *Open in Tab Group* and *Copy Link*. The check used the 17 Oct x
  boxes.
- State `review_required`, cleanup confirmed, stopped state restored, 25
  protected files unchanged. [Summary](reel-attempt-3-summary.json); 78 archived
  files, manifest `f6d25941a0670eb8727a74bf9998bc64809ec36ea5394402870f72584af9bb46`.
  The run left Safari's link menu open on the phone.

### Fix

- `farm_reel_layout.link_menu` (shared by Reel, TikTok and X): the rows stay
  fixed, the labels may sit anywhere from x 40 to 360 but must share one left
  edge (within 12 px). The tap target is the exact *Download Linked File*
  label's own centre.
- A layout test uses the phone's 20 Oct rows. Negatives: a misaligned label, a
  missing preview header, a missing *Download Linked File*, and a column pushed
  past x 360. The retained 17 Oct menu still gives its original target.
- Before the next window: Reel layout 13/13, TikTok and X layout 15/15, and the
  three protocol happy paths pass.
- The share-sheet and download screens use full-width system sheets anchored to
  the screen edges. They matched this phone exactly on 17 Oct, so they are
  unchanged rather than loosened without evidence.
- All three windows re-prepared on this fix (dry probes 3/3, ready), backend
  fingerprint `0781cafdfd114bc0ad375dbe23715621b69103a6b0468d5c2acf40126b7a70aa`:

  | Window | Token | Colour code | Download name | Video SHA-256 |
  |---|---|---|---|---|
  | Reel | `65b4ad84ef48` | `[3,7,2,0,7,3]` | `imouse-reel-pwwxuy` | `1742576125348d707bb1a0a3d6e6ae9d2b7e5c5f13142647acfb2f9b7db586e5` |
  | TikTok | `85724c91afc3` | `[3,1,4,0,2,4]` | `imouse-tt-ndnhvn` | `52047d47f61ad9dc1750c7bcef1aa7381b4c9a0ad891af13e25b1fd15530038c` |
  | X | `4408ea3ca4a3` | `[7,1,6,2,3,0]` | `imouse-x-hcxhkf` | `939d68b24b355d5bb723a5d9a0add991ee74646da1c1b7a9e39c65cecf399ada` |

## 4. Reel window on `54262d8`: four attempts, all stopped on frame freshness

- The operator asked that the farm do the phone-side steps itself. Two additions
  came out of that (sections 5 and 7).
- **Calibration for auto-connect.** The operator screenshotted C24C's Screen
  Mirroring sheet before mirroring, opened it in Photos, and connected. One
  read-only frame then gave the not-yet-mirroring geometry: card x 42–458 from
  y 341, separators at y 458 / 520 / 583 / 645 / 709, so row centres at
  (250, 489) / 551 / 614 / 677. The mirroring-state sheet sits higher (row 1 at
  472), so the old fixed point would have been 17 px off.
- Four attempts ran in the same window, with no restart or reconnect:
  - The Run scripts now allow attempts 2–5, each only if every earlier attempt is
    a confirmed, cleaned-up stop before import.
  - Every attempt stopped safely:
    1. A stale first frame (2.5 s).
    2. A decision aged to 1,550 ms (after Home).
    3. A stale frame (1.9 s) on the transfer page.
    4. A decision aged to 1,503.6 ms at *Copy caption*.
  - Nothing was imported in any attempt.
- **Cause.** The PC was at 70–100 % CPU from other work: Defender scanning, a
  headless Chrome automation, a Node process and other sessions. Frames arrived
  0.8–1.9 s old (0.5–0.9 s earlier in the night), and each OCR call took about
  0.7 s (a new PowerShell process per call). The operator chose to keep the 1.5 s
  limit and fix the decision method.
- The window was then stopped (stopped state restored, 25 protected files unchanged).
  [Summary of all four attempts](reel-prep4-attempts-1-4-summary.json); 175 archived files, manifest
  `2393c96c892c85a485d85c9f0a4229b134f246f2548cb7423a894d09cbbd9e15`.

## 5. Guarded start-screen helper (`tools/farm_start_screen.py`)

Brings C24C to a window's verified start screen so the operator does not have to.
- It holds the lease and decides every tap on a fresh frame.
- Text recognition is slow on a loaded PC, so a tap is decided on a newer frame
  that matches the recognized one in pixels, and that frame's age counts.
- It refuses any screen it does not recognize and never repeats an uncertain tap.
- Instagram profile route: already at the top → nothing; own profile scrolled →
  tap the profile tab; anything else → Home, then the workflow's own app route
  (app icon, or Spotlight *Search* and its result), then the feed's profile tab.
- Live on 20 Oct:
  - From a scrolled profile: one tap reached the top.
  - From Safari: Home → *Search* → *Instagram* → feed → profile tab → exact
    @xs.halle.xo profile.
  - The lease was released each time.

## 6. Decisions reconfirmed by a newer frame (keeps the 1.5 s limit)

- **`farm_draft_workflow.Workflow`.**
  - When a recognized decision's frame ages past 1.5 s before anything is sent
    (`DecisionExpired`, or the new `FrameNotRecent`), `bound_command` calls
    `reconfirm`.
  - `reconfirm` captures up to three newer frames, moving the pointer only. A
    newer frame counts only if it is from the same receiver stream, lease and
    input generation, is itself ≤ 1.5 s old, and matches the recognized frame
    under that screen's own settling rule (the same masks used for two-frame
    settling).
  - The command is then sent once, bound to the recognized observation, with the
    newer frame's age checked at dispatch. Confirming frames are journaled
    (`decisionConfirmations`) and exported with the evidence.
- **Settling (`farm_transitions.wait_for_transition`).** It takes
  `require_recent`. Screens with a confirmation rule may settle on frames that
  are no longer recent. All other checks stay: expiry, pairing, identity,
  context, sequence and the two-frame comparison.
- **Scope.** Only the settled Reel, TikTok and X screens have a confirmation
  rule. The carousel path, transient callouts and prompt answers keep the plain
  rule unchanged.
- **Tests (X protocol fixture).**
  - Recognition that outlasts the budget is reconfirmed twice and the draft is
    created.
  - A screen that changes after its decision frame settled is never tapped: every
    confirmation is rejected and the run stops.
- **Complete suite** (`python-shard-confirm-*.txt`): 559 tests in five parallel shards,
  557 passed. X 10, TikTok 11, Reel 9 and carousel 58 all pass. The two failures were load
  flakes in untouched code: the rehearsal timing test again, and a loopback
  connection abort (`WinError 10053`) in a transfer-session test. Both pass alone,
  together with the 6 new auto-connect tests (`python-rerun-confirm.txt`: 25 passed).
- All three windows re-prepared on this code: backend fingerprint
  `37ac9686d30e4934f24744c3d73d36f4cca1fc078f2c3de579e3d4dae226f9f3`, dry probes 3/3, ready.
  Tokens: Reel `ff9863545bbb`, TikTok `a32329d208b0`, X `cb3872ad0bff` (each
  `live/preparation.json` is authoritative).

## 7. PC-initiated screen mirroring (`tools/farm_mirroring.py`)

The operator asked for the original app's one-click auto-connect. The vendor's version
replays calibrated taps blind. Ours keeps the handoff's rule that the receiver must be
positively identified:

- **Preconditions:** the private receiver is up but not live, and C24C is free under a
  held lease. Bonjour (`dns-sd`) must show `iMouse2-C24C`, at most four AirPlay
  receivers, and every other receiver sorting after ours under plain, case-insensitive
  and number-aware order. Then ours is provably row 1. A *Bedroom TV*, an uppercase
  name or `iMouse2-C241` can sort first, so the run refuses rather than guessing.
- **Bounded blind sequence:** ControlBar (Fn+C), the Screen Mirroring tile (199, 432),
  then row 1 (250, 489) from the calibration. The receiver must go live within 8 s;
  otherwise it stops with no retry or further input.
- **After connecting:** Control Center is closed by two taps below the sheet and grid
  (250, 960), each decided on fresh frames.
- **Own transport:** C24C only, ControlBar as the only key, clicks only at those points.
- **Tests:** 6 offline tests (`tools/test_farm_mirroring.py`) cover the browse parser,
  the first-row proof, refusals that send nothing, the exact three blind inputs plus
  the verified close, no retry after a failed connection, and the transport limits.

## 8. After the PC restart (20 Oct, 17:29)

- **Board unplugged.** The operator unplugged C24C's iMouse board overnight.
  Auto-connect's first key then failed in the kernel (`Board C24C` not
  enumerated, code 33), which held C24C's input as designed. The PC then
  rebooted, so that window's services ended without their Stop script. Afterwards
  there were no rack processes or listeners, and the 25 protected files were
  unchanged (`restoration.json` written by hand, archive `reel-prep5-interrupted`,
  45 files).
- **Locked phone.** On the next window, auto-connect sent its three inputs, but
  the phone was **locked**: nothing connected within 8 s, so it stopped as
  designed. The operator unlocked the phone and mirroring was connected.
  Precondition for auto-connect: farm phones must have Auto-Lock set to Never. No
  passcode is ever entered.
- **Start screen.** Two fixes:
  - **Control Center left open.** The start-screen helper now recognizes Control
    Center (the *Focus* tile and the battery row; OCR reads them as "Focus C" and
    "... 93% ...") and closes it with one confirmed tap on its empty lower area.
  - **Search pill.** After the restart, the Home screen's Search pill template
    failed (5.4 % changed pixels against a 4 % limit), because its translucent fill
    takes the wallpaper's tint. The Reel run's own Home recognition uses the same
    template. `farm_creation_layout.home_search` keeps the template and, when it
    fails, accepts the exact OCR word *Search* inside the pill box.
  - Tests: Control Center is still refused as Home; a new test covers the label
    fallback and its negatives; carousel creation, the layout suites and the three
    protocol happy paths pass.
- All three windows re-prepared: fingerprint
  `dd9726a1b3426d39b661be66c4c90b22730f396e253aab4a7b6efba803e1b9a8`; tokens Reel
  `03f451facdd9`, TikTok `f854b4bfcdb0`, X `9f50b5f1a993`. Archive
  `reel-prep6-auto-connect-and-start-screen` (68 files).
