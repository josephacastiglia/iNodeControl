# Lanes: parallel work in Switchboard

The Marketing Farm is worked on by several Switchboard agent tabs at once ("lanes"), each on its own
branch in its own folder (`iMouseXP-2.0-combined-candidate.worktrees\<lane>`), and one orchestrator
that hands out work and merges it into `local/combined-candidate-20261012`. Since 3 Nov the
orchestrator is the Claude chat opened in the `iMouseXP-2.0` folder (the project's Claude memory lives
there); Switchboard's own Orchestrator tab stays idle, so only one chat merges, pushes and edits the tracker.
Every lane reads this file first. Started 27 Oct 2026.

## Rules for every lane

- **Draft only.** Never post, publish, send or message. Never sign in, enter credentials, tap
  'Review account', or change account or system settings. Never Save draft for a leftover; unsaved
  leftovers from stopped runs may be discarded (the operator's standing approval). Never delete
  saved drafts or Photos items: the operator does that.
- **Commit by name** (`.switchboard-lanes.json`): `git add -- <path>` for each file you changed,
  never `git add -A` or `git add .`; then `python tools/privacy_scan_staged.py` before every commit.
  Device IDs, screen captures, phone frames and account handles never go into Git. Run output stays
  under `output/` and `windows/`, which are not committed. Never push; the orchestrator does.
- **Only your phones.** Drive only the slots listed for your lane below. The kernel's leases should
  refuse a phone another lane holds (not yet proven with two lanes at once); if yours is refused,
  stop and report, don't take it.
- **Never touch the rack** (kernel, receivers, `Start-/Stop-Multiphone.ps1`, `Release-Receiver.ps1`,
  `auto_connect.py`) unless you are the Rack lane: one restart stops every lane's phones. A stalled
  mirror or a dropped board: stop and report it to the orchestrator.
- **Only your files.** Change the files your lane owns. Shared modules (below) change only with the
  orchestrator's OK, in a small commit it merges at once. `MARKETING-SUITE-TRACKER.md` and the
  farm README are the orchestrator's: put what they should say in your summary.
- Never run legacy `tools/setup_imouse_farm.py` or `Open Marketing Farm.ps1`. Verifiers are
  read-only; a check number is never reused.
- Phone work from a lane folder works as from the main folder: `tools/farm_paths.py` finds the main
  folder's rack state and the private evidence archive. Tests whose fixtures sit untracked in the
  main folder (`analysis/farm-platform-drafts-20261017`) skip in a lane folder; run those from the
  main folder or say they were skipped.

## Phones

Rack A is the first 20-slot box (slots numbered by the operator, 1 = far left). Rack B is the second
box of 20 phones, each with its own board and accounts, on this PC. Both racks run on one kernel
(:9916, up to 40 receivers); all 36 phones were connected from the PC on 30 Oct, and the orchestrator
connects only the phones the running lanes need. Rack B phones get lanes once their accounts are named.

| Phone | Board | Platform / account | Lane |
|---|---|---|---|
| A16 | F215 | YouTube | (not connected 4 Nov) |
| A17 | 724E | X (first account) | Repeatability |
| A18 | C24C | Instagram Reel | Scheduler |
| A20 | C214 | TikTok | Repeatability |
| B5 | CD51 | Social apps (iPhone 6s); accounts not yet cleared by the operator | Small phone |
| Other rack B | own | No marketing apps (most carry dating apps, which the farm never opens) | Scale gate (home screen only) |

Rack A has 19 boards (one hub port is empty); the other 14 phones are in the September full-rack
config (`iMouseXP-2.0/analysis/full-rack-config`, device IDs known) but not yet in the farm.

**Rack B** (plugged in 28 Oct 22:32): 20 boards on its own USB host controller, listed with their
hub ports in `analysis/farm-multiphone-20261020/rack-b-boards.json`. Its phones were flat and
charging through their boards; the boards dropped on and off USB for the first minutes, then all
20 stayed present (every 10 s, 22:40-23:01; rack A's 19 never dropped). Bring-up, once the
phones are on:
1. Each phone: on, unlocked, on the farm Wi-Fi, with the pointer settings rack A uses
   (AssistiveTouch on, 'Always Show Menu' off). The operator does this on the phones.
2. Per board, held mode, one at a time: a receiver that accepts any phone (as F215's did on
   20 Oct), connected from the board itself; the receiver log names the phone's device ID and
   model; lock the receiver to it.
3. `pointer_identify.py`: the operator names the physical slot (1 = far left) as the pointer
   circles; `pointer_measure.py` calibrates the model. USB hub/port order is not slot order.
4. Names `iMouse2-B<slot>` and console names `Phone B<slot>`; backend and media ports per slot.
5. The operator names each phone's platform and account (handles stay out of Git).

## Lanes

| Lane | Work (tracker priority) | Owns |
|---|---|---|
| Rack | Restart one phone's receiver without stopping the kernel; backend and media ports for any slot (today fixed for A16-A20); rack B bring-up with names that can't collide with rack A's (slot numbers repeat); a kernel per rack (7). Built and tested off the live kernel; live trials only when the orchestrator schedules them | `src/iMouse.Kernel/`, `analysis/farm-multiphone-20261020/` rack scripts (`*Multiphone*.ps1`, `Release-Receiver.ps1`, `auto_connect.py`, `prepare_slots.py`, `prepare_multiphone.py`, `phone-slots.json`), the port tables in `prepare_window.py` and `tools/farm_creation_runs.py` |
| TikTok photo | TikTok photo post with its sound kept, to a verified draft (3) | `tools/farm_tiktok_*`, their tests |
| X image | X image post to a verified draft (3) | `tools/farm_x_*`, their tests |
| Photos cleanup | Match each test video in Photos to its package; move only those to Recently Deleted, after the operator's OK per run (2) | new `tools/farm_photos_*` and tests |
| Scheduler | Review queue, scheduled runs, daily budgets, unattended restart; local layer merged 4 Nov; now running approved slots on A18 (4) | `tools/farm_preparation_schedule.py`, new `tools/farm_schedule*`, their tests |
| Repeatability | Back-to-back X image (A17) and TikTok photo (A20) runs; the open shared fixes (`farm_observations.classify` Likes on A20, `farm_creation_layout.app_target` enlarged Spotlight reread, verifier `accountHistory`) (2, 3) | `tools/farm_x_*`, `tools/farm_tiktok_*`, and, cleared 4 Nov, `farm_observations.py` and `tools/farm_creation_layout.py` in small commits |
| Small phone | B5 (iPhone 6s): read-only sign-in survey, then the verified formats on a 4.7-inch phone once the operator clears its accounts (3, 7) | new `tools/farm_small_*` and tests; 4.7-inch additions elsewhere described, not made |
| Scale gate | The 8- and 19-phone gates on rack B's home screens: mirroring and input only, no app ever opened (release gates) | new `analysis/scale-gate-20261104/` |

**Shared (orchestrator's OK first):** `tools/farm_screen_layout.py`, `farm_observations.py`,
`farm_start_screen.py`, `farm_carousel_inspection.py`, `farm_creation_runs.py`, `farm_paths.py`,
`imouse_farm_server.py`, `privacy_scan_staged.py`, and `analysis/farm-multiphone-20261020/`
`run_window.py`, `verify_window.py`, `relaunch_check.py`, `close_app.py`, `prepare_window.py`,
`Start-Window.ps1`, `Stop-Window.ps1`.

## The orchestrator

Works in the main folder. Gives each lane one piece at a time, reviews `sb lane diff`, merges one
lane at a time (every merge runs the privacy scan first; a failure changes nothing), syncs the
others, keeps the tracker and this file current, and pushes. Rack work that stops the kernel is
scheduled when no lane is on a phone.
