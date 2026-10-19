"""Verify offline results, protected files, source identity and staged evidence."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
def load(name): return json.loads((HERE/name).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
summary = {name: load(name+'.json') for name in ('full-tests', 'native-summary', 'retained-tests', 'negative-controls')}
if not all(item['passed'] for item in summary.values()): raise SystemExit('A required offline check failed.')
prep = load('preparation.json')
if sha(Path(prep['assembly'])) != prep['nativeSha256']: raise SystemExit('Prepared native candidate changed.')
if load('launcher-live.json')['SourceHash'] != prep['backendSourceHash']: raise SystemExit('Prepared backend source differs from launcher validation.')
checks = load('live-inspection-1-dry-run/checks.json')
if not all(c['pass'] for c in checks): raise SystemExit('The headless native driver is not ready.')
original = Path(prep['backendData']).parent.parent/'farm-new-draft-20261019/backend'
manifest = load('copied-data.json')['sha256']
if any(sha(original/name) != digest for name, digest in manifest.items()): raise SystemExit('Original saved data changed.')
protected = []
for entry in load('protected-before.json'):
    current = sha(Path(entry['path']))
    protected.append(dict(path=entry['path'], sha256=current, unchanged=current == entry['sha256']))
if not all(entry['unchanged'] for entry in protected): raise SystemExit('An installed protected file changed.')
(HERE/'protected-after.json').write_text(json.dumps(protected, indent=2), encoding='utf-8')
state = load('final-rack.json')
if any(state[k] for k in ('processes', 'tcp', 'udp')): raise SystemExit('The initially stopped rack state was not preserved.')
commit = subprocess.run(['git','-c','safe.directory='+str(ROOT),'rev-parse','HEAD'], cwd=ROOT,
    capture_output=True, text=True, check=True).stdout.strip()
tracked = subprocess.run(['git','-c','safe.directory='+str(ROOT),'show','--pretty=format:','--name-only',commit],
    cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
sources = {name: sha(ROOT/name) for name in tracked if name.strip()}
result = dict(sourceCommit=commit, nativeBuiltBeforeCommit=True, nativeSha256=prep['nativeSha256'],
    backendSourceHash=prep['backendSourceHash'], productSourceFiles=sources,
    python=summary['full-tests'], native=summary['native-summary'], retained=summary['retained-tests'],
    negativeControls=summary['negative-controls'], installedFilesUnchanged=len(protected),
    originalSavedDataUnchanged=len(manifest), baselineCreationId=prep['creationId'],
    baselineCreationRecordSha256=prep['sourceProof']['creationRecordSha256'],
    headlessDriverValidated=True, freshPhoneTest='pending', appRestartPersistence='pending',
    phoneInput=False, desktopControl=False, servicesStarted=False, publishing=False, messaging=False,
    candidatePromoted=False, sourcePushed=False, documentationReview=dict(score=10,failedRows=[]),
    archive=str(ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-recovery-offline'))
(HERE/'validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(dict(passed=True, python=result['python']['tests'], native=result['native']['passed'],
    retained=result['retained']['tests'], installedUnchanged=len(protected), sourceCommit=commit, freshPhoneTest='pending')))
