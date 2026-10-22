# iNodeControl / iMouse 2.0: full context handoff

Updated **22 October 2026, about 13:45 EDT**, by Claude (Code). This supersedes
`CLAUDE-HANDOFF-20261019.md` for the current state. Keep that document for history before
19 October, the preserved-branch map and the private-evidence archive layout.

**In one line:** the Marketing Farm now runs on four rack phones at once, one platform per
phone. Instagram Reel has one independently verified draft (slot 18). TikTok (slot 20), X
(slot 17) and YouTube Short (slot 16) run live; each run stops safely on the next unseen
screen variant, which then gets a fix and a test. **Nothing is ever posted or messaged.**

## 1. Start here

| Item | Value |
|---|---|
| Private GitHub repository | <https://github.com/josephacastiglia/iNodeControl> |
| Working folder | `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-combined-candidate` |
| Development branch | `local/combined-candidate-20261012` (always continue here) |
| Old default `main` | `ee445d7`, the original import; **not** the current product |
| Python | `C:\Users\joey_\AppData\Local\Programs\Python\Python311\python.exe` |
| Private evidence (outside Git) | `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\` |

Read in this order:

1. This document.
2. [`analysis/farm-multiphone-20261020/README.md`](analysis/farm-multiphone-20261020/README.md):
   the four-phone rack, windows, and every live finding since 20 October.
3. [`CLAUDE-HANDOFF-20261019.md`](CLAUDE-HANDOFF-20261019.md): what was accepted before
   20 October (Instagram carousel, recovery), the branch map and evidence rules.
4. `MARKETING-FARM-ACCEPTANCE.md` and the opening sections of `MARKETING-FARM-STATUS.md`.

Venture context: `ventures-brain/nodetheory-io/BRAIN.md` (selling phone-farm services; it
indexes this repository) and `ventures-brain/ofm-halle-mass-marketing/BRAIN.md` (the client
relationship the accounts belong to; its status there "needs reconfirmation").

## 2. What the project is

iNodeControl is **iMouse 2.0**: a Windows .NET 8 WPF console, an independent C# kernel and
independent UxPlay AirPlay receivers that drive a rack of iPhones. The box holds 20 phone
slots, numbered by the operator 1 (far left) to 20 (far right).

```text
Console / Python farm backend -> HTTP kernel (:9916) -> USB HID board -> iPhone   (input)
iPhone -> AirPlay over Wi-Fi -> UxPlay receiver -> frames -> OCR/templates          (video)
```

Input and video are separate channels. An input lease stops two controllers driving one
phone. **A successful HTTP/HID reply never proves the phone showed or saved anything**: every
decision is made on a fresh, recognized frame, and anything uncertain stops for review.

The active feature is the **Marketing Farm**: prepare content, carry it to a phone, and save
it as a **draft** in Instagram, TikTok, X or YouTube, then independently reopen and verify the
draft. Publishing and messaging are disabled by the operator.

## 3. The seven marketing priorities (status 22 October)

| # | Priority | Status | What remains |
|---|---|---|---|
| 1 | New content to a verified draft | Passed for an Instagram carousel (C24C, 17-19 Oct) and now an **Instagram Reel** (slot 18, 22 Oct). | Each other format and account needs its own acceptance. |
| 2 | Repeatability and recovery | Scoped carousel recovery passed (19 Oct). Since 21 Oct the runs back out of leftover screens on four phones (previews, share sheets, menus, editors, drafts). | Repeated new-content runs, proven app relaunch, unattended recovery. |
| 3 | Platform coverage | Reel verified. TikTok, X, YouTube Short running live (section 6). Permission-prompt validation sits on an unmerged branch. | Verified TikTok, X and YouTube drafts; prompt validation; then TikTok photo (sound kept) and X image. Story/text/thread/long video/community stay unsupported. |
| 4 | Scheduler and warmup | Local preparation and simulations only. | Review queue, scheduled phone runs, real budgets, unattended restart. |
| 5 | Analytics | Observations keep evidence; low-view rules can pause. | A verified metrics provider checked against real account data. |
| 6 | Publishing and messaging | **Disabled by the operator. Not authorized.** | Only with a separate explicit scope. |
| 7 | Rack and release | Four phones connect, are identified and driven at once. | More phones, longer unattended runs, usability, packaging, clean-PC install/update/rollback. |

The separate core release gates (Home/App Switcher reliability, the FKA first-space typing
issue, recasting, 8- and 19-phone scale, endurance, clean-PC install) remain open; keep them
apart from this list.

## 4. The rack today

| Slot | Board | Receiver | Phone IP | Platform | Account | Backend | Media |
|---|---|---|---|---|---|---|---|
| 18 | C24C | `iMouse2-18` | 192.168.4.57 | Instagram Reel | `xs.halle.xo` | 9915 | 9917 |
| 20 | C214 | `iMouse2-20` | 192.168.4.27 | TikTok video | `xs.hallexx` | 9925 | 9927 |
| 17 | 724E | `iMouse2-17` | 192.168.4.65 | X video | new account, bound at run time | 9935 | 9937 |
| 16 | F215 | `iMouse2-16` | 192.168.4.69 | YouTube Short | signed-in channel, bound at run time | 9945 | 9947 |

- Receiver ports 7110/7130/7140/7150 (slots 18/20/17/16). The PC is 192.168.4.26.
- Kernel: `output/multiphone-kernel-20261020/iMouse2.Kernel.exe`, DLL SHA-256
  `2350ca2241ae58e7324bc976759f31227c4b6cfe89940bf43632deaa8468cfaf`, API `http://127.0.0.1:9916/api`.
  It starts every receiver **held**; one is advertised at a time so each phone sees exactly
  one new Screen Mirroring choice.
- C241 is excluded. Slot assignments are in `phone-slots.json`, confirmed by the operator.
- The new X account's handle is **never written to Git** (see section 10).

## 5. How to operate

All commands run from `analysis/farm-multiphone-20261020/`.

### Bring-up after power or a stop

```powershell
.\Start-Multiphone.ps1 -Stage slots                      # kernel + four held receivers; no input
.\Release-Receiver.ps1 -Board C214 -Stage slots           # advertise one receiver
python auto_connect.py --board C214 --phone-ip 192.168.4.27   # Home, Control Center, tile, row; mDNS proof first
# repeat Release + auto_connect for 724E (.65), F215 (.69), C24C (.57) as needed
```

`auto_connect.py` sends a blind tap on the Screen Mirroring tile only after an mDNS query from
that phone's own address proves the card opened; a live receiver then proves the board drives
that phone. Since 22 Oct it renews its 15-second lease before every command: two reconnects
outlasted the lease, which left C214 and F215 **stopped**. To clear a stopped, unowned board:
`POST /input/resume {"id": <deviceId>, "expected_generations": {<deviceId>: <generation>}}`.

### One window per phone

```powershell
python prepare_window.py --platform tiktok --slot 20 --phone-ip 192.168.4.27 --account xs.hallexx
#   reel and tiktok need --account; x and youtube must not have one (bound at run time)
.\Start-Window.ps1 -Window tiktok-slot20                 # backend only
python ..\..\tools\farm_start_screen.py tiktok-profile windows\tiktok-slot20\start-screen-1 windows\tiktok-slot20\creation-config.json
python run_window.py --window tiktok-slot20 --attempt 1  # never replays an attempt
python watch_run.py --window tiktok-slot20 --driver-output <driver output file>
.\Stop-Window.ps1 -Window tiktok-slot20
```

- Start screens: `instagram-profile`, `tiktok-profile`, `x-timeline`, `youtube-home`. They back
  out of known leftovers (Control Center, Reel details/editor via "Start over", never "Save
  draft", New reel picker) and stop on anything else.
- **Re-prepare after any change to the 47 fingerprinted backend files** (list in
  `tools/imouse_farm_server.py`, `source_hash`): move the old folder to
  `windows-archive/<window>-prepN`, then run `prepare_window.py` again. The start-screen tool and
  the analysis scripts are not fingerprinted.
- A new attempt in the same window is allowed only after a confirmed stop **before import**
  (`retryBeforeImportAllowed: true`). Otherwise re-prepare: each preparation stages a new video.
- `verify_window.py --window reel-slot18 --attempt 1 --check N` reruns only the Reel verifier on
  an already-saved draft (never re-creates). It refuses unless creation stopped exactly there.
- `one_tap.py` sends one supervised navigation tap (required labels, publish/share guard, fresh
  after-frame). Used to back out of screens a stopped run left, for example X's empty composer
  (Cancel), TikTok's gallery (x at 34,90) and camera (x at 37,113).

### Shut down

```powershell
.\Stop-Window.ps1 -Window <each running window>
.\Stop-Multiphone.ps1 -Stage slots     # graceful stop, then an mDNS goodbye so phones drop the names
```

The kernel kills UxPlay without its mDNS goodbye; without `mdns_goodbye.py` phones keep listing
stopped receivers for 75 minutes.

## 6. Platform status and exact next steps

**Instagram Reel, slot 18: done.** Run 38 saved one Reel draft (22 Oct 01:11); verifier check 3
reopened the unique matching draft with the exact caption "Fresh reel acceptance" and account
`xs.halle.xo`, played the package video and kept it (01:22). Reels drafts: 1022 (ours) and 1017
(17 Oct).

**TikTok, slot 20: in progress.** Safari on this phone runs in Private Browsing. Runs reach:
Safari transfer, download, Save Video, TikTok profile, gallery, selecting the package video.
The badge and tray checks for the selection were fixed today on real frames (rim-insensitive
badge, tray matched by tile colours). Next: editor, removing the suggested sound (this is a
no-sound test), caption paste, Drafts, then the verifier. A run (prep 56) was in progress when
this was written.

**X, slot 17: blocked on the phone.** Since today's power-up the X app ignores every pointer
click (avatar, header tabs, bottom tabs; hover highlights still show), while iOS and other apps
on the same phone take clicks. Pointer landings measure within 5 px. Needs the operator to
force-close and reopen X on phone 17 (check for an app update or an account notice). Then
continue: the run already passes the timeline, account menu (yesterday), Safari transfer and
Save Video, and opens the composer; the Paste-callout branch (`x_composer_focused`) is next.

**YouTube Short, slot 16: blocked on the phone.** YouTube shows "Connect to the Internet - You're
offline" on phone 16 since the power-up (the other phones load content). Needs the operator to
restore that phone's internet (Wi-Fi without internet, or the date/time after a power loss). The
labelled five-item tab bar on this phone is now accepted (`yt_home`, create + at 250,1011).
The rest of the YouTube flow has not run on this phone yet.

## 7. What the live runs taught (all handled, with tests)

Most fixes live in `tools/farm_creation_layout.py`, `farm_reel_layout.py`, `farm_reel_creation.py`,
`farm_tiktok_layout.py`, `farm_x_layout.py`, `farm_youtube_layout.py` and `farm_start_screen.py`;
their tests are in `tools/test_farm_safari_start.py` (45 tests) unless noted.

- **Phones differ.** Safari Private Browsing (black toolbar icons matched by shape, grey address
  selection, dimmed home indicator, a shorter link menu, white or blue download glyphs);
  wallpaper showing through iOS search controls (empty field read by its placeholder, the clear
  button by its glyph); different pointer reset spots (C24C about 106,70; 724E about 172,111).
- **Leftovers from stopped runs.** Share sheets of any route (also with a "Send Copy" row),
  previews, the full-screen player (play glyph), link menus, Downloads, Reel details/editor
  ("Start over"), an address still selected, X's open side menu or composer.
- **App changes.** Instagram: Next pill over blurred photos, "First draft", details list rows,
  darkened cover, washed-out Preview title, feed reload after the profile. TikTok: launch splash,
  covered feed header, activity bubble beside Inbox, multi-select gallery with the newest items
  last, white-backed test thumbnails. X (new account): extra header tabs, "Try Grok Bot" menu
  row, first-use tips, avatar joined to the first composer row, Paste callout on the first tap.
  YouTube: the labelled tab bar.
- **Timing.** Decisions older than 1.5 s are re-confirmed on a newer frame under a per-screen
  rule (still screens, a playing Preview, Spotlight's stable Top Hit, an address selection);
  without a rule the run stops. Three parallel runs make this common.
- **OCR.** Split names are joined per line; small light labels are re-read from an enlarged band;
  a garbled account read never overrides a clean read of another account.

## 8. Code map (multi-phone work since 20 October)

| Area | Files |
|---|---|
| Kernel: held receivers, release | `src/iMouse.Kernel/ReceiverFleet.cs`, `ApiServer.cs`, `KernelStartup.cs`, `Program.cs` |
| Rack scripts | `analysis/farm-multiphone-20261020/`: `Start-Multiphone.ps1`, `Release-Receiver.ps1`, `Stop-Multiphone.ps1`, `prepare_slots.py`, `auto_connect.py`, `pointer_measure.py`, `pointer_identify.py` |
| Windows | `prepare_window.py`, `Start-Window.ps1`, `Stop-Window.ps1`, `run_window.py`, `watch_run.py`, `verify_window.py`, `one_tap.py` |
| One phone per window | `tools/farm_phone_identity.py` (PhoneIdentity; config version 2: phone, allowed, account) |
| Shared creation | `tools/farm_draft_creation.py`, `farm_draft_workflow.py`, `farm_creation_layout.py`, `farm_start_screen.py` |
| Platforms | `tools/farm_{reel,tiktok,x,youtube}_{layout,creation,runs}.py` |
| mDNS | `tools/mdns_goodbye.py`, `tools/mdns_watch.py` |
| Privacy | `tools/privacy_scan_staged.py` (lists live in the evidence archive, section 10) |

## 9. Tests

```powershell
& $python -m unittest discover -s tools -p 'test_farm*.py'                 # full farm suite, about 45 min
& $python -m unittest test_farm_safari_start                               # live-finding tests, under 1 s (from tools/)
```

The full suite has **not** been run on the latest commits (its last run, on 21-22 Oct code, had
one failure and two errors, all fixed since). The X creation and live-finding tests passed on
b9ba44a. Running the full suite slows live runs (CPU), so run it while the phones are idle.

## 10. Rules in force

- **Draft only.** Never tap Post, Share, Publish, Your Story or Send. Never message.
- **One platform per phone, on the account signed in on that phone** (operator, 21 Oct). Reel and
  TikTok windows name that handle; X and YouTube bind the signed-in account at run time.
- **Never sign in, enter credentials or change account settings.** The operator signs in.
- **X:** the 20 Oct mass suspension's cause is unknown; X automation is allowed only for the new
  slot 17 account (operator, 22 Oct), draft-only, minimal input.
- **Permission prompts:** recognized on every screen; a run stops with a one-time request until
  an input method is validated (branch below).
- **TikTok:** photo carousels keep a sound; the video acceptance test removes it on purpose.
- **Privacy.** Run `python tools/privacy_scan_staged.py` before every commit. Its private lists
  are `iMouseXP-2.0-evidence-archive/privacy/withheld-candidates.txt` and `extra-handles.txt`
  (the new X handle is there; never copy it into Git). Keep device IDs, phone screen captures,
  kernel logs and `receivers-ready.json` out of Git (ignored folders: `windows/`,
  `windows-archive/`, `identify/`, `look/`, `measure/`, `autoconnect/`).
- **Git.** Stage files explicitly; never `git add -A`, `git push --all/--mirror`, force-push, or
  push `backup/*`. Never run the legacy `tools/setup_imouse_farm.py` or `Open Marketing Farm.ps1`
  (untracked copies sit in the tree; they would overwrite the hardened source).
- **Live boundaries.** Confirm the kernel identity, the phone binding and a free lease before
  input; never steal a lease; keep FKA and phone settings unchanged; stop only owned processes.

## 11. Known issues and risks

- X ignores clicks on slot 17 and phone 16 is offline (section 6): both need the operator.
- Every attempt imports a new test video into that phone's Photos and Safari Downloads;
  several have accumulated on slots 17, 18 and 20. Nothing was deleted.
- Each new app or phone variant costs one stopped run; expect more before TikTok, X and YouTube
  each produce a verified draft.
- Frames older than 1.5 s under load; keep parallel runs to two or three.
- The prompt-validation work is unmerged (below).

## 12. Waiting for the operator

1. Force-close and reopen X on phone 17.
2. Restore internet on phone 16.
3. Merge `refs/heads/local/prompt-validation-20261020` (001fe6c; its complete-suite record
   lists 597 tests)? Not merged without an explicit yes.
4. Whether to clean up the accumulated test videos and test drafts on the phones.

## 13. Branches

| Branch | State |
|---|---|
| `local/combined-candidate-20261012` | Current product; continue here |
| `local/prompt-validation-20261020` | Permission-prompt validation, unmerged, awaiting the operator |
| `local/youtube-short-20261020` | Merged into the current branch at e2e28c6 |
| Others | See `CLAUDE-HANDOFF-20261019.md`, section 8 |

Commits since the 19 October handoff, newest first: b9ba44a, 4215063, c7214c0, a0ae609,
e2e28c6, bbaf045, 99a6b34, 800b695, 527f9b5, 83fdf56, 3ede8ff, 0719fd1, 54262d8, 805bcd6,
06f7a44, 71b3b35, c358e74, f7fab4a, ba923f6, 425935a, 6134558, b1fea23 (plus this handoff).
