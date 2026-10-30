"""Offline: rack B's 20 boards added to rack A's prepared kernel, on one kernel. Starts nothing.

Rack B (plugged in 28 Oct) has no phones known yet, so, as rack A's added boards were (28 Oct), each
board is bound to a placeholder phone 'pending-<board>': its pointer moves (pointer_identify.py
names its slot) and its receiver, locked to the placeholder, refuses every phone but logs the one
that tries (device ID, model, address). Receivers 'iMouse2-<board>', console 'Board <board>' in group
'Rack B', ports from 7300; every receiver starts held. The calibration is rack A's placeholder
until a phone's model is known. Rack A's rows are copied unchanged.

The kernel is the 29 Oct build that takes up to forty receivers (rack A's 19 and rack B's 20).

  python prepare_rack_b.py slots/preparation-racka-<date>.json

Reads that archived rack A preparation; writes slots/preparation.json (refuses to overwrite it) and
a run folder under output/. Device IDs stay in output/, never in Git.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'slots'
KERNEL = ROOT / 'output/multiphone-kernel-20261029/iMouse2.Kernel.exe'
PLACEHOLDER = '3848'   # A rack A board still on its placeholder: its device and calibration rows are the template.
FIRST_PORT = 7300


def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 2: raise SystemExit('Usage: prepare_rack_b.py slots/preparation-racka-<date>.json')
    if (OUT / 'preparation.json').exists(): raise SystemExit('slots/preparation.json exists; archive it first.')
    base_path = HERE / sys.argv[1]
    base = load(base_path)
    source = Path(base['runDirectory']) / 'data'
    for name, digest in base['dataSha256'].items():
        if sha(source / name) != digest: raise SystemExit(f'Rack A {name} changed.')
    devices, receivers = load(source / 'devices.json'), load(source / 'receivers.json')
    calibration = load(source / 'pointer-calibration.json')
    rack_b = [b['board'].upper() for b in load(HERE / 'rack-b-boards.json')['boards']]
    if len(rack_b) != 20 or len(set(rack_b)) != 20: raise SystemExit('Expected 20 distinct rack B boards.')
    if set(rack_b) & {d['pid'].upper() for d in devices}: raise SystemExit('A rack B board is already on rack A.')
    device_t = next(d for d in devices if d['pid'] == PLACEHOLDER and d['deviceid'] == f'pending-{PLACEHOLDER}')
    calibration_t = next(c for c in calibration if c['Pid'] == PLACEHOLDER)
    for i, board in enumerate(rack_b):
        phone = f'pending-{board}'
        devices.append(dict(device_t, deviceid=phone, name=f'Board {board}', pid=board, uid=board, gname='Rack B'))
        receivers.append(dict(DeviceId=phone, BoardPid=board, Name=f'iMouse2-{board}', Pipe=f'iMouse2-{board}-frames',
                              Port=FIRST_PORT + 10 * i, Mac=f'02:49:4D:32:{board[:2]}:{board[2:]}'))
        calibration.append(dict(calibration_t, Pid=board))
    if len(receivers) > 40: raise SystemExit(f'{len(receivers)} receivers; the kernel takes forty.')
    for key in ('Port', 'Name', 'Pipe', 'Mac', 'BoardPid', 'DeviceId'):
        if len({str(r[key]).upper() for r in receivers}) != len(receivers): raise SystemExit(f'Receiver {key}s collide.')
    run = ROOT / f"output/candidate-runs/multiphone-racks-ab-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    data = run / 'data'; data.mkdir(parents=True)
    for name, rows in (('devices.json', devices), ('receivers.json', receivers), ('pointer-calibration.json', calibration)):
        (data / name).write_text(json.dumps(rows, indent=2), encoding='utf-8')
    enabled = [d['pid'] for d in devices]
    arguments, previous = [], None
    for a in base['arguments']:
        if a == str(source): a = str(data)
        elif a == str(source / 'receivers.json'): a = str(data / 'receivers.json')
        elif previous in ('--input-pid', '--hold-receivers'): a = ','.join(enabled)
        arguments.append(a); previous = a
    if str(source) in ' '.join(arguments): raise SystemExit('Kernel arguments were not rewritten.')
    preparation = dict(base, runDirectory=str(run), kernel=str(KERNEL), kernelSha256=sha(KERNEL.with_suffix('.dll')),
                       arguments=arguments, inputEnabled=enabled, held=enabled, boards=enabled,
                       receivers=[dict(board=r['BoardPid'], name=r['Name'], port=r['Port']) for r in receivers],
                       derivedFrom=str(base_path.relative_to(HERE)).replace('\\', '/'), rackB=rack_b,
                       dataSha256={n: sha(data / n) for n in ('devices.json', 'receivers.json', 'pointer-calibration.json')})
    (OUT / 'preparation.json').write_text(json.dumps(preparation, indent=2), encoding='utf-8')
    print(json.dumps(dict(boards=len(enabled), rackB=len(rack_b), run=str(run.relative_to(ROOT)))))


if __name__ == '__main__':
    main()
