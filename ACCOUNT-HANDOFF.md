# iMouse 2.0: account handoff, 28 Sep 2026

Written for continuing this project under a new Claude account. Repository: https://github.com/josephacastiglia/iNodeControl (owner `josephacastiglia`). **Nothing has been merged, promoted or deployed as part of this handoff.**

## 1. State at handoff (28 Sep 2026, 22:30 local)

- **The PC was restarted at 18:12 on 28 Sep.** The kernel, receivers and installed console are **not running**, so phone mirroring is off until the app is opened again with the desktop shortcut **"iMouse 2.0 - Independent AirPlay"** (see §3). Nothing was restarted by the handoff work.
- **Phone settings that need restoring: none.**
  - C24C's Full Keyboard Access (FKA) was switched Off and back On by the operator on 27 Sep. It was verified **On** from a frame at 21:52:24, with Appearance unchanged (Auto-Hide 1s, Increase Size Off, High Contrast Off, Color Default).
  - The FKA-Off compatibility check (§6) was prepared but **not started**, so no setting was changed for it.
- **Left on C24C:** test notes (`Hithere` ×3, `Hi there` ×2, one empty note, plus older test notes listed in the reports). C241 had no input from these sessions.
- **Receiver-discovery work is pending** until the problem recurs naturally. Do not restart receivers to reproduce it.

## 2. Chats, worktrees and branches

The user worked in five chats. All local chats had clean worktrees at handoff; their commits are on the branches below. Commit hashes are abbreviated.

| Chat | Where it worked | Branch | Tip | Unique work |
|---|---|---|---|---|
| Surface timed-out tap/drag/key commands in console (this handoff) | worktree `.claude/worktrees/vigorous-nightingale-2cc961` | `claude/input-timeout-integration` | see `git log` (this file is its latest commit) | Integration line: 41+ commits over `main`. Contains both branches below plus all 27 Sep work |
| Chunk desktop console text under 8s kernel deadline | worktree `jovial-yonath-f044e9` | `claude/jovial-yonath-f044e9` | `a6e4a9b` | None beyond its branch; fully contained in the integration branch |
| Stop UI tests writing the operator's settings | worktree `funny-margulis-86e51b` | `claude/funny-margulis-86e51b` | `43b43f7` | None beyond its branch; fully contained in the integration branch |
| Repository and build familiarization | not a local session (cloud) | `claude/focused-noether-s600e0` (portal + rack agent) | `6b24a96` | Already on GitHub before this handoff; no local copy |
| Artifact familiarization | main checkout, last active 17 Sep | none | — | No uncommitted work attributable to it |

**Uncommitted work found in the main checkout** (not from any of the five chats: `analysis/gate4-1000-tap/status.json` names the agent `openai-codex/gpt-6-sol`, 24–25 Sep):
- Gate 2 single-app evidence;
- a 1,000-tap Gate 4 suite and results summary;
- edits to `FINISH-CRITERIA.md`, `GAPS.md`, `cold-boot-evidence.json` and `tools/force_recast.py`;
- `HANDOFF-SESSION-2026-09-10.md`.

This work was preserved without touching the checkout, as branch **`handoff/main-uncommitted-20260925`** (`ba733c2`, parent `main`). The files remain uncommitted in the main checkout too. **It has not been reviewed or validated.** Its screenshots and `results.jsonl` are git-ignored and are in the local backup (§8).

Other local branches:
- `claude/vigorous-nightingale-2cc961` equals `main` (`ee445d7`).
- `backup/input-timeout-integration-pre-redaction` is **local only; do not push**. See §9.

## 3. Working release (what the operator uses)

- **Shortcut:** "iMouse 2.0 - Independent AirPlay", which runs `Open iMouse 2.0.ps1` in the main checkout. It checks the saved connection, starts the kernel if needed and opens the console. See `OPEN-THIS-APP.md`.
- **Kernel:** `release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe` (`iMouse2.Kernel.dll` SHA-256 `BD1A6816…E634FC`, built 22 Sep). It is launched with:
  - `http://127.0.0.1:9913/api/ --data-dir analysis\two-phone-config --input-pid C24C,C241`;
  - `--receivers analysis\two-phone-config\receivers.json`;
  - `--receiver tools\airplay\uxplay\build-imouse\uxplay.exe --receiver-runtime tools\airplay\msys64\ucrt64`.
  - Legacy movement pacing (no `--precise-delay`).
- **Console:** `release\iMouse2-two-phone-candidate\iMouse2.exe` (`iMouse2.dll` SHA-256 `CC8049B4…A038D2`, built 23 Sep). Despite the folder name, this is the **installed** console. Operator settings are `%APPDATA%\iMouse2\settings.json` (SHA-256 `72F51CC0…E5BA`, address `http://127.0.0.1:9913`).
- **Receivers:** UxPlay 1.74, `iMouse2-C24C` on port 7110 and `iMouse2-C241` on port 7120, each restricted to its phone.
- **Phones:**
  - C24C: "XR C24C", device `86:1D:4A:04:2F:F6`, board uid `C24CBFBD`;
  - C241: "Phone in hand - C241", `FE:A9:BC:D7:A0:44`, `C241BFBD`. **Do not send input to C241 unless told to.**
- **Release provenance gap:** 14 of 16 kernel sources match the repository. `AirplayProcess.cs` and `ReceiverFleet.cs` match no recorded version (PDB hashes in `analysis/home-tab-20260927/README.md`).
- `release/`, `build/` and the MSYS2 toolchain are git-ignored and exist only on this PC (§8).

## 4. Unpromoted candidates (none are deployed)

| Candidate | Source | Binary (local only) | Status |
|---|---|---|---|
| Console with text chunking, input-timeout recovery and settings isolation | `claude/input-timeout-integration` at `b0708e3` | `%TEMP%\claude\imouse-candidate-5\` (`iMouse2.dll` `E5A51FC6…3AC3`, `iMouse2.exe` `2A0D5CB9…5253`) | Long sends, Stop, Resume and timeout reporting pass. Blocked by the fresh-field first-space loss (§5) |
| Test kernel `--home-sequence vendor\|command-h\|command-wake` | integration branch (`068bb68` era) | `%TEMP%\claude\imouse-test-kernel-home\` (exe `162993B5…2A45AF`, dll `83BBF441…32843B`) | Test-only. Home V1 is untested on a phone: running it needs receiver restarts (§5) |
| Earlier console candidates (text chunk, integrated-1..3, candidate-4) | see `analysis/*-candidate-*/` reports | `%TEMP%\claude\imouse-*` | Superseded by candidate-5 |

## 5. Build, test and launch

- **Build a console** into a separate folder, never over `release\`:
  `dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o <folder> --no-incremental`
- **Build a kernel:** `dotnet build src/iMouse.Kernel/<project>.csproj -c Release -o <folder>`.
- **Self-tests:**
  - kernel `iMouse2.Kernel.exe --self-test` (98 pass on the integration branch);
  - console `iMouse2.exe --self-test` and `--ui-test` (mock transport; see `KEYBOARD-SPEC.md` and the candidate reports).
- **Launch a candidate safely:** `tools/candidate-launcher/Start-iMouse2Candidate.ps1 -ConsoleExe <full path> -DataDir <own folder> [-ViaProxy -ProxyExe <InputFaultProxy.exe>] [-CheckOnly]`.
  - Use an isolated settings folder containing `"trackPointer": false`.
  - It never touches `%APPDATA%\iMouse2` or `release\`.
- **Live rack rules (from the user):**
  - resolve PIDs fresh and check `GET /api/input/status` before input, since other controllers, including the installed console, can hold a phone's lease;
  - use one phone at a time, C24C by default;
  - make no receiver or kernel restarts, and change no phone setting, without explicit approval.

## 6. Tests completed and open issues

**Completed and recorded:**
- Text chunking (12-character chunks) and input-timeout recovery: `analysis/text-chunking-candidate-20260925/`, `analysis/input-timeout-candidate-20260925/`.
- **Missing first space:** in an operator-toggled comparison on 27 Sep (C24C, fresh notes, `Hi there`), the space was lost with FKA **On** 3/3 and kept with FKA **Off** 2/2. The comparison stopped at 5 of 6 trials. FKA is implicated under those conditions; the mechanism and fix are not established. See `analysis/fka-space-loss-20260927/README.md` and `KEYBOARD-SPEC.md`.
- **Lower-screen targeting:** closed. The "taps stop at y 783" problem was the desktop-automation cursor, not the kernel or phone. A move-only test reached y 920, 1012 and about 1068. See `analysis/lower-screen-targeting-20260927/`.
- **Console click failures:** closed as unreproduced (`analysis/console-click-investigation-20260927/`). The isolated-VM plan is paused (`analysis/isolated-test-environment-plan-20260927/`).
- **Receiver rediscovery:**
  - A graceful restart did not bring C24C back within 25 minutes.
  - A Lightning replug at the phone was followed by recovery once, with charging and accessory state changed together.
  - Pending until the problem recurs naturally. See `analysis/airplay-discovery-20260927/` and `analysis/accessory-connection-20260927/`.

**Open:**
- Fresh-field exact typing (FKA-related, above).
- Home types a Tab: vendor Home = Tab + Command+H. V1 is ready but needs a window with receiver restarts (`analysis/home-tab-20260927/`).
- Receiver rediscovery on the phones after restarts.
- Unreviewed Gate 2 and Gate 4 work on `handoff/main-uncommitted-20260925`.
- Release gates 1–12 in `FINISH-CRITERIA.md`: none is signed off.

## 7. Next recommended task

**The FKA-Off compatibility check on C24C only.** The user authorized it on 28 Sep; it was prepared and not started. The procedure:
- **Setup:**
  - The operator switches FKA Off and back On by hand, confirming dialogs, and leaves the settings page visible for capture each time.
  - Close the installed console normally, so C24C is released.
  - Run candidate-5 via the launcher with the logging proxy and the prepared isolated folder `%TEMP%\claude\imouse-candidate-5 data\fka-off\` (hover tracking off).
  - Request desktop control of that executable only.
- **Typing** through the real Send text button:
  - `Hi there` in 3 fresh Notes notes and 3 fresh Settings search fields;
  - one 100-character string with spaces, digits and punctuation;
  - the operator does a physical Home gesture between trials.
- **Navigation** through the console buttons:
  - Home ×3, one after 60 s idle and one with an open disposable note (capture its text before and after, and check the Tab);
  - App Switcher ×3 and Control Centre ×3, the operator dismissing each by hand;
  - one safe tap and one scroll swipe.
- **Stop** a command's trials on any unintended action. No replacement gestures and no FKA command remapping.
- **Report** a compatibility matrix, restore FKA On, verify it, and restart the installed console without letting it take control.

**First, after the restart:** open the app with the shortcut and have the operator recast both phones.

## 8. What GitHub contains, and what stays local

**On GitHub** (after this handoff's pushes):
- `main` (`ee445d7`);
- `claude/focused-noether-s600e0` (portal and rack agent);
- `claude/input-timeout-integration`;
- `claude/jovial-yonath-f044e9`;
- `claude/funny-margulis-86e51b`;
- `handoff/main-uncommitted-20260925`.

It holds source, reports, Markdown and JSON evidence, and scripts. Screenshots, BMP/PNG/JPG frames, `.jsonl` logs, binaries and toolchains are excluded by `.gitignore`.

**Local only, on this PC:**

| What | Location | Backed up in `iMouseXP-2.0-handoff-backup-20260928`? |
|---|---|---|
| Git-ignored evidence (frames, captures, jsonl, logs) in the main checkout, including the Gate 4 shots and `results.jsonl` | `analysis/**` | Yes: `main-checkout-ignored/` |
| Git-ignored evidence in worktrees (inline-prediction frames; proxy log) | `jovial-yonath-f044e9/analysis`, `vigorous-nightingale-2cc961/analysis` | Yes: `worktree-*-ignored/` |
| External evidence archive (10 dated folders with `SHA256SUMS.txt`) | `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\` | Yes: `evidence-archive/` (the original stays in place) |
| Working release binaries and the built UxPlay receiver | `release\`, `tools\airplay\uxplay\build-imouse\` | Yes: `release-binaries/` |
| Candidate and test builds with their data folders | `%TEMP%\claude\imouse-*` | Yes: `temp-builds/` |
| Session scratch folders (scripts, task outputs, patches) | `%TEMP%\claude\C--Users-joey--Desktop-Claude-Code-iMouseXP-2-0*` | Yes: `session-temp/` |
| Vendor install copy, **contains a stored vendor login** | `build\` (296 MB) | **No.** Deliberately excluded because of the credential; stays only on this PC |
| MSYS2 toolchain, downloaded protocol dependencies, `bin`/`obj` outputs | `tools\airplay\msys64` (3 GB), `tools\protocol-deps`, `**\bin`, `**\obj` | No: re-downloadable or rebuildable |
| Chat transcripts and the auto-memory | `%USERPROFILE%\.claude\projects\…` | No: they belong to the old account's local Claude data |

The backup folder is local, next to the repository, with `SHA256SUMS.txt`. It has **not** been uploaded anywhere. Copying it to another drive or cloud storage is the user's decision.

## 9. Redaction note (history rewritten before first push)

The 27 Sep accessory review had recorded the USB serial of the user's personal iPhone. Before the integration branch was first pushed, that string was replaced with `(withheld: personal device)` in its unpublished history. Only that one line changed.

Commits from the accessory review onward have new hashes:

| Old | New |
|---|---|
| `9a1ad71` | `249fb39` |
| `6d64f32` | `2a32b6b` |
| `23fd20f` | `19c309a` |
| `2642e3d` | `7ee6edb` |
| `7778b2a` | `a9087a3` |
| `f449c5e` | `ba4d291` |
| `412aa0c` | `3e3a251` |
| `544bda1` | `8731eb7` |

Earlier hashes, such as `3c1f035` and `b0708e3`, are unchanged. The original line is kept only in the local branch `backup/input-timeout-integration-pre-redaction`: do not push it.
