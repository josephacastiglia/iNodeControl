"""Archive one live window attempt privately, then clear it so the window can be re-prepared.

Usage: python archive_attempt.py reel|tiktok|x <attempt-label>
Copies the attempt's untracked live-folder outputs, the tracked preparation files it
ran with, and the private run folder into iMouseXP-2.0-evidence-archive (outside Git),
verifies every copy by SHA-256, writes a manifest, and only then removes the
originals. Writes a summary here without OCR text, frames or handles. No socket or phone.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive' / '20261020-farm-live-windows'
name, label = sys.argv[1], sys.argv[2]
record = ROOT / f'analysis/farm-{name}-draft-20261019'
live = record / 'live'
prep = json.loads((live / 'preparation.json').read_text(encoding='utf-8'))
run = Path(prep['runDirectory'])
dest = ARCHIVE / f'{name}-{label}'
if dest.exists(): raise SystemExit('This attempt is already archived; nothing is overwritten.')


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


untracked = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '--others', '--exclude-standard', '-z', str(live)],
                           capture_output=True, check=True).stdout.decode('utf-8').split('\0')
untracked = [ROOT / p for p in untracked if p]
tracked = [live / n for n in ('preparation.json', 'native-options-1.json', 'native-dry-options.json',
                              'preparation-recheck.json', 'protected-before.json')]
copies = []
for source in untracked + tracked:
    target = dest / 'live' / source.relative_to(live)
    target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); copies.append((source, target))
for source in sorted(p for p in run.rglob('*') if p.is_file()):
    target = dest / 'run' / source.relative_to(run)
    target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target); copies.append((source, target))
for source, target in copies:
    if sha(source) != sha(target): raise SystemExit('Archive copy differs: ' + str(source))
manifest = '\n'.join(f'{sha(t)}  {t.relative_to(dest).as_posix()}' for _, t in copies) + '\n'
(dest / 'SHA256SUMS.txt').write_text(manifest, encoding='utf-8')
manifest_sha = hashlib.sha256(manifest.encode('utf-8')).hexdigest()

# Summary for Git: states, labels, timings and counts only.
runs = sorted((run / 'backend' / f'{name}-creations').glob('*/record.json'))
summary = dict(window=name, attempt=label, archive=str(dest.relative_to(ROOT.parent)), files=len(copies),
               manifestSha256=manifest_sha, testToken=prep['testToken'], backendSourceHash=prep['backendSourceHash'],
               phoneInput=True, publishing=False, messaging=False)
if runs:
    r = json.loads(runs[0].read_text(encoding='utf-8'))
    summary.update(runId=runs[0].parent.name, state=r.get('state'), error=r.get('error'), cleanup=r.get('cleanup'),
                   evidenceExport=r.get('evidenceExport'), savedDraftVerified=r.get('savedDraftVerified'),
                   actions=[dict(label=a.get('label'), state=a.get('state')) for a in r.get('actions', [])],
                   commands=[dict(fun=c.get('fun'), purpose=c.get('purpose'), state=c.get('state'),
                                  x=(c.get('data') or {}).get('x'), y=(c.get('data') or {}).get('y')) for c in r.get('commands', [])
                             if not str(c.get('purpose', '')).startswith(('enter-transfer-url-',))],
                   typedKeyCommands=sum(1 for c in r.get('commands', []) if str(c.get('purpose', '')).startswith('enter-transfer-url-')),
                   observations=[dict(role=e.get('role'), state=e.get('state'),
                                      sequence=((e.get('observation') or {}).get('frameEvidence') or {}).get('sequence'),
                                      ageMs=((e.get('observation') or {}).get('frameEvidence') or {}).get('ageUpperBoundMs'))
                                 for e in r.get('observations', [])],
                   transitionChecks=[{k: t.get(k) for k in ('stage', 'attempt', 'state', 'reason', 'mean', 'changed')}
                                     for t in r.get('transitionChecks', [])],
                   mediaVideoRequests=(r.get('mediaDelivery') or {}).get('videoRequests'))
restoration = live / 'restoration.json'
if restoration.exists():
    value = json.loads(restoration.read_text(encoding='utf-8-sig'))
    summary.update(restored=value.get('restored'), protectedFilesUnchanged=all(p.get('unchanged') for p in value.get('protectedFiles', [])))
(HERE / f'{name}-{label}-summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')

# Clear only what was archived: the untracked attempt outputs and the run folder.
for source in untracked: source.unlink()
for folder in sorted((p for p in live.rglob('*') if p.is_dir()), reverse=True):
    if not any(folder.iterdir()): folder.rmdir()
shutil.rmtree(run)
print(json.dumps(dict(archived=str(dest), files=len(copies), manifestSha256=manifest_sha, cleared=True)))
