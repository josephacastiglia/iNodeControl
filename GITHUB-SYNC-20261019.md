# iNodeControl: cross-agent GitHub preservation — 19 October 2026

This audit preserves project source, scripts, reports and reviewed text evidence
from **28 September through 19 October 2026**, including older history needed by
those changes. It covers the saved work from ChatGPT/Codex, Claude, Gemini and
Orca/OMP found on this PC plus the repository's existing GitHub branches.
It is a backup/publication audit, not product release acceptance.

## Where to continue

Use **`local/combined-candidate-20261012`**, not the old default `main` import.
The latest product/live-validation checkpoint before this documentation audit is
`a8f726ff96cff791bfd57a50fd39d8294c1414f0`. Read `MARKETING-FARM-STATUS.md`,
`RESUME-NEXT.md`, `WORK-REMAINING.md` and `MARKETING-FARM-ACCEPTANCE.md` there.
The candidate remains unpromoted. Snapshot branches preserve historical and
experimental work; do not merge or apply them wholesale over the candidate.

For a new checkout of the development branch, run:

```powershell
git -c core.autocrlf=false clone --branch local/combined-candidate-20261012 https://github.com/josephacastiglia/iNodeControl.git
```

The explicit line-ending setting preserves stored evidence bytes for checksum
checks. The desktop shortcut and installed release are independent of this Git
backup operation and were not changed.

## Preserved work

All eight registered worktrees were inspected. Three contained project material
that was not committed: **3,309 selected files, including 22 tracked edits**.
Separate preservation commits capture them without switching branches, staging
the operator's files or altering their working copies:

| Branch | Preservation commit | Contents |
|---|---|---|
| `handoff/orca-working-tree-20261019` | `4eef760f66df` | 458 selected files; original working folder/index unchanged |
| `handoff/gemini-and-local-records-20261019` | `3d95ec846a82` | 2825 selected files; original working folder/index unchanged |
| `handoff/fka-probe-working-tree-20261019` | `ff5fde280634` | 26 selected files; original working folder/index unchanged |

The Gemini/original-records snapshot includes its original handoffs, legacy
installer, web UI and blueprint, plus the two handoff/export files from the
separate Orca `iMouse2Automations` project. Those originals are historical;
running the old installer can overwrite the hardened implementation.
The export's account header is redacted. Its exact original remains local.

These additional lines retain their own history:

- `local/combined-candidate-20261012`: integrated desktop/kernel and marketing
  candidate, including the fresh C24C draft/recovery validation.
- `local/coordinator-work`: earlier Orca/OMP coordinator commits.
- `claude/input-timeout-integration`: later Claude UIA/FKA work through `d0c4ccf`.
- `local/fka-passthrough-probe`: the probe's base; its uncommitted changes are in
  the separate snapshot above.
- `handoff/orca-coordinator-reflog-20261002`: `b946b942c82d`, a coordinator commit
  found only in the reflog and otherwise absent from branch tips.
- Existing `claude/*` and September handoff branches remain intact. Cloud portal
  and rack-agent work is already on `claude/focused-noether-s600e0` (`6b24a96`).

`analysis/github-sync-20261019/audit.json` records exact tips and snapshot results.
Each snapshot also contains a SHA-256 manifest of every selected source file.
No history is force-pushed, no branch is merged, and `main` is unchanged.
The post-push verification record is added after reading GitHub's actual refs.

## Privacy and local artifacts

The target repository is **private**. Unpublished reachable history and all
selected new files were scanned for credential patterns, private keys and the
known withheld personal-device identifier. The Gemini installer's five embedded
compressed source payloads were scanned without running the installer. Two
repeated test placeholders were reviewed in their fixture/self-check context.
No operational credentials or withheld identifier were found in the publish set.

**`backup/input-timeout-integration-pre-redaction` stays local and must never be
pushed.** No raw authentication stores, vendor installation/configuration with a
stored login, phone screenshots/captures, SQLite/session stores, installed builds
or downloaded toolchains are added to GitHub by this audit. Generated build trees,
unrelated `installed-marketing` and nested `sites/keystone-cards` are excluded.

Private evidence remains in `iMouseXP-2.0-evidence-archive` and the dated handoff
backup. `local-evidence-catalog.json` records the available archive-manifest hashes;
it is a catalog, not a claim that raw artifacts were uploaded. The new private
cross-agent preservation folder keeps the original Orca export and a local Git
bundle. That bundle includes withheld history and must never be uploaded.

## Audit boundary

The audit inspected local branches, all registered worktrees, detached tips,
stashes, recent reflogs, the dedicated Orca project, saved project locations and
handoffs, and every GitHub branch. Orca's live runtime was unavailable after a
window-start timeout; no agent prompt or work was dispatched. Git/file inspection
still covered its saved implementations.

Unsaved or inaccessible cloud-only conversation material cannot be recovered
from Git. General account chat transcripts and memories are not exported. The
dedicated project handoff export is included after redaction. This backup does
not prove unfinished features work: historical claims stay separate from the
candidate's measured acceptance records.
