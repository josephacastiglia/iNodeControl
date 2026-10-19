"""Read-only file/data preflight; no socket or phone commands."""
import hashlib
import json
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OFFLINE = ROOT/'analysis/farm-recovery-20261019'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path): return json.loads(path.read_text(encoding='utf-8-sig'))
prep = load(OFFLINE/'preparation.json')
validation = load(OFFLINE/'validation.json')
if (not validation['python']['passed'] or validation['native']['passed'] != 564
        or not validation['retained']['passed'] or not validation['negativeControls']['passed']):
    raise SystemExit('Offline checks are incomplete.')
for name, digest in validation['productSourceFiles'].items():
    if sha(ROOT/name) != digest: raise SystemExit('Product source changed: '+name)
if sha(Path(prep['assembly'])) != prep['nativeSha256'] or sha(Path(prep['kernel']).with_suffix('.dll')) != prep['kernelSha256']:
    raise SystemExit('Prepared binary changed.')
archive = Path(validation['archive'])
manifest = {line.split('  ', 1)[1]: line.split('  ', 1)[0]
    for line in (archive/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines()}
probe = ROOT/'output/farm-recovery-native-probe-20261019/NativeProbe.exe'
for name in ('NativeProbe.exe', 'NativeProbe.dll'):
    if sha(probe.parent/name) != manifest['headless-driver/'+name]: raise SystemExit('Prepared native driver changed.')
backend = Path(prep['backendData'])
if sha(backend/'draft-creations'/prep['creationId']/'record.json') != prep['sourceProof']['creationRecordSha256']:
    raise SystemExit('Retained source creation changed.')
with sqlite3.connect('file:'+str(backend/'preparation-schedule.db')+'?mode=ro', uri=True) as db:
    config = json.loads(db.execute('SELECT document FROM preparation_config WHERE id=1').fetchone()[0])
    if config.get('enabled'): raise SystemExit('Recurring preparation is enabled; do not start this test backend.')
devices = load(Path(prep['runDirectory'])/'data/devices.json')
receivers = load(Path(prep['runDirectory'])/'data/receivers.json')
calibrations = load(Path(prep['runDirectory'])/'data/pointer-calibration.json')
if (len(devices) != 1 or devices[0]['pid'] != 'C24C' or devices[0]['uid'] != prep['expectedUid']
        or len(receivers) != 1 or receivers[0]['DeviceId'] != prep['expectedDeviceId']
        or receivers[0]['BoardPid'] != 'C24C' or receivers[0]['Name'] != 'iMouse2-C24C'
        or len(calibrations) != 1 or calibrations[0].get('Pid') != 'C24C'):
    raise SystemExit('C24C mapping changed.')
protected = load(OFFLINE/'protected-after.json')
for value in protected:
    if sha(Path(value['path'])) != value['sha256']: raise SystemExit('Protected installed file changed: '+value['path'])
options = load(OFFLINE/'native-options.json')
options.update(output=str(HERE/'native-inspection-1'), dataDirectory=str(Path(prep['runDirectory'])/'native-live-1-data'))
if Path(options['output']).exists() or Path(options['dataDirectory']).exists():
    raise SystemExit('Never overwrite a live inspection or replay its pending request.')
(HERE/'native-options-1.json').write_text(json.dumps(options, indent=2), encoding='utf-8')
(HERE/'protected-before.json').write_text(json.dumps(protected, indent=2), encoding='utf-8')
prep.update(nativeProbe=str(probe), nativeProbeSha256=sha(probe), nativeProbeManagedSha256=sha(probe.with_suffix('.dll')), sourcePreserved=True,
    phoneInput=False, desktopControl=False, preparationDisabled=True)
(HERE/'preparation.json').write_text(json.dumps(prep, indent=2), encoding='utf-8')
print(json.dumps(dict(prepared=True, protectedFiles=len(protected), sourcePreserved=True, phoneInput=False)))
