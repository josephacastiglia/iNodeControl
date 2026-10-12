# iMouse 2.0: return handoff to the Omp/Orca session, 1 Oct 2026

Written about 19:00 local on 1 Oct 2026 by the Claude Code session that worked after [ACCOUNT-HANDOFF.md](ACCOUNT-HANDOFF.md) (28 Sep). Development returns to the Omp/Orca session. **This session has stopped and none of its tools are running.**

Nothing was merged, promoted or deployed. No product source changed. No receiver or kernel was restarted by this session (the PC restart is described in §1). Repository: https://github.com/josephacastiglia/iNodeControl.

## 1. Rack state at handoff (checked 18:58–18:59)

- **PC:** a Windows power-off was started from the Start menu at 04:13:52 on 1 Oct, and the PC booted at 17:34:55. At 17:56:33 the operator's startup ("iMouse 2.0 - Independent AirPlay") started:
  - kernel PID 16112, `release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe`, with exactly the arguments in ACCOUNT-HANDOFF §3 (no `--precise-delay`);
  - receivers PID 3252 (`iMouse2-C24C`) and PID 10960 (`iMouse2-C241`), both live;
  - the installed console, PID 15848.
- **Leases:** both phones unowned and not stopped, generation 0.
- **C24C:** Home screen (read-only frame `R1-handoff-state.png`, 18:59:09). **C241:** never addressed or captured by this session.
- **Test tools from this session:** none running.
  - Candidate-5 and its InputFaultProxy ended with the 04:13 shutdown. Before that, candidate-5 released C24C normally: its last proxy entry is `/input/release` at 04:13:07, code 0.
  - A background transcript search was stopped.
  - Other processes on the PC (MCP servers, `tools/agent_ops/save_run.py`) were not started by this session and were left alone.

## 2. Outstanding: restoration, settings, leases

| Item | State | Action needed |
|---|---|---|
| C24C Full Keyboard Access | **Original: On** (frame 01:07:22, `01-fka-original.png`). The operator switched it Off for the check (01:19:52, `02-fka-off.png`), then back On by hand at about 03:45 and checked it on the phone | **Not frame-verified.** With the operator present, show Settings › Accessibility › Keyboards › Full Keyboard Access and capture it. Expected: On, Auto-Hide 1s, Increase Size Off, High Contrast Off, Color Default |
| Other phone settings | None changed by this session | None |
| Leases and stopped inputs | None | None |
| Installed console | Running from the verified path (§5), holding no lease | None. Hover tracking is on, so keep the mouse off its phone picture during tests |
| Candidate-5, proxy | Not running | None |
| Test notes on C24C (1 Oct) | Three `Hi there` notes; the 100-character note, with one invisible character appended by Home; Settings search Recents may show "Hi there". Older notes as in ACCOUNT-HANDOFF | Leave, or the operator deletes them by hand |

## 3. What changed since ACCOUNT-HANDOFF.md

**Product changes: none.** Candidate-5 (built from `b0708e3`) is unchanged.

| Branch | Commit (full) | Kind | What | Pushed |
|---|---|---|---|---|
| `claude/track-gate-evidence` | `429c65981f2ac69dea676a935ad2542be50c0d31` | Repo config + evidence | Commits the content of `handoff/main-uncommitted-20260925` again, on `main`, with run-record `.jsonl` files | Yes (before this handoff) |
| | `dbef7014f23577d1b2c5a6283d77543b8b67e31e` | Repo config | `.jsonl` tracking limited to an explicit allowlist (only `analysis/gate4-1000-tap/results.jsonl`); `.gitattributes`: `analysis/**/*.jsonl -text` (byte-exact) | Yes |
| | `54d3a4622aee6a868035630e0145e034d5007608` | Documentation | Gate 4 recorded as passed within its scope, and what the written criterion still requires | Yes |
| | `9afdd04a39346a5045d24659d969acb4025ef7d7` | Documentation | Gate 4: harness provenance gap; path note (later corrected) | In this handoff |
| | `900f5b409bbe47e519914a17c53a3d645fe4cee0` | Documentation | Gate 4: the corner-reset path is inferred, kept separate from what was measured | In this handoff |
| `claude/gate4-harness-v2` | `4876908ef435814a6b37056e27031f2edd406434` | Test tool | `tools/gate4_v2/`: Gate 4 suite v2, mock kernel, 14 offline tests | In this handoff (new branch) |
| | `96680a20a9034b4df5fec27ec84f9c1d4fc3252c` | Test tool | Harness hash independent of line endings | In this handoff |
| | `2c98f44823afa018b3d62897f438629e0755135d` | Documentation | v2 README: the v1 path is inferred, not recorded | In this handoff |
| `claude/input-timeout-integration` | `e3a136d3abcc98a69c78c01e9572055908914d9f` | Documentation | `KEYBOARD-SPEC.md`: FKA evidence reconciled (C24C's 16 Sep frame shows a ring; 1 Oct FKA Off results and their limits) | In this handoff |
| | `dfc9ef3af0cb6c336645ce7f12617ac0198b2364` | Proposed experiment + test tool | `analysis/fka-typing-mode-20261001/`: A/B plan and `fka_activate_trial.py` (mock self-check only; **not run**) | In this handoff |
| | the commit adding this file | Documentation | This handoff | In this handoff |

**Evidence outside Git:** `iMouseXP-2.0-evidence-archive\20261001-fka-off-compat-b0708e3\` (§10).

**Incomplete work, labelled rather than finished:**
- the Gate 5 FKA-Off check (partial: §6);
- Gate 4 v2 (offline only; folding it into the v1 file path is recommended but not done);
- the six-note A/B (planned, not run).

## 4. Integrated versus separate, and dependency order

```
main  ee445d7
├── claude/input-timeout-integration   product line (text chunking, input-timeout recovery, settings isolation;
│                                       contains claude/jovial-yonath-f044e9 a6e4a9b and claude/funny-margulis-86e51b 43b43f7)
│                                       + 27 Sep–1 Oct FKA/keyboard documentation + this handoff
├── handoff/main-uncommitted-20260925  ba733c2  snapshot of Orca's uncommitted 24–25 Sep work (unchanged)
│   └── claude/gate4-harness-v2         Gate 4 v2 test tool
└── claude/track-gate-evidence          the same 12 files as ba733c2 (identical content, committed separately)
                                        + allowlisted Gate 4 results.jsonl + the Gate 4 record
```

- **Not integrated with each other.** The integration branch has none of Orca's Gate 2/Gate 4 work or the gate records. The gate-record line has none of the product changes or the FKA documentation. The integration branch does not touch `FINISH-CRITERIA.md`, `GAPS.md`, `.gitignore` or `.gitattributes`, so the two lines are independent.
- **Order if combined later** (the user's decision; nothing was merged):
  1. Use `claude/track-gate-evidence` in place of `handoff/main-uncommitted-20260925`. It carries the same files plus the reviewed records.
  2. Rebase `claude/gate4-harness-v2` onto it, then fold `tools/gate4_v2/` into `tools/gate4_1000_tap_suite.py` (the evidence branch's FINISH-CRITERIA already names the v2 branch).
  3. `claude/input-timeout-integration` can go before or after; it does not depend on 1–2.
- `claude/vigorous-nightingale-2cc961` equals `main`. Its worktree is detached at `071c3eb` and still holds the candidate launcher used on 1 Oct.
- `backup/input-timeout-integration-pre-redaction` stays local and must not be pushed (ACCOUNT-HANDOFF §9).

## 5. Installed release versus candidates (SHA-256 verified 1 Oct 18:58)

| Role | Path | SHA-256 |
|---|---|---|
| **Installed kernel** | `release\iMouse2-kernel-two-phone\iMouse2.Kernel.dll` | `BD1A68168E9270F029336CF8E13FF85E9B15FD67951EF545D1E973C2BFE634FC` |
| | `…\iMouse2.Kernel.exe` | `A2C5B90636854F20487F9760499869838C3F674809D978668002D220B189D5AC` |
| **Installed console** | `release\iMouse2-two-phone-candidate\iMouse2.dll` | `CC8049B444998B1D95E8D8AEC41FB1DFE3552A9D4AA58E92F64D3289A5A038D2` |
| | `…\iMouse2.exe` | `46B9732947BA21ECFBEB57EFE2786B83DEA1FF4DDF3C456F1F85EFCF5F7AEAD5` |
| Operator settings | `%APPDATA%\iMouse2\settings.json` | `72F51CC0BEE805F722D73BC024CAD771B19A68E2E7C04D9D47F8E9E4A8A5E5BA` |
| Receiver | `tools\airplay\uxplay\build-imouse\uxplay.exe` | `4C1A24F35DE00D2C3A8D50A4B0BCFB06A9F5C16BD185810EC54466AC090D2208` |
| Candidate-5 console (`b0708e3`, not deployed) | `%TEMP%\claude\imouse-candidate-5\iMouse2.dll` | `E5A51FC6204566FA3B48C650FC239A42B158217D8045D2712850173980303AC3` |
| | `…\iMouse2.exe` | `2A0D5CB94AF84226269507C2442BAC3DDAE524DB6E1EED4306B7C2AF79945253` |
| Test kernel `--home-sequence` (test only) | `%TEMP%\claude\imouse-test-kernel-home\iMouse2.Kernel.exe` | `162993B5504F00D7282866BC91E9BE4B3BCCA4A990DE41A37AD51E82302A45AF` |
| | `…\iMouse2.Kernel.dll` | `83BBF441C5A6516C4B0C8EAAA5D998835F31ACDC0DE14CAD87D8D688C132843B` |

The installed kernel, console and settings hashes match the values recorded in ACCOUNT-HANDOFF §3. The release provenance gap noted there is unchanged.

## 6. Tests completed since ACCOUNT-HANDOFF, and their limits

**Gate 5 FKA-Off compatibility, C24C only, 1 Oct 01:07–02:40. Partial.**
- Setup: candidate-5 through the console's real Send text and buttons; every command went through InputFaultProxy; C241 was never leased or addressed.

| Control | Result with FKA Off |
|---|---|
| `Hi there`, 3 fresh Notes notes + 3 fresh Settings search fields | **6/6 exact** |
| 100 characters (letters, digits, spaces, punctuation) | Every visible character exact; 9 chunks of 12 (last 4), all code 0, 13.3 s. One space sits at a line wrap, where it cannot be seen |
| Home with a note open | Reached Home but **appended an invisible character** to the note (consistent with Home's Tab). Stop rule applied after 1 of 3 |
| App switcher | **0/3**, although every command returned code 0 |
| Control Centre | 1/1 opened |
| Not run | Control Centre ×2, one safe tap, one scroll swipe, two Home trials |

- **Limits:** no FKA On control in the same session. Visible text comes only from frames. Code 0 means the HID writes completed, not that text was inserted. This does not sign off Gate 5.

**Offline only (no phone):**
- Gate 4 v2: 14 tests against its mock kernel.
- `fka_activate_trial.py --self-check`: 6 checks. It fails, as intended, under three mutations (an added lone space, a command to C241, a missing release).
- Re-reading the Gate 4 results: every row targets (250, 900) and times Home as its last setup step. The corner reset before each click is **inferred** from kernel source, not recorded.
- 27 Sep frames: no Typing Mode banner 4 s after the send. Caret presence is blink-dependent and not informative.

## 7. Unresolved defects

1. **First space lost in a fresh field with FKA On.** Lost 3/3 and kept 2/2 with FKA Off in the 27 Sep same-day comparison; kept 6/6 with FKA Off on 1 Oct. The mechanism is unproven. Exact fresh-field typing with FKA On remains a Gate 5 blocker for candidate-5.
2. **Home types a Tab into a focused text field** (27 Sep with FKA On; 1 Oct with FKA Off). The candidate fix, `--home-sequence command-h` on the test kernel, is untested and needs receiver restarts.
3. **App switcher did nothing 0/3 with FKA Off.** A dependency on FKA is suggested by a historical comparison only (it worked 16 Sep, when a focus ring indicates FKA On), not by a controlled one.
4. **Open items from the earlier Orca records:**
   - Gate 6: C24C 4/5 on 22 Sep, `accepted: false`.
   - Gate 10: resumed-block interactions 0/64 (every acquire returned 409), the uxplay memory slope, and the prior Phone 5 stall.
   - Gate 11: five-phone group Home missed.
5. **Carried over from ACCOUNT-HANDOFF:** receiver rediscovery pending natural recurrence; release provenance gap.

## 8. Orca evidence reconciliation

**Where the claim came from.** The Omp session "Continue Finish Criteria Roadmap" (16–25 Sep; Gemini 3.8 Flash orchestrating, `openai-codex/gpt-6-sol` as the working agent at the end; several Gate 5/6 result files name Grok 4.7, run in separate Orca-launched sessions) closed on 25 Sep 05:55 UTC with a chat summary of 11 of 12 gates passed. **Orca's own files do not support it.** In its preserved commit `ba733c2`:
- `GAPS.md` marks Gates 1–2 passed and Gates 3–12 Partial;
- `FINISH-CRITERIA.md` marks Gates 1, 2 and 4 passed, and its sign-off row reads "Gates 1–12 passed … Not signed off".

No gate is signed off. Do not repeat the 11/12 figure.

**Successful prior work, kept within its demonstrated scope:**

| Gate | Prior result (files) | Scope it shows | Still required by the written criterion |
|---|---|---|---|
| 1 | `analysis/independence-audit/cold-boot-evidence.json`, `pass: true` (24 Sep) | Cold boot with no vendor runtime | Pass field checked here; the run was not re-audited |
| 2 | `analysis/gate2-single-app/gate2-evidence.json`, `pass: true` | One app on the existing shortcut | As for Gate 1 |
| 4 | `analysis/gate4-1000-tap/` (`results.jsonl`, `status.json`, `ISOLATION-AUDIT.md`): 1,000/1,000, p95 2,419 ms, 0 stuck, 0 cross-phone after the audit | **Passed within scope:** two phones, kernel API, one target | Varied targets and distances, taps after interruption recovery, the other 17 pairs, recovery recorded in the run. The v1 harness was edited after the run, so the version that ran is not preserved |
| 5 | `analysis/gate5-everyday-controls-20260916/` (`run_controls.py`, `predeclared-cases.json`): Control Centre, App Switcher and swipes on both phones; C24C Spotlight typing | Short API-driven controls | Through the actual console: long press, drag, vertical swipe, exact Notes text with Enter, keyboard settings, unsupported buttons reporting failure; plus defects 1–3 |
| 6 | `analysis/gate6-release-validation-20260916/run_gate6.py` (dispatch 1,820–1,844 ms; C24C 4/5, `accepted: false`); `pointer-reliability-20260915/gate6-7ms-*` (9/9 per phone) | API dispatch time (the HTTP elapsed of `/mouse/click`) | Console click to first correct visible response, ≥100 per category, median/p95, misses kept, under workload |
| 7 | `analysis/gate7-video-accounting/report.json` | Kernel-store frame sampling, 5 phones | The console's present path |
| 8, 9, 11, 12 | as listed in `GAPS.md` | 2- and 4-phone groups; crash detect and relaunch; 5 live phones and a 19-slot schema; diagnostics bundle | As listed in `GAPS.md` |
| 10 | `analysis/gate10-endurance-20260916/` | **8.05 h of duration** across two kernels | Not an 8-hour pass under the written bullets: 0/64 interactions, a 1.93 h Phone 5 freeze, memory +90 MB/h; plus the 24 h run |

**Gate 6, before any new work.** Extend `run_gate6.py`; do not write a parallel harness.
1. Start timing at the console action. Console buttons can be invoked through UIA. Taps on the phone picture need real mouse input or a console test hook; that is the user's choice.
2. Take command completion from the proxy log.
3. Replace the fixed 0.8 s single frame with the poll loop in `tools/measure_display_latency.py` (`first_visible_ms`, `settled_ms`), and add a correctness check.
4. Account for console display delay, either from PrintWindow captures or as a separately reported figure (15 Sep: p50 38 ms, p95 70 ms).
5. Take at least 100 observations per category, with misses kept and the second phone streaming.

## 9. Missing-space investigation and FKA observations

**FKA observations, newest first:**
- **1 Oct 18:59:** state unknown from frames (Home screen only). The operator reported it back **On** at ~03:45.
- **1 Oct 01:07:** **On**, frame-verified (Auto-Hide 1s, Increase Size Off, High Contrast Off, Color Default; "To activate: Space"). Off from 01:19:52 for the check.
- **27 Sep 21:52:** On, frame-verified.
- **16 Sep:** inferred **On**. C24C's Gate 5 Control Center frame shows a blue ring (262 strongly blue pixels, as on C241; 0 in the 1 Oct FKA Off frame). This contradicts the older "no FKA ring" notes in `KEYBOARD-SPEC.md` (corrected in `e3a136d`) and in `analysis/c241-typing-diagnostic/findings.json` (left as the 22 Sep record).
- **14 Sep:** **no record.** The `A B Test 123!` note that kept its first space says nothing about FKA.

**Already settled by records:**
- A preceding letter, `Enter`, and going Back and composing again inside Notes all still lose the space.
- Re-focusing the same Settings field kept it.
- Once a field has lost its first space, later spaces are kept.

So the state resets per new text element, consistent with FKA's Activate (Space) hypothesis, which remains unproven.

**Six-note A/B comparison: PENDING. It has not run.** The plan and tool are in [`analysis/fka-typing-mode-20261001/`](analysis/fka-typing-mode-20261001/README.md).
- Design: C24C, FKA On, fresh notes made as on 27 Sep. Both arms send the same `Hi there`; arm B adds one pointer click inside the empty note before sending. Order A B B A A B. No dummy space, no key-mapping change, no setting change.
- Readout:

| Arm A | Arm B | Reading |
|---|---|---|
| lost | kept | The click enters the space-typing state: a candidate route, still needing a Gate 5 test and approval |
| lost | lost | A click is not the entry. Next: read FKA's Commands page (view only) |
| kept | either | The control failed; re-establish the baseline first |

## 10. Next concrete task

A coordinated window with the operator, C24C only, about 15 minutes:
1. Frame-verify FKA On, and optionally read its Commands page.
2. Run the six-note A/B with `fka_activate_trial.py` (preflight refuses if any phone is held).

Then extend `run_gate6.py` as in §8. Pending decisions for the user:
- folding Gate 4 v2 into the v1 file path;
- how the Gate 6 harness clicks the phone picture (real mouse input or a test hook);
- a receiver-restart window for testing the Home Tab fix.

## 11. Evidence and backup locations

| What | Where | In Git? |
|---|---|---|
| 1 Oct FKA-Off check: frames, `run.txt`, `README.md`, `APPSWITCH-ANALYSIS.md`, `FKA-HISTORY.md`, the proxy log snapshot and `proxy-log-final.jsonl`, session scripts | `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261001-fka-off-compat-b0708e3\` (63 files, `SHA256SUMS.txt`) | No. **Not in the 28 Sep backup** |
| Earlier evidence (27 Sep FKA comparison, including `fka_trial.py`) | `…-evidence-archive\20260927-*` | No; in the 28 Sep backup |
| A/B output (created when run) | `…-evidence-archive\20261001-typing-mode-ab\` | Does not exist yet |
| Candidate-5's isolated data folder | `%TEMP%\claude\imouse-candidate-5 data\fka-off\` | No |
| This session's scratch (frames and scripts; everything needed is copied into the archive) | `%TEMP%\claude\C--Users-joey--Desktop-Claude-Code-iMouseXP-2-0\f5164357-f274-45c4-a01b-2c896bc7a95b\scratchpad\` | No; transient |
| 28 Sep full backup | `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-handoff-backup-20260928\` | No; local only |
| Orca's session transcript (the source of the 11/12 summary) | `C:\Users\joey_\.omp\agent\sessions\-Desktop-Claude Code-iMouseXP-2.0\2026-09-16T02-39-16-220Z_01a0a815-30fc-7394-8291-64dd9b7fafd6.jsonl` | No |
| Vendor install and service config, **containing a stored vendor login** | `build\`, `C:\iMouseXP\IMService.json` | No. Never copy, print or upload them |

## 12. Branches and push state after this handoff

| Branch | Tip | Remote |
|---|---|---|
| `claude/input-timeout-integration` | the commit adding this file | pushed in this handoff |
| `claude/track-gate-evidence` | `900f5b409bbe47e519914a17c53a3d645fe4cee0` | pushed in this handoff |
| `claude/gate4-harness-v2` | `2c98f44823afa018b3d62897f438629e0755135d` | pushed in this handoff (new) |
| `handoff/main-uncommitted-20260925` | `ba733c2bc5bb0c1d9cb69c02fb44e3a450f3bd87` | unchanged, already on GitHub |
| `claude/jovial-yonath-f044e9`, `claude/funny-margulis-86e51b` | `a6e4a9b…`, `43b43f7…` | unchanged, already on GitHub |
| `main` | `ee445d70e5f7e3cd9497a9162fc89ba9f6061e4a` | untouched |
| `claude/vigorous-nightingale-2cc961` | equals `main` | local only |
| `backup/input-timeout-integration-pre-redaction` | `544bda1…` | **local only; never push** |

**Worktrees:**
- `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0`: main checkout, `claude/track-gate-evidence`;
- `.claude\worktrees\keyboard-spec-reconcile`: `claude/input-timeout-integration`;
- `.claude\worktrees\gate4-harness-v2`: `claude/gate4-harness-v2`;
- `.claude\worktrees\vigorous-nightingale-2cc961`, `jovial-yonath-f044e9`, `funny-margulis-86e51b`: detached.

All were clean at handoff.
