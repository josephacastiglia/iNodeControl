"""Prepare a private C24C kernel and verify dependencies, without starting it."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

RECORD = Path(__file__).resolve().parent
ROOT = RECORD.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import stage_release as stage
import validate_rack_config as rack


def write(name, value):
    (RECORD / name).write_text(json.dumps(value, indent=2), encoding='utf-8')


package = ROOT / 'output/staging/combined-re-improvements-20261014'
assert stage.verify(package) == [], 'Preserved receiver package failed its checksum/source checks.'
source = ROOT.parent / 'iMouseXP-2.0/analysis/two-phone-config'
names = ('receivers.json', 'devices.json', 'pointer-calibration.json')
before = {name: stage.row(source / name) for name in names}
rows = [rack.read_records(source / name) for name in names]
assert rack.validate(*rows)['configuration_valid']
chosen = [[r for r in items if r[key] == 'C24C'] for items, key in zip(rows, ('BoardPid', 'pid', 'Pid'))]
assert all(len(r) == 1 for r in chosen)
assert rack.validate(*chosen)['bindings_complete']
assert chosen[0][0]['DeviceId'] == chosen[1][0]['deviceid'] == rack.KNOWN['C24C']

run = ROOT / 'output/candidate-runs/farm-live-final-20261018'
run.mkdir(parents=True, exist_ok=False)
data = run / 'data'
data.mkdir()
for name, selected in zip(names, chosen):
    (data / name).write_text(json.dumps(selected, indent=2, ensure_ascii=False), encoding='utf-8')

# Copy the already validated receiver/runtime, rather than depend on installed files.
shutil.copytree(package / 'payload/receiver', run / 'receiver')
shutil.copytree(package / 'dependencies/receiver-runtime/runtime', run / 'runtime')
for origin, destination in ((package / 'payload/receiver', run / 'receiver'),
                            (package / 'dependencies/receiver-runtime/runtime', run / 'runtime')):
    for path in origin.rglob('*'):
        if path.is_file():
            assert stage.row(path) == stage.row(destination / path.relative_to(origin))

kernel = ROOT / 'output/codex-farm-live-kernel-20261018/iMouse2.Kernel.exe'
assert hashlib.sha256(kernel.with_suffix('.dll').read_bytes()).hexdigest() == 'c72fa4e0b02b82ec4f7a949c9a80375c69da68d7357084401c7bb422c194a873'
arguments = ['http://127.0.0.1:9916/api/', '--data-dir', str(data), '--input-pid', 'C24C',
             '--receivers', str(data / 'receivers.json'), '--receiver', str(run / 'receiver/uxplay.exe'),
             '--receiver-runtime', str(run / 'runtime')]
result = subprocess.run([str(kernel), '--validate-startup', *arguments], capture_output=True, timeout=30,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
(RECORD / 'startup-validation.stdout.json').write_bytes(result.stdout)
(RECORD / 'startup-validation.stderr.txt').write_bytes(result.stderr)
assert result.returncode == 0
validation = json.loads(result.stdout)
assert validation['valid'] and validation['allowed'] == ['C24C'] and validation['receiver_count'] == 1
assert all(validation[key] is False for key in ('hardware_accessed', 'listener_started', 'receivers_started', 'settings_written'))
assert validation['build']['sha256'] == hashlib.sha256(kernel.with_suffix('.dll').read_bytes()).hexdigest()
assert before == {name: stage.row(source / name) for name in names}

protected_record = ROOT / 'analysis/candidate-retry-20261013/restoration-files.json'
protected = {item['path']: stage.row(Path(item['path'])) for item in stage.load(protected_record)
             if Path(item['path']).is_file() and Path(item['path']).name not in ('receiver-C24C.log', 'receiver-C241.log')}
for path in (ROOT.parent / 'iMouseXP-2.0').glob('output/gemini-farm-tab-r4/iMouse2.*'):
    if path.is_file(): protected[str(path)] = stage.row(path)
write('protected-files.json', protected)
write('preparation.json', dict(kernel=str(kernel), arguments=arguments, validation=validation,
    runDirectory=str(run), expectedDeviceId=rack.KNOWN['C24C'], expectedBoard='C24C',
    expectedUid=chosen[1][0]['uid'], sourceConfigurationHashes=before,
    runtimeFiles=stage.inventory(run, 'no-manifest'), serviceStarted=False, consoleLaunched=False,
    phoneInput=False, releaseChanged=False, recognitionSource='d173ee1fdfeca06f2cbdd2fbfae3e8bff9894a70', buildSource='9fa7a859bbeb60495cdbbda326d25010c3ba7961',
    note='Only C24C configured. Vendor Home remains unchanged and will not be used in an editable field.'))
print(json.dumps({'prepared': True, 'kernelHash': validation['build']['sha256'],
                  'receiverCount': 1, 'kernelPort': 9916, 'releaseChanged': False}))
