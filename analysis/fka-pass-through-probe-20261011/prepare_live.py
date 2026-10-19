"""Read-only rack preflight and isolated files for the approved C24C window."""
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from PIL import Image

record = Path(__file__).resolve().parent
repo = record.parents[1]
main = repo.parent / 'iMouseXP-2.0'
live = record / 'live-20261011'
if live.exists():
    raise SystemExit('Refusing to replace live record')
live.mkdir()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def get(path):
    raw = urllib.request.urlopen('http://127.0.0.1:9913/api/' + path, timeout=5).read()
    return json.loads(raw)['data']

states = {path: get(path) for path in ('input/status', 'kernel/status', 'device/get')}
(live / 'release-api-before.json').write_text(json.dumps(states, indent=2), encoding='utf-8')
assert not any(p['active'] or p['releasing'] for p in states['input/status']['phones']), 'Active work found'
other = next(p for p in states['input/status']['phones'] if p['id'] == 'FE:A9:BC:D7:A0:44')
assert not other['owned'] and other['generation'] == 0, 'C241 is in use or has unexpected history'
assert states['kernel/status']['allowed'] == ['C24C', 'C241']
assert states['kernel/status']['receiver_pid'] == 2360
assert sha(record / 'build/iMouse2.Kernel.dll').upper() == 'DC3EF3A46D81F2F3D91BFF0757A0B7564AE1E284FF1FD4BEA83B717BE5AF49B4'
assert sha(main / 'release/iMouse2-kernel-two-phone/iMouse2.Kernel.dll').upper() == 'BD1A68168E9270F029336CF8E13FF85E9B15FD67951EF545D1E973C2BFE634FC'
snapshot = live / 'release-snapshot'
snapshot.mkdir()
copied = []
for directory in ('release/iMouse2-kernel-two-phone', 'analysis/two-phone-config'):
    for source in (main / directory).iterdir():
        if not source.is_file():
            continue
        target = snapshot / directory / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        assert sha(source) == sha(target)
        copied.append((target.relative_to(snapshot).as_posix(), sha(target)))
for source in (main / 'Open iMouse 2.0.ps1', main / '.claude/worktrees/keyboard-spec-reconcile/tools/kernel-window/Stop-ConsoleProcessGracefully.ps1'):
    target = snapshot / source.name
    shutil.copy2(source, target)
    assert sha(source) == sha(target)
    copied.append((target.relative_to(snapshot).as_posix(), sha(target)))
(snapshot / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in copied), encoding='utf-8')
config = live / 'kernel data'
config.mkdir()
phone_id = '86:1D:4A:04:2F:F6'
selections = [('devices.json', 'deviceid', phone_id), ('receivers.json', 'DeviceId', phone_id), ('pointer-calibration.json', 'Pid', 'C24C')]
for name, field, value in selections:
    entries = json.loads((main / 'analysis/two-phone-config' / name).read_text(encoding='utf-8-sig'))
    selected = [entry for entry in entries if entry[field] == value]
    assert len(selected) == 1, (name, selected)
    if name == 'devices.json':
        assert selected[0]['pid'] == 'C24C' and selected[0]['uid'] == 'C24CBFBD'
    (config / name).write_text(json.dumps(selected, indent=2), encoding='utf-8')
settings = Path(os.environ['APPDATA']) / 'iMouse2/settings.json'
metadata = {'time_utc': datetime.now(timezone.utc).isoformat(), 'operator_settings_sha256': sha(settings), 'operator_settings_mtime_ns': settings.stat().st_mtime_ns,
    'release_kernel_sha256': sha(main / 'release/iMouse2-kernel-two-phone/iMouse2.Kernel.dll'),
    'release_console_sha256': sha(main / 'release/iMouse2-two-phone-candidate/iMouse2.dll'),
    'receiver_sha256': sha(main / 'tools/airplay/uxplay/build-imouse/uxplay.exe'),
    'candidate_sha256': sha(record / 'build/iMouse2.Kernel.dll')}
(live / 'preflight-hashes.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
raw = urllib.request.urlopen('http://127.0.0.1:9913/api/pic/screenshot?id=' + phone_id + '&binary=true', timeout=5).read()
assert raw[:2] == b'BM', 'No mirrored frame'
(live / 'original-fka.bmp').write_bytes(raw)
Image.open(live / 'original-fka.bmp').save(live / 'original-fka.png')
print(f'{len(copied)} release files copied and verified; C241 free at generation 0; C24C-only config prepared')
print(live / 'original-fka.png')
