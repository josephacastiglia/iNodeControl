# Input timeout and recovery, integrated candidate, 26 Sep 2026

**Status: partial acceptance. Not promoted, not deployed.** It is committed locally on branch `claude/input-timeout-integration`, which also merges the text-chunking report commits (`a6e4a9b`) and the test-mode settings isolation (`43b43f7`), and adds `--data-dir` (`a1560ed`), 12-character text chunks (`b994de9`) and an optional `trackPointer` setting for test configurations (`b0708e3`). Nothing is pushed or merged. Evidence is reported by build; see the acceptance matrix below.

- **Failed / open: fresh-field exact typing.** The first space typed into a fresh field is lost on every build tested, and the cause is unknown. It needs its own focused investigation. The console does not compensate for it, and must not silently do so.
- **Passed live:**
  - Chunked typing in a previously used field, first-click Stop, lost-tap recovery and lost-drag cleanup (27 Sep, `b994de9`).
  - First-click Resume with a real mouse click, and the full-hold frame record of the lost drag (27 Sep, `b0708e3`).
- **Not explained:** three Resume clicks failed once on `b994de9`. They were not reproduced on a mock kernel or on C24C (see Resume click investigation). No product change was made for it.

### Acceptance matrix

| Requirement | Result | Build and evidence |
|---|---|---|
| Fresh-field exact typing | **Failed / open** | First space lost on `b994de9` (27 Sep) and on every earlier build |
| 100 characters in a previously used field | Passed | `b994de9`: exact; 9 chunks, slowest 1,838 ms |
| First-click Stop during a long send | Passed | `b994de9` |
| Lost tap: timeout shown, paused tap not sent, no replay | Passed | `b994de9` and `b0708e3` |
| First-click Resume with a real mouse click after a lost tap and lease expiry | Passed | `b0708e3`, C24C, 15:35:34; mock kernel twice |
| Lost drag: console omits `/mouse/up`; kernel cleanup release confirmed | Passed | `b994de9` (8 ms) and `b0708e3` (9 ms) |
| Lost drag: phone state for the whole hold and after release | Passed | `b0708e3`: note held overscrolled for the whole 8 s, back at rest within one 0.5 s frame of the kernel release |
| Connecting a test candidate sends no input and takes no lease | Passed | `b0708e3` with `"trackPointer": false` |
| Operator settings untouched by candidates | Passed | Hash `72F51CC0…` unchanged; see the stale-launch note under Resume click investigation |
| Offline suites | Passed | `b0708e3`: kernel 79, `--self-test` 191, `--ui-test` 151, harness S1–S6 |
| Chunk completion under arbitrary host load | Not guaranteed | By design; an overrun is reported and never retried |

The working release was not modified: the kernel binary, the receivers, `release/`, `Open iMouse 2.0.ps1` and the shortcuts. For the live checks, the installed console (PID 10696) was closed normally after confirming it held no lease. It was not relaunched before the rack went down; the operator's launcher starts it with the rest of the release. The operator settings file `%APPDATA%\iMouse2\settings.json` was never written by the candidate. Its content hash (`72F51CC0…`) is unchanged throughout. Its timestamp changed once, at 06:57:30Z on 26 Sep: this session ran UI tests of the pre-isolation candidate 1 for an A/B comparison, which rewrote it with the same bytes.

## What the candidate is

| | |
|---|---|
| Branch | `claude/input-timeout-integration`, local, in worktree `.claude/worktrees/vigorous-nightingale-2cc961` |
| Base | `8d6a2853216d06ab2490906635b4ec312ae7034d` on `claude/jovial-yonath-f044e9`: text chunking (`5ea0438`) plus a test-only fix (`8d6a285`), on `ee445d7` |
| Applied | `vigorous-delta.patch` only, with `git apply --3way`, clean. sha256 `f6d25b3c12c3f171feb387bf3d64848aea38d3ebc6e2b9275ef29f44092b70ae`, 9 files, 1074 insertions, 31 deletions |
| Hand edit | `KEYBOARD-SPEC.md`: jovial's bullet "Recovery after a timeout is handled only on the text path … not integrated into this candidate" is replaced by "Timeout recovery covers every input path" |
| Not edited | Jovial's `analysis/text-chunking-candidate-20260925/REPORT.md`. It stays the record of that candidate. Two of its open issues are resolved here: item 3 (single-command timeout recovery) and item 6 (renewal notice overwrite) |
| Build | `%TEMP%\claude\imouse-candidate-integrated-1\`. Console at the root: `iMouse2.dll` SHA-256 `E6CEA6AD2A9D2B79F53384582F6D31BE9ABD2838118C985B78F1694C0DF45DAA`, `iMouse2.exe` `EEC6B7E05EF0B9D0741A049F056513FFD475926A05AFFC00CF5C1DC82CBF66CE`. Kernel self-test build in `kernel-selftest\`, harness in `harness\` |

## What this change adds to the text-chunking base

1. **Timeouts are visible on every input path.** A timed-out tap, key or drag pauses input with `Input paused: request timed out; the outcome is unknown. Check the phone, then choose Resume input.`, is logged once, and enables Resume. A Stop, selection change or disconnect stays silent: the console checks whether it cancelled the command itself, not what type of exception came back.
2. **Queued input is reported as not sent.** A command waiting behind one that failed or timed out ends as `Not sent: input was paused by an earlier failure or timeout while this waited.` It never reaches the kernel. A command queued when the operator presses Stop stays a plain cancellation.
3. **Prompt cleanup after an uncertain gesture** (below).
4. **A refused renewal no longer replaces a failure's notice.** A renewal already in flight when a failed command revoked the lease used to post "Ownership renewal failed" over "Input paused: …". This is jovial's open issue 6, fixed at the source.
5. **Tests and tooling.**
   - Console self-tests went from 143 to 181 and UI checks from 126 to 143.
   - The kernel gained 8 tests.
   - `tools/input-cleanup-harness` runs the real console client against the real kernel server over loopback HTTP, with a simulated board and injected faults. It is test tooling, not part of either product build.

## Prompt cleanup after an uncertain gesture

**The problem.** A drag's move can time out, or its answer can be lost, after the button went down. The console then paused locally, sent no `/mouse/up` (the paused lease client refuses it), and stopped renewing. The button stayed down on the kernel until lease expiry, measured at 21.8 s after the failure was detected.

**Protocol choice**, taken from `InputSessions` and `ApiServer`:

| Mechanism | What it does | Suitable here? |
|---|---|---|
| `/input/stop {id}` | Takes no token. Closes whoever holds the phone and latches Stop | No. It would interrupt a newer controller |
| `/input/release {id, token}` | `ValidateOwner` first, so a wrong or stale token gets code 409 and changes nothing. Otherwise it cancels the lease and any command still active under it, drains, and writes button-up and key-up. Answers 0, or 33 if the board write failed. Does not latch Stop | Yes. It is scoped to this console's lease on one phone |
| Lease expiry | The watchdog closes an unrenewed lease within 100 ms of its deadline | Fallback only: 20–30 s |

**What happens now** (`InputLeaseClient`):
- The lease client marks a phone `ButtonMaybeDown` when a `/mouse/down` leaves. A confirmed `/mouse/up`, `/mouse/click`, `/mouse/swipe` or `/mouse/reset` clears it.
- When a command fails or times out and a phone in it may have a button down, the client starts a release at once.
  - It runs on a pool thread, with `CancellationToken.None` and without the phone's gate, so it does not wait on the failed command's cancelled token or on the input queue that command still holds.
  - It sends one `/input/release` per affected phone, each with that phone's own token.
- It never resends the gesture and never resumes. The phone stays paused until the operator chooses Resume input. Resume and release wait for the cleanup's answer before reusing the lease.
- The result is raised as `InputCleanup`.
  - The activity log always records it.
  - The panel shows it only if nothing happened since. After a Stop, Resume or selection change it is logged as "Earlier input failure: …" and the panel is left alone.

**Confirmed or not.** Each phone's result is one of these:

| Kernel answer | Reported | Token |
|---|---|---|
| 0 | Confirmed: the kernel closed this lease and released the button | Cleared |
| 409, then `/input/status` shows not releasing, no release failure, generation > 0 | Confirmed: the kernel had already closed it (failure, deadline, expiry, Stop) and released | Cleared |
| 409, then status shows `release_failed`, still releasing after 3 s, generation 0 (kernel restarted), or no status | Not confirmed, with the reason | Cleared |
| 33 | Not confirmed: the board could not complete the release | Cleared |
| No answer or an HTTP failure | Not confirmed | Kept, so the operator's Resume tries again |

Panel after a confirmed release: `Input paused: request timed out; held button released (confirmed). Check the phone, then choose Resume input.` When it is not confirmed, it says `button release not confirmed`, and the log adds the lease-expiry fallback and that Resume tries the release again. "Confirmed" means the kernel's HID write, not what iOS registered.

## Failure boundaries and where each is tested

| Boundary | Harness scenario (real kernel code, simulated board) | Unit tests |
|---|---|---|
| Kernel command failure | S3 | Console #20; kernel *A drag move that fails lifts the held button without /mouse/up* |
| Kernel command deadline | S2 (the race went both ways across runs; both confirmed) | Kernel *… cut by the 8 s command deadline …* |
| Command completed, answer lost | S1 | Console #18; UI *A drag timeout releases each mirrored phone's own lease at once* |
| Cleanup request fails | S4 (503, then an explicit Resume) | Console #22 (code 33) |
| Cleanup request times out | S6 (release dropped, expiry fallback measured) | Console #21 |
| Stale cleanup after ownership changed | S5 (another controller stops, resumes, takes the lease and presses) | Console #23; kernel *A stale release is refused and leaves a newer controller's held button and lease alone* |
| Queued input stays unsent | S1 (tap queued behind the lost move) | Console #17; UI queued key |
| No automatic replay or Resume | Every scenario checks the console's requests after detection: only `/input/release`, plus `/input/status` after a 409 | Console #18, #21; UI drag check |
| Resume waits for an unanswered release | | Console #24 |
| Operator Stop overtakes the release | | Console #25 |
| Renewal race (jovial's issue 6) | | Console #19 |

## Test results, integrated build

`test-results-integrated/` holds the files. All from the build folder above:

| Suite | Result |
|---|---|
| Kernel `--self-test` | 79 passed |
| Console `--self-test` | 181 passed, 10 of 10 runs |
| Console `--ui-test` | 143 checks, 25 of 25 runs |
| `InputCleanupHarness` | Every check in all 6 scenarios passed, 3 of 3 runs |

Earlier runs are kept as history: `cleanup-harness-worktree-run{1,2,3}.json` (before integration) and `cleanup-harness-integration-preview.json` (a preview built from jovial's uncommitted state).

## Measured cleanup behaviour (simulated board, loopback HTTP)

Times run from the console detecting the failure to the first button-up report the board received. The values are the three integrated runs.

| Case | Detection | Button-up after detection | Kernel's answer after detection |
|---|---|---|---|
| S1 answer lost, button held | 8.0 s after the move left (HTTP timeout) | 6.7, 6.9, 7.2 ms | 10.1, 9.5, 10.3 ms |
| S2 move hung on the board | about 8 s | −0.5 to −0.2 ms here; +2.3 ms in an earlier run (the kernel's deadline and the console's release race) | 5.7–6.3 ms |
| S3 board write failed | at once | −0.3 to −0.2 ms (the kernel released before answering) | 0.6–0.7 ms |
| S4 release refused (503) | | Not released by cleanup; released 1.4–1.7 ms after the operator's Resume | |
| S6 release lost | | 21.8 s by lease expiry (29.8 s after the press) | |

So the button stays down for about 8 s plus under 10 ms when an answer is lost; before this change it was about 30 s. **This is simulated evidence only.** No phone or board was measured.

## Remaining limitations

- **Detection is bounded by the 8 s HTTP timeout.** This change does not alter it.
- **If the kernel is unreachable, nothing can be released now.** The release is reported as not confirmed. A live kernel then releases on lease expiry (measured 21.8 s after detection). A dead kernel releases nothing, and the board keeps its last report. Immediate release is not guaranteed.
- **A crashed and restarted kernel.** Its status shows generation 0, which is reported as "no record of this lease (restarted?)", not confirmed. If the new kernel's slot was used again before the status query, a close by the new kernel would read as confirmed. That case is untested.
- **Scope.** Cleanup covers a button held across commands (`/mouse/down` … `/mouse/up`). Taps, swipes and key strokes release within their own kernel command.
- **A command that left and was then cut by a failed renewal** is still logged as a timeout ("outcome may be unknown").
- **Test-isolation hazard, existing behaviour.** `--ui-test` rewrites `%APPDATA%\iMouse2\settings.json`, the file the installed console reads, with the values it loaded; they were unchanged. A separate task was suggested to isolate it.

## Provenance

- **Text-chunking source.**
  - Commit `8d6a2853216d06ab2490906635b4ec312ae7034d` (parent `5ea04382e4525fe13457018dd360b77f1679d684`, base `ee445d70e5f7e3cd9497a9162fc89ba9f6061e4a`).
  - Its owner's patches are outside every worktree, in `%TEMP%\claude\C--Users-joey--Desktop-Claude-Code-iMouseXP-2-0--claude-worktrees-jovial-yonath-f044e9\5833754a-0a75-4837-a381-6827cd6d4def\scratchpad\handoff\`. The SHA-256 values below were verified here.
  - `0001-*.patch` `9f0f98b9a8086c59b60cae45fcadbcc1aed0eebd72527f34fb267cb53e867130`
  - `0002-*.patch` `3310b9fdf2f0a1caac06a9bb22c6de81e66abae30de314c7014f8c57330e396b`
  - `text-chunking-ee445d7..8d6a285.diff` `a6d216628fabc8550c5c08708e3773a854743820d2c3989678ee190ce71fd057`
- **This change.**
  - `vigorous-delta.patch` = `git diff bf35aaf2 572a899b`.
  - `bf35aaf21bdac788f1950b756eaa75e8a25e7454` is `ee445d7` plus `jovial-snapshot-0212.patch`, the uncommitted snapshot this work began on (sha256 `3f7db12f9d5d95e4eda537a9cbbdb445b15c929b91eb00bbcf080a7a69ca3bdf`).
  - `572a899b4855917cdc3016d3979f1fe8263e6ac7` is the pre-integration candidate tree, verified equal to the worktree just before integration.
- **What the snapshot missed compared with `8d6a285`.**
  - Up to 03:21: see `jovial-after-snapshot-0321.diff`.
  - After that: the `KEYBOARD-SPEC.md` Inline Predictions wording and the failed-chunk UI assertion.
  - The delta applied over all of it without conflict. The snapshot itself was not merged.

**Handoff inventory**
- Jovial's `analysis/text-chunking-candidate-20260925/evidence-inventory.txt` (committed) lists every screenshot and raw JSONL with its size and SHA-256.
- Those files are `local-only`: `.gitignore:25` ignores `/analysis/**/*.png`. They exist only in `.claude/worktrees/jovial-yonath-f044e9/analysis/`: 97+ PNGs in `text-chunking-candidate-20260925/` and 3 in `c24c-text-chunking-20260925/`, which `KEYBOARD-SPEC.md` links to.
- Archive them before that worktree is cleaned up; they are not in any commit.
- This candidate adds no screenshots.

## Chunk size: 32 → 12 characters (27 Sep)

**Failure preserved.** `live-20260926/check1b-deadline-overrun.txt` has the verbatim proxy-log lines and archive hash. A 32-character chunk ran 8,021 ms, got code 33, and the phone was stopped after 30 of 32 characters were typed.

**Measured.** `tools/input-cleanup-harness --chunk-timing` runs the kernel's own `InputRouter` (timing unchanged) on a simulated board, with spinning threads at normal priority for load. Raw data is in `chunk-timing/`.

| Load (16 logical cores) | 12 characters, max | 16, max | 32, max | Worst ms per character |
|---|---|---|---|---|
| Idle | 1,987 ms | 2,630 ms | 5,234 ms | 166 |
| 16 threads | 2,316 ms | 3,313 ms | 5,704 ms | 219 |
| 32 threads, run 1 | 3,015 ms | 4,053 ms | 8,614 ms | 371 (at 24 characters) |
| 32 threads, run 2 | 2,054 ms | 2,883 ms | — | 185 |
| 48 threads | 2,205 ms | 2,943 ms | — | 188 |

Live on C24C, 32-character chunks took 4.9–5.7 s, plus one 8,021 ms overrun (about 267 ms per character).

**Chosen:** `ApiClient.TextChunk = 12`.
- At the worst measured rate that is about 4.5 s; at the live overrun's rate, about 3.2 s. 16 would reach about 5.9 s at the worst rate.
- 200 characters is now 17 chunks.
- The kernel deadline, HID timing and the no-retry rule are unchanged.
- **No size guarantees completion under arbitrary load.** An overrun is still reported as timed out and never retried.

**Tests.** The text-chunk self-tests and UI checks now derive every count from `TextChunk` instead of hard-coding 32, 64, seven or eight. A new check keeps `TextChunk × 371 ms` within 5 s.

**Portal.** Its independent `TEXT_CHUNK = 32` needs the same evaluation. See `PORTAL-TEXT-CHUNK-NOTICE.md`; that branch was not edited.

## Resume click investigation and live re-check, 27 Sep 2026, build `b0708e3`

**What failed on `b994de9`.** After the lost tap in check 3, three mouse clicks on Resume input (15:07:33, 15:07:42, 15:08:14) sent nothing. UI Automation Invoke then worked (15:08:33). This is diagnostic evidence only: Invoke skips hit testing, so it is not an acceptance check.
- **Enabled state.** At 15:08:09 UIA reported Resume enabled, on screen, rectangle 655–808 × 50–100 physical px.
- **Hit test.** The clicks at frame (277,28) and (277,29) map inside that rectangle at 2.64× scaling. The third, at (310,30), missed the button.
- **Wider than Resume.** Two Activity clicks (15:07:00 and 15:07:15) also did nothing, while the console was foreground and responding. So from 15:07:00 to 15:08:20 no top-bar click reached the console.
- **Overlays.** The Activity/Controls drawer starts below the top bar (`DrawerHost.Margin` = top bar height), so it cannot cover these buttons.
- **Code path.** `ResumeInput_Click` has no early return that fits: Invoke ran the same handler successfully. The pause notice refreshes the button state. A paused press on the preview takes no mouse capture (`BeginGesture` returns before `CaptureMouse`).
- **Timing.** The clicks came after the kernel lease expired (acquire 15:06:28, expiry about 15:06:58).

**Reproduction with mocks (not reproduced).**
- Setup: `input-cleanup-harness --serve` (the kernel's own ApiServer and InputRouter, simulated board, synthetic frame) behind the fault proxy, driven by real mouse clicks on a candidate console.
- Resume worked on the first click both times: at 22 s, and at about 50 s, after lease expiry. Activity also opened on the first click. The latter run replayed the check-3 sequence exactly: lost tap, paused tap, Activity, Resume.

**Live re-check on C24C (not reproduced).**
- Before each top-bar click, `tools/click-probe` confirmed the top-level window, foreground window and UIA element under the point all belonged to the candidate (PID 27944), with Resume enabled.
- The same sequence then passed on the first click: lost tap, lease expiry (C24C stopped, generation 6), paused tap, Activity, Resume. `/input/release` 409, `/input/status` 0, `/input/resume` 0 at 15:35:34.
- Resume after the lost drag also worked on the first click (15:37:02).

**Conclusion.**
- No console-side cause was found, and the failure did not recur in three attempts. So no product change was made.
- The remaining explanation is untested: this session's computer-use tool masks other applications' windows, so a transparent window from another process over the top bar would not have shown in its screenshots. `textinputhost.exe` was among the masked windows in a later capture, but that is only a hypothesis.
- Future live checks should run `tools/click-probe` before each click so a recurrence identifies what received the click.

**Unintended stale launch (15:24:00–15:24:13).**
- Asking the computer-use tool to open "Imouse2" launched `%TEMP%\claude\imouse-candidate-integrated-2\iMouse2.exe` (`a1560ed`), without `--data-dir`. It connected to the release kernel and saved settings. It was closed after 13 s.
- It took no lease and sent no input: C24C stayed at generation 5 and C241 at 1.
- It rewrote `%APPDATA%\iMouse2\settings.json` with identical bytes (hash `72F51CC0…` unchanged; timestamp 19:24:00Z) and its own `data\settings.json`.
- Since then candidates are brought forward by PID, never opened by name.

**Setup for the re-check.**
- **Candidate.** `%TEMP%\claude\imouse-candidate-5\` built from `b0708e3`: `iMouse2.dll` SHA-256 `E5A51FC6204566FA3B48C650FC239A42B158217D8045D2712850173980303AC3`, `iMouse2.exe` `2A0D5CB94AF84226269507C2442BAC3DDAE524DB6E1EED4306B7C2AF79945253`. Self-test 191 and UI test 151 run on this binary.
- **Isolated settings.** Data folder `imouse-candidate-5 data\live` with `{"address":"http://localhost:9923","theme":"light","trackPointer":false}`. On connect the proxy log shows no commands, and both phones stayed unowned.
- **Rack.** The installed console (PID 3516, release path verified) was closed normally at 15:32:51. C24C identity was checked (XR C24C, board C24C, uid C24CBFBD, receiver 36456). Both phones were unowned, and `tools/phone-frame-capture` was self-checked read-only on C24C (6 of 6 frames).

**Check A: lost tap, then first-click Resume.** Frames every 1 s for 100 s (100 of 100).
- `/mouse/click` code 0 in 1,843 ms, answer withheld. Panel paused at about 10 s.
- The paused tap sent nothing, and the lease expired.
- The only change on the phone was the iOS edit menu appearing at 15:34:39, after the tap. Text unchanged.

**Check B: lost drag, full-hold capture.** Frames every 0.5 s for 90 s (177 of 177).

| Time (EDT) | Kernel / console | Phone (frames) |
|---|---|---|
| 15:36:28.43 | — | Note at rest, edit menu showing |
| 15:36:28.51 | `/mouse/down` code 0 (123 ms): the button is down | — |
| 15:36:28.71 | Drag `/mouse/move` completed by the kernel (code 0, 200 ms); **answer withheld** | — |
| 15:36:28.93 → 36.54 | Console waiting; panel still reads ready | Menu dismissed; note pulled about 50 px down (overscroll, scroll indicator shown) in every frame of the hold |
| 15:36:36.51 | Console timeout; **no `/mouse/up` sent** | — |
| 15:36:36.517 | `/input/release` code 0 (4.5 ms). Log: `…the kernel confirmed it 9 ms after the failure` | — |
| 15:36:37.06 | — | Content back at rest |
| 15:36:37.58 | — | Edit menu shown again |
| 15:37:02.61 | Resume (first click): status 0, resume 0 | No change |

- **Held about 8.0 s,** from the down at 28.51 to the kernel release at 36.52.
- **The console did not send `/mouse/up`.** On its own that proves nothing about the phone. What shows the touch ending is the frames: iOS holds an overscroll only while a touch is down, and the note stayed pulled down until the kernel's release and was back at rest in the next frame.
- **Effects:** the edit menu was dismissed and then shown again. There was a temporary overscroll; no text changed, nothing was selected, and there was no lasting scroll (the first and last frames differ only in the blinking caret).
- **Observation:** during the 8 s hold the panel still reads `Input ready`, because the console cannot know the answer is lost until its timeout.

**Restore.**
- The candidate was closed at 15:38:35 and the proxy stopped. The installed console was relaunched from the release folder (PID 12328) and not interacted with.
- Afterwards both phones were unowned (C24C generation 7, C241 generation 1), and kernel 28776 and receivers 36456 and 13616 were running.
- Operator settings hash unchanged; the timestamp is the installed console's own save at 19:38:36Z.

**Evidence.** `iMouseXP-2.0-evidence-archive/20260927-live-b0708e3/` holds:
- the proxy log, both frame captures with `frames.tsv`, the click probes, and the contact sheet of the hold;
- the capture self-checks;
- the mock-kernel reproduction log;
- the check-3 screenshots from `b994de9`.

`SHA256SUMS.txt` lists 328 files; the copied files were verified against their sources.

## Live validation, 27 Sep 2026, build `b994de9` (C24C only; all four checks run)

**Setup.**
- **Candidate.** `%TEMP%\claude\imouse-candidate-integrated-3\` built from `b994de9`: `iMouse2.dll` SHA-256 `12059878E6C3C93DFC33542B0ED15F460B4BA43D92EE2EFD5685F8B563E13455`. Offline suites on this build: kernel 79, `--self-test` 191, `--ui-test` 147, harness all passed.
- **Launch.** `Start-iMouse2Candidate.ps1 -ViaProxy`, data folder `%TEMP%\claude\imouse-candidate-integrated-3 data\live` with its own `settings.json`. The console connected through the proxy (`:9923`) to the release kernel (PID 28776). Receivers 36456 and 13616 kept running throughout.
- **Preflight.** C24C was first owned by another controller, so testing waited. With the user's go-ahead, the installed console (PID 25092, path verified under `release\iMouse2-two-phone-candidate`) was closed normally at 15:01:05. Both phones then read not owned, generation 1.
- **Hover tracking** was on at launch. It acquired C24C and sent 2 `/mouse/move` before it was switched off. That moved the pointer only.
- No input was sent to C241. It stayed at generation 1 from 15:01 until after the installed console was restored.

**Check 1: 100-character typing with 12-character chunks.** `Revisedbuild 27 Sep: twelve character chunks type this one hundred character line #9, all OK!!!!!!!`, sent with the Send text button.

| Run | Field | Kernel (9 chunks, all code 0) | Phone |
|---|---|---|---|
| 1a | Fresh note | 1772, 1822, 1778, 1810, 1838, 1777, 1805, 1801, 582 ms | First space lost (`Revisedbuild`); the rest exact |
| 1b | Same note, new line (Enter 145 ms) | 1789, 1838, 1780, 1813, 1828, 1777, 1794, 1800, 580 ms | Exact, all 100 characters |

The slowest chunk was 1,838 ms, about 22% of the 8 s deadline. **Result: chunking verified in a previously used field; fresh-field exact typing stays open.**

**Check 2: first-click Stop during a long send (200 characters).** Stop input was clicked once, about 7.5 s in.
- Kernel: chunks 1–4 took 1807, 1799, 1798 and 1827 ms (code 0). Chunk 5 got code 33 after 622 ms. `/input/stop` answered 0 in 6.2 ms.
- Phone: `Stop check 27 Sep, revised build: one click on Stop`, that is 48 confirmed characters plus 3 of chunk 5. Two frames 5 s apart were identical.
- Resume input: `/input/status` then `/input/resume`, both 0.
- **Result: pass.**

**Check 3: lost tap answer.** The proxy withheld the answer to one `/mouse/click` on blank note space.
- The kernel ran the click (code 0, 1,760 ms).
- The panel showed `Input paused: request timed out…` about 8 s after the click was sent. A second tap while paused sent nothing.
- The paused client stopped renewing, so the kernel lease expired and C24C was stopped (generation 4).
- Phone: the tap on the caret line opened the iOS edit menu (Paste | Select | Select All | AutoFill). Nothing was replayed.
- Resume input: `/input/release` 409 (lease already closed by the kernel), `/input/status` 0, `/input/resume` 0.
- **Observation.** Three mouse clicks on Resume input did not reach its handler; UI Automation Invoke did. In check 4, one mouse click on Resume worked. This is not reproduced and not explained.
- A later recovery tap acquired a new lease and ran with code 0 (1,685 ms).
- **Result: pass.**

**Check 4: lost drag answer.**
- **Two earlier attempts** (15:09:11 and 15:09:58) pressed, held and moved with the desktop-automation tool. The console logged them as `Long press (1779 ms)` and `Long press (2898 ms)`. Each sent move, down and up (all code 0) and no drag moves, so nothing was withheld. Each long press on the note left the iOS edit menu showing.
- **The measured attempt** was one drag from blank note space at 15:12:03, with the answer to the first drag move withheld.

| Time (EDT) | Event |
|---|---|
| 15:12:04.335 → .485 | Setup `/mouse/move`, code 0 (150 ms) |
| 15:12:04.487 → .613 | `/mouse/down`, code 0 (126 ms): the button is down |
| 15:12:04.613 → .814 | Drag `/mouse/move`: the kernel completed it (code 0, 201 ms); **answer withheld** |
| ≈15:12:12.613 | Console timeout, 8 s after the move was sent |
| 15:12:12.621 | `/input/release` code 0 (4.6 ms). Log: `Held button released after the request timed out on 86:1D:4A:04:2F:F6: the kernel confirmed it 8 ms after the failure.` |

- **The button was held about 8.0 s**, from the down at 04.61 to the release at 12.62. Cleanup finished 8 ms after timeout detection. `/mouse/up` was not sent, as designed under ownership.
- Panel: `Input paused: request timed out; held button released (confirmed). Check the phone, then choose Resume input.`
- Resume input (mouse click): `/input/status` 0 and `/input/resume` 0 at 15:12:36. Panel `Input ready · previous action discarded`.
- **Phone.** A frame at 15:12:58 compared with one at 15:10:14: the note text is unchanged, nothing is selected, and the content and edit menu sit about 22 px lower. No held touch remained. The planned frame-by-frame burst for this attempt did not start (a quoting error in the launch), so the phone was not observed during the hold.
- **Result: pass for kernel acknowledgement and cleanup timing.** The visible effect during the hold was not captured.

**Restore.**
- The candidate was closed normally at about 15:13 and the proxy stopped. The installed console was relaunched from `release\iMouse2-two-phone-candidate` (PID 3516) and not interacted with.
- Afterwards both phones read not owned (C24C generation 5, C241 generation 1). Kernel 28776 and receivers 36456 and 13616 were running.
- The operator settings hash (`72F51CC0…`) is unchanged. Its timestamp moved to 19:13:14Z, when the installed console started and saved its own settings.

**Evidence.** `iMouseXP-2.0-evidence-archive/20260927-live-b994de9/` next to the repository: the proxy log, phone captures, capture scripts and burst timing files, and `SHA256SUMS.txt` (58 files, verified against the source). The test note stays on C24C.

## Live validation, 26 Sep 2026, build `a1560ed`, 32-character chunks (historical; checks 1–2 only)

**Setup.**
- **Candidate.** `%TEMP%\claude\imouse-candidate-integrated-2\` built from `a1560ed`: `iMouse2.dll` SHA-256 `BEB949B9A0EB4522A6355608855BF0C890DD5B6F7ADE2602A58EFA5CDEBA9A85`, `iMouse2.exe` `E25A661221D769C6CA0A741F1FFB647F3538BF8A92509821E6CC26F114748590`.
- **Launch.** `tools/candidate-launcher/Start-iMouse2Candidate.ps1 -ViaProxy`, with data folder `%TEMP%\claude\imouse-candidate-integrated-2 data\live`, which holds its own `settings.json`. The console connected through the proxy (`http://localhost:9923`) to the release kernel. No settings mirror was written beside the exe.
- **Preflight at 03:03:06.**
  - Kernel PID 34796 from `release\iMouse2-kernel-two-phone`; receivers 9760 (C24C) and 16500 (C241); installed console 10696.
  - C24C `86:1D:4A:04:2F:F6` "XR C24C", board C24C, uid `C24CBFBD`: not owned, not active, generation 68.
  - The jovial session confirmed exclusivity in writing: no input, lease, console or kernel calls until release.
- **Unplanned hover move.** Hover tracking ("Move phone pointer with mouse") was on by default and sent one `/mouse/move` at 03:03:48, before it was switched off. That moved the pointer only; nothing was tapped.

**Environment.**
- Host CPU was 85–100% during the checks.
- The load came from several headless Chrome (Puppeteer) processes of about one core each, plus Windows `TextInputHost`. None belonged to this work.

**Check 1: 100-character typing.** `Integrated check 26 Sep: chunked Send text types one hundred characters in four chunks #7, all OK!!!`, sent with the Send text button in a new note.

| Run | Field | Kernel | Phone |
|---|---|---|---|
| 1a | Fresh note | 4 chunks, code 0: 4.76, 5.69, 5.05, 0.58 s | `Integratedcheck 26 Sep: …` First space lost (the open issue); the rest exact |
| 1b | Same note, new line | Enter 156 ms; chunk 1 ran 8,021 ms and got code 33 (the kernel's own 8 s deadline; C24C stopped, generation 69) | 30 of 32 characters typed (`Integrated check 26 Sep: chunk`), then nothing. The console showed `Input paused: request timed out…` and logged `Send text timed out: 0 of 100 characters confirmed. Chunk 1 of 4 may be partly typed and was not retried. Chunks 2–4 were not sent.` Nothing was replayed |
| — | Resume input (operator) | `/input/release` 409 (lease already closed by the kernel), `/input/status`, `/input/resume` 0 | Panel `Input ready · previous actions discarded` |
| 1c | Same note, new line | Enter 350 ms; 4 chunks, code 0: 5.07, 4.93, 5.22, 0.59 s | Exact, all 100 characters (checked on a crop of the phone's own 500×1080 frame) |

**Result:**
- **Chunking verified** in a previously used note.
- **Fresh-field exact typing stays unresolved.**
- **Side effect.** Pressing Enter in 1c accepted iOS's pending inline prediction on line 1b, which became `…chunked Send text` with `ed Send text` never sent. Read typed text before pressing Enter or leaving a field.
- **Load finding (1b).** The 32-character chunk normally takes about 5 s. Under this host load one exceeded 8 s, so the chunk-size margin is not enough under sustained CPU load.

**Check 2: first-click Stop during a long send.** 200 characters were sent into the same note. Stop input was clicked once about 7.5 s in, with the Controls drawer open.
- Kernel: Enter 156 ms (code 0). Chunk 1 in 4.95 s (code 0). Chunk 2 was cut after 2.95 s (code 33). `/input/stop` answered 0 in 11.7 ms. C24C was then stopped, generation 71.
- Phone: `Stop check 26 Sep: this long send is cut by one c`, which is chunk 1 plus 17 characters of chunk 2. Frames 5 s apart showed no further typing, and nothing more was sent.
- Panel: `Input stopped · choose Resume input to continue`.
- **Result: the first click on Stop took effect, the send stopped within the chunk in flight, and nothing was replayed.**

**Checks 3 and 4:** not run (see Status).

**Evidence.**
- In this folder: `live-20260926/settings.json` (the candidate's own) and `live-20260926/phone-captures.sha256`.
- The proxy log (`proxy-log.jsonl`: every command, with the kernel's answer code and duration) is raw JSONL, which `.gitignore` excludes. It is in the archive below and listed in its `SHA256SUMS.txt`.
- The phone captures are PNGs, which `.gitignore` excludes. They are archived at `iMouseXP-2.0-evidence-archive/20260926-live-candidate/phone/` next to the repository, with `SHA256SUMS.txt`.
- The test note stays on C24C, titled `Integratedcheck 26 Sep: …`. It was not deleted.

## Live validation plan

These checks run on C24C only, through this candidate's console (`%TEMP%\claude\imouse-candidate-integrated-1\iMouse2.exe`). Start only when the jovial session has released C24C and the user has approved desktop control. Before any live action:
1. Resolve process paths and PIDs fresh.
2. Confirm C24C is `86:1D:4A:04:2F:F6` / board C24C / uid `C24CBFBD`.
3. Read `GET /api/input/status` and confirm C24C is not owned and not active.
4. Leave C241 (`FE:A9:BC:D7:A0:44`) and every other phone untouched.

The running kernel already serves this candidate (protocol 1, `/input/release`), so no kernel restart or replacement is needed.

| Check | How | Pass |
|---|---|---|
| Exact 100-character typing | Send text into a note that has already lost its first space, the only context where exact text was seen. Record a fresh-note run as is | Exact text, or a recorded mismatch. The missing-space issue stays open either way |
| First-click Stop during text entry | Start 200 characters with the drawer open and click Stop input once | Typing stops within one chunk; the panel reads stopped; Resume is required |
| Visible timeout and explicit Resume | A loopback proxy between this console and the kernel loses the answer to one tap on a blank area (the kernel still runs it) | The panel shows the timeout; nothing is sent until Resume; Resume recovers |
| Safe drag cleanup | The same proxy loses the answer to one move of a short drag in blank space inside an open note | The log shows a confirmed release about 8 s after the move; the phone shows no held touch afterwards |

**The proxy** is `tools/input-fault-proxy` (built as `%TEMP%\claude\imouse-candidate-integrated-1\proxy\InputFaultProxy.exe`). It is test tooling next to the release; the kernel and phone configuration are unchanged.
- It forwards everything to the kernel unchanged.
- `GET /proxy/lose?fun=<command>&skip=N` lets the (N+1)th matching command reach the kernel and withholds the answer once. It logs every command with the kernel's actual answer code.
- Only `/mouse/*`, `/key/sendkey` and `/input/status` can be armed; ownership calls are refused.
- Offline check against the running kernel, read-only requests only, 26 Sep 00:21: the device list and a C24C frame were identical through the proxy. Armed `/input/status` reached the kernel (code 0) and the client got no answer within 8 s. The next request was answered. Arming `/input/release` was refused.

Pointing the console at the proxy (`http://localhost:9923`) makes it save that address in the shared `%APPDATA%\iMouse2\settings.json`. Back the file up before the test, reconnect to `http://127.0.0.1:9913` afterwards, and verify the file is byte-identical to the backup.

## Requirements kept open

- **Failed / open: the first space typed into a fresh text field goes missing; cause unresolved.** It needs a separate, focused investigation. Neither the console nor this candidate adds or re-sends a space to hide it, and none should without a known cause.
  - Jovial's record: 21 of 21 sends lost that space, and it was 9 of 9 alike with Show Predictions Inline on, off and restored on.
  - Jovial's 26 Sep diagnostic, reported to this session and not re-verified here: "Hi", then a lone space, then "there" as three Send text commands, all kernel code 0.
    - Two fresh Notes notes and two fresh Settings search fields all read "Hithere".
    - The cursor did not move on the lone space.
    - Once it brought up the text-edit menu instead, which suggests Full Keyboard Access "Activate" on the focused field.
  - So the loss is not specific to Notes. Full Keyboard Access is the leading hypothesis, but it is untested because that needs a settings change and authorization.
  - Nothing here attributes a cause.
  - A fresh-field result such as "Chunkcheck…" is this open issue, not a regression.
- **Live validation through the actual candidate console** (above).
