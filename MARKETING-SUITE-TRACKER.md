# Marketing suite: what is left

The single running list for the iMouse 2.0 Marketing Farm. Updated as work lands; the newest
state wins. Details live in `analysis/farm-multiphone-20261020/README.md` and the dated handoffs.

Last updated: 25 Oct 2026.

## Seven priorities

| # | Priority | Where it stands | What is left |
|---|---|---|---|
| 1 | New content to a verified draft | **All four first formats verified:** Instagram carousel (C24C, 17-19 Oct), Instagram Reel (slot 18, 22 Oct), X video (slot 17, 23 Oct, prep 71), YouTube Short (slot 16, 23 Oct, prep 65), TikTok video (slot 20, 24 Oct, prep 67). | Every further format or account needs its own first pass. |
| 2 | Repeatability and recovery | Runs back out of leftover screens on all four phones; unsaved leftovers are discarded under the operator's standing approval. `close_app.py` closes an app from the switcher; `relaunch_check.py` closes and cold-starts the app, then reruns the read-only check. **Back to back: Reel runs 45 and 46, TikTok runs 75 and 76, and X runs 72 and 73, each verified in a row with no change between (25 Oct); YouTube runs 76 and 77 (27 Oct).** **Survive an app relaunch: TikTok (24 Oct), Instagram Reel (25 Oct), YouTube (26 Oct, check 17).** **X: the video draft did not.** YouTube's 'Continue your draft video?' prompt is answered automatically (Start over). | Unattended recovery (phone 16's mirror stalls still need a rack restart). |
| 3 | Platform coverage | Reel, X, YouTube and TikTok video verified. Permission-prompt validation merged (24 Oct). | TikTok photo (sound kept) and X image. Story, text, thread and long video stay unsupported. |
| 4 | Scheduler and warmup | Local preparation and simulations only. | Review queue, scheduled phone runs, real daily budgets, unattended restart. |
| 5 | Analytics | Observations keep evidence; low-view rules can pause a schedule. | A real metrics source, checked against actual account numbers. |
| 6 | Publishing and messaging | Disabled by the operator. | Only with a separate, explicit scope. |
| 7 | Rack and release | Four phones connected, identified and driven at once. | More phones, longer unattended runs, usability, packaging, clean-PC install/update/rollback. |

## Core release gates (separate from the list above)

All open: Home and App Switcher reliability; the first space dropped when typing (FKA);
recasting after a receiver restart; 8- and 19-phone scale; endurance; clean-PC install.

## Platform status

| Platform | Phone | State | Next step |
|---|---|---|---|
| Instagram Reel | 18 (C24C) | Verified 22 Oct and in runs 40, 42, 45, 46 (45-46 back to back); **survives an app relaunch** | Longer unattended series. |
| X video | 17 (724E) | Verified 23 Oct (prep 71) and in runs 72 and 73 (back to back); **video lost after an app relaunch** | Decided: X video drafts are short-lived (below). |
| YouTube Short | 16 (F215) | Verified 23 Oct (read-only check 3); **survives an app relaunch** (26 Oct); runs 69 and 71 verified in one pass, 70 by re-check; **runs 76 and 77 verified back to back (27 Oct)** | — |
| TikTok video | 20 (C214) | Verified in runs 67, 73, 75 and 76 (75-76 back to back); **survives an app relaunch** | Longer unattended series. |

## Waiting for the operator

1. ~~Phone 16's 'Continue your draft video?' prompt~~: solved 26 Oct without the operator. The earlier
   tap had missed the button (y 583, the button is at y 616); a tap at its centre works.
2. ~~Phone 20 AssistiveTouch~~: 'Always Show Menu' turned off by the operator (23 Oct).
3. ~~Merge the prompt-validation branch~~: merged 23 Oct on the operator's yes.
4. Cleanup (operator: 'you do'). Saved drafts are deleted permanently, so the operator deletes leftover
   test drafts; X's text-only 'Fresh x acceptance' was deleted by the operator (24 Oct). Test videos in Photos: Claude to build a cleanup
   that matches each video to its package and only moves those to Recently Deleted (recoverable).
5. ~~X video drafts after a relaunch~~: decided 23 Oct (operator left it to Claude), see Decisions.
6. Phone 16 YouTube drafts to delete, when convenient (27 Oct): the untitled 'Oct 26, 2026' drafts
   (closing YouTube on an unsaved Add details saves one; run 74's leftover was closed that way at the
   operator's request, since Back did not work on the phone either) and the extra 'Fresh short test'
   drafts from runs 69-77.
7. (old) Phone 16 (26 Oct, 02:00): YouTube run 67 stopped on Add details with the title pasted, unsaved.
   That screen's back arrow ignores pointer taps (also a slow press, Escape and an edge swipe), so the
   leftover cannot be discarded from the PC. Either the operator taps Back -> Discard on the phone, or
   YouTube is closed from the switcher, after which its camera offers 'Start over', which *saves* the
   leftover as one extra draft (for the operator to delete later).

## Decisions

- **X video drafts are short-lived (23 Oct).** An X video draft is created right before it is used
  and X is not closed in between; nothing assumes it survives an app restart or a reopen-and-save.
  The scheduler (priority 4) creates X video drafts inside the posting window, never days ahead.
  Text-only X drafts are not a substitute: the post needs its video.
- Prompt validation merged (24 Oct, e2ee3a8, operator's yes), adapted to the per-phone kernel identity.
- All four verifiers are read-only (X and YouTube 23 Oct, TikTok 24 Oct, Reel 25 Oct): Drafts must show exactly one
  draft with the package video (and the exact text where the list shows it); nothing is reopened.

## Rules learned the hard way

- Never reopen and save again a saved X draft: it drops the video. Verifiers read Drafts only.
- An X video draft also loses its video when X is closed and relaunched (23 Oct, relaunch check 2).
- A reopened YouTube draft can hang on 'Processing'; the verifier never reopens drafts.
- The Claude desktop app updating itself stops the kernel and backends (22 Oct, 22:53).
- Run test suites only while the phones are idle; CPU load breaks the 1.5 s frame-age rule.

## Log

- 23 Oct: X verified (prep 71). X and YouTube verifiers made read-only. Tracker started.
- 23 Oct 11:45: rack reconnected after the night; YouTube verified (read-only check 3). X relaunch
  check: X closed and cold-started; Drafts then held only a text-only draft (video lost). YouTube
  relaunch check stopped on the camera's 'Continue your draft video?' prompt (mirror frozen).
- 24 Oct: prompt validation merged. TikTok verified (prep 67): picker rows found by gutter thickness,
  'Drafts: 1' read enlarged, slot 20's drafts grid (no 'Sort by' row) and larger cover. Kernel stops
  whenever the Claude session or app restarts; bring-up is part of every resume.
- 24 Oct: TikTok relaunch check 3 passed (closed from the switcher, cold-started, draft found). The
  switcher shows the front card centred or pushed right with its name cut off; TikTok's card is found
  by its profile's 'Following'.
- 25 Oct: Reel verifier made read-only. Instagram relaunch check 3 passed (22 Oct draft found after a
  cold start; a Meta 'Your Meta Account is here' sheet was dismissed by tapping the dimmed area, never
  'Review account'). The switcher key was once ignored on phone 16; it is sent once more when the app
  is still full screen. YouTube's camera alert ignores pointer taps; relaunch check parked.
- 25 Oct afternoon: repeat runs. Reel 40, 42, 45, 46 verified (45-46 back to back, no change
  between); TikTok 73 verified. Every failed run stopped safely before saving and got its fix:
  OCR ('Add a caption..', mangled download codes, header tabs, 'Edit cover' under the pointer,
  the caret on placeholders), an Instagram crossfade, a late Create sheet, slot 20's lighter caret
  and its two drafts-grid layouts.
- 25 Oct evening: TikTok 75 and 76 verified back to back with no change between, after the caret
  retry was limited to fields that already hold a pasted description.
- 25 Oct evening: X 72 and 73 verified back to back with no change between (two same-text drafts;
  the thumbnail tells them apart).
- 26 Oct: YouTube relaunch solved. 'Continue your draft video?' is YouTube's own dialog, not an iOS
  alert; the "ignored" tap had landed 33 px above Start over. Creation, the verifier and the start
  screen now answer it with Start over (saves the draft) at the label's centre. Phone 16's mirror had
  silently stopped for 9 h (full kernel restart). Switcher swipes on slot 16 fail about half the time
  with no visible change: up to 3 swipes on the same card. The camera lost its Drafts button (white
  record button, effects row); Drafts is now reached through the Add gallery. **Relaunch check 17
  passed.**
- 26 Oct night: YouTube runs 66 and 67 stopped safely before saving (OCR missed 'Add' over a lamp, then
  'Title' beside the caret; both are now read again enlarged). The USB boards of phones 16 and 20
  dropped off and came back (two rack restarts); phone 16's mirror froze once more right after a tap.
- 26-27 Oct night, YouTube on the new camera layout: run 69 verified in one pass; 70 saved and verified
  by re-check 5; 71 verified in one pass. Stops, each safe and fixed: Windows OCR tilting the Drafts list
  5.1 deg (words rotated back), the thumbnail's 'TEST' on the title line, a fading/solid caret (title read
  with the caret blanked), the Paste decision 13 ms past its age limit (reconfirmed), the + disk tinted by
  the feed, the draft prompt drawn smaller. Phone 16's mirror stalled twice more and its USB board once
  (rack restarts); switcher swipes on phone 16 fail often (3 of 3 at 00:30).
- 27 Oct 02:30-03:10: run 74's leftover closed from the switcher (first try). The relaunched home feed's
  + disk was tinted pink, red near white (grey test now asks for a channel below white). Run 75 stopped
  before input (pointer dot over the 'YouTube' header), then on a mirror stall at the draft prompt
  (rack restart; all four reconnected first try). **Runs 76 and 77 verified back to back.**
