# Marketing suite: what is left

The single running list for the iMouse 2.0 Marketing Farm. Updated as work lands; the newest
state wins. Details live in `analysis/farm-multiphone-20261020/README.md` and the dated handoffs.

Last updated: 23 Oct 2026.

## Seven priorities

| # | Priority | Where it stands | What is left |
|---|---|---|---|
| 1 | New content to a verified draft | Verified: Instagram carousel (C24C, 17-19 Oct), Instagram Reel (slot 18, 22 Oct), X video (slot 17, 23 Oct, prep 71), YouTube Short (slot 16, 23 Oct, prep 65, read-only check 3). | TikTok video. Every further format or account needs its own first pass. |
| 2 | Repeatability and recovery | Runs back out of leftover screens on all four phones; unsaved leftovers are discarded under the operator's standing approval. `close_app.py` closes an app from the switcher; `relaunch_check.py` closes and cold-starts the app, then reruns the read-only check. **X: the video draft did not survive a relaunch** (only a text-only draft remained). YouTube: the draft survived a force-close overnight, but the relaunch check is blocked (below). | Finish the YouTube and Reel relaunch checks; back-to-back new-content runs; unattended recovery. |
| 3 | Platform coverage | Reel, X and YouTube verified. TikTok reaches the new-draft details screen. | Finish TikTok; then TikTok photo (sound kept) and X image. Merge permission-prompt validation (operator's yes needed). Story, text, thread and long video stay unsupported. |
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
| TikTok video | 20 (C214) | Reaches details; cover check fixed for slot 20 | Blocked by the AssistiveTouch button (see below). |

## Waiting for the operator

1. Phone 16: YouTube shows 'Continue your draft video?' and the mirror freezes on it (no frames even
   when the pointer moves), so the farm cannot tap. Tap 'Start over' on the phone (it says it saves the
   draft and starts a new Short), or tell me the phone itself is frozen.
2. Phone 20: Settings > Accessibility > Touch > AssistiveTouch > turn off 'Always Show Menu'
   (one-time; the other three phones already hide the button while the mouse is connected).
3. ~~Merge the prompt-validation branch~~: merged 23 Oct on the operator's yes.
4. Clean up test videos (Photos, Safari Downloads) and leftover test drafts (X's text-only
   'Fresh x acceptance')? Nothing saved is deleted without a yes.
5. ~~X video drafts after a relaunch~~: decided 23 Oct (operator left it to Claude), see Decisions.

## Decisions

- **X video drafts are short-lived (23 Oct).** An X video draft is created right before it is used
  and X is not closed in between; nothing assumes it survives an app restart or a reopen-and-save.
  The scheduler (priority 4) creates X video drafts inside the posting window, never days ahead.
  Text-only X drafts are not a substitute: the post needs its video.
- Prompt validation merged (23 Oct, operator's yes), adapted to the per-phone kernel identity.

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
