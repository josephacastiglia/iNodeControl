# Fresh-field space loss: Full Keyboard Access experiment, 27 Sep 2026

## Result of the controlled comparison, 27 Sep 21:37–22:21 (closed after 5 of 6 trials)

**Under these conditions, Full Keyboard Access is implicated.**
- With FKA On, the first space of `Hi there` was missing in fresh notes: 3 of 3.
- With FKA Off it was kept: 2 of 2.
- Restoring On brought the loss back.
- Scope:
  - one phone (C24C), one field type (a new Notes note), one string, five trials;
  - it shows the loss depends on the FKA setting in this setup, not the mechanism inside iOS;
  - it is not a fix, and other FKA interactions (Home's Tab, Typing Mode) were not tested.

**Setup.**
- Release kernel 30652 through its API, with C24C's lease held only during each trial (script `fka_trial.py`, copied into the evidence folder). No console, no receiver restart, no code or HID-timing change, no other setting touched. C241 was never addressed.
- **Every trial ran identically:**
  1. the operator's physical Home gesture beforehand (never the software Home);
  2. reset, move to Notes (192, 250), long press (down, 0.95 s, up);
  3. 1.0 s, then tap New Note (212, 396);
  4. 3.0 s, then `/key/sendkey key="Hi there"`;
  5. 4.0 s, then a frame.
- **The operator changed FKA by hand** on C24C's settings page and handled any dialogs. Each state was captured from the settings page before the operator returned Home.

**Setting state (from frames of the FKA settings page):**

| Time | State | Frame |
|---|---|---|
| 21:39:55 | Original: FKA **On**, Auto-Hide 1s, Increase Size Off, High Contrast Off, Color Default ("To activate: Space") | `S0-original-fka-page-b.png` |
| 21:44:54 | FKA **Off**, Appearance unchanged | `S1-fka-off-page.png` |
| 21:52:24 | FKA **On** again, Appearance matches the original | `S2-fka-restored-on-page-b.png` |

**Trials.** The three measures are recorded separately:
- **Submitted** is the exact `key` sent. It was the same in every trial: `Hi there`, bytes `48 69 20 74 68 65 72 65`.
- **Kernel** is the command's result code. Code 0 means the HID writes completed, not that anything was inserted.
- **Visible** is what the note shows in the frame 4 s later.

| Trial | FKA | Kernel | Visible | Frame |
|---|---|---|---|---|
| ON1, 21:42:29 | On (original) | 0 | `Hithere`: space missing | `ON1-3-after-send.png` |
| ON2, 21:44:10 | On (original) | 0 | `Hithere`: space missing | `ON2-3-after-send.png` |
| OFF1, 21:45:23 | Off | 0 | `Hi there`: exact | `OFF1-3-after-send.png` |
| OFF2, 21:46:00 | Off | 0 | `Hi there`: exact | `OFF2-3-after-send.png` |
| ON3, 21:56:04 | On (restored) | 0 | `Hithere`: space missing | `ON3-3-after-send.png` |
| ON4 | On (restored) | not run | not run | `ON4-refused-screen.png` |

- **ON4 was not run.** At 22:12 its preflight found C24C owned by another controller (lease renewing, generation 7), so it sent nothing. The only other controller running was the installed console (30604). The lease was not taken over.
- The operator then closed the test at 5 of 6 trials.

**What this establishes, and what it does not:**
- In this setup, the first space in a freshly created note is lost with FKA On and kept with FKA Off. The loss returned when FKA was restored.
- **Established here:** the same submitted text and the same kernel reports gave different insertion depending only on the FKA setting. The kernel sends identical reports either way (offline review below).
- **Not established:**
  - *why.* "FKA's Activate key (Space) takes the first Space in a newly focused field" is consistent with this, but was not shown directly.
  - whether other fields behave the same (Settings search was not retested);
  - whether other FKA effects (Home's Tab) share the cause;
  - what product change, if any, is appropriate.
- Two trials per condition and one restored-On trial is a small sample. The result is clear-cut within it: 3/3 against 2/2.

**Side effects on C24C.**
- Five new notes: `Hithere` ×3 and `Hi there` ×2.
- One empty new note, opened by the operator while trying to type physically before the test.
- The Notes quick-action menu was opened once for locating (`LOC-*`) and dismissed by the operator.
- No other setting was changed. FKA was restored to On by the operator and verified.

**Rack after closing (22:21):**
- kernel 30652 and receivers 6264 / 6100 unchanged, both mirroring, restarts 1 / 0;
- installed console 30604 running;
- operator settings `72F51CC0…` unchanged;
- no test process running;
- this session holds no lease. The installed console holds C24C's lease; it was left alone.

Evidence: `iMouseXP-2.0-evidence-archive/20260927-fka-comparison/`, containing `run.txt`, 30 frames, `fka_trial.py` and `SHA256SUMS.txt` (32 files).

---

*(Earlier session, 15:47–16:16. Superseded by the operator-toggled comparison at the top of this file.)*

**Status: ended early.** The FKA Off comparison was **not performed** in this session. Whether Full Keyboard Access causes the lost space is **unresolved**. Fresh-field exact typing remains **failed / open**. The candidate is not promoted.

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
- Plain `SendInput` clicks failed the same way, so the automation tool is not the cause. **Corrected later:** `SendInput` from the agent's shell injects nothing at all, so this proves nothing. See `analysis/console-click-investigation-20260927/README.md`.
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

## Offline review, 27 Sep evening (no live action)

Sources:
- this session;
- `KEYBOARD-SPEC.md`;
- `analysis/text-chunking-candidate-20260925/REPORT.md`;
- the vendor key capture `analysis/hid-keys-20260914.jsonl` with `hid-key-markers.jsonl` (main checkout);
- `INDEPENDENT-KERNEL.md`;
- the 14 Sep frames `analysis/live-notes-space*.bmp`;
- the C241 FKA diagnostics (`analysis/c241-typing-*`).

### 1. What the console submits (established)

- **The space is in the submitted text.**
  - The Send text box held exactly `48 69 20 74 68 65 72 65`, read back through UI Automation.
  - The 25 Sep harness sends (`ApiClient.SendTextAsync`, no UI) lost the same space.
  - A lone ` ` sent on its own returned code 0 (26 Sep).
- `Hi there` is one chunk (8 of 12 characters), so chunking cannot split it.
- **Gap:** the logging proxy recorded each command's timing and code, not its body. The body is inferred from the box contents and the code path, not captured.

### 2. What HID reports the kernel sends (established from code; not captured on the wire for the release kernel)

- **Every space is sent the same way:** `Ascii(' ')` = (0, 44), sent as a `Stroke`:
  1. `A2 00 00…` (clear);
  2. 45 ms;
  3. `A2 00 2C…` (Space down), held 90 ms;
  4. `A2 00 00…` (release);
  5. 35 ms settle.
- The kernel keeps no per-field or per-note state, so every space in a text gets the same reports. The self-test "Space is emitted as USB usage 44 between letters" covers this.
- **Byte-identical to the vendor's Space.** The 14 Sep capture of `IMService` typing `" Ab Z!"` shows `A2 00 2C` for both spaces. Only the timing differs: the vendor holds a key about 38–46 ms, ours holds Space 90 ms.
- **The timing does not separate success from failure.**
  - The 14 Sep kernel already held Space 90 ms (`INDEPENDENT-KERNEL.md`), and C24C Notes then showed `A B`, then `A B Test 123!`, keeping the space after `A`.
  - The same reports and timing later lost the first space 21/21 (25 Sep) and 4/6 (27 Sep).
- Code 0 means the HID writes completed, not that the board delivered them or iOS inserted them.
- A stateless transport has no knowledge of which text field is focused on the phone. A loss tied to "the first space in each newly focused field", with later spaces kept, is not a pattern the PC side can produce except by coincidence. This is an inference, not a capture.

### 3. What iOS visibly inserts (observed)

- **First space lost:**
  - 21/21 fresh notes (25 Sep, 90 ms hold, sent through the console library);
  - 4/6 fresh fields at FKA On (27 Sep): lost in every field that was the first one focused after entering the app, kept in 2 Settings search fields refocused after Cancel.
- **Later spaces in the same field are kept,** including after a 3 s pause.
- **Lost wherever it falls:** position 3, 6, 7 or 11, first line or body, one lease or fresh leases, with or without a leading Enter. A preceding non-space key does not use up the effect.
- **A lone space sent as its own command** (26 Sep): the cursor did not move in 4/4 fresh fields. **Once it brought up the text-edit menu** (Select | Select All | AutoFill), which is how iOS answers an activation or tap on an already-active text field.
- **The fresh-note UI** (Done, undo, formatting bar) looks the same on 14 Sep, when the space was kept, and 27 Sep, when it was lost. The difference is not visible on screen.
- **FKA state over time:**
  - C24C's FKA was **On** on 27 Sep (`state-00`), showing "To activate: Space".
  - Its state on 14 Sep is not recorded.
  - The 21–22 Sep notes that C24C showed "no FKA ring" are weak evidence of Off, because Auto-Hide is 1 s.
  - C241, with FKA On, needed Typing Mode for letters to insert into empty Spotlight, and its Space opened the AssistiveTouch menu when the ring was there.

### Remaining explanations (none established)

- **R1: FKA's "Activate" (Space) takes the first Space** on the newly focused text element. After that, the field is in a state where Space types.
  - Consistent with: FKA On; the listed Activate key; the one edit-menu response; refocused fields keeping the space.
  - Not shown by any test.
- **R2: a non-FKA iOS text-input feature consumes the first Space of a text session.** For example, inline predictions (turning them off showed no change, but that did not rule them out), autocorrect, or another keyboard feature.
- **R3: phone-side keyboard-accessory state.** For example, a state that the 27 Sep Lightning replug may have reset. The current behaviour after the replug is unknown.

The existing trials cannot separate these: all failing trials had FKA On, and the one success has an unknown FKA state.

## Proposed test: FKA comparison with the operator on the toggle (not yet run; for approval)

**Smallest distinguishing test.**
- One same-session control at FKA On, then two fresh notes at FKA Off, then restore.
- Every trial sends ` Hi there` (leading space, then an inner space). That tells whether a first space is consumed even with no preceding word, and which space goes.
- Everything else matches the 27 Sep N1–N3 trials:
  - focus: Home, long-press Notes, New Note;
  - timing: 3 s wait, send, 4 s wait, frame.
- Driven through the release kernel API with C24C's lease. No console, no receiver restart, no HID timing or code change, no other setting touched.
- **The operator physically operates the FKA switch and its confirmation dialog.** The pointer is never used on the toggle or the alert, because it failed there on 27 Sep.

Procedure (about 10 minutes):
1. **Preflight, read-only:**
   - kernel and receiver PIDs;
   - C24C live and unowned;
   - C241 not addressed at any point;
   - operator settings hash;
   - one frame of C24C.
2. **Control (FKA On, as it is now):**
   - acquire the lease;
   - Home, long-press Notes, then tap New Note (frame checks between steps);
   - wait 3 s, send ` Hi there`, wait 4 s, take a frame;
   - release the lease.
3. **Operator:** on C24C, Settings → Accessibility → Keyboards → Full Keyboard Access → switch **Off**, and confirm the dialog by hand. Then return to the Home Screen (swipe up) and tell me. I confirm Off from a frame only.
4. **FKA Off:** repeat step 2 twice, one fresh note each.
5. **Operator:** switch FKA back **On** by hand, confirm any dialog, return Home. I verify On and the original Appearance rows from a read-only frame.
6. **Finish:**
   - lease released, C24C unowned;
   - receivers unchanged;
   - settings hash unchanged;
   - frames and text readings preserved.

How the results read:

| Control (On) | Off trials | Reading |
|---|---|---|
| a space lost | both exact ` Hi there` (or `Hi there` with only the leading space trimmed by Notes) | FKA implicated (R1). Not yet a fix |
| a space lost | same loss as On | FKA not responsible; R2 or R3 |
| nothing lost | — | The current phone state differs from 25–27 Sep, possibly after the replug; R3 gains weight. Stop and report; the FKA trials would not discriminate |

**Side effects:** three new notes containing ` Hi there`. Pressing Home types the vendor Tab into the open note, as recorded earlier; each note's text is read before Home.

## Evidence

The archive is `iMouseXP-2.0-evidence-archive/20260927-fka-space-loss-b0708e3/`, with `SHA256SUMS.txt` listing 217 files, verified against their sources. It contains:
- `frames/`: every phone frame, one folder per step, each with `frames.tsv`;
- `trials.tsv`;
- `toggle-events.txt`;
- `proxy-log.jsonl`, with every command, its kernel answer code and duration;
- `probes.txt`, the crops, the candidate's `settings.json`, and `session-scripts/`.
