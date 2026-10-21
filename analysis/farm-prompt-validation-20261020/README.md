# Permission-prompt validation window: prepared offline

Prepared 20 Oct 2026 on branch `local/prompt-validation-20261020` (worktree
`C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-prompts`, cut from `71b3b35`).
**Nothing in this record has been run against a phone.** No kernel, receiver,
backend or service was started, and no phone input, desktop automation,
publishing, messaging, FKA change or installed-release change happened.

Goal (operator, 20 Oct): permission prompts handled without people constantly
stepping in. The plan comes from sections 3–4 of
[the permission-prompt record](../farm-permission-prompts-20261020/README.md).
This folder holds everything that window needs:

| What | Where |
|---|---|
| Window steps (observe, trials, probe, confirm, promote) | `tools/farm_prompt_validation.py` |
| Evidence wiring: a method is validated only from window evidence | `tools/farm_permission_prompts.py` (`WINDOW_EVIDENCE`, `window_problems`, `evidence`, `RUN_METHODS`, `SAFE_ANSWER`, `CANCEL_ANSWERS`) |
| Offline stand-in for tests and the dry run | `tools/farm_prompt_fixture.py` |
| Tests | `tools/test_farm_prompt_validation.py`, `tools/test_farm_permission_prompts.py` |
| Window scripts | `live/Start-PromptWindow.ps1`, `live/Run-PromptStep.ps1`, `live/Stop-PromptWindow.ps1` |
| Preparation and its read-only recheck | `prepare_prompt_window.py`, `live/verify_preparation.py`, `live/preparation.json`, `live/protected-before.json` |
| Offline dry run of every step | `dry_run.py`, `dry-run/` (synthetic results, never evidence) |
| Window results (written during the window) | `window/<label>.json`; private records and frames in `output/candidate-runs/prompt-validation-20261020/trials/` |

## 1. Review of the move-only absolute probe

The probe is `--absolute-probe-pid C24C`, commit `373dd58` (14 Oct). It has never
been sent to a phone.

- **The private kernel contains it.** The private kernel
  `output/codex-farm-live-kernel-20261018` (DLL SHA-256 `c72fa4e0…a873`) was built
  from `9fa7a85`, which contains `373dd58`. No kernel source changed between
  `9fa7a85` and `71b3b35`.
  - A static byte check of the DLL finds the probe's strings. The preparation
    and the recheck repeat that check.
  - The kernel was not run for this review. The 14 and 18 Oct records report
    290 kernel self-tests passing on this source, including the probe's tests.
- **Startup guard** (`KernelStartup.cs`). The probe needs normal service mode,
  exactly one `--input-pid` board equal to the probe board, and that board in
  `--hid-replies-pid`. The router constructor repeats the check and needs that
  board's calibration (at most 65535 pixels per axis).
- **Router** (`InputRouter.cs`).
  - On the probe board only `/mouse/move` and `/mouse/reset` pass validation.
    Click, down, up, swipe and keys are refused before any transport opens.
    A batch cannot reach a second board.
  - Each move sends one zero-button `A0` report:
    `A0 00 xLo xHi yLo yHi 00 00`, with x = ⌊32767·x/500⌋ and y = ⌊32767·y/1080⌋.
    There is no retry and no `A1` fallback.
  - On failure or Stop, only the key release (`A2` zeros) is sent before the
    transport closes. The relative `A1` zero report is skipped, so probe mode
    never sends a relative report.
  - A lease is still required. The kernel's tests cover the refusals, the report
    bytes, the lease and no replay after a failed or cancelled write.
- **Status.** `/kernel/status` reports `input_configuration.absolute_probe_board`,
  `hid_reply_boards`, `control_compatibility.absolute_probe` ("experimental moves
  only…") and the `hid_replies` counters. `Start-PromptWindow.ps1` and the tool
  check the first three; the probe records the counters around every move.

Findings that shaped the procedure:

1. **The probe kernel cannot send any relative pointer, click or key.** The
   trials therefore need the normal kernel. The window has two parts and two
   mirroring connections: part A is the normal kernel, part B the probe kernel.
2. **`/mouse/reset` in probe mode is an absolute move to (0, 0).** It is not the
   relative corner reset. The probe step never sends it.
3. **The frame and the screen share one aspect.** Frames are 500×1080 and C24C
   is an iPhone XR (414×896 points): both are 0.463. If iOS maps the full A0
   range to the display, a point in the frame is the same point on the screen.
   - Not known: whether the board forwards `A0` to the iPhone as an absolute
     pointer, whether iOS shows the pointer there, and with what scale or offset.
4. **A move is not expected to press.** Its button byte is 0, but how iOS reads
   an absolute report is unproven. So the probe uses blank points on a blank
   page. It stops at the first change other than the pointer.
5. **There is no press.** A guarded absolute press and release is a later
   build, and only if this probe puts the pointer where it was sent.
6. **No defect** was found that blocks the window.

## 2. The guarded answer path and how a method becomes validated

`tools/farm_prompt_validation.py` runs one step per call.

- It uses only the private kernel on `127.0.0.1:9916` and only C24C.
- It checks the kernel's SHA-256, its PID and start time as recorded by the
  Start script, the C24C-only mapping and which kernel mode is running.
- `observe` is read-only. Trials and the probe need C24C free, take their own
  lease and always release it.
- Its transports send only:
  - the lease commands;
  - reset, move, click, down and up with the left button;
  - **Tab, Escape and a single Space**, never Return, Home or text.
- The probe transport sends only lease commands and moves.

Every trial runs in this order:

1. A read-only pre-check with no lease and no input. It needs a recognized prompt
   family that has a safe answer. Otherwise **nothing is sent**.
2. The lease. The pointer is reset to the top-left corner, off the alert, and
   rests 1.2 s.
   - A label under a resting pointer is not read (17 Oct), so the full check
     waits until the pointer is parked.
3. The runs' fresh-frame move to (480, 300), then an owned decision frame with
   OCR. It must show the same prompt, with the safe answer and the other
   answers read and at least 40 pixels apart. Otherwise the step stops with
   only the pointer moves sent.
4. **Exactly one method, aimed only at the safe answer**: the answer that grants
   nothing the app does not already have.
   - For most prompts it is the declining button: "Don't Allow", "Don't Allow Paste" or
     "Ask App Not to Track".
   - On iOS's reminder about full photo-library access the app already has, it is
     **Allow Full Access**, which keeps the current setting. *Limit Access* would
     change it and open the photo selection.
   - An answer that grants new access is never a target.
5. The runs' parking move to (480, 300), an outcome frame, and release.

| Method | What is sent | Same as the runs |
|---|---|---|
| `pointer_tap` (class check) | move to the button, 0.6 s, one click | the settled tap in `answer_prompt` |
| `keyboard_escape` (class check) | Escape; only where the alert's cancel action is the safe answer | `answer_prompt`'s Escape |
| `long_press` | move, 0.6 s, button down, 1.1 s, button up | the hold step in `answer_prompt` |
| `keyboard_focus` | Tab, at most 4 times, then one Space only on a verified focus | not in the runs yet (see below) |

A test reads the runs' `answer_prompt` and `CreationWorkflow.step` source and
holds these sequences and timings equal. A method validated in the window is
then the same input the runs send.

Read-only frames are kept inside those timings as evidence: one while the
pointer rests on the answer (aim), one during a long press (held), and one just
after the click, release, Escape or Space (immediate). No extra input is sent.

### Keyboard focus

Recorded facts about C24C:

- Full Keyboard Access is on.
- Its Commands pages (11 Oct) list **Tab = Move forward** and
  **Space = Activate**. None of them assigns Escape, which fits Escape being
  ignored on 17 Oct.
- Those pages also list Tab chords (Tab L = Lock Screen, Tab X, Tab R) and
  modifier chords (SOS = ⌃⌥⇧⌘S). The kernel releases every key before the next
  one, and the validation transport can send only single Tab, Escape and Space
  strokes. No chord can be formed.
- Its settings show **Auto-Hide 1 s**: the focus highlight hides one second
  after the last key, while the focus itself stays. The farm leaves FKA
  unchanged.

The trial works like this:

1. The unfocused frame is taken after the 1.2 s rest, so no old highlight is
   left in it.
2. After each Tab, the step waits for a new frame and takes it within about
   0.3 s, without OCR.
3. It compares that frame with the unfocused frame, per answer:
   - one answer changed and nothing else: that answer is focused;
   - only the prompt's title band changed (its title row and the next 90
     pixels): another control is focused (iOS 18's location alert has a
     *Precise: On* control), and the next Tab follows;
   - two answers changed, or text and answers together changed: the step stops.
4. **Space is sent only when the highlight is on the safe answer alone and
   the prompt text is unchanged.** It must follow within 900 ms of that frame,
   with nothing sent in between. A late frame sends nothing.
5. `--no-activate` finds the focus and stops before Space.

The detector was checked on real 17 Oct frames. Consecutive frames of the
unchanged alert read as no focus, and the dismissed alert reads as a changed
alert.

A pointer hovering an answer highlights it **exactly like a focus**: the
detector reads the hovered *Don't Allow* as focused. This is why the trial parks
the pointer off the alert before the unfocused frame and sends nothing but Tab
until Space.

**Return is never sent.** On a hardware keyboard, Return triggers an alert's
preferred action, often *Allow*, whatever has focus. The coordinating brief
allowed Space or Return. Return is left out deliberately, so that only the
safe answer can ever be the target.

**The runs cannot send Tab or Space today.**

- `CreationKernel` (`farm_draft_transport.py`) permits only the keys Home, Enter
  and Escape, and text without spaces (characters 33–126).
- `CreationWorkflow.step` refuses spaces.
- `answer_prompt` raises for `keyboard_focus`.

Those are adapter and run files, and another session may be changing them.
Using keyboard focus in runs is therefore a follow-up. Until then
`RUN_METHODS` (`pointer_tap`, `keyboard_escape`, `long_press`) keeps runs from
choosing a validated method that they cannot send. The run then stops with its
one-time request, and the reason names the waiting method.

### From a window result to a validated method

1. **A trial writes two records.**
   - The summary `window/<label>.json` goes into Git. It holds no OCR text and no
     frames, only their SHA-256.
   - The private record and frames go under `output/…/trials/<label>/`.
2. **The operator confirms what the phone shows.** Run
   `Run-PromptStep.ps1 -Step confirm -Label … -Answer safe|other|unclear -Observed "…"`.
   `safe` means the phone shows the safe answer took effect.
3. **`promote` prints the `WINDOW_EVIDENCE` entry**, or the reasons there is none.
   An entry needs all of these:
   - a phone trial that completed with its lease released;
   - every command answered;
   - the safe answer as target;
   - the outcome `dismissed` and a **safe** confirmation for `validated`,
     or the outcome `ignored` for `ignored`.
4. **A reviewed commit adds the entry** to `farm_permission_prompts.WINDOW_EVIDENCE`
   together with its summary. A test checks every entry against its summary's
   SHA-256.

Rules that keep this safe:

- **Nothing is validated by default.** `plan()` counts an entry only when
  `window_problems()` finds it complete.
- **Evidence is per family.** A method validated on a paste prompt answers paste
  prompts only.
- **Contradictions are not used.** If results for one family and method
  disagree, including the 17 Oct ones, the pair becomes `conflicting` and no run
  uses it.
- **Escape only declines.** Escape reaches only an alert's cancel action, so it
  is used only when that action is the safe answer (`CANCEL_ANSWERS`). It is
  never used for an allowing answer such as Photos' *Allow Full Access*, and
  never on the full-access reminder, whose cancel action may be *Limit Access*.
- **Evidence is per phone.** Window entries are C24C's. On 20 Oct the same
  move-then-click answered a prompt on one rack phone and was ignored on another
  (section 3a), so another phone needs its own evidence.

`farm_permission_prompts.py` is one of the 43 fingerprinted backend files.
**Once this branch is merged, the prepared Reel, TikTok and X windows must be
re-prepared.**

## 3. Prompts that can be raised on demand

None is confirmed yet. The 17 Oct YouTube prompt never returns once answered.
Every candidate is answered only with its safe answer.

### C1. Paste from Other Apps set to Ask

This is the candidate in the record. The family is `paste`; the safe answer is
*Don't Allow Paste*.

- **How to raise it:**
  1. Copy a short neutral text in Notes.
  2. In the app, use an action that reads the clipboard itself, such as the
     app's own Paste button. The system edit-menu Paste never asks.
- **Confirm on the phone, before any method trial:**
  - Record the value under Settings › *App* › Paste from Other Apps. iOS
    defaults to Ask.
  - Find which app and action shows
    *"App" would like to paste from "Notes"* with both buttons.
  - Check that the alert returns on the next try.
  - Check that `observe` recognizes it.
  - Run the class check: the click is ignored and Escape is ignored, as on 17 Oct.
- **Proof of the safe answer:** the field stays empty.
- **Restore:** the recorded setting.
- **Cost:** no setting change if it is already Ask; repeatable.

### C2. Maps location set to Ask Next Time

The family is `location`; the safe answer is *Don't Allow*.

- **How to raise it:**
  1. Set Settings › Privacy & Security › Location Services › Maps to
     *Ask Next Time Or When I Share*.
  2. In Maps, tap the current-location button. The alert shows *Allow Once*,
     *Allow While Using App*, *Don't Allow* and a *Precise: On* control.
- **Confirm on the phone, before any method trial:**
  - Record the original value.
  - The operator approves this setting change.
  - It is a privacy alert of the same kind as the local-network one.
- **Proof of the safe answer:** Maps' location setting reads *Never* and no
  blue dot shows.
- **Restore:** the recorded value.
- **Cost:** one setting change per try, because each *Don't Allow* sets *Never*.

### C3. Real first-run prompts

These are the target families themselves: local network, notifications,
photos.

- **How to raise them:** open an installed app that has never asked. Settings ›
  Privacy & Security › Local Network (and the others) list which apps have
  already asked.
- **Proof of the safe answer:** the app's entry in that list.
- **Cost:** one try only; no setting change. Use it only after C1 or C2 has
  shown a working method.

### Ruled out

- **A Safari website prompt.** The page is HTTP, and Safari draws that prompt
  itself.
- **Reset Location & Privacy, or deleting and reinstalling an app.** Too
  disruptive for a farm phone.
- **AirDrop Accept/Decline.** A sharing alert, not a permission prompt; the farm
  does not recognize it.
- **The clipboard dialog of Shortcuts.** Shortcuts draws it itself.

### If the class check answers

If a candidate answers the class check (the click or Escape dismisses it), it is
a different input class from the 17 Oct alert.

- Its safe-answer result is still evidence for its own family.
- It cannot stand in for the others.
- Move on to the next candidate.

## 3a. Live findings of 20 Oct (coordinator, other rack phones)

These are the coordinator's observations, not this session's evidence, and not
C24C. They change the plan as follows.

- **A new prompt: the full-access reminder.** iOS shows
  *"App" has been able to access your entire photo library … continue to allow
  full access?* with *Limit Access* and *Allow Full Access*.
  - It is now the family `photos_reminder`. Its safe answer and policy answer
    are both *Allow Full Access*, which keeps the current setting.
  - It is answered even outside a media-picker step, and even for another app,
    because keeping the setting changes nothing.
  - An alert with this wording that also offers *Don't Allow* is not this
    reminder; it stops for review.
  - A run without a validated method stops with:
    *Choose "Allow Full Access" … That keeps the current setting; iOS repeats
    this reminder from time to time.*
  - The reminder recurs on its own schedule, so it cannot be raised on demand.
    If it shows during the window, `observe` and a `pointer_tap` trial on it are
    worth one try each.
- **A click can show on the alert and still do nothing.** On rack slot 16
  (board F215), pointer clicks on that alert's button registered visually
  (hover highlight, pressed dot), but the alert did not act. On another phone
  the same move-then-click worked.
  - In a trial this is the outcome `ignored`: one try, never repeated in that
    step. The record keeps the aim and immediate frames, the frame after, and
    the command journal.
  - **The runs still allow a second answer.** `ReelCreationWorkflow.observe`
    answers at most `PROMPT_LIMIT` (2) prompts per observation, so a prompt that
    is still showing after a click gets one more click before the run stops.
  - Making it stop at once with that evidence is a two-line change in
    `farm_reel_creation.py`, an adapter file this branch was asked not to touch.
    It is left as a follow-up.

## 4. Window plan

### Before the window

- **Agree a time.** The operator is at C24C with mirroring available.
- **Stop what conflicts.** The Reel, TikTok and X windows and the installed rack
  must not be running. The Start script refuses otherwise and never stops
  anything.
- **Choose the candidate and approve settings.** The operator chooses C1 or C2
  and approves any setting change; C2 needs one.
- **Run the offline check,** from `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-prompts`:

  ```powershell
  .\analysis\farm-prompt-validation-20261020\live\Start-PromptWindow.ps1 -Part A -CheckOnly
  ```

  It runs the refusals and the read-only recheck, and starts nothing.

All commands run from the worktree root. `$s` stands for
`.\analysis\farm-prompt-validation-20261020\live`.

### Part A: normal private kernel

| Step | Who | Action | Expected | If not |
|---|---|---|---|---|
| A0 | session | `& "$s\Start-PromptWindow.ps1" -Part A` | kernel ready, receiver started | stop |
| A1 | operator | Connect C24C mirroring to **iMouse2-C24C** | live frames | wait up to 10 min, then the operator decides; rediscovery once took 31 min |
| A2 | operator | Raise the candidate prompt and leave it unanswered. Don't touch the phone again until asked. | the prompt shows | — |
| A3 | session | `& "$s\Run-PromptStep.ps1" -Step observe -Part A -Label a1-observe` | prints the family and the safe answer. If both are empty, `window/a1-observe.json` shows `detected` and `promptReason`: a pointer resting on the answer hides its label, and trials park the pointer first | if no family is detected: no trials on this prompt; the operator chooses the safe answer by hand |
| A4 | session | `… -Step trial -Part A -Method pointer_tap -Label a2-class-tap` | `ignored` | if `dismissed`: the operator checks the phone; `confirm`; this prompt is another class; go to A10 |
| A5 | session | `… -Method keyboard_escape -Label a3-class-escape` | `ignored` | as A4 |
| A6 | session | `… -Method long_press -Label a4-long-press` | `ignored` or `dismissed` | if `dismissed`: `confirm`, then the operator raises the prompt again (C2: set Ask Next Time first) |
| A7 | session and operator | `… -Method keyboard_focus -NoActivate -Label a5-focus-only`. The operator watches where the highlight goes after each Tab. | `focusPath` matches what the operator saw | if they disagree, or the result is `ambiguous`: skip A8 |
| A8 | session | `… -Method keyboard_focus -Label a6-keyboard-focus` | `dismissed` (then `confirm`) or `ignored` | — |
| A9 | operator | If the prompt still shows, choose the safe answer by hand | — | — |
| A10 | both | Another candidate, if time allows. Use new labels `a11-…`. | — | — |
| A11 | operator, then session | Restore every changed setting, then `& "$s\Stop-PromptWindow.ps1" -Part A` | restored; 25 protected files unchanged | stop and preserve logs |

A confirmation looks like this. Use no double quotes inside `-Observed`.

```powershell
& "$s\Run-PromptStep.ps1" -Step confirm -Label a4-long-press -Answer safe -Observed 'Settings shows Maps location Never'
```

### Part B: move-only probe kernel

Run part B only after part A is restored (or skipped), and only if the operator
agrees to reconnect mirroring.

| Step | Who | Action | Expected |
|---|---|---|---|
| B0 | session | `& "$s\Start-PromptWindow.ps1" -Part B` | kernel reports `absolute_probe_board: C24C` |
| B1 | operator | Reconnect mirroring. Open Safari at `about:blank` in light appearance. Leave the pointer alone. | a blank white page |
| B2 | session | `& "$s\Run-PromptStep.ps1" -Step probe -Part B -Label b1-probe` | `positioned` at all five points: (250,540), (80,160), (420,160), (420,860), (80,860) |
| B3 | operator | Say what they saw: did the pointer jump, did anything else change? | noted in the window log below |
| B4 | session | `& "$s\Stop-PromptWindow.ps1" -Part B` | restored |

The probe stops itself at the first point where the pointer is not seen. Record
the result; do not run it again with other points.

### After the window

1. **Promote each result.** Run `Run-PromptStep.ps1 -Step promote -Label <label>`
   for every trial with a result. Add the printed entries to `WINDOW_EVIDENCE`
   in one reviewed commit with the summaries.
2. **Archive the private evidence.** Move the trials and frames to
   `iMouseXP-2.0-evidence-archive`.
3. **Update the records:** the permission-prompt record, section 4, and
   `MARKETING-FARM-STATUS.md`.
4. **Follow up on what was validated.**
   - A validated `long_press`: runs use it as soon as its entry lands.
   - A validated `keyboard_focus`: add it to the run answer path (adapter
     files) and to `RUN_METHODS`.
   - A `positioned` probe: build the guarded absolute press for a later window.

## 5. Stop conditions

Stop input at once, stop the running part gracefully, and keep every record
when any of these happens:

- **A guard refuses.** Any refusal from Start, Run or Stop; any identity or
  hash mismatch; the kernel exits; the receiver restarts or its session changes.
- **C24C is not free.** Never take over another owner's lease.
- **An outcome is uncertain.** A command has a lost reply. Never repeat that
  method.
- **The answer was not the safe one.** A trial dismissed the prompt, but the
  phone shows anything other than the safe answer's result. The operator restores
  the setting.
- **The screen changed in another way:** another app, a different prompt, typed
  text, or a page change during the probe.
- **The prompt is not readable.** `observe` detects no family, or a trial's
  frame after parking the pointer cannot read the safe answer's label (the trial
  then stops by itself).
- **Keyboard focus is unclear.** The tool and the operator disagree on where the
  highlight is, or a step reports `ambiguous`, `alert_changed` or
  `focused_text_changed`.
- **The probe moved anything but the pointer,** or the pointer was not at its
  point. Never follow with clicks, raw reports or other points.
- **Mirroring is not live** within the agreed wait.
- **The agreed time ends.**
- **The operator says stop.** Create `STOP` in the running step's folder under
  `output/candidate-runs/prompt-validation-20261020/trials/<label>/`; each step
  lasts under 2 minutes.

## 6. Offline validation

| Check | Result |
|---|---|
| `test_farm_prompt_validation.py` | 33 tests: transports, trials, keyboard focus, the full-access reminder, faults, probe, promotion, equivalence with the runs, real 17 Oct frames, script parsing |
| `test_farm_permission_prompts.py` | 13 tests, including the window-evidence rules and the reminder |
| Complete suite `python -m unittest discover -s . -p "test_farm*.py"` | see `python-full.txt` |
| `dry_run.py` | every command-line step against the stand-in; `dry-run/dry-run.json` |
| `Start-PromptWindow.ps1 -Part A -CheckOnly` and `-Part B -CheckOnly` | Passed for both parts on 20 Oct (04:21 and 04:23 UTC) against earlier preparations. For the final preparation (21 Oct, 03:56 UTC) both refused, because the coordinator's multi-phone rack was running (a kernel on 9916 and four receivers): `live/check-only-*.json`. That refusal is the guard working; nothing was started or stopped. |
| `live/verify_preparation.py --part A` and `--part B` | Both ready at 03:56 UTC on 21 Oct: sources, kernel, receiver, mapping and the 25 protected files unchanged (`live/preparation-recheck-*.json`) |

Live windows and then the coordinator's rack were running, so the dry run and the test runs ran at Windows Idle priority and never took CPU from them.

The retained-frame suites need the Git-ignored 17 Oct frames inside the checkout.
For this run they were copied, unchanged and ignored by Git, from the
combined-candidate checkout into this worktree. Without them those suites skip.

## 7. Limits

- **The fixture tests check the protocol and the guards only.** The stand-in
  answers whichever methods it is told to; it says nothing about iOS.
- **The real FKA highlight on an alert has not been seen.** The detector was
  tested on drawn highlights and on real unfocused frames. A7, with the operator
  watching, is its first real check.
- **The 1 s Auto-Hide** comes from C24C's 11 Oct settings page.
- **The Paste trigger (C1) is unknown** until it is found on the phone.
- **Validation is per family.** A method needs evidence on each family before
  runs use it there.
- **The preparation is bound to this worktree's paths.** Prepare again
  (`prepare_prompt_window.py`) before running from another checkout.

## Window log

Fill in during the window: time, step label, what the operator saw, and any
deviation.
