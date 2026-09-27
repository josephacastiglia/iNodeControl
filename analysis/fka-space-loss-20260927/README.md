# Fresh-field space loss: Full Keyboard Access experiment, 27 Sep 2026

**Status: ended early.** The FKA Off comparison was **not performed**. Whether Full Keyboard Access causes the lost space is **unresolved**. Fresh-field exact typing remains **failed / open**. The candidate is not promoted.

## Build and setup

- **Candidate** `%TEMP%\claude\imouse-candidate-5\`, built from `b0708e3`. The report was started at `cafa52d`, whose `src/` and `tools/` are identical to `b0708e3`.
  - Hashes: `iMouse2.dll` `E5A51FC6…3AC3`, `iMouse2.exe` `2A0D5CB9…5253`. Both match the values recorded at build time.
  - The DLL's embedded version is `2.0.0+b0708e3db0940a47b48fd2365a2fd790b723358c`.
  - A rebuild at `cafa52d` differs only because the SDK stamps the current commit into the assembly.
- **Launch.** Started with `Start-iMouse2Candidate.ps1 -ViaProxy`, identified by PID (35716), never by app name.
  - Data folder `imouse-candidate-5 data\fka`, with `{"address":"http://localhost:9923","theme":"light","trackPointer":false}`.
  - Connecting sent no commands and took no lease.
- **Rack.**
  - C24C was verified as XR C24C, board C24C, uid C24CBFBD, iOS 18.7.10, receiver 36456. It was unowned at the start (generation 7).
  - The installed console (PID 12328, release path verified) was closed normally at 15:47:49.
  - C241 received no input and stayed at generation 1.
  - The kernel (28776) and receivers (36456, 13616) ran throughout.
- **Send text.** The box held exactly `Hi there` (bytes `48 69 20 74 68 65 72 65`, set through UI Automation and read back). Each trial clicked the real Send text button once.
  - Send text types the box contents as they are, with no dummy or compensating keys.
  - Every trial's `/key/sendkey` is in the proxy log.

## Original setting

Full Keyboard Access was **On** (frame `state-00-original-fka-page`, 15:52:23). The page lists "To activate: Space". Other rows, recorded and not changed:
- Keyboards & Typing: Hover Typing Off, Key Repeat On, Sticky Keys Off, Slow Keys Off, Show Lowercase Keys On.
- FKA Appearance: Auto-Hide 1s, Increase Size Off, High Contrast Off, Color Default.

## Trials at the original setting (FKA On)

Each trial used its own freshly focused, empty field, with a 3 s wait before sending and a 4 s wait before the post frame. Every send completed (code 0).

| Trial | Field and how it was focused | Submitted | Observed | `/key/sendkey` done | ms |
|---|---|---|---|---|---|
| ON-N1 | New Notes note: Home, long-press Notes, New Note | `Hi there` | `Hithere` | 15:59:00.285 | 1189 |
| ON-N2 | Same | `Hi there` | `Hithere` | 15:59:51.381 | 1192 |
| ON-N3 | Same | `Hi there` | `Hithere` | 16:00:42.318 | 1188 |
| ON-S1 | Settings search: first focus after opening Settings | `Hi there` | `Hithere` | 16:03:41.998 | 1191 |
| ON-S2 | Settings search: refocused after Cancel | `Hi there` | `Hi there` | 16:04:17.672 | 1190 |
| ON-S3 | Settings search: refocused after Cancel | `Hi there` | `Hi there` | 16:10:13.522 | 1191 |

- ON-S3 was attempted twice before (16:04:50 and 16:08:25). Each time the console's Controls click did nothing, so no text was sent (finding 1). Only the third attempt is a trial.
- Pre and post frames for every trial are listed in `trials.tsv` in the archive.

**What this shows.**
- At the original setting the loss is **not constant**: it happened in 4 of 6 fresh fields.
- It happened every time a field was the first one focused after navigating into the app. It did not happen in the two Settings search fields refocused after Cancel.
- That difference is an observation from 6 trials. It is not established.
- None of this tests FKA, because the Off condition was never reached.

## Why the comparison stopped

| Time | Event |
|---|---|
| 16:11:40 | FKA page, switch On (`state-01`) |
| 16:11:51 | Tap on the switch (code 0). The switch was drawn Off under an alert: "Important: Are you sure you want to turn off Full Keyboard Access?" (Cancel, Yes) |
| 16:12:05, 16:12:44 | Two taps on Yes (code 0, pointer visibly on Yes). The alert stayed |
| 16:13:02 | Tap on Cancel (code 0). The alert stayed. Testing stopped and the user was told |
| after 16:13 | The user tapped Cancel on the phone itself |
| 16:16:12 | Read-only frame: **FKA On**, alert gone, Appearance rows as recorded (`state-07-after-physical-cancel`) |

- The alert accepted none of the pointer taps.
- No Escape, Space or other keyboard input was sent to it, and no workaround was tried.
- FKA was never actually turned off.

## Restoration

- The candidate closed normally at 16:16:26. `/input/release` code 0 at 16:16:26.272, after which C24C was unowned (generation 8).
- No phone input was sent after 16:13:02 apart from that release.
- The proxy was stopped. The installed console was relaunched from `release\iMouse2-two-phone-candidate` (PID 38884) and not used; it took no lease.
- The kernel and receivers are unchanged, and C241 is unowned at generation 1.
- Operator settings hash `72F51CC0…` is unchanged. The timestamp is the installed console's own save when it started.

## Side effects on C24C

- **Existing test note** "Revisedbuild 27 Sep…": the first Home press (15:48:17) typed a Tab after "Stop" while that note was open for editing. It was left as is (finding 3).
- **New notes:** three new notes titled "Hithere" (ON-N1 to N3). The Notes list had 35 notes before.
- **Older "Hithere" notes:** two were opened by taps that fell short of their target (15:54:36 and 15:55:44). One was put into edit mode; nothing was typed into either.
- **Freeform** was opened by a tap that fell short of the Settings dock icon (16:01:10). Its welcome sheet was left undismissed.
- **VPN settings page** was opened twice by short taps. It was viewed only.
- **Settings search Recents** may include "Hi there" / "Hithere".
- **FKA** was restored to On by the user's physical Cancel. The phone was left on the FKA settings page.

## Findings for later investigation

These were recorded here and not fixed.

**1. Ordinary console mouse clicks intermittently fail.**
- Clicks on Controls, Activity and Reset did nothing from about 16:04:50 until 16:07:24. Controls failed again at 16:08:25, while a click on Settings worked straight after. The three failed Resume clicks on 27 Sep (`b994de9`) are probably the same thing.
- Hit testing: the click probe put every point in the candidate's own window (PID 35716). That window was foreground and responding.
- Mouse capture: `GetGUIThreadInfo` showed no window holding capture and no menu or move mode.
- Plain `SendInput` clicks failed the same way, so the automation tool is not the cause.
- The clicked button showed the keyboard focus ring but did not fire.
- Recovery: clicks worked again after a UI Automation Invoke of Activity followed by a click on the drawer's Close link.
- Scripts are in `session-scripts\` in the archive: `guithread.ps1`, `win32click.ps1`, `drawer.ps1`, plus `tools/click-probe`.

**2. Phone taps fail to reach lower-screen targets.**
- After the first tap of the session, taps aimed below about phone y 783 stopped at y ≈ 783. Examples: Accessibility at y 922 twice, Notes compose at y 1012 three times, Settings dock icon at y 1002.
- They stopped there whether or not the console's Reset came first.
- The console maps these points correctly: hovering with real cursor moves gave image y 1009 at frame y 462 (`hover-map.ps1`). So the cut-off is past the console: in the kernel's HID movement or on the phone.
- The very first tap of the session (the dock at y ≈ 1002, 15:48:26) did land.
- Calibration in use: `analysis/two-phone-config/pointer-calibration.json`, C24C origin 14, 5.12 / 5.09 px per unit.

**3. Home can insert a Tab into an active text field.**
- The console's Home sends Tab (usage 43), then Left GUI+H (`InputRouter`, `fn=="Home"`).
- With a Notes note open for editing, the Tab went into the note.
- Any text field focused when Home is pressed can receive that Tab.

## Evidence

The archive is `iMouseXP-2.0-evidence-archive/20260927-fka-space-loss-b0708e3/`, with `SHA256SUMS.txt` listing 217 files, verified against their sources. It contains:
- `frames/`: every phone frame, one folder per step, each with `frames.tsv`;
- `trials.tsv`;
- `toggle-events.txt`;
- `proxy-log.jsonl`, with every command, its kernel answer code and duration;
- `probes.txt`, the crops, the candidate's `settings.json`, and `session-scripts/`.
