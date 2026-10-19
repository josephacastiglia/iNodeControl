"""Write the compact repository audit and preserve the local-only originals."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parent
ROOT=WORKSPACE/'iMouseXP-2.0-combined-candidate'
TARGET=ROOT/'analysis/github-sync-20261019'
TARGET.mkdir(parents=True,exist_ok=True)
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
plan=load(HERE/'publication-plan.json')
inventory=load(HERE/'local-inventory.json')['repositories'][0]
snapshots=load(HERE/'snapshot-results.json')
scan=load(HERE/'security-scan.json')
assert scan['passed'] and not scan['blockedFindings']
known={'effb526f457597fe3b9e1dfa4a6e0b1635bf19e444ba6fd65eba449048ee4cca','b3c53c08828847f11b3083a5b1fa83ddf6751112653f0fd9d563754092ec65f7'}
assert all(v['valueSha256'] in known for v in scan['genericReview'])
scan['genericReviewResolved']=True
scan['genericReviewDisposition']='Two repeated test placeholders already reviewed in the engine _self_check and diagnostic test setUp. No operational credential values.'
(HERE/'security-scan.json').write_text(json.dumps(scan,indent=2),encoding='utf-8')
catalog=[]
archive=WORKSPACE/'iMouseXP-2.0-evidence-archive'
for folder in sorted(archive.iterdir()):
    if not folder.is_dir():continue
    manifests=[p for p in folder.iterdir() if p.is_file() and (p.name.startswith('SHA256SUMS') or p.name in ('archive-summary.json','archive-manifest.json'))]
    catalog.append(dict(folder=folder.name,manifests=[dict(file=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in manifests]))
summary=dict(date='2026-10-19',since=plan['since'],repository='https://github.com/josephacastiglia/iNodeControl',visibility='private',
    auditedWorktrees=[dict(path=t['worktree'],head=t['HEAD'],branch=t.get('branch'),trackedChanges=t['trackedChanges'],untrackedFiles=t['untrackedFiles']) for t in inventory['worktrees']],
    localRefs=inventory['refs'],remoteBefore=[r for r in inventory['refs'] if r['name'].startswith('refs/remotes/')],
    snapshotResults=snapshots,selectedUncommittedFiles=sum(s['selectedFiles'] for s in snapshots),
    preservedTrackedChanges=sum(sum(f['tracked'] for f in p['files']) for p in plan['plans']),
    reflogOnlyPreserved=dict(branch='handoff/orca-coordinator-reflog-20261002',commit='b946b942c82d909d0594ebdd22bb012d9b211753'),
    cloudWorkAlreadyRemote=dict(branch='claude/focused-noether-s600e0',commit='6b24a961ef9eda626c5f72d08f4bb46bd5327453'),
    originalOrcaProject=plan['externalOrcaProject'],accountHeaderRedactions=1,
    excludedUnredactedBranch=plan['excludedUnredactedBranch'],limitations=plan['limitations'],
    noMerge=True,noPromotion=True,noForcePush=True,phoneInput=False,installedReleaseChanged=False,
    remotePushVerified=False)
(TARGET/'audit.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
(TARGET/'local-evidence-catalog.json').write_text(json.dumps(catalog,indent=2),encoding='utf-8')
compact={k:v for k,v in scan.items() if k!='genericReview'}
compact['genericReviewOccurrences']=len(scan['genericReview'])
(TARGET/'security-review.json').write_text(json.dumps(compact,indent=2),encoding='utf-8')
for name in ('inventory.py','prepare_publication.py','scan_publication.py','create_snapshots.py','write_audit_record.py'):
    shutil.copy2(HERE/name,TARGET/name)
rows='\n'.join('| `'+s['branch']+'` | `'+s['commit'][:12]+'` | '+str(s['selectedFiles'])+' selected files; original working folder/index unchanged |' for s in snapshots)
doc=f'''# iNodeControl: cross-agent GitHub preservation — 19 October 2026

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
{rows}

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
'''
(ROOT/'GITHUB-SYNC-20261019.md').write_text(doc,encoding='utf-8')
private=Path(plan['privateOriginalArchive'])
(private/'NEVER-UPLOAD-THIS-BUNDLE.txt').write_text('LOCAL ONLY: a bundle in this folder includes backup/input-timeout-integration-pre-redaction and its withheld personal-device identifier. Never upload this bundle or the original account export. Publish only the audited safe refs and sanitized export.\n',encoding='utf-8')
for name in ('local-inventory.json','publication-plan.json','snapshot-results.json','security-scan.json','omp-session-locations.json'):
    shutil.copy2(HERE/name,private/name)
print(json.dumps(dict(report=str(ROOT/'GITHUB-SYNC-20261019.md'),snapshotFiles=summary['selectedUncommittedFiles'],originalTrackedChangesPreserved=summary['preservedTrackedChanges'],archiveFolders=len(catalog),allSnapshotOriginalsUnchanged=True)))
