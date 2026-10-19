"""Preserve the release and stage the approved repeat without input or restarts."""
import hashlib
import json
import os
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

record = Path(__file__).resolve().parent
repo = record.parents[1]
main = repo.parent / 'iMouseXP-2.0'
live = record / 'live-repeat-20261011'
live.mkdir(exist_ok=False)

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def get(p): return json.loads(urllib.request.urlopen('http://127.0.0.1:9913/api/' + p, timeout=5).read())['data']
def save(name, value): (live / name).write_text(json.dumps(value, indent=2), encoding='utf-8')

states = {p: get(p) for p in ('kernel/status', 'input/status', 'device/get')}
assert states['kernel/status']['allowed'] == ['C24C', 'C241']
assert states['kernel/status']['receiver_pid'] == 42720
assert not any(p['active'] or p['releasing'] or p['stopped'] for p in states['input/status']['phones'])
other = next(p for p in states['input/status']['phones'] if p['id'] == 'FE:A9:BC:D7:A0:44')
assert not other['owned'] and other['generation'] == 0
save('release-api-before.json', states)
provenance = json.loads((record / 'provenance.json').read_text(encoding='utf-8'))
assert all(sha(repo / name) == digest for name, digest in provenance['source_sha256'].items())
assert all(sha(record / 'build' / name) == digest for name, digest in provenance['build_sha256'].items())

snapshot = live / 'release-snapshot'
snapshot.mkdir()
copied = []
for relative in ('release/iMouse2-kernel-two-phone', 'analysis/two-phone-config'):
    for source in (main / relative).iterdir():
        if source.is_file():
            target = snapshot / relative / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            assert sha(source) == sha(target)
            copied.append((target.relative_to(snapshot).as_posix(), sha(target)))
for source in (main / 'Open iMouse 2.0.ps1', record / 'live-20261011/release-snapshot/Stop-ConsoleProcessGracefully.ps1'):
    target = snapshot / source.name
    shutil.copy2(source, target)
    assert sha(source) == sha(target)
    copied.append((target.relative_to(snapshot).as_posix(), sha(target)))
(snapshot / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in copied), encoding='utf-8')

config = live / 'kernel data'
config.mkdir()
phone = '86:1D:4A:04:2F:F6'
for name, field, value in (('devices.json', 'deviceid', phone), ('receivers.json', 'DeviceId', phone), ('pointer-calibration.json', 'Pid', 'C24C')):
    entries = json.loads((main / 'analysis/two-phone-config' / name).read_text(encoding='utf-8-sig'))
    selected = [e for e in entries if e[field] == value]
    assert len(selected) == 1
    if name == 'devices.json': assert selected[0]['pid'] == 'C24C' and selected[0]['uid'] == 'C24CBFBD'
    (config / name).write_text(json.dumps(selected, indent=2), encoding='utf-8')

candidate_source = repo.parent / 'iMouseXP-2.0-evidence-archive/20261010-typing-mode-ab/build/imouse-candidate-5'
assert sha(candidate_source / 'iMouse2.dll').upper() == 'E5A51FC6204566FA3B48C650FC239A42B158217D8045D2712850173980303AC3'
candidate = live / 'candidate'
candidate.mkdir()
for source in candidate_source.iterdir():
    if source.is_file() and source.suffix in ('.dll', '.exe', '.json', '.pdb'):
        shutil.copy2(source, candidate / source.name)
        assert sha(source) == sha(candidate / source.name)
candidate_data = live / 'console data'
candidate_data.mkdir()
(candidate_data / 'settings.json').write_text(json.dumps({'address':'http://127.0.0.1:9913','theme':'light','trackPointer':False}), encoding='utf-8')

settings = Path(os.environ['APPDATA']) / 'iMouse2/settings.json'
hashes = {
    'operator_settings_sha256': sha(settings), 'operator_settings_mtime_ns': settings.stat().st_mtime_ns,
    'release_kernel_sha256': sha(main / 'release/iMouse2-kernel-two-phone/iMouse2.Kernel.dll'),
    'release_console_sha256': sha(main / 'release/iMouse2-two-phone-candidate/iMouse2.dll'),
    'receiver_sha256': sha(main / 'tools/airplay/uxplay/build-imouse/uxplay.exe'),
    'candidate_kernel_sha256': sha(record / 'build/iMouse2.Kernel.dll'),
    'candidate_console_sha256': sha(candidate / 'iMouse2.dll'),
    'time_utc': datetime.now(timezone.utc).isoformat(),
}
save('preflight-hashes.json', hashes)
raw = urllib.request.urlopen('http://127.0.0.1:9913/api/pic/screenshot?id=' + phone + '&binary=true', timeout=5).read()
assert raw[:2] == b'BM'
(live / 'original-fka.bmp').write_bytes(raw)
Image.open(live / 'original-fka.bmp').save(live / 'original-fka.png')
print('Release snapshot and source/build hashes verified; C24C-only config and isolated preserved console staged.')
print(live / 'original-fka.png')
