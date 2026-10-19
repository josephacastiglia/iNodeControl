"""Stage private receiver/data and verify unchanged candidate assembly, offline."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

RECORD = Path(__file__).resolve().parent
ROOT = RECORD.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import stage_release as stage
import validate_rack_config as rack
from farm_draft_runs import source_content, CONTENT_SHA256
from farm_drafts import CarouselDrafts


def write(name, value):
    (RECORD/name).write_text(json.dumps(value, indent=2), encoding='utf-8')


checks = json.loads((RECORD/'offline-tests.json').read_text(encoding='utf-8'))
assert checks['passed'] and checks['tests'] == 7 and not checks['skipped']
previous = json.loads((ROOT/'analysis/farm-prompt-recovery-20261018/validation.json').read_text(encoding='utf-8'))
assert previous['pythonTests']['passed'] and previous['pythonTests']['tests'] == 106
native = ROOT/'output/codex-farm-interface-20261018/iMouse2.dll'
assert hashlib.sha256(native.read_bytes()).hexdigest() == previous['nativeDllSha256']
changed = [name for name, digest in previous['sources'].items()
           if (name.startswith(('tools/', 'src/')) or name == 'Open Marketing Farm Candidate.ps1')
           and hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest]
assert changed == [], changed
package = ROOT/'output/staging/combined-re-improvements-20261014'
assert stage.verify(package) == [], 'Receiver package checksum/source checks failed'
source = ROOT.parent/'iMouseXP-2.0/analysis/two-phone-config'
names = ('receivers.json', 'devices.json', 'pointer-calibration.json')
before = {name: stage.row(source/name) for name in names}
rows = [rack.read_records(source/name) for name in names]
assert rack.validate(*rows)['configuration_valid']
selected = [[row for row in items if row[key] == 'C24C']
            for items, key in zip(rows, ('BoardPid', 'pid', 'Pid'))]
assert all(len(items) == 1 for items in selected)
assert rack.validate(*selected)['bindings_complete']
assert selected[0][0]['DeviceId'] == selected[1][0]['deviceid'] == rack.KNOWN['C24C']

run = ROOT/'output/candidate-runs/farm-prompt-recovery-live-20261018'
run.mkdir(parents=True, exist_ok=False)
data = run/'data'; data.mkdir()
for name, items in zip(names, selected):
    (data/name).write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding='utf-8')
for origin, destination in ((package/'payload/receiver', run/'receiver'),
                            (package/'dependencies/receiver-runtime/runtime', run/'runtime')):
    shutil.copytree(origin, destination)
    for file in origin.rglob('*'):
        if file.is_file(): assert stage.row(file) == stage.row(destination/file.relative_to(origin))

kernel = ROOT/'output/codex-farm-live-kernel-20261018/iMouse2.Kernel.exe'
config = json.loads((ROOT/'analysis/farm-interface-integration-20261018/candidate-workflow-config.json').read_text())
assert hashlib.sha256(kernel.with_suffix('.dll').read_bytes()).hexdigest() == config['kernelSha256']
arguments = ['http://127.0.0.1:9916/api/', '--data-dir', str(data), '--input-pid', 'C24C',
    '--receivers', str(data/'receivers.json'), '--receiver', str(run/'receiver/uxplay.exe'),
    '--receiver-runtime', str(run/'runtime')]
result = subprocess.run([str(kernel), '--validate-startup', *arguments], capture_output=True,
    timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
(RECORD/'startup-validation.json').write_bytes(result.stdout)
(RECORD/'startup-validation.stderr.txt').write_bytes(result.stderr)
assert result.returncode == 0
validation = json.loads(result.stdout)
assert validation['valid'] and validation['allowed'] == ['C24C'] and validation['receiver_count'] == 1
assert all(validation[key] is False for key in ('hardware_accessed','listener_started','receivers_started','settings_written'))
assert before == {name: stage.row(source/name) for name in names}

backend = run/'backend'; backend.mkdir()
source_db = ROOT/'output/codex-farm-interface-20261018/draft-workflow-data/backend/carousel-drafts.db'
source_hash = stage.row(source_db)
with sqlite3.connect(source_db.as_uri()+'?mode=ro', uri=True) as origin:
    with sqlite3.connect(backend/'carousel-drafts.db') as destination: origin.backup(destination)
assert source_hash == stage.row(source_db)
draft_id = 'eeb59816-5805-4169-aa1c-d91fe1e2c14f'
drafts = CarouselDrafts(backend/'carousel-drafts.db', backend/'stage')
assets, caption, digest = source_content(drafts.export(draft_id, 5))
assert digest == CONTENT_SHA256 and len(assets) == 3
write('candidate-workflow-config.json', config)
prior_protected = json.loads((ROOT/'analysis/farm-interface-integration-20261018/protected-files.json').read_text())['files']
assert all(hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() == row['sha256'] for row in prior_protected), 'Protected release/settings changed since previous checkpoint'
protected = {row['path']: stage.row(Path(row['path'])) for row in prior_protected}
write('protected-files.json', protected)
sources = {str(file.relative_to(ROOT)): hashlib.sha256(file.read_bytes()).hexdigest()
           for file in (ROOT/'tools').iterdir() if file.is_file() and file.suffix in ('.py','.ps1','.json')}
sources.update({str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in RECORD.iterdir() if path.suffix in ('.py', '.ps1')})
write('validation-sources.json', sources)
write('preparation.json', dict(kernel=str(kernel), arguments=arguments, validation=validation,
    runDirectory=str(run), backendData=str(backend), expectedDeviceId=rack.KNOWN['C24C'], expectedUid=config['expectedUid'],
    nativeAssembly=str(native), nativeSha256=previous['nativeDllSha256'], draftId=draft_id, revision=5,
    contentSha256=digest, sourceDatabaseUnchanged=True, sourceConfigurationHashes=before,
    runtimeFiles=stage.inventory(run, 'no-manifest'), serviceStarted=False, consoleLaunched=False,
    phoneInput=False, releaseChanged=False, offlineTests=checks,
    backendSourceHash=previous['backendSourceHash'], productChecks=previous['pythonTests'],
    backendWrapper=str(RECORD/'test_backend.py'), localFaultRecord=str(RECORD/'local-delay.json'),
    nativeProbe=str(ROOT/'output/farm-interface-live-native-probe-20261018/NativeProbe.exe'),
    nativeProbeSha256='6800e1ea561b8f4c4af3c26b2b0a7d768822400d5c25bab92f5ee467b67a126e',
    testFault=dict(kind='local_pre_dispatch_age_delay',seconds=1.65,maximumInjections=1,purpose='prepared-save-once')))
print(json.dumps(dict(prepared=True, receiverCount=1, kernelPort=9916, nativeUnchanged=True,
    sourceDatabaseUnchanged=True, protectedFiles=len(protected), phoneInput=False)))
