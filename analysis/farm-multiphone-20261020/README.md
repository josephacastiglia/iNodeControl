# Multi-phone bring-up, 20 Oct 2026

One private kernel (port 9916) with four receivers: C24C, C214, 724E, F215. C241 is excluded.
No backend and no farm automation run here. The only phone input sent was move-only pointer
squares (`pointer_identify.py`).

## Box slots

The operator numbered the 20-phone box from 1 (far left) to 20 (far right). See `phone-slots.json`.

| Slot | Board | Receiver | Proof |
|---|---|---|---|
| 16 | F215 | iMouse2-F215 | operator; receiver log shows an iPhone XR, not the C241 phone. Board pairing not yet proven: F215 input is not enabled until its phone is bound. |
| 17 | 724E | iMouse2-724E | locked receiver accepted only its saved phone; pointer square moved its own mirror only; operator confirmed |
| 18 | C24C | iMouse2-C24C | same |
| 20 | C214 | iMouse2-C214 | same |

The September pointer calibrations are off: commanded moves landed short. Recalibrate before any tap.

## One-at-a-time connection (option 1)

Every phone on the Wi-Fi lists every advertised receiver, so phones being set up saw names
meant for other phones. The kernel now accepts `--hold-receivers <boards>`. Held receivers are
not started, so no phone can list them. `POST {"fun":"/device/airplay/connect","data":{"pid":"C214"}}`
starts one held receiver; it then stays advertised until the kernel stops. `/kernel/status`
reports a held receiver's state as `held`.

```powershell
.\Start-Multiphone.ps1 -Stage held      # every receiver held
.\Release-Receiver.ps1 -Board C24C      # advertise one; connect that phone; repeat per board
.\Stop-Multiphone.ps1 -Stage held       # Ctrl+C stop, then withdraw every name
```

`prepare_multiphone.py --held` writes `held/preparation.json` and its own run folder, pinned to
the rebuilt kernel in `output/multiphone-kernel-20261020` (DLL sha256 `2350ca22…`). The live
Reel/TikTok/X windows still pin the 18 Oct kernel and are unaffected.

Run on 20 Oct: C24C 21:27, C214 21:29, 724E 21:29, F215 21:40, each picked from a list with one
new name. Releases are logged in `held/releases.jsonl`.

## Stale names after a restart

The first held start still showed all four names in a Bonjour browse. Cause: the kernel ends each
UxPlay receiver by killing it, and UxPlay's built-in mDNS responder (`lib/mdnsd`) only sends its
goodbye on a clean unregister. Listeners then keep the names for the record TTL
(`MDNSD_TTL_SERVICE`, 4500 s, 75 minutes). `tools/mdns_goodbye.py` sends that goodbye
(the `_airplay._tcp` and `_raop._tcp` PTR records with TTL 0, from port 5353, on every IPv4
interface). It refuses any receiver its kernel reports running. This PC's Bonjour removed the
three stale names within a second. `Stop-Multiphone.ps1` now sends it after every stop.

The same kill-without-goodbye likely explains earlier cases where a restarted receiver was
not relisted by a phone until a replug.

## Mistake recorded

On the earlier live windows (same day), `archive_attempt.py` was run in parallel with
`Stop-ReelWindow.ps1`. Stop failed ("Private process identity changed: backend") because the
processes had already exited. Afterwards no process or listener remained and the 25 protected
files were unchanged; the records are archived as `reel-prep8-unused`. Archive only after Stop
has finished.

## Not committed

Kernel logs, `receivers-ready.json`, and the `identify/` frames and records contain phone device
IDs and home-screen captures. They are kept in the private evidence archive.

## Windows: one platform per phone (21 Oct)

Operator decisions (21 Oct): one platform per phone (slot 18 Instagram Reel, slot 20 TikTok,
slot 17 X, slot 16 YouTube Short), each on the account signed in on that phone. X is held after
the operator's X accounts were suspended on 20 Oct at 19:17; logs show no farm X automation.

Slot-named receivers (`prepare_slots.py`, `iMouse2-16/17/18/20`, F215 locked to the slot 16
phone). `auto_connect.py` reconnected all four phones from the PC through their own boards; an
AirPlay query from each phone's address proved its Screen Mirroring card was open before the
row tap. `pointer_measure.py` (reset, move, compare frames; animated icons masked) put every
detected landing within 10 px on all four phones. A Search tap plus Home worked on each.

`tools/farm_phone_identity.py` makes every live gate compare against one window's phone; a
window config (version 2) names that phone, the kernel's exact allow-list and the signed-in
account. Per window:

```powershell
python prepare_window.py --platform reel --slot 18 --phone-ip <phone LAN IP> --account <handle>
.\Start-Window.ps1 -Window reel-slot18      # backend only; the shared kernel keeps running
python ..\..\tools\farm_start_screen.py instagram-profile windows\reel-slot18\start-screen-1 windows\reel-slot18\creation-config.json
python run_window.py --window reel-slot18 --attempt 1
.\Stop-Window.ps1 -Window reel-slot18
```

Ports: backend 9915/9925/9935/9945 and media 9917/9927/9937/9947 for slots 18/20/17/16.
A code change alters the backend source fingerprint, so a window is re-prepared (the old one
moves to `windows-archive/`).

Reel on slot 18, attempts that each stopped safely and led to a fix with tests:
1. Safari on its blank Start Page (no tab) -> `safari_blank` (Start Page, focused or not).
2. Home-screen OCR outlasting the 1.5 s frame limit -> home-screen roles reconfirm on a newer frame.
3. Downloads list OCR split a file name -> rows rebuilt from fragments, matched by the unique code.
4. Safari reopened on the Downloads sheet -> recognized; Done closes it.
5. The download opened in iOS's full-screen video player with its playback overlay (whole video
   dimmed, no Files toolbar) -> overlay recognized; two reveal taps, then the Share icon template is
   polled and Done or Share is pressed while it shows.

22 Oct, preps 24-38, each stop safe and fixed with a test in `tools/test_farm_safari_start.py`:
an earlier share sheet left open (closed by its x); the previous transfer page shown while the new
one loads (read-only wait for this file name); the Next pill over blurred photos (pill pixels only);
'First draft' joined to its icon by OCR; a reconfirmed Quick Look frame without OCR text (pixels
only); the player overlay without OCR '10' labels (white play glyph); the selection tray, the details
cover and the Preview matched by the package's six tile colours when the strict pixel match narrowly
misses (other test videos score .4 or more); small editor toolbar labels and the Preview account read
from an enlarged band; the share sheet settled 35 px lower; the details list grew ('Tag products');
OCR split 'mouse'+'htxkyd' with no dash; Instagram reloading to its feed after the profile (one
profile-tab recovery); a white video washing out the Preview title; a playing Preview reconfirmed by
its button bar. `farm_start_screen.py` now backs out of leftover Reel details, editor ('Start over',
never 'Save draft') and picker.

**Result (slot 18, 22 Oct 01:11-01:22):** run 38 saved one Reel draft; its verifier stopped on the
Preview title. `verify_window.py` reran only the verifier on the same admitted package (checks 2 and
3; check 3 passed): the unique matching draft reopened with the exact caption and account
xs.halle.xo, played the package video and stayed in Reels drafts. Nothing was shared or published.

```powershell
python verify_window.py --window reel-slot18 --attempt 1 --check 3   # Refused unless creation saved an unverified draft.
```

## TikTok (slot 20) and X (slot 17, new account), 22 Oct, preps 39-53

Neither has a saved draft yet. Every stop was safe (no wrong tap, nothing posted) and each fix has
a test in `tools/test_farm_safari_start.py`.

- Reached: TikTok saves the video to Photos, reopens TikTok on the profile, opens the gallery and
  selects the package video. X saves the video, reopens X and opens the empty composer.
- Phone differences found: slot 20's Safari runs in Private Browsing (black toolbar icons, grey
  address selection, a shorter link menu, a white download glyph in a dark bar); Siri Suggestions
  and wallpaper-dependent search controls; TikTok's launch splash and covered feed header; the new
  X account's extra header tabs, 'Try Grok Bot' menu row, first-use tips and the Paste callout
  that opens on the first tap; share sheets with a 'Send Copy' row.
- Next on resume: TikTok from the selected video (editor, sound removal, caption, Drafts, verifier);
  X from the Paste callout (caption, attach video, save draft, verifier). Then YouTube Short (slot 16).
- Start screens: `farm_start_screen.py tiktok-profile|x-timeline <folder> <config>`.

## 22 Oct afternoon: after the power-up

- Bring-up: `Start-Multiphone.ps1 -Stage slots`, then `Release-Receiver.ps1` + `auto_connect.py` per
  phone (slots 20, 17, 16), each with mDNS proof. Two reconnects outlasted their 15 s lease and
  left C214/F215 stopped; cleared with `/input/resume` at the expected generation, and
  `auto_connect.py` now renews the lease before every command.
- Start screens: `youtube-home` added (shared app-home routine with `x-timeline`); TikTok's
  profile-tab decision compares only the Profile tab (an activity bubble appears beside Inbox);
  a lone settling-pointer blob is ignored (each phone resets its pointer to a different spot).
- TikTok: the selection badge is compared two pixels inside its rim; Safari's blue
  "downloading" ring counts as the download badge.
- YouTube (slot 16): the labelled five-item tab bar is accepted (create + at 250,1011).
- Blocked on the phones: X on slot 17 ignores every pointer click since the power-up (hover still
  shows; other apps take clicks); phone 16 shows YouTube "You're offline".
- `one_tap.py`: one supervised navigation tap for backing out of leftover screens.
- Full context handoff: `CLAUDE-HANDOFF-20261022.md` in the repository root.

## 22-23 Oct night: phones back, three platforms running

- 22:53 the kernel and every window backend died together when the Claude desktop app updated
  itself (Windows logged its service reinstall at that minute); no crash was recorded. Restart:
  `Stop-Multiphone.ps1 -Stage slots`, `Start-Multiphone.ps1 -Stage slots`, then
  `Release-Receiver.ps1` + `auto_connect.py` per phone. Slots 20 and 17 needed a second
  `auto_connect.py` (the first tap on their row did not connect; the next one did).
- Leftover unsaved edits from stopped runs: the operator approved discarding them (23 Oct, "Discard
  both", then "you can discard whatever you like"). `discard_leftover.py` taps the one 'Discard'
  of an exactly recognized TikTok editor menu or X Cancel sheet; YouTube's camera close offers
  'Start over' (taken with `one_tap.py`). 'Save draft' is never chosen for a leftover.
- Stops fixed (each safe, each with a test): X's new Edit Video screen after Add (Next, never
  Save); Safari's Downloads size line missed by OCR (read again enlarged); TikTok's sound pill x
  moved left by a short sound name; YouTube's selected tile drawn under a dark veil with its
  border a pixel lower, a larger 'Save draft' label on slot 16, and a clipped title placeholder.

### 23 Oct, 01:30-02:15: first saved drafts on X and YouTube

- **YouTube (slot 16, prep 65):** Save draft pressed once; YouTube showed 'Draft saved'. Creation
  then stopped on the home check (the toast covers the + on slot 16; now `yt_home_saved`).
  `verify_window.py` gained a YouTube case for exactly this (the Save answered, the toast seen,
  nothing after). Its check 1 reopened the draft and saw it play, then Next showed a
  'Processing' overlay that was still up 25 minutes later. The phone was left on it, untouched.
- **X (slot 17, prep 66):** Save to drafts pressed once; the verifier then stopped on its own
  steps (the drafts tip over the placeholder, the Drafts list loading, the thumbnail's colour
  match, the edited card reopening paused under a play button), each fixed in turn.
- **Mistake:** backing out of the reopened X draft by hand, 'Save to drafts' was pressed while
  the reopened card was still paused on its first frame. The draft was saved again **without its
  video** (its Drafts row now has no thumbnail). Never re-save a reopened draft by hand; the
  verifier re-saves only after it has seen the video play. A text-only 'Fresh x acceptance' draft
  remains on slot 17's account; a new X run needs a different caption or that draft removed.
- **TikTok (slot 20):** reached the new-draft details screen. Slot 20 shows a different layout
  (rows 54 px higher, now accepted), and its cover thumbnail does not match yet: a different
  crop, plus the AssistiveTouch button sitting over the cover's right side. Open.

### 23 Oct, 02:40-03:10

- The operator deleted the text-only X draft and moved phone 20's AssistiveTouch button. A moved
  button still lands on some screen (at the left edge it covered TikTok's picker grid), and the
  other three phones never show it: iOS hides it while a pointer is connected unless
  'Always Show Menu' is on. Turning that off on phone 20 is a one-time setting (operator's).
- YouTube's 'Processing' stayed up; `close_app.py` closed YouTube from the app switcher (switcher
  key and swipe sent directly, as auto_connect does; the app's own card label decides the swipe).
  Reopening the Short camera then asked 'Continue your draft video?' ('Starting over will save the
  draft and start a new Short'). Phone 16's mirror then stopped delivering frames; left there.
- Fixed: TikTok's larger cover card on slot 20; a share sheet still sliding up after Share
  (read-only wait instead of a stop).
