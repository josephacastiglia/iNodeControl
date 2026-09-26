# Text-chunking candidate: validation report

Date: 25 Sep 2026, updated 26 Sep 2026 (times are local, UTC−4). Status: **candidate only**. The fresh-field exact-text requirement is open. It is not merged, not promoted, and has not replaced the installed console.

## Verdict

| Requirement | Result |
|---|---|
| Long text no longer latches Stop | **Met.** Every 100- and 200-character send completed without Stop, through the harness and through the Send text button |
| Exact 100 characters through the real Send text button | **Open for fresh fields.** Met only in a note that had already lost its first space (U2, F2). In a fresh note the first space is lost (U1, F1), and a lone first space was also lost in fresh Settings search fields. See open issue 1 |
| Stop during a long send stops further chunks and reports accurately | **Met on the final build** (U4b). On the earlier build the first Stop click was swallowed (U4a); fixed in this candidate |
| Explicit recovery without replay | **Met** (U5) |
| Taking and releasing control | **Met** (U6) |
| Over-limit text rejected, not truncated and sent | **Met** (U3). The box no longer truncates pasted text |
| Windows `--self-test` / `--ui-test` on the final candidate | **Pass after a test-only fix**: 143, and 126 in 15 of 15 runs, zero real-phone input. Before the fix, one UI check failed in about 1 run in 5 (see Tests) |

## Source revision

- Base commit: `ee445d70e5f7e3cd9497a9162fc89ba9f6061e4a` ("Import iMouse 2.0 source and development records").
- **Checkpoint commit:** the local commit on branch `claude/jovial-yonath-f044e9` that adds this report, containing the code, `KEYBOARD-SPEC.md` and this folder's text evidence. A file cannot hold its own commit ID, so the full ID is recorded in the follow-up report commit (see [Checkpoint and handoff](#checkpoint-and-handoff)). It is not merged or pushed.
- The committed `src/` is byte-identical to what the final candidate was built from. Before committing, `git diff ee445d7 -- src` was confirmed equal to the build-time `candidate-src.patch` (SHA-256 `1725349BABC14BD59DA7093947E1304D1760B9EEE5BEF5A7416447CDA9CEE5BE`). Every file under `src/iMouse.Console` was last written by 03:04:41, before the 03:05:06 build.
- The build-time patch files (`candidate-src.patch`, and `candidate-full.patch` SHA-256 `1A46C154…`, which predates the KEYBOARD-SPEC correction) are superseded by the commit and are not kept.

## Executable

Built with `dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o <folder> --no-incremental` into a separate folder. No release folder or shortcut was touched.

| File | SHA-256 |
|---|---|
| `%TEMP%\claude\imouse-candidate-textchunk\iMouse2.exe` (`C:\Users\joey_\AppData\Local\Temp\claude\imouse-candidate-textchunk\iMouse2.exe`) | `B1C38A1EE0156C178106FFE18EC8EC32AE359C149066F089FE05D9B9C117D060` |
| `…\iMouse2.dll` | `6AD50CBA4C81F48F98731CD111EDC13C5BDA908681CFCBFEE3B3C34BA48B733E` |

**Current candidate (26 Sep)**, built from the test-fix commit into a new folder. Its product code is identical to the build above; only the UI test's check changed.

| File | SHA-256 |
|---|---|
| `C:\Users\joey_\AppData\Local\Temp\claude\imouse-candidate-textchunk-2\iMouse2.exe` | `2C9AF29184691DF575EF45E1ACECAA45EB20368A383CFC99D1FA111A0C6B8111` |
| `…\imouse-candidate-textchunk-2\iMouse2.dll` | `4258EAB4D07D759BABD7DD3DE8453194EF0688B001622D76FD641B03DB2E150F` |

The `6AD50CBA…` build above, which the 25 Sep UI validation and the Inline Predictions experiment used, is kept unchanged in its own folder for traceability. A .NET build embeds its output path, so a rebuild in another folder has a different hash even from identical source.

**Build A**, used for U1–U4a, was an earlier build into the same folder. It differed from the final build only by the drawer fix (the `TopBar` name and one line in `ShowDrawer`) and that fix's UI test. Its hash was not recorded.

## Tests (final build)

- `--self-test`: exit 0, **143 passed**. Of these, 30 cover text chunking: splitting, one lease, sequential sends, a failure on chunk 3, Stop mid-text, a timeout, cancellation before sending, mirrored phones, the unowned path, and unchanged single-command exceptions.
- `--ui-test`: exit 0, **126 passed** in each of three runs, `realPhoneInputCommands = 0`. New checks include a 200-character send becoming 7 chunks, a failure on chunk 3, a box with no `MaxLength`, the over-limit counter and refusal, and Stop reachable while a drawer is open.
- Mutation checks:
  - Chunking disabled (`TextChunk = 1000`): both suites fail.
  - Drawer fix removed: the UI test fails with `hit Rectangle`, the drawer's dimming overlay.
- The latest run's output files are in [`test-results/`](test-results/): `self-tests.json` and `ui-interactions.json`.

**Correction (26 Sep): the UI test was flaky, and the earlier "three runs" pass was luck.**

- Re-running it five times each on the `6AD50CBA…` build and on a fresh build from the checkpoint commit gave 4 of 5 passes on both. Every failure was at *A failed chunk shows input paused and offers Resume*.
- A diagnostic build that recorded the state text caught it once in 20 runs. Input was correctly paused and Resume enabled, but the text read `Ownership renewal failed: Code 409: … Expired or invalid token` instead of `Input paused: …`.
- Cause: a lease renewal already in flight when the mock kernel revoked the lease posted its own notice just after the failed send's notice, replacing the wording. The 50 ms test heartbeat makes this frequent; the 10 s production heartbeat makes it rare.
- Fixed in the test only. The check now asserts the paused state (not ready, Resume enabled, no "ready" text) instead of the wording. No product code changed.
- Afterwards: `--self-test` 143 passed, and `--ui-test` passed 15 of 15 runs at 126 each, with zero real-phone input. These results are in `test-results/`.
- The wording overwrite is an existing behaviour of the renewal code. It is listed under open issues for the integration session and is not changed here.

## Changes made in this round

1. **The 200-character cap is temporary and never truncates.** The box's `MaxLength="200"` is removed, because WPF truncates pasted text to `MaxLength` silently and the shortened text would then send. A counter shows `N / 200` and turns red with `too long to send` above the cap. Send text refuses with `Send text takes at most 200 characters at a time; this is N. Nothing was sent.` The docs and code comments now say the cap bounds how long one send holds the phones, and that chunking does not require it.
2. **Stop input takes the first click while a drawer is open.** `DrawerHost` covered the whole window, top bar included, and its overlay closes the drawer on click. Send text lives in the Controls drawer, so the first Stop click during a send only closed the drawer (U4a). The drawer now starts below the top bar.
3. **Documentation corrected.** `KEYBOARD-SPEC.md` no longer calls the missing space a Notes quirk. Findings and hypotheses are kept separate. Text-path timeout recovery is distinguished from single-command timeout recovery, which is not integrated. The cap is described as temporary.

## Controlled typing comparisons (C24C only)

**Identity checked before any input:** device `86:1D:4A:04:2F:F6` "XR C24C", board `C24CBFBD`, receiver `iMouse2-C24C`. It was not owned and not stopped.

**Tooling.** Sends went through the candidate's own `ApiClient.SendTextAsync`, driven by a small harness that references the built DLL. That tests phone behaviour, **not** the button.

**Focus preparation, identical for every trial:**

1. From the Notes list, tap compose with a lease-aware tap: a random pixel inside the button, after `/mouse/reset`.
2. Wait 3.0 s.
3. Screenshot the phone and require an empty note editor (mean brightness above 250, under 0.5% dark pixels). The list view measures 240.8 and fails. All 17 trials passed at 254.3.
4. For body trials, send a spaceless title line and Enter, then wait 3.0 s.
5. Send the text.
6. Wait 1.5 s and screenshot.
7. Tap Back.

**Test notes.** Every trial used a new note. Existing notes were not edited, including `A B Test 123!`.

- `L` = `Chunk check 2026 on C24C types 100 characters in four chunks of 32 with one lease (no Stop) #78 & OK` (100 characters, four chunks).
- Screenshots are `trials/<id>-*-empty.png`, `-typed.png` and `-zoom.png`.
- Raw records, including start times and durations, are in [`trials/trials.jsonl`](trials/trials.jsonl).

| Id | Context | Sent | Observed | Chunks / time |
|---|---|---|---|---|
| T01, T04, T07 | New note, first line | `L` | `Chunkcheck 2026 on C24C … & OK` (the space after `Chunk` missing, rest exact) ×3 | 4/4, 16.7–16.8 s |
| T02, T05, T08 | Body, after title `Body<id>` + Enter, separate send 3 s later | `L` | Title exact; body `Chunkcheck …`, rest exact ×3 | 4/4, 16.7–16.8 s |
| T03, T06, T09 | New note, first line | `Chunk check` | `Chunkcheck` ×3 | 1/1, 2.0–2.1 s |
| P01 | New note | `Chunkcheck test` | `Chunkchecktest` (iOS suggestion bubble "Chunkcheck test") | 1/1, 2.7 s |
| P02 | New note | `Hi there` | `Hithere` | 1/1, 1.6 s |
| P03 | New note | `Chunkk check` | `Chunkkcheck` | 1/1, 2.2 s |
| P04 | Title `BodyP04` + Enter, 3 s, `Chunk check`, **same lease** | | `BodyP04` / `Chunkcheck` | 1/1, 1.7 s |
| P05 | Title `BodyP05`, 3 s, `\nChunk check` (**Enter first**) | | `BodyP05` / `Chunkcheck` | 1/1, 2.3 s |
| P06, P08 | `Warm up` + Enter, 3 s, separate send `Chunk check` | | `Warmup` / **`Chunk check` (exact)** ×2 | 1/1, 1.9–2.0 s |
| P07 | New note | `A B C` | `AB C` | 1/1, 1.1 s |

Earlier harness runs the same day (R1–R3, [analysis/c24c-text-chunking-20260925/](../c24c-text-chunking-20260925/)): two new-note first lines gave `Chunkcheck …`, and a second paragraph (Enter + `L` in one send) was exact.

**Findings**, from what was observed:

- 21 of 21 sends containing the first space typed into a note lost that space. The 7 later sends into such notes lost no spaces: R3, P06, P08, U2, F2, U4a, U4b. Each of these was typed into a note that had already lost its first space.
- The loss occurs with one chunk or four. It occurs with the space at position 3, 6, 7 or 11, which rules out a fixed keystroke index or time; P01's 6th keystroke arrived.
- It occurs on the first line and in the body, with a fresh lease or one held lease (P04), and with or without a leading Enter (P05).
- A 3 s idle gap does not reproduce it once the note has lost its first space (P06, P08).
- The kernel confirmed every chunk, and none of these sends latched Stop.

**Hypotheses** at the time of these trials:

1. **iOS Inline Predictions consumes that space.** A tip reading "Inline Predictions — Press space to input predictive text" and grey predicted text were on screen during these runs. In U4b an Enter accepted a pending prediction and inserted `he` that was never sent. **Later tested and not supported.** Turning Show Predictions Inline off did not change the result (see [Inline Predictions experiment](#inline-predictions-experiment)).
2. **Full Keyboard Access** handles that space. It is set up on these phones; see KEYBOARD-SPEC. Still untested, because it needs a further settings authorization.

The kernel keeps no per-note state and sends identical reports for every space, which points at the phone, but that is not proven. The older `A B Test 123!` capture, which kept its first space, is unexplained.

**Reproduction:** on C24C, in Notes, tap compose, then send `Hi there` through Send text or `SendTextAsync`. Observed: `Hithere`.

## Actual candidate console (real buttons)

**Setup.** The candidate was launched from the separate folder and connected to `127.0.0.1:9913` (the address in `%APPDATA%\iMouse2\settings.json`). **XR C24C** was selected; "Mirror to all" was off and C241 was unticked the whole time. Desktop control was granted for the candidate's exe path. An earlier grant had resolved to the installed console, which was not interacted with. Clicks went only to the candidate window.

**Navigation** (not under test):

- Console taps landed off target while "Move phone pointer with mouse" was on, because the pointer drifts after hover moves. Reset pointer and then a tap worked.
- For F1/F2 the enlarged preview did not fit the window, so compose was tapped with the lease-aware script while the candidate held no lease.

**Evidence:** `ui/`. Console captures use PrintWindow. Full log text was read through UI Automation into `ui/U4b-activity-log.txt`.

| Step | Build | Action | Result |
|---|---|---|---|
| U1 | A | Fresh note; type `L` in the box (`100 / 200`); Send text | Log `Send text: 100 characters in 4 chunk(s)`. No Stop. Phone `Chunkcheck …`, **99/100** (open issue 1) |
| U2 | A | Enter button, then Send text `L` | Second paragraph **exact** `L`. No Stop |
| U3 | A | Paste 101 more characters (201); Send text | Box kept all 201. Counter `201 / 200 · too long to send` in red. Log `Send text takes at most 200 characters at a time; this is 201. Nothing was sent.` Phone unchanged; kernel generation unchanged (88) |
| U4a | A | 200 characters (7 chunks); Send text; **one** Stop click about 11 s in, with Controls open | **Failed.** The click only closed the drawer. Log `Send text: 200 characters in 7 chunk(s)`, no stop; all 200 typed. Led to change 2 |
| U4b | **final** | 200 characters; Send text; **one** Stop click about 11 s in, with Controls open | **Passed.** Header `Input stopped · choose Resume input to continue`. Log `Send text stopped: 64 of 200 characters confirmed. Chunk 3 of 7 may be partly typed and was not retried. Chunks 4–7 were not sent.` then `Input stopped: 86:1D:4A:04:2F:F6`. Kernel `stopped=True`, lease revoked, generation 91. Phone shows the 64 confirmed characters plus `k brown fox ` (12 of chunk 3's 32), identical 8 s later (`U4b-stopped-t0-vs-t8.png`) |
| U5 | final | Resume input | Header `Input ready · previous actions discarded`. Kernel `stopped=False`, not owned. Phone identical 8 s later (`U5-no-replay-compare.png`): nothing replayed, the rest of chunk 3 was not re-sent |
| U6 | final | Reset pointer, then Settings → Disconnect, then Connect | Reset pointer took control (kernel `owned=True`). Disconnect released it (`owned=False`, "Controller released.", generation 92, not stopped). Connect brought input back ready without taking the phone (`owned=False`) |
| F1 | final | Fresh note; Send text `L` | `Chunkcheck …`, **99/100** (open issue 1) |
| F2 | final | Enter button, then Send text `L` | **Exact `L`, 100/100** (`F1F2-final-build-zoom.png`) |

Closing the candidate released C24C (generation 95, not stopped).

## Inline Predictions experiment

25 Sep 2026, 21:18–21:40. The user authorized temporarily changing Inline Predictions on C24C only and restoring it afterwards. No other setting was changed.

**Rack at start.** The PC had restarted at 20:06 and the rack was down.

- The user restarted it with `Start Two Phone Test.ps1` at 21:21 (kernel PID 34796, receivers PIDs 9760 and 16500) and started mirroring on C24C.
- The script also opened the installed console (PID 29352), which held and renewed C24C's lease.
- With the user's agreement I closed it normally, after confirming its path and that no phone had a command in progress. C24C then showed "Controller released."
- C241 was offline and not mirroring throughout, and received no input.

**Identity:** `86:1D:4A:04:2F:F6` "XR C24C", board `C24CBFBD`, receiver `iMouse2-C24C`, iOS 18.7.10.

**Original setting (S0).** Settings → General → Keyboard shows the iOS 18 label **"Show Predictions Inline"**: **ON**.

- The Hardware Keyboard page has no inline-predictions switch. It shows layout English (US) "Automatic — U.S." (a Gate 5 item that had not been captured before), with Auto-Capitalization, Auto-Correction and "." Shortcut on.
- Evidence: `inline-predictions/S0-original-keyboards-page.png`, `S0-original-hardware-keyboard-page.png`.

**Procedure, identical for all nine trials:**

1. The candidate is disconnected, so C24C's lease is free. Setup aborts otherwise.
2. From the Notes list, the lease-aware script taps compose. It sends `/mouse/reset` before the click.
3. Wait exactly 3.0 s, then require an empty note by pixel check. All nine measured mean 255 with 0 dark pixels.
4. In the candidate console (PID 35336, final build, dll `6AD50CBA…`): Settings → Connect, then Controls. Check `Target: XR C24C` and that the box holds `Hi there` (`8 / 200`).
5. Click the real **Send text** button and wait 4 s.
6. Capture the phone, then Settings → Disconnect in the candidate.

HID timing was unchanged: same build, same kernel. The console's **Reset pointer button was not needed and not used**: every setup tap came from the script, which resets the pointer itself, and no setup tap missed.

**Setting changes.**

- Turned **OFF** at 21:33 (`S1-show-predictions-inline-OFF.png`).
- **Restored to ON** at 21:36 (`S2-show-predictions-inline-RESTORED-ON.png`).
- Each time, all eight switches from Auto-Capitalization to Smart Punctuation were read before and after. Only Show Predictions Inline changed.
- After restoring, all eight match the original. The switch area differs from S0 by a mean of 0.53 pixel levels, which is the pointer dot.

| Trials | Show Predictions Inline | Sent with the Send text button | Observed |
|---|---|---|---|
| B1, B2, B3 | ON (original) | `Hi there` | `Hithere` ×3 |
| O1, O2, O3 | OFF | `Hi there` | `Hithere` ×3 |
| R1, R2, R3 | ON (restored) | `Hi there` | `Hithere` ×3 |

Evidence: `inline-predictions/<id>-empty.png`, `-typed.png`, `-zoom.png`, the side-by-side `hi-there-B-O-R-sheet.png`, and the timings in `ip-trials.jsonl`.

**Result.** The setting did not change the result: 9 of 9 lost the space whether it was on, off or restored. These trials do **not support** the Inline Predictions hypothesis, but they do not definitively rule it out (see Limits). As instructed, step 5 (the 100-character comparison) was not run and no other setting was touched. Neither an environmental workaround nor a software fix was found.

**Limits.** No grey inline prediction appeared after `Hithere` in any condition. So the screenshots do not independently show the switch changing Notes' behaviour, only that the switch changed and the result did not. Notes was not relaunched after the change, though each trial used a new note.

**Setup incidents (no setting changed):**

- The first tap in Settings landed on the VPN row, because the list was still settling after launch. The VPN page opened; nothing on it was tapped, and VPN stayed "Not Connected". Later taps waited 2.5 s and re-checked the layout first.
- The layout check before the OFF tap did not run: a function named `Diff` collided with PowerShell's `diff` alias. The per-switch before/after check did run and confirmed that only the intended switch changed. The layout check was fixed before the restore tap and ran there (difference 0.56).

**Proposed next isolated test (no settings changes).**

1. In a fresh note, split `Hi there` into three Send text clicks through the same path: `Hi`, then a single space on its own, then `there`.
2. Screenshot the phone after each click. This shows what the lone space's HID report does on screen at that moment: a character, a Full Keyboard Access focus change or activation, or a popover.
3. If the lone space also disappears, repeat the split in a fresh text field in another app, for example a new Reminders item. That separates Notes-specific behaviour from system keyboard handling.

Only if both point at system handling would a Full Keyboard Access comparison, which needs a further settings authorization, be the next step.

## Lone-space diagnostic

26 Sep 2026, 01:24–01:38. No settings were changed.

**Pre-flight.**

- C24C `86:1D:4A:04:2F:F6` "XR C24C" (board `C24CBFBD`) was mirroring, not owned, not active and not stopped, generation 48. No other session was using it.
- The installed console (PID 10696) was minimized, so it was left running and not closed. C241 was offline and untouched.
- The console was the **current candidate**: `imouse-candidate-textchunk-2` (dll `4258EAB4…`, built from commit `8d6a285`), PID 412. The user first declined desktop control for this build, then approved it on a second request.

**Hover incident (no text input).** Before any trial, the setup guard found C24C owned. The candidate had taken the lease through its default "Move phone pointer with mouse", from a mouse passing over its phone preview. That sends pointer moves only, not taps or keys. Disconnecting the candidate released it (generation 48 → 49). "Move phone pointer with mouse" was then turned off in the candidate for this session. It is a per-session console option, not a keyboard setting and not HID timing.

**The lone space is not trimmed or rejected before it is sent.**

- In code: `SendText_Click` rejects only empty text (`IsNullOrEmpty`, not `IsNullOrWhiteSpace`) and characters outside 32–126, and never trims. `ApiClient` trims only URLs. The kernel's `Text()` returns the JSON string unchanged, and `Validate` accepts 1–1000 characters, so a space becomes one Spacebar stroke (usage 44).
- Observed: before each lone-space send the box counter read `1 / 200`. The console then logged `Send text: 1 characters in 1 chunk(s)`, which it writes only when the kernel answered code 0.

**Procedure.** Each field was fresh: a new note prepared exactly as in the earlier trials (compose, 3.0 s, empty-note check), or a newly opened Settings search field. Three separate clicks on the real **Send text** button, about 20 s apart: `Hi`, then exactly one ASCII space, then `there`.

After each click, three phone screenshots were taken 300 ms apart. Each records the cursor's x-position on the text row and the right edge of the dark text. A trailing space is invisible, so the evidence is whether the cursor moved plus the final text. The raw log is `lone-space/trial-log.json`; screenshots are `lone-space/<id>-typed-f1..f3.png` and `<id>-zoom.png`; the console's log lines are `lone-space/*-activity-log.txt`.

| Field | `Hi` (ack time) | Lone `" "` (ack time) | `there` (ack time) | Final text |
|---|---|---|---|---|
| D1: fresh Notes note | 01:27:12. Text edge x=63, cursor x=66 | 01:27:32. Cursor **still x=66** | 01:27:54 | **`Hithere`** |
| D2: fresh Notes note | 01:28:58. Text edge x=63 (cursor blinked off in all 3 frames) | 01:29:18. Cursor x=66 | 01:29:38 | **`Hithere`** |
| E1: fresh Settings search field | 01:33:26. Text edge x=80. A blue focus ring was around the field | 01:34:32. Cursor x=82, directly after `Hi`. **Text-edit menu "Select \| Select All \| AutoFill" appeared**, and the results were unchanged | 01:35:07 | **`Hithere`** |
| E2: fresh Settings search field | 01:36:35. Text edge x=80, cursor x=82 | 01:36:57. Cursor x=82. No menu in the captures | 01:37:27 | **`Hithere`** |

**Findings.**

- In 4 of 4 fresh fields, a space sent alone as the first space was acknowledged by the kernel (code 0) but not inserted. The cursor did not advance, and the final text was `Hithere`. This happened in two apps (Notes and Settings search) and with a separate one-character command.
- So it is not caused by chunking or by the space sharing a command with letters. Because the first space also went missing in Settings search, a Notes-only explanation is unlikely.
- Once, in E1, the lone space produced the text-edit menu that iOS shows when a focused text field is activated.

**Next hypothesis (untested, not proven).** iOS **Full Keyboard Access** may treat the first Space in a newly focused text field as its *Activate* command (Space is FKA's default Activate key). That would activate the field, which in E1 showed the edit menu, instead of typing a space; after that, spaces type normally. The evidence is consistent with this but **does not show that Full Keyboard Access is responsible**. FKA was never changed, the Activate binding was not read, and other system-level text handling would fit the same observations. Four observations support it:

1. FKA focus rings were visible throughout: on FaceTime, on Back, on the Apple Account row, and around the search field in E1.
2. The E1 edit menu.
3. The earlier finding that later spaces in the same field are fine.
4. KEYBOARD-SPEC's C241 record, where Typing Mode was entered with "Tab until the blue ring is on the field, then Space".

**Limits.**

- FKA was not changed; that needs its own authorization.
- The edit menu was captured once in two Settings trials and never in Notes. It may be transient.
- Some captures missed the cursor while it blinked.
- E1a was captured three times while the probe was adapted to Settings. The first attempt crashed after saving its screenshots. The second counted the blue focus ring as the cursor (x=26). The third bounded the search. Nothing was sent between these captures, so all show the same "after `Hi`" state.
- Settings search is a different control from Notes' editor, though it uses the same system text handling.
- Only C24C was tested.

**No environmental workaround and no software fix has been demonstrated.** Turning FKA off would be an environmental workaround at best. Sending a sacrificial space or other compensating keystroke is explicitly out of scope.

**Proposed next isolated test.**

1. Read-only first: open Settings → Accessibility → Keyboards & Typing → Full Keyboard Access → Commands on C24C and record which key is bound to *Activate*. Change nothing.
2. Then, only with authorization: turn FKA off, repeat `Hi` / lone space / `there` in two fresh notes with the same procedure, and restore FKA afterwards.

**Artifacts and side effects.**

- Two new notes in C24C Notes, both `Hithere`, for 33 notes in total. None were deleted.
- The Settings search was used twice and cancelled each time: nothing was opened from the results, no setting changed, and Show Predictions Inline was confirmed still ON.
- Every desktop typing action in this diagnostic reported keystrokes ("Typed N char(s)"), not the clipboard fast path. The clipboard was not changed here; it may still hold a test string from earlier passes.
- At the end the candidate was closed and C24C released (generation 68). The installed console stayed running and minimized. The kernel and both receivers are running, and C24C is mirroring.
- C24C was then handed to the integration session.

## Remaining failures and open issues

1. **The first space typed into a fresh text field is lost (cause unresolved).**
   - It happens through the real button too (U1, F1). Exact text through the UI was obtained only after a note had already lost its first space. This is not a clean pass.
   - Turning Show Predictions Inline off did not change it (9 of 9 identical across ON, OFF and restored ON).
   - A space sent alone as the first space was also lost, in fresh Notes notes and in fresh Settings search fields (4 of 4). That makes a Notes-only explanation unlikely.
   - Full Keyboard Access taking that Space as *Activate* is the leading hypothesis (see [Lone-space diagnostic](#lone-space-diagnostic)). It is untested and **not proven**.
   - No environmental workaround and no software fix has been found. **The fresh-field exact-text requirement remains open.**
2. **iOS alters text next to what was sent.**
   - An Enter accepted a pending inline prediction (`over t` → `over the`, U4b).
   - Leaving a note applied pending autocorrections (`Hithere` → `Hi there`, `Chunkchecktest` → `Chunkcheck test` in the list).

   Exact-text checks must read the screen before leaving the note, and even then iOS may add text the kernel never sent.
3. **Single-command timeout recovery is not in this candidate.** A timed-out tap, drag or key still pauses input silently, with Resume disabled. The text path handles its own timeouts (self-tested only; no live timeout was induced). The fix is being built separately in worktree `vigorous-nightingale-2cc961`. As of this report it is uncommitted and changes the same six files, so integrating it needs a deliberate merge into a new candidate, followed by both suites. Nothing from it was copied here.
4. **Pointer drift in the console** (existing behaviour). With "Move phone pointer with mouse" on, console taps landed about 30 px off target until Reset pointer. Not part of this change.
5. **Cosmetic issues:**
   - After Disconnect, the header still says `Input ready · previous actions discarded`.
   - On relaunch the candidate opened on the secondary monitor and had to be moved.
6. **A lease-renewal notice can replace a failed-send notice** (existing renewal code, for the integration session). If a renewal is in flight when the kernel revokes the lease after a failed command, `InputLeaseClient`'s renewal loop posts "Ownership renewal failed: …", which replaces the more accurate "Input paused: …" in the header. Input is still paused and Resume offered. Only the wording misleads. This touches the notice logic that the timeout-recovery work also changes.
7. **Unverified references:** `rack-agent/src/actions.js` and `rack-agent/test/conformance.test.mjs` are cited in the docs as given, but they are not in this checkout.

## Rack state and side effects

- The kernel (`release\iMouse2-kernel-two-phone`, PID 5804) and both AirPlay receivers stayed running. At the end the receiver state was `mirroring`, live.
- C241 (`FE:A9:BC:D7:A0:44`) received no input and was never selected. Its generation stayed at 18 throughout.
- The installed console `release\iMouse2-two-phone-candidate\iMouse2.exe` (PID 7928) was not used or changed. No release file or shortcut was modified.
- A console from the timeout-recovery session (PID 19536, running from that session's scratchpad) was running during this work, and it was left alone. *Correction (26 Sep):* this report first said it "was connected to the kernel", which I had not verified. That session reports that its scratchpad consoles ran only `--self-test` and `--ui-test`, which use the in-process fake transport and never contact :9913. Separately, every trial's `/input/acquire` for C24C succeeded, and the kernel refuses acquisition while another client owns the phone, so no other client held C24C when a trial started.
- C24C Notes now holds the dedicated test notes from this work (titles like `Chunkcheck…`, `Body…`, `Warmup`, `AB C`, `Hi there`). None were deleted.
- The desktop typing tool entered text through the Windows clipboard, so the clipboard holds the last test string.
- "Move phone pointer with mouse" was left on in the candidate. It is a per-session setting and is not saved.

**After the Inline Predictions experiment (21:40):**

- **Show Predictions Inline on C24C is back to its original ON**, restored and verified at 21:36 (`inline-predictions/S2-show-predictions-inline-RESTORED-ON.png`). No other phone setting was changed.
- The candidate (PID 35336) was closed normally, and C24C showed "Controller released."
- The original console `release\iMouse2-two-phone-candidate\iMouse2.exe` was reopened as PID 10696, with the cursor parked away from its window. Over 12 s it did not take C24C (owned stayed False, generation unchanged at 48), so it sent no input.
- The kernel (PID 34796) and both receivers are running, and C24C is mirroring.
- C241 was offline, never selected, and received no input; its generation stayed at 0 after the restart.
- C24C Notes holds nine more test notes (B1–B3, O1–O3, R1–R3, each `Hithere`), 31 notes in total. None were deleted.

## Evidence inventory

[`evidence-inventory.txt`](evidence-inventory.txt) lists every file in this folder with its size and SHA-256, and marks each as committed or local-only. Screenshots (`*.png`) and the raw `*.jsonl` trial logs are local-only, because the repository ignores `/analysis/**/*.png` and `/analysis/**/*.jsonl`; they were deliberately not force-added. Following the repository's convention for typing evidence (`c241-typing-investigation/trial-log.json`), each raw log is also saved as a committed `trial-log.json` array with local absolute paths made relative: `trials/trial-log.json`, `inline-predictions/trial-log.json` and `lone-space/trial-log.json`. The other committed text evidence is this report, `ui/U4b-activity-log.txt`, `lone-space/*-activity-log.txt` and `test-results/*.json`.

**Preserve the screenshots until they are archived.**

- The 162 screenshots (18.3 MB) and 3 raw JSONL logs exist only in this worktree, at `.claude/worktrees/jovial-yonath-f044e9/analysis/text-chunking-candidate-20260925/`.
- Three earlier screenshots from 25 Sep are in the sibling folder `analysis/c24c-text-chunking-20260925/`:
  - `c24c-01-new-note.png`, SHA-256 `C9084812C61C01EF69EFA034689929A2DBB6651C3E1EFA94AB5D1F9D37BC53D0`
  - `c24c-02-new-note-repeat.png`, SHA-256 `E03D3B145CEA3350CC174FA1F0545BE20319C9CB9015B8C337C73002E5D5583D`
  - `c24c-03-second-paragraph.png`, SHA-256 `BD3D323DC482F22C6902C9ED9298479ABF7C6A403D4096694B5EB7F7EA874CC5`
- Removing this worktree, or running `git clean -x` in it, would delete them. Archive both folders first and check the copies against `evidence-inventory.txt`.

## Checkpoint and handoff

All commits are local on branch `claude/jovial-yonath-f044e9`: not pushed, not merged, not promoted.

| Commit | Content |
|---|---|
| `ee445d70e5f7e3cd9497a9162fc89ba9f6061e4a` | Base |
| `5ea04382e4525fe13457018dd360b77f1679d684` | Checkpoint: text-chunking code, tests, KEYBOARD-SPEC, this report and its text evidence |
| `8d6a2853216d06ab2490906635b4ec312ae7034d` | **Stable for integration.** Test-only fix of the flaky failed-chunk UI check, plus report and test-result updates |
| `e41b8a8773386dbe075d2d56506e072ef5e5b5f9` | Report only: the lone-space diagnostic and this handoff. No `src/` changes |
| The commit that adds this row | Report only: final wording. A Notes-only explanation is unlikely; Full Keyboard Access is not proven; the fresh-field exact-text requirement stays open; screenshot preservation note. No `src/` changes |

**Candidate binary**, built from `8d6a285`:

- `C:\Users\joey_\AppData\Local\Temp\claude\imouse-candidate-textchunk-2\iMouse2.dll`, SHA-256 `4258EAB4D07D759BABD7DD3DE8453194EF0688B001622D76FD641B03DB2E150F`
- `…\iMouse2.exe`, SHA-256 `2C9AF29184691DF575EF45E1ACECAA45EB20368A383CFC99D1FA111A0C6B8111`
- `--self-test` 143 passed; `--ui-test` 15 of 15 runs at 126, with zero real-phone input.
- A clean build from `git archive 5ea0438` also passed `--self-test` 143 before the flake was fixed.

**Handoff patches against the base**, outside every worktree, in `C:\Users\joey_\AppData\Local\Temp\claude\C--Users-joey--Desktop-Claude-Code-iMouseXP-2-0--claude-worktrees-jovial-yonath-f044e9\5833754a-0a75-4837-a381-6827cd6d4def\scratchpad\handoff\`:

- `0001-Chunk-console-Send-text-into-32-character-commands-w.patch`, SHA-256 `9F0F98B9A8086C59B60CAE45FCADBCC1AED0EEBD72527F34FB267CB53E867130`
- `0002-Make-the-failed-chunk-UI-check-assert-paused-state-n.patch`, SHA-256 `3310B9FDF2F0A1CAAC06A9BB22C6DE81E66ABAE30DE314C7014F8C57330E396B`
- `text-chunking-ee445d7..8d6a285.diff`, SHA-256 `A6D216628FABC8550C5C08708E3773A854743820D2C3989678EE190CE71FD057`

`git diff ee445d7 8d6a285` produces the same diff from any worktree.

**Integration.**

- The timeout-recovery session ("Surface timed-out tap/drag/key commands in console", worktree `vigorous-nightingale-2cc961`) was told by message that `8d6a285` is stable. I did not modify its worktree.
- Read-only check: its branch `claude/input-timeout-integration` contains `8d6a285` as an ancestor, followed by its own commits `7e65548` (timeouts made visible) and `8c66dc8` (a loopback fault proxy for tests).
- It reports fixing open issue 6 (the renewal notice) at the root, in `InputLeaseClient.RenewAsync`.
- C24C was handed to it at 01:38, not owned and not stopped, generation 68. Combining this work with the test-settings isolation and timeout recovery belongs to that session.
