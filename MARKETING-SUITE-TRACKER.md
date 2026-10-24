# Marketing suite: what is left

The single running list for the iMouse 2.0 Marketing Farm. Updated as work lands; the newest
state wins. Details live in `analysis/farm-multiphone-20261020/README.md` and the dated handoffs.

Last updated: 24 Oct 2026.

## Seven priorities

| # | Priority | Where it stands | What is left |
|---|---|---|---|
| 1 | New content to a verified draft | **All four first formats verified:** Instagram carousel (C24C, 17-19 Oct), Instagram Reel (slot 18, 22 Oct), X video (slot 17, 23 Oct, prep 71), YouTube Short (slot 16, 23 Oct, prep 65), TikTok video (slot 20, 24 Oct, prep 67). | Every further format or account needs its own first pass. |
| 2 | Repeatability and recovery | Runs back out of leftover screens on all four phones; unsaved leftovers are discarded under the operator's standing approval. `close_app.py` closes an app from the switcher; `relaunch_check.py` closes and cold-starts the app, then reruns the read-only check. **TikTok: the draft survived a relaunch (24 Oct).** **X: the video draft did not survive** (only a text-only draft remained). YouTube: survived a force-close overnight; the formal check is blocked (below). | Reel and YouTube relaunch checks; back-to-back new-content runs; unattended recovery. |
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
| Instagram Reel | 18 (C24C) | Verified 22 Oct | Repeat runs (priority 2). |
| X video | 17 (724E) | Verified 23 Oct, prep 71; **video lost after an app relaunch** | Decided: X video drafts are short-lived (below). |
| YouTube Short | 16 (F215) | Verified 23 Oct (read-only check 3) | Relaunch check: the camera's 'Continue your draft video?' prompt freezes phone 16's mirror. |
| TikTok video | 20 (C214) | Verified 24 Oct (prep 67); **survives an app relaunch** (relaunch check 3) | Repeat runs. |

## Waiting for the operator

1. Phone 16: after every YouTube cold start the Short camera asks 'Continue your draft video?' and
   phone 16's mirror stops delivering frames while it shows, so the farm cannot tap it. Does the phone
   itself respond normally then? (Blocks only the YouTube relaunch check.)
2. ~~Phone 20 AssistiveTouch~~: 'Always Show Menu' turned off by the operator (23 Oct).
3. ~~Merge the prompt-validation branch~~: merged 23 Oct on the operator's yes.
4. Cleanup (operator: 'you do'). Saved drafts are deleted permanently, so the operator deletes leftover
   test drafts (X's text-only 'Fresh x acceptance'). Test videos in Photos: Claude to build a cleanup
   that matches each video to its package and only moves those to Recently Deleted (recoverable).
5. ~~X video drafts after a relaunch~~: decided 23 Oct (operator left it to Claude), see Decisions.

## Decisions

- **X video drafts are short-lived (23 Oct).** An X video draft is created right before it is used
  and X is not closed in between; nothing assumes it survives an app restart or a reopen-and-save.
  The scheduler (priority 4) creates X video drafts inside the posting window, never days ahead.
  Text-only X drafts are not a substitute: the post needs its video.
- Prompt validation merged (24 Oct, e2ee3a8, operator's yes), adapted to the per-phone kernel identity.
- All four verifiers are read-only (X and YouTube 23 Oct, TikTok 24 Oct): Drafts must show exactly one
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
