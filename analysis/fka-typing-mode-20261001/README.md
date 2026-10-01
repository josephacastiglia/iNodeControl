# First space lost with FKA On: can the supported input path enter Typing Mode? (plan, not run)

Offline, 1 Oct 2026. No phone input, desktop control or setting change was used to prepare this. The live comparison below waits for a coordinated window with the operator.

## Question

With Full Keyboard Access On, the first Space typed into a fresh text field is lost. The leading explanation is R1 in [`../fka-space-loss-20260927/README.md`](../fka-space-loss-20260927/README.md): FKA treats Space as **Activate** until the focused text element is in Typing Mode, and the consumed Space is what activates it. Is there a way into that state through the input path the product already supports? The constraints are no extra or dummy space, no change to keyboard mappings, and no FKA setting change.

## What the existing records already settle

| Candidate entry through the supported path | Evidence | Result |
|---|---|---|
| A preceding letter (`Hi` before the space) | 21/21 fresh notes, 25 Sep; `Hi` / lone space / `there` as three sends, 26 Sep | Does not help. The space after `Hi` is still lost |
| `Enter` before the text | 25 Sep body trials (title line, Enter, text) | Does not help. Body and first line lost alike |
| Staying in the app (Back, then compose again) | 25 Sep: every trial was list → compose → send → Back, never leaving Notes | Does not help. Each new note loses it again, so the state is per text element, not per app session |
| Re-focusing the *same* element | 27 Sep: two Settings search fields re-focused after Cancel kept the space; the first focus lost it | Kept, which is consistent with a per-element state |
| A consumed Space | 25 Sep: once a note had lost its first space, every later send was exact | Kept afterwards. Consistent with R1 |
| Tab to move the FKA ring onto the field, then Space | C241, 22 Sep: entered Typing Mode and `hi` typed | Works, but needs a Space. Excluded here |
| Pointer click inside the field | C241, 22 Sep: a UIKit cursor and AutoFill appeared, letters did not insert | **Confounded.** The FKA ring was on AssistiveTouch, so this does not show what a click does in a C24C note, where letters do insert |
| Tab, Escape, Backspace on their own | None in a fresh field | Untested. Tab can type a tab character into a field (Home's Tab, 27 Sep and 1 Oct), so it is a visible compensating key, not a clean entry |
| A dedicated Typing Mode command | FKA's Commands page has not been read | Unknown. Reading it is view-only, but it needs the operator or pointer navigation in Settings |

Also checked offline, with no result: the 27 Sep after-send frames show no Typing Mode banner 4 s after the send. The caret is present in ON2 and ON3 and absent in ON1, so its absence there is blink timing, not a signal.

So within the supported path and without a space, one entry remains untested and unconfounded: **a pointer click inside the already-focused empty note**. The 26 Sep lone Space once produced the text-edit menu (Select | Select All | AutoFill), which is how iOS answers a tap on an active text field. That suggests FKA's Activate and a tap on the field may be close equivalents. It does not show it.

## Proposed comparison: smallest that distinguishes

**One variable:** whether the fresh, auto-focused note receives one pointer click inside its body before the text is sent.

- Phone: C24C only, FKA On as it is now (no toggle, so no operator dialog work).
- Field: a new Notes note made exactly as on 27 Sep: the operator's physical Home, long-press Notes, the New Note quick action, 3.0 s.
- Text: `Hi there` (bytes `48 69 20 74 68 65 72 65`), one `/key/sendkey`, identical in both arms.
- Arm A: wait 1.5 s, frame, send.
- Arm B: one `/mouse/click` at (250, 520) inside the empty body, wait 1.5 s, frame, send.
- Order: A B B A A B, so drift over the session falls on both arms. 6 notes, about 12 minutes.
- Driven by [`fka_activate_trial.py`](fka_activate_trial.py): the 27 Sep `fka_trial.py` with this one condition added and nothing else changed. Release kernel API, C24C's lease held only during each trial, and a refusal if any phone is held by anyone, including the installed console.

**Scoring.** Each trial is read from its after-send frame, before anything navigates away (leaving a note applies pending autocorrections, 25 Sep). Three measures are kept apart:
- *Submitted:* the exact bytes, logged by the script.
- *Kernel:* the result code. Code 0 means the HID writes completed, not that anything was inserted.
- *Visible:* the note text read from the frame.

The `-2b-before-send` frame records whether arm B's click opened the edit menu (Paste / AutoFill). That is analysed as part of arm B, not removed.

### What the result would distinguish

| Arm A | Arm B | Reading |
|---|---|---|
| lost 3/3 | kept 3/3 | A click on the focused element puts it in the state where Space types. This supports R1's per-element Activate account, and it names a candidate route inside the supported path, which would still need its own Gate 5 test and approval before any product change |
| lost 3/3 | lost 3/3 | A pointer click does not enter that state. R1 is neither confirmed nor refuted. Next: read FKA's Commands page (view-only) for a non-Space entry. R2 (a non-FKA text feature) keeps its weight |
| kept | kept or lost | The control failed: the phone no longer reproduces the 27 Sep loss, for example after the 1 Oct PC restart or the 27 Sep replug (R3). Stop; neither arm can be interpreted |
| mixed, either arm | | Report the counts as they are. Six trials cannot settle a mixed result. A repeat would be decided with the operator, not run automatically |

**What it cannot show.**
- Why iOS behaves this way. It shows only which focus path keeps the space.
- That successful HID reports mean correct text. Only the frames speak to visible text.
- Anything about other fields (Settings search, Spotlight), other phones, or FKA Off.

## Window procedure (for coordination)

1. **Preflight (read-only):** fresh PIDs; `GET /api/input/status` shows nothing owned; one C24C frame; confirm the operator settings hash. The installed console is running and holds no lease. Its hover tracking can take C24C's lease if the mouse rests on its phone picture, so the operator keeps the mouse off it. If a lease appears anyway, the script refuses and sends nothing, as ON4 did on 27 Sep.
2. **Optional view-only step, if the operator agrees:** the operator opens Settings → Accessibility → Keyboards → Full Keyboard Access, confirms it reads On (closing the still-open item from today), and opens Commands so the page can be read for a Typing Mode entry. Then they return Home.
3. **Six trials** in the order A B B A A B. Before each, the operator makes a physical Home gesture and says "ready". The script runs one trial. Its log, frames and submitted bytes go to `iMouseXP-2.0-evidence-archive/20261001-typing-mode-ab/`.
4. **Finish:** C24C unowned, receivers unchanged, settings hash unchanged, `SHA256SUMS.txt` written. C241 is never addressed (the self-check asserts this).

**Side effects:** six new notes on C24C (`Hithere` or `Hi there`), plus any edit menu that arm B's click opens and the operator dismisses with the next physical Home.

## Mock checks (done)

`python fka_activate_trial.py --self-check` runs the trial logic against a recording fake transport and sends nothing. It checks that:
1. only C24C is addressed;
2. both arms send exactly `Hi there`, once, and no other key (no `fn_key`, no lone space);
3. the arms differ by exactly one body click, after the New Note click;
4. the waits and frames match across arms;
5. it refuses, and sends nothing, when either phone is held;
6. a failure mid-trial still releases the lease and never sends the text.

The check fails, as it should, under three in-memory mutations: an added lone space, one command addressed to C241, and a missing release.
