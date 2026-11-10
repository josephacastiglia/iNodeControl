# Evidence, branches and backups: where everything that is not on this branch lives

The tip of the development branch holds the product: source, tests, the rack scripts, and the few
evidence folders that code, tests or the release gates still read. Everything else is in one of three
places: Git history (section 1), another branch (section 2), or private folders on the development PC
that never go into Git (section 3). Section 4 lists the rules that keep the private part private.

## 1. Removed from the tip on 9 Nov 2026, kept in Git history

The 9 Nov audit removed dated documents from the repository root and evidence that nothing reads from
`analysis/`. All of it is unchanged in history; the last commit that has it is tagged
**`evidence-20261109`**.

### Root documents

Removed (19): `ACCOUNT-HANDOFF.md`, `CLAUDE-HANDOFF-20261019.md`,
`CLAUDE-HANDOFF-20261022.md`, `FARM-CONTINUATION.md`, `GEMINI-HANDOFF.md`, `GITHUB-SYNC-20261019.md`,
`HANDOFF.md`, `HANDOFF-SESSION-2026-09-10.md`, `handoff.html`, `INDEPENDENT-KERNEL.md`,
`MARKETING-FARM-ACCEPTANCE.md`, `MARKETING-FARM-STATUS.md`, `ORCA-RETURN-HANDOFF.md`, `PROGRESS.md`,
`RE-IMPROVEMENTS-PLAN.md`, `RESUME-NEXT.md`, `TESTING.md`, `TWO-PHONE-TEST.md`, `WORK-REMAINING.md`.
What replaces them: state is `MARKETING-SUITE-TRACKER.md`, lanes are `LANES.md`, release gates are
`FINISH-CRITERIA.md`, and the branch and backup map they carried is sections 2 to 4 of this file.

Read one with `git show evidence-20261109:PROGRESS.md`.

The same audit removed scripts and tools nothing used any more (the browser console, the September
launchers and measurement scripts, the HID capture tools, the older release-staging path). They are at
the tag too; the commit messages on the branch list each of them.

### Evidence folders and files under `analysis/`

117 folders (1,563 files) and 21 loose files left the tip: nothing outside `analysis/` reads them,
and `FINISH-CRITERIA.md`, `MARKETING-SUITE-TRACKER.md`, `LANES.md`, `README.md` and `docs/` do not link
them. The number after each name is its count of tracked files. Frames, captures and logs were never
in Git: those are in the private evidence archive (section 3).

September and undated (42 folders, 215 files): the first two-phone app, the release-gate runs and the
keyboard and receiver investigations.

`accessory-connection-20260927` (1), `airplay-discovery-20260927` (1), `app-identification` (1),
`c241-clean-typing` (4), `c241-typing-diagnostic` (13), `c241-typing-investigation` (4),
`candidate-validation-20260915` (6), `click-after-home-20260915` (2),
`click-candidate-validate-20260915-b` (2), `click-candidate-validate-20260915` (2),
`console-click-investigation-20260927` (1), `diagnostics` (2), `display-latency-20260915` (3),
`finish-criteria-audit-20260916` (1), `five-phone-config` (3), `fka-space-loss-20260927` (1),
`fka-typing-mode-20261001` (4), `footer-home-speed-20260914` (1), `force-recast-mapping` (2),
`four-phone-config` (3), `gate11-five-phone-validation` (5), `gate11-four-phone-validation` (13),
`gate4-targeting-baseline-20260916` (7), `gate6-release-validation-20260916` (11),
`gate8-group-control-20260916` (5), `gate9-recovery-20260916` (8), `home-latency` (1),
`home-tab-20260927` (1), `input-ownership-20260916` (10), `input-ownership-live-20260917` (4),
`input-timeout-candidate-20260925` (21), `isolated-test-environment-plan-20260927` (1),
`led-hardware-20260923` (11), `lower-screen-targeting-20260927` (1), `performance-audit` (14),
`phone4-board-probe` (12), `phone5-board-verification` (10), `precise-candidate-deploy-20260915`
(3), `stability-c24c` (2), `text-chunking-candidate-20260925` (13), `two-phone-footer-verify` (1),
`two-phone-live-test-20260914` (4)

11 to 14 October (42 folders, 840 files): the combined desktop candidate and its review packages.

`binding-policy-20261012` (27), `candidate-acceptance-20261012` (16), `candidate-launcher-20261012`
(12), `candidate-live-20261013` (20), `candidate-retry-20261013` (15),
`cleanup-diagnostics-20261012` (23), `combined-candidate-20261012` (59),
`combined-shutdown-package-20261013` (18), `combined-timing-package-20261013` (18),
`console-diagnostics-20261012` (16), `consolidated-package-20261013` (19), `drag-ordering-20261012`
(25), `fleet-shutdown-20261013` (50), `frame-freshness-20261012` (11),
`gate6-console-cleanup-20261013` (14), `gate6-failure-handling-20261013` (13),
`gate6-preflight-20261013` (19), `hid-input-replies-20261014` (12), `input-cleanup-20261012` (21),
`kernel-startup-20261012` (20), `launcher-startup-errors-20261013` (53), `navigation-live-20261014`
(7), `offline-backlog-20261011` (5), `persistence-20261012` (32), `pointer-queue-20261012` (20),
`preview-freshness-20261012` (6), `re-improvements-20261014` (43), `receiver-logging-20261012` (7),
`receiver-memory-20261012` (5), `receiver-process-cleanup-20261013` (27),
`receiver-retry-status-20261013` (18), `release-staging-20261012` (9), `response-timing-20261013`
(14), `runtime-capsule-20261012` (11), `runtime-provenance-20261012` (22),
`runtime-readiness-20261012` (11), `runtime-startup-guard-20261013` (16), `scope-release-20261012`
(26), `screenshot-backpressure-20261013` (27), `screenshot-client-20261013` (27),
`vendor-protocol-rea-20261014` (18), `wall-freshness-20261012` (8)

17 October onwards (33 folders, 508 files): building the Marketing Farm's first drafts.

`farm-action-evidence-20261018` (1), `farm-carousel-20261017` (2),
`farm-carousel-inspection-20261018` (1), `farm-draft-continuity-20261018` (1),
`farm-interface-integration-20261018` (19), `farm-interface-live-20261018` (31),
`farm-journal-read-race-20261019` (4), `farm-layout-stability-20261018` (5),
`farm-live-final-20261018` (16), `farm-live-layout-20261018` (7), `farm-live-transitions-20261018`
(14), `farm-live-verification-20261018` (2), `farm-live-windows-20261020` (22),
`farm-native-transfer-20261017` (4), `farm-new-draft-20261019` (27), `farm-observations-20261017`
(2), `farm-permission-prompts-20261020` (2), `farm-photo-package-20261103` (1),
`farm-preparation-continuity-20261018` (3), `farm-prompt-recovery-20261018` (10),
`farm-prompt-recovery-live-20261018` (43), `farm-prompt-validation-20261020` (24),
`farm-recognition-20261017` (1), `farm-recovery-20261019` (37), `farm-recovery-live-20261019` (126),
`farm-reel-draft-20261019` (24), `farm-save-reopen-20261018` (1), `farm-tiktok-draft-20261019` (27),
`farm-transition-holds-20261018` (2), `farm-verification-20261018` (1), `farm-x-draft-20261019`
(23), `farm-youtube-draft-20261020` (11), `github-sync-20261019` (14)

Loose files: `BUILD-DECISIONS.md`, `IPHONE-BUILD.md`, `LIVE-RECONNECT-RESULTS.md`, `OVERVIEW.md`, `PHONE-FARM-CORE-REVIEW.md`, `UXPLAY-RECONNECT-TEST.md`, `binary-inventory.json`, `direct-click.json`, `direct-diagonal.json`, `direct-home.json`, `direct-reset.json`, `direct-search-move.json`, `file-manifest.json`, `firewall-approved-rules.json`, `independent-status.json`, `kernel-self-tests.txt`, `post-crash-status.json`, `receiver-disconnect-status.json`, `receiver-reconnected-status.json`, `ui-labels-english.json`, `verification.json`.

What stays under `analysis/` is what something still reads or cites: the rack scripts
(`farm-multiphone-20261020`), the scale gate's code, test fixtures, configurations the launchers and
tools read, the evidence `FINISH-CRITERIA.md` links for the release gates, `HARDWARE.md`,
`HID-PROTOCOL.md` and the HTML sources of the three PDFs in the root.

Bring one folder back, or look inside it, without leaving your branch:

```powershell
git ls-tree -r --name-only evidence-20261109 -- analysis/gate9-recovery-20260916      # what it held
git show evidence-20261109:analysis/gate9-recovery-20260916/results.json                 # read one file
git checkout evidence-20261109 -- analysis/gate9-recovery-20260916                    # restore the folder, staged
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
