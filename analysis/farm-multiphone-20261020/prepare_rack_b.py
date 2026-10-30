"""Offline: rack B's 20 boards on rack A's prepared kernel, in two steps, as rack A's added boards
were (28 Oct). Starts nothing.

  python prepare_rack_b.py pending slots/preparation-racka-<date>.json
      Each rack B board bound to a placeholder phone 'pending-<board>': its pointer moves
      (identify_rack_b.py names its slot) and its receiver 'iMouse2-<board>', locked to the
      placeholder, refuses every phone but logs the one that tries (device ID, model, address);
      learn_rack_b.py makes each phone try. Console 'Board <board>' in group 'Rack B', ports from
      7300, calibration rack A's placeholder.
  python prepare_rack_b.py bound slots/preparation-racksab-pending-<date>.json
      Each rack B board bound to the one phone its receiver logged, named 'Phone B<slot>' /
      'iMouse2-B<slot>' from rack-b-slots.json (a board with no logged phone stays on its
      placeholder). Every 4.7-inch phone (6s/7/8, both racks) gets the measured calibration.

Rack A's other rows are copied unchanged. The kernel is the 29 Oct build that takes up to forty
receivers. Every receiver starts held. Writes slots/preparation.json (refuses to overwrite it) and
a run folder under output/. Device IDs stay in output/, never in Git.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'slots'
KERNEL = ROOT / 'output/multiphone-kernel-20261029/iMouse2.Kernel.exe'
PLACEHOLDER = '3848'   # A rack A board still on its placeholder: its device and calibration rows are the template.
FIRST_PORT = 7300
sys.path.insert(0, str(HERE))
from prepare_rack_a import MODELS, REQUEST  # noqa: E402
from card_survey import SMALL  # noqa: E402

# A 4.7-inch phone's frame: its 375x667 screen letterboxed in 500x1080 from y 95, 5.61 px per unit
# (pointer_measure.py on rack A slot 2, 30 Oct).
SMALL_CALIBRATION = dict(Width=500, Height=1080, OriginX=SMALL['ox'], OriginY=SMALL['oy'],
                         PixelsPerUnitX=SMALL['ppu'], PixelsPerUnitY=SMALL['ppu'])


def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def logged_phone(run, board):
    """The one phone that asked board's receiver to mirror, in any racks A+B run: (device ID, model)."""
    found = set()
    for log in sorted(Path(run).parent.glob(f'multiphone-racks-ab-*/data/receiver-{board}.log')):
        text = re.sub(r'^\S+ ', '', log.read_text(encoding='utf-8', errors='replace'), flags=re.M)
        found |= {(m.group(3), m.group(2)) for m in REQUEST.finditer(text)}
    if len({f[0] for f in found}) > 1: raise SystemExit(f'{board}: more than one phone in its receiver logs.')
    return found.pop() if found else None


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ('pending', 'bound'):
        raise SystemExit('Usage: prepare_rack_b.py pending|bound slots/preparation-<archived>.json')
    step = sys.argv[1]
    if (OUT / 'preparation.json').exists(): raise SystemExit('slots/preparation.json exists; archive it first.')
    base_path = HERE / sys.argv[2]
    base = load(base_path)
    source = Path(base['runDirectory']) / 'data'
    for name, digest in base['dataSha256'].items():
        if sha(source / name) != digest: raise SystemExit(f'Base {name} changed.')
    devices, receivers = load(source / 'devices.json'), load(source / 'receivers.json')
    calibration = load(source / 'pointer-calibration.json')
    rack_b = [b['board'].upper() for b in load(HERE / 'rack-b-boards.json')['boards']]
    if len(rack_b) != 20 or len(set(rack_b)) != 20: raise SystemExit('Expected 20 distinct rack B boards.')
    learned = {}
    if step == 'pending':
        if set(rack_b) & {d['pid'].upper() for d in devices}: raise SystemExit('A rack B board is already on the kernel.')
        device_t = next(d for d in devices if d['pid'] == PLACEHOLDER and d['deviceid'] == f'pending-{PLACEHOLDER}')
        calibration_t = next(c for c in calibration if c['Pid'] == PLACEHOLDER)
        for i, board in enumerate(rack_b):
            phone = f'pending-{board}'
            devices.append(dict(device_t, deviceid=phone, name=f'Board {board}', pid=board, uid=board, gname='Rack B'))
            receivers.append(dict(DeviceId=phone, BoardPid=board, Name=f'iMouse2-{board}', Pipe=f'iMouse2-{board}-frames',
                                  Port=FIRST_PORT + 10 * i, Mac=f'02:49:4D:32:{board[:2]}:{board[2:]}'))
            calibration.append(dict(calibration_t, Pid=board))
    else:
        # The base may itself be a bound step (30 Oct: 12 phones bound, 8 learned afterwards); a board
        # already bound keeps its binding.
        slots = {v['board']: int(k) for k, v in load(HERE / 'rack-b-slots.json')['slots'].items()}
        for board in rack_b:
            d = next(x for x in devices if x['pid'] == board)
            r = next(x for x in receivers if x['BoardPid'] == board)
            if r['DeviceId'] != d['deviceid']: raise SystemExit(f'{board}: receiver and device bindings differ.')
            if d['deviceid'] != f'pending-{board}':
                if r['Name'] != f"iMouse2-B{slots.get(board)}": raise SystemExit(f'{board}: bound but not to its slot name.')
                continue
            got = logged_phone(base['runDirectory'], board) if board in slots else None
            if got is None: continue
            phone, model = got
            name, width, height = MODELS.get(model, ('iPhone', 0, 0))
            learned[board] = dict(slot=slots[board], model=model)
            d.update(deviceid=phone, name=f'Phone B{slots[board]}', device_name=name, width=width, height=height)
            r.update(DeviceId=phone, Name=f'iMouse2-B{slots[board]}')
        # Every 4.7-inch phone, rack A's included (slots 2, 5-8 were on the September placeholder).
        small = {d['pid'] for d in devices if (d.get('width'), d.get('height')) == (375, 667)}
        calibration = [dict(c, **SMALL_CALIBRATION) if c['Pid'] in small else c for c in calibration]
    if len(receivers) > 40: raise SystemExit(f'{len(receivers)} receivers; the kernel takes forty.')
    for key in ('Port', 'Name', 'Pipe', 'Mac', 'BoardPid', 'DeviceId'):
        if len({str(r[key]).upper() for r in receivers}) != len(receivers): raise SystemExit(f'Receiver {key}s collide.')
    run = ROOT / f"output/candidate-runs/multiphone-racks-ab-{step}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
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
                       derivedFrom=str(base_path.relative_to(HERE)).replace('\\', '/'), rackB=rack_b, rackBStep=step,
                       rackBLearned=learned,
                       dataSha256={n: sha(data / n) for n in ('devices.json', 'receivers.json', 'pointer-calibration.json')})
    (OUT / 'preparation.json').write_text(json.dumps(preparation, indent=2), encoding='utf-8')
    print(json.dumps(dict(step=step, boards=len(enabled), bound=len(learned), run=str(run.relative_to(ROOT)))))


if __name__ == '__main__':
    main()
