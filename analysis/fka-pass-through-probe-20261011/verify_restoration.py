"""Read-only release verification after the approved C24C probe window."""
import hashlib
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

record = Path(__file__).resolve().parent
main = record.parents[2] / 'iMouseXP-2.0'
live = record / 'live-20261011'
output = live / 'restoration-verified.json'
if output.exists():
    raise SystemExit('Refusing to replace an existing restoration record')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def get(path):
    return json.loads(urllib.request.urlopen('http://127.0.0.1:9913/api/' + path, timeout=5).read())['data']

before = json.loads((live / 'preflight-hashes.json').read_text(encoding='utf-8-sig'))
settings = Path(os.environ['APPDATA']) / 'iMouse2/settings.json'
paths = {
    'release_kernel_sha256': main / 'release/iMouse2-kernel-two-phone/iMouse2.Kernel.dll',
    'release_console_sha256': main / 'release/iMouse2-two-phone-candidate/iMouse2.dll',
    'receiver_sha256': main / 'tools/airplay/uxplay/build-imouse/uxplay.exe',
    'candidate_sha256': record / 'build/iMouse2.Kernel.dll',
    'operator_settings_sha256': settings,
}
hashes = {key: sha(path) for key, path in paths.items()}
assert all(hashes[key] == before[key] for key in hashes), 'Binary/settings hash changed'

stable_files = []
for line in (live / 'release-snapshot/SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
    digest, relative = line.split('  ', 1)
    if relative.startswith('release/') or relative in (
        'Open iMouse 2.0.ps1', 'analysis/two-phone-config/devices.json',
        'analysis/two-phone-config/receivers.json', 'analysis/two-phone-config/pointer-calibration.json'
    ):
        assert sha(main / relative) == digest, relative
        stable_files.append(relative)

process_command = "$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('iMouse2.Kernel.exe','iMouse2.exe','uxplay.exe') } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine) | ConvertTo-Json -Depth 4"
processes = json.loads(subprocess.check_output(['powershell.exe', '-NoProfile', '-Command', process_command], text=True, encoding='utf-8-sig'))
expected = {
    42780: main / 'release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe',
    804: main / 'release/iMouse2-two-phone-candidate/iMouse2.exe',
    42720: paths['receiver_sha256'],
    24004: paths['receiver_sha256'],
}
assert len(processes) == 4 and {p['ProcessId'] for p in processes} == set(expected), 'Unexpected rack/test process'
for process in processes:
    assert Path(process['ExecutablePath']) == expected[process['ProcessId']], 'Wrong process path'
    if process['ProcessId'] in (42720, 24004):
        assert process['ParentProcessId'] == 42780

kernel = get('kernel/status')
states = get('input/status')
assert kernel['allowed'] == ['C24C', 'C241'] and len(kernel['receivers']) == 2
assert {r['receiver_pid'] for r in kernel['receivers']} == {42720, 24004}
assert all(r['live'] for r in kernel['receivers']), 'Mirroring incomplete'
assert len(states['phones']) == 2
assert all(not any(p[k] for k in ('active', 'stopped', 'releasing', 'release_failed')) for p in states['phones'])
other = next(p for p in states['phones'] if p['id'] == 'FE:A9:BC:D7:A0:44')
assert not other['owned'] and other['generation'] == 0, 'Unexpected C241 control history'
# The installed console has already been returned to the operator. Do not close it or
# forcibly release an idle C24C lease merely to make a later snapshot look free.
initial = json.loads((live / 'console-restored.json').read_text(encoding='utf-8-sig'))
assert all(not p['owned'] and not p['active'] and p['generation'] == 0 for p in initial['input']['phones'])

for name, phone in (('C24C', '86:1D:4A:04:2F:F6'), ('C241', 'FE:A9:BC:D7:A0:44')):
    raw = urllib.request.urlopen('http://127.0.0.1:9913/api/pic/screenshot?id=' + phone + '&binary=true', timeout=5).read()
    assert raw[:2] == b'BM', name
    path = live / ('release-restored-' + name + '.bmp')
    path.write_bytes(raw)
    Image.open(path).save(path.with_suffix('.png'))

result = {
    'time_utc': datetime.now(timezone.utc).isoformat(),
    'hashes': hashes, 'release_hashes_unchanged': True,
    'stable_release_files_verified': stable_files,
    'operator_settings_content_unchanged': True,
    'operator_settings_mtime_ns_before': before['operator_settings_mtime_ns'],
    'operator_settings_mtime_ns_after': settings.stat().st_mtime_ns,
    'processes': processes, 'kernel': kernel, 'input': states,
    'test_processes_gone': True, 'both_phones_mirroring': True,
    'both_free_immediately_after_console_restore': True,
    'C24C_idle_lease_at_later_verification': next(p for p in states['phones'] if p['id'] == '86:1D:4A:04:2F:F6')['owned'],
    'idle_lease_note': 'If held: acquired after return to the installed console; owner not exposed by status. No attempt made to disturb it.',
    'C241_test_input': 'None: absent from test configuration; no test request addressed it',
    'FKA_restoration': 'Operator physically Off then On; restore-check-pending/before.png verifies On and original appearance before the final baseline',
}
output.write_text(json.dumps(result, indent=2), encoding='utf-8')
print('Restoration verified: original release, both live phones, no test processes; binary/config/settings hashes unchanged.')
print('C24C has an idle lease at this later snapshot:', result['C24C_idle_lease_at_later_verification'])
print('Settings timestamp changed:', result['operator_settings_mtime_ns_before'] != result['operator_settings_mtime_ns_after'])
print(output)
