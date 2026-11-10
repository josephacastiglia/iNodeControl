"""Offline: rack A with its other boards added to the four slot phones. Starts nothing.

Rack A has 19 boards; the farm drove four (slots 16, 17, 18, 20). The September full-rack config
lists the rest, but with no phone bound ('unbound-<board>'), and the kernel takes input only for
a board bound to an explicit phone. So, in two steps (28 Oct):

  python prepare_rack_a.py pending   each added board bound to a placeholder phone 'pending-<board>':
                                      its pointer moves (pointer_identify.py --watch names its slot)
                                      and its receiver, locked to that placeholder, refuses every phone
                                      but logs the one that tries: its device ID, model and address.
  python prepare_rack_a.py bound     each added board bound to the one phone its receiver logged, named
                                      'Phone <slot>' / 'iMouse2-<slot>' from phone-slots.json.

Boards listed in ADDED only (C241 since 28 Oct, on the operator's word that it is no longer their phone). The bound step keeps a board with no slot on its placeholder:
28 Oct, five boards moved no phone the operator could see (their slots are empty, flat or off). The four slot phones are copied unchanged. Every
receiver starts held (Release-Receiver.ps1 advertises one at a time). Device IDs stay in the run
folders under output/, never in Git. Writes slots/preparation.json; refuses to overwrite it
(archive the previous one first).
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import farm_paths  # noqa: E402
from rack_kernels import kernel_folder  # noqa: E402  (beside this script)
STATE = farm_paths.rack_state(HERE)  # phone-slots.json: here in a checkout, the data folder when installed
RUNS = farm_paths.run_root(ROOT)
# --source DIR names the full-rack config (devices, receivers, calibration of every board).
FULL = farm_paths.source_option(sys.argv, ROOT.parent / 'iMouseXP-2.0/analysis/full-rack-config')  # release-lint: dev-fallback
OUT = kernel_folder()   # slots/: the current preparation and the earlier ones this one derives from
ADDED = ('E414', '3523', 'C415', '764E', '374C', '3848', 'D446', '9515', '7949', '704E', '694E', '1248', '1814', 'D142',
         'C241')   # Untouchable until 28 Oct, when the operator said its phone is no longer theirs.
# Screen sizes in points by model identifier; an unknown model keeps the September placeholder.
MODELS = {'iPhone11,8': ('iPhone XR', 414, 896), 'iPhone12,1': ('iPhone 11', 414, 896),
          'iPhone12,8': ('iPhone SE (2nd)', 375, 667), 'iPhone14,6': ('iPhone SE (3rd)', 375, 667),
          'iPhone8,1': ('iPhone 6s', 375, 667), 'iPhone9,1': ('iPhone 7', 375, 667), 'iPhone9,3': ('iPhone 7', 375, 667),
          'iPhone10,1': ('iPhone 8', 375, 667), 'iPhone10,4': ('iPhone 8', 375, 667),
          'iPhone10,2': ('iPhone 8 Plus', 414, 736), 'iPhone10,5': ('iPhone 8 Plus', 414, 736)}
# The address is IPv4 or IPv6 (phone 14 asked over IPv6, 28 Oct).
REQUEST = re.compile(r'Remote: (\S+)\s*\n(?:.*\n){0,3}?.*connection request from .* \((iPhone[\d,]+)\) with deviceID = ([0-9A-F:]{17})')


def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def logged_phone(run, board):
    """The one phone that asked board's receiver to mirror, in any rack A run (a board left on its
    placeholder in a bound run is tried there, as E414 was): (device ID, model, address)."""
    logs = sorted(Path(run).parent.glob(f'multiphone-racka-*/data/receiver-{board}.log'))
    if not logs: raise SystemExit(f'{board}: no receiver log in a rack A run; connect its phone first.')
    found = set()
    for log in logs:
        text = re.sub(r'^\S+ ', '', log.read_text(encoding='utf-8', errors='replace'), flags=re.M)   # drop timestamps
        found |= {(m.group(3), m.group(2), m.group(1)) for m in REQUEST.finditer(text)}
    if len({f[0] for f in found}) != 1: raise SystemExit(f'{board}: expected one phone in its receiver log, found {len(found)}.')
    return sorted(found)[-1]


def main():
    step = sys.argv[1] if len(sys.argv) > 1 else ''
    if step not in ('pending', 'bound'): raise SystemExit('Usage: prepare_rack_a.py pending|bound')
    if (OUT / 'preparation.json').exists(): raise SystemExit('slots/preparation.json exists; archive it first.')
    base = load(OUT / 'preparation-4phone-20261020.json')
    source = Path(base['runDirectory']) / 'data'
    for name, digest in base['dataSha256'].items():
        if sha(source / name) != digest: raise SystemExit(f'Four-phone {name} changed.')
    if sha(Path(base['kernel']).with_suffix('.dll')) != base['kernelSha256']: raise SystemExit('Kernel changed.')
    devices, receivers = load(source / 'devices.json'), load(source / 'receivers.json')
    calibration = load(source / 'pointer-calibration.json')
    full = {name: {r['pid' if 'pid' in r else 'BoardPid' if 'BoardPid' in r else 'Pid']: r for r in load(FULL / name)}
            for name in ('devices.json', 'receivers.json', 'pointer-calibration.json')}
    slots = {v['board']: int(k) for k, v in load(STATE / 'phone-slots.json')['slots'].items()}
    xr = next(c for c in calibration if c['Pid'] == 'C24C')
    # The bound step reads the pending run's receiver logs (its preparation archived under this name).
    pending_run = load(OUT / 'preparation-pending.json')['runDirectory'] if step == 'bound' else None
    learned = {}
    for board in ADDED:
        d, r, c = (dict(full['devices.json'][board]), dict(full['receivers.json'][board]), dict(full['pointer-calibration.json'][board]))
        # C241 was bound in September (the phone then in hand); it is identified afresh like the rest.
        if (board != 'C241' and not d['deviceid'].startswith('unbound-')) or r['DeviceId'] != d['deviceid']:
            raise SystemExit(f'{board}: September binding changed.')
        # A board with no slot yet stays on its placeholder in the bound step too: five boards showed no
        # pointer (28 Oct) while the operator counts 16 working phones, so they are tried again.
        if step == 'pending' or board not in slots:
            phone = f'pending-{board}'
            d.update(deviceid=phone, name=f'Board {board}', gname='Rack A')
            r.update(DeviceId=phone)
        else:
            phone, model, address = logged_phone(pending_run, board)
            name, width, height = MODELS.get(model, ('iPhone', 0, 0))
            learned[board] = dict(slot=slots[board], model=model, address=address)
            d.update(deviceid=phone, name=f'Phone {slots[board]}', device_name=name, width=width, height=height, gname='Rack A')
            r.update(DeviceId=phone, Name=f'iMouse2-{slots[board]}')
            if model == 'iPhone11,8': c = dict(xr, Pid=board)   # Same model as the four: their measured scale.
        devices.append(d); receivers.append(r); calibration.append(c)
    if len({r['Port'] for r in receivers}) != len(receivers): raise SystemExit('Receiver ports collide.')
    if len({r['Name'] for r in receivers}) != len(receivers): raise SystemExit('Receiver names collide.')
    run = RUNS / f"output/candidate-runs/multiphone-racka-{step}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
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
    preparation = dict(base, runDirectory=str(run), arguments=arguments, inputEnabled=enabled, held=enabled, boards=enabled,
                       receivers=[dict(board=r['BoardPid'], name=r['Name'], port=r['Port']) for r in receivers],
                       slots={b: s for b, s in sorted(slots.items(), key=lambda kv: kv[1]) if b in enabled},
                       derivedFrom='slots/preparation-4phone-20261020.json', rackAStep=step, pendingRun=pending_run,
                       added=list(ADDED), learned={b: dict(slot=v['slot'], model=v['model']) for b, v in learned.items()},
                       dataSha256={n: sha(data / n) for n in ('devices.json', 'receivers.json', 'pointer-calibration.json')})
    (OUT / 'preparation.json').write_text(json.dumps(preparation, indent=2), encoding='utf-8')
    if learned: (run / 'learned-addresses.json').write_text(json.dumps({b: v['address'] for b, v in learned.items()}, indent=2), encoding='utf-8')
    print(json.dumps(dict(prepared=step, boards=len(enabled), run=str(run.relative_to(RUNS)),
                          receivers=[r['Name'] for r in receivers])))


if __name__ == '__main__':
    main()
