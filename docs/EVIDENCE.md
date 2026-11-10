# Evidence, branches and backups: where everything that is not on this branch lives

The tip of the development branch holds the product: source, tests, the rack scripts, and the few
evidence folders that code, tests or the release gates still read. Everything else is in one of three
places: Git history (section 1), another branch (section 2), or private folders on the development PC
that never go into Git (section 3). Section 4 lists the rules that keep the private part private.

## 1. Removed from the tip on 9 Nov 2026, kept in Git history

The 9 Nov audit removed dated handoff and status documents from the repository root. They are
unchanged in history; the last commit that has them is tagged **`evidence-20261109`**.

Root documents removed (19): `ACCOUNT-HANDOFF.md`, `CLAUDE-HANDOFF-20261019.md`,
`CLAUDE-HANDOFF-20261022.md`, `FARM-CONTINUATION.md`, `GEMINI-HANDOFF.md`, `GITHUB-SYNC-20261019.md`,
`HANDOFF.md`, `HANDOFF-SESSION-2026-09-10.md`, `handoff.html`, `INDEPENDENT-KERNEL.md`,
`MARKETING-FARM-ACCEPTANCE.md`, `MARKETING-FARM-STATUS.md`, `ORCA-RETURN-HANDOFF.md`, `PROGRESS.md`,
`RE-IMPROVEMENTS-PLAN.md`, `RESUME-NEXT.md`, `TESTING.md`, `TWO-PHONE-TEST.md`, `WORK-REMAINING.md`.
What replaces them: state is `MARKETING-SUITE-TRACKER.md`, lanes are `LANES.md`, release gates are
`FINISH-CRITERIA.md`, and the branch and backup map they carried is sections 2 to 4 of this file.

Read one file, or bring one back, without leaving the branch you are on:

```powershell
git show evidence-20261109:PROGRESS.md
git checkout evidence-20261109 -- PROGRESS.md      # restores it into the working folder, staged
```

## 2. Branches

Continue development on **`local/combined-candidate-20261012`**. `main` is the old September import
and is not the product. The other branches preserve history; none of them is merged or applied
wholesale over the candidate.

| Branch | What it holds | In the candidate's history? |
|---|---|---|
| `local/combined-candidate-20261012` | The product: desktop console, kernel, rack scripts and the Marketing Farm | it is the candidate |
| `main` | The first import (September, `ee445d7`); left unchanged | yes |
| `local/coordinator-work` | Earlier Orca/OMP coordinator commits (`01fb669`) | yes |
| `claude/input-timeout-integration`, `local/fka-passthrough-probe` | Claude's control, input-timeout, UIA and FKA work (`d0c4ccf`) | yes |
| `claude/jovial-yonath-f044e9` | Text chunking (`a6e4a9b`) | yes |
| `claude/funny-margulis-86e51b` | Settings isolation (`43b43f7`) | yes |
| `claude/track-gate-evidence` | Gate evidence (`900f5b4`) | yes |
| `local/prompt-validation-20261020`, `local/youtube-short-20261020` | October side lines (`001fe6c`, `99a6b34`) | yes |
| `claude/gate4-harness-v2` | The experimental Gate 4 harness history (`2c98f44`) | no |
| `claude/focused-noether-s600e0` | Cloud portal and rack agent (`6b24a96`); reference only, on GitHub only | no |
| `handoff/main-uncommitted-20260925` | `ba733c2`: Gate 2 and Gate 4 work found uncommitted in the main checkout on 25 Sep; never reviewed | no |
| `handoff/orca-coordinator-reflog-20261002` | `b946b942c82d`: a coordinator commit that was only in the reflog | no |
| `handoff/orca-working-tree-20261019` | `4eef760f66df`: 458 files from Orca's working folder | no |
| `handoff/gemini-and-local-records-20261019` | `3d95ec846a82`: 2,825 files: Gemini's handoffs, the legacy installer, web UI and blueprint, and the redacted Orca export | no |
| `handoff/fka-probe-working-tree-20261019` | `ff5fde280634`: 26 probe files | no |
| `sb/chat-<lane>` | Switchboard lane branches (local; the orchestrator merges them, see `LANES.md`) | as merged |
| `backup/input-timeout-integration-pre-redaction` | **Local only. Never push.** See section 4 | no, and it must stay out |

"Yes" was checked on 9 Nov with `git merge-base --is-ancestor <branch> evidence-20261109`: those
branches add nothing the candidate lacks. The "no" rows are the only places their content exists.

The 19 Oct preservation audit (every worktree, stash, reflog and GitHub branch inspected; 3,309
uncommitted files preserved; 15 local tips verified against GitHub) is recorded in
`analysis/github-sync-20261019/` at tag `evidence-20261109`. It was a backup audit, not acceptance of
any feature.

The preserved Gemini snapshot contains the legacy `tools/setup_imouse_farm.py` installer and
`Open Marketing Farm.ps1`. Never run them: the installer overwrites the current source.

A new checkout keeps evidence bytes intact (stored hashes are checked against them) with:

```powershell
git -c core.autocrlf=false clone --branch local/combined-candidate-20261012 https://github.com/josephacastiglia/iNodeControl.git
```

## 3. Private, on the development PC only

None of this is on GitHub, and none of it may be added.

| What | Where (beside or inside the main checkout) |
|---|---|
| Evidence archive: dated folders of frames, captures and logs, each with `SHA256SUMS.txt`; `privacy/` holds the lists `tools/privacy_scan_staged.py` reads | `..\iMouseXP-2.0-evidence-archive\` |
| Cross-agent preservation (19 Oct): the original Orca export and a Git bundle that includes withheld history | `..\iMouseXP-2.0-evidence-archive\20261019-cross-agent-preservation\` |
| The 28 Sep handoff backup: ignored evidence from the checkouts of that date, the release binaries, candidate builds and session scratch folders, with `SHA256SUMS.txt`. It has no October work | `..\iMouseXP-2.0-handoff-backup-20260928\` |
| Rack state: preparations, process records, window folders, run output, databases, device and receiver data | `analysis\farm-multiphone-20261020\slots\`, `...\windows\`, `output\` (all ignored) |
| The vendor install copy, which **contains a stored vendor login** | `build\` in the first checkout; deliberately in no backup |
| Installed release, toolchains and build outputs (rebuildable or re-downloadable) | `release\`, `tools\airplay\msys64\`, `tools\protocol-deps\`, `**\bin`, `**\obj` |

## 4. Rules

- **Never push `backup/input-timeout-integration-pre-redaction`, and never upload the cross-agent Git
  bundle** (`NEVER-UPLOAD-THIS-BUNDLE.txt` sits beside it). Both hold the one line that was withheld
  before the integration branch was first pushed: a 27 Sep accessory review had recorded the USB serial
  of a personal iPhone, and it was replaced with `(withheld: personal device)` in the unpublished
  history. Commits from that review onward were rewritten once, before any push:

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

  Earlier hashes (for example `3c1f035`, `b0708e3`) are unchanged.
- Never `git push --all` or `git push --mirror`, and never `git add -A` or `git add .`: stage files by
  name and run `python tools/privacy_scan_staged.py` before every commit (`LANES.md`).
- Device IDs, MAC addresses, account handles, phone frames, captures, databases and login or session
  stores stay out of Git.
- Never run `git clean -x`, delete ignored evidence or remove a worktree before its ignored files are
  verified to exist in the evidence archive.
- "It is not on `main`" does not mean it is lost: check every branch above, the tag and the two private
  folders before saying something was never saved.
