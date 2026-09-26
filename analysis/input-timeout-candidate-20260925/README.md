# Input timeout and recovery, integrated candidate, 26 Sep 2026

**Status: integrated, not promoted, not deployed. Not yet ready for final acceptance.** It is committed locally on branch `claude/input-timeout-integration`, on top of the text-chunking commit `8d6a285` (not pushed, not merged). Two things block acceptance:

1. **No live validation.** Nothing in this candidate has run on a phone. At 00:1x EDT on 26 Sep the jovial session asked to keep C24C until its own diagnostic is decided with the user. That session also reported that the user declined desktop control for its build. Live checks through this candidate's console need the user's approval for desktop control too.
2. **The missing first space is still unexplained.** It stays open (see Requirements kept open).

The working release was not touched: the kernel (`release/iMouse2-kernel-two-phone`, `http://127.0.0.1:9913/api/`), the AirPlay receivers, the installed console (`release/iMouse2-two-phone-candidate`), the shortcuts and the `release/` folders. PIDs change on restart; resolve them fresh before any live step.

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

## Live validation plan (not run)

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

- **The first space typed into a note goes missing; cause unresolved.**
  - Jovial's record: 21 of 21 sends lost that space, and it was 9 of 9 alike with Show Predictions Inline on, off and restored on.
  - Full Keyboard Access is untested and needs authorization.
  - Nothing here attributes it to Notes or to any setting.
- **Live validation through the actual candidate console** (above).
