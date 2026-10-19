"""Offline staging of existing draft evidence; no service or socket is started."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import farm_test_network  # Refuse every network connection during preparation.
import imouse_social_automation as engine
from imouse_farm_server import FarmBackendRuntime

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(name, value): (HERE/name).write_text(json.dumps(value, indent=2), encoding='utf-8')

state = json.loads((HERE/'initial-rack.json').read_text(encoding='utf-8-sig'))
age = (datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(state['utc'].replace('Z', '+00:00'))).total_seconds()
if age < 0 or age > 90 or any(state[k] for k in ('processes', 'tcp', 'udp')):
    raise SystemExit('Recheck stopped processes/ports before copying the old candidate data. No service was started.')
for name in ('full-tests.json', 'retained-tests.json', 'negative-controls.json'):
    if not json.loads((HERE/name).read_bytes())['passed']: raise SystemExit('Complete offline checks first.')
old = json.loads((ROOT/'analysis/farm-new-draft-20261019/attempt-15-preparation.json').read_bytes())
source = Path(old['backendData']).resolve()
source.relative_to(ROOT)
run = ROOT/'output/candidate-runs/farm-recovery-20261019'
if run.exists(): raise SystemExit('Never overwrite an existing recovery candidate or its evidence.')
manifest = {str(p.relative_to(source)): sha(p) for p in source.rglob('*') if p.is_file()}
backend = run/'backend'
shutil.copytree(source, backend)
if any(sha(backend/name) != digest for name, digest in manifest.items()):
    raise SystemExit('A source file changed during copying; preserve the copy for review.')
write('copied-data.json', dict(source=str(source), destination=str(backend), files=len(manifest),
    sha256=manifest, checkedBeforeOpeningCopy=True, serviceStarted=False))
data = run/'data'; data.mkdir()
for name in ('devices.json', 'receivers.json'): shutil.copy2(Path(old['runDirectory'])/'data'/name, data/name)
config = json.loads((ROOT/'analysis/farm-new-draft-20261019/creation-config.json').read_bytes())
write('creation-config.json', config)
with patch.object(engine.MediaPullOrchestrator, 'detect_host_lan_url', return_value='http://127.0.0.1:9915'):
    runtime = FarmBackendRuntime(backend/'imouse_farm.db', run/'stage', port=9915, execution_mode='live',
        draft_creation_config=HERE/'creation-config.json')
try:
    origin = 'b8c155e2-1670-4f60-a090-aeff921e162e'
    eligible = runtime.draft_recoveries.eligibility(origin)
    if not eligible['eligible']: raise RuntimeError(eligible['contentReason'])
    original = runtime.draft_creations.get(origin)
    if not original['savedDraftVerified']: raise RuntimeError('The baseline creation lost its retained verification.')
    proof = eligible['sourceProof']
    native = ROOT/'output/codex-farm-recovery-20261019/iMouse2.dll'
    kernel = Path(old['kernel'])
    if sha(kernel.with_suffix('.dll')) != old['kernelSha256']: raise RuntimeError('The unchanged private kernel hash differs.')
    prep = dict(backendData=str(backend), runDirectory=str(run), stage=str(run/'stage'),
        config=str(HERE/'creation-config.json'), backendSourceHash=runtime.source_hash,
        assembly=str(native), nativeSha256=sha(native), creationId=origin,
        draftId=eligible['draftId'], revision=eligible['revision'],
        recoveryStoreId=runtime.draft_recoveries.store_id, sourceProof=proof,
        packageSha256=original['packageSha256'],
        kernel=str(kernel), kernelSha256=old['kernelSha256'], expectedDeviceId=old['expectedDeviceId'], expectedUid=old['expectedUid'],
        arguments=['http://127.0.0.1:9916/api/', '--data-dir', str(data), '--input-pid', 'C24C',
            '--receivers', str(data/'receivers.json'), '--receiver', str(Path(old['runDirectory'])/'receiver/uxplay.exe'),
            '--receiver-runtime', str(Path(old['runDirectory'])/'runtime')],
        serviceStarted=False, phoneInput=False, desktopControl=False, sourceDataUnchanged=True)
    if any(sha(source/name) != digest for name, digest in manifest.items()):
        raise RuntimeError('Original source data changed; no phone is admitted.')
    write('preparation.json', prep)
    write('native-options.json', dict(assembly=str(native), nativeSha256=sha(native),
        backendSourceHash=runtime.source_hash, recoveryStoreId=runtime.draft_recoveries.store_id,
        creationId=origin, draftId=eligible['draftId'], revision=eligible['revision'],
        output=str(HERE/'live-inspection-1'), dataDirectory=str(run/'native-data')))
    print(json.dumps(dict(filesCopied=len(manifest), eligible=True, baselineVerified=original['savedDraftVerified'],
        originalSaveOutcome=proof['originalSaveOutcome'], phoneInput=False, serviceStarted=False)))
finally: runtime.jobs.close()
