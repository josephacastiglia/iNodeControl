"""Offline preparation of one private kernel with four receivers: C24C, C214, 724E and F215. No socket or phone.

C24C's mapping and calibration come from the verified Priority 2 window. C214, 724E and F215
come from the 22 Sep five-phone setup. C241 is excluded. F215's receiver, recorded as
'iMouse2-Phone5', is renamed 'iMouse2-F215'; every other field is copied unchanged. Refuses
to overwrite an existing run folder. Starts nothing.

With --held, prepares the one-at-a-time mode instead: the multi-phone kernel (built with
--hold-receivers) starts with every receiver held, and Release-Receiver.ps1 advertises one
board's receiver at a time, so the phone being connected sees one new choice. It writes its
own run folder and held/preparation.json.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUN = ROOT / 'output/candidate-runs/multiphone-20261020'
FIVE = ROOT.parent / 'iMouseXP-2.0/analysis/five-phone-config'
P2 = ROOT / 'analysis/farm-recovery-live-20261019'
BOARDS = ('C24C', 'C214', '724E', 'F215')
ENABLED = ('C24C', 'C214', '724E')   # F215's receiver is still unbound: it runs for discovery, with no input.
HELD = '--held' in sys.argv[1:]
HELD_KERNEL = ROOT / 'output/multiphone-kernel-20261020/iMouse2.Kernel.exe'
if HELD:
    RUN = ROOT / 'output/candidate-runs/multiphone-held-20261020'
OUT = HERE / 'held' if HELD else HERE


def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if RUN.exists(): raise SystemExit('The multi-phone run folder exists; never overwrite it.')
    previous = load(P2 / 'preparation.json')
    kernel = Path(previous['kernel'])
    if sha(kernel.with_suffix('.dll')) != previous['kernelSha256']: raise SystemExit('Prepared private kernel changed.')
    kernel_sha = previous['kernelSha256']
    if HELD:
        kernel, kernel_sha = HELD_KERNEL, sha(HELD_KERNEL.with_suffix('.dll'))
    verified = Path(previous['runDirectory']) / 'data'
    pick = lambda rows, key, pid: [r for r in rows if r[key].upper() == pid]
    devices, receivers, calibration = [], [], []
    for pid in BOARDS:
        source = verified if pid == 'C24C' else FIVE
        d, r, c = (pick(load(source / 'devices.json'), 'pid', pid), pick(load(source / 'receivers.json'), 'BoardPid', pid),
                   pick(load(source / 'pointer-calibration.json'), 'Pid', pid))
        if not (len(d) == len(r) == len(c) == 1): raise SystemExit(f'{pid}: mapping, receiver or calibration missing or ambiguous.')
        if pid == 'F215':
            if r[0]['Name'] != 'iMouse2-Phone5': raise SystemExit('F215 receiver record changed.')
            r[0] = dict(r[0], Name='iMouse2-F215')
        devices += d; receivers += r; calibration += c
    if len({r['Port'] for r in receivers}) != len(receivers): raise SystemExit('Receiver ports collide.')
    data = RUN / 'data'; data.mkdir(parents=True)
    for name, rows in (('devices.json', devices), ('receivers.json', receivers), ('pointer-calibration.json', calibration)):
        (data / name).write_text(json.dumps(rows, indent=2), encoding='utf-8')
    source_data = str(verified)
    arguments = []
    for a in previous['arguments']:
        if a == source_data: a = str(data)
        elif a == str(verified / 'receivers.json'): a = str(data / 'receivers.json')
        elif a == 'C24C' and arguments and arguments[-1] == '--input-pid': a = ','.join(ENABLED)
        arguments.append(a)
    if source_data in ' '.join(arguments) or ','.join(ENABLED) not in arguments: raise SystemExit('Kernel arguments were not rewritten.')
    if HELD: arguments += ['--hold-receivers', ','.join(BOARDS)]
    preparation = dict(runDirectory=str(RUN), kernel=str(kernel), kernelSha256=kernel_sha, arguments=arguments, held=list(BOARDS) if HELD else [],
                       boards=list(BOARDS), inputEnabled=list(ENABLED), receivers=[dict(board=r['BoardPid'], name=r['Name'], port=r['Port']) for r in receivers],
                       sources={'C24C': str(verified), 'others': str(FIVE)}, excluded=['C241'], renamed={'F215': 'iMouse2-Phone5 -> iMouse2-F215'},
                       dataSha256={n: sha(data / n) for n in ('devices.json', 'receivers.json', 'pointer-calibration.json')},
                       protectedBefore=str(P2 / 'protected-before.json'), serviceStarted=False, phoneInput=False)
    OUT.mkdir(exist_ok=True)
    if (OUT / 'preparation.json').exists(): raise SystemExit('A preparation already exists here; never overwrite it.')
    (OUT / 'preparation.json').write_text(json.dumps(preparation, indent=2), encoding='utf-8')
    print(json.dumps(dict(prepared=True, receivers=preparation['receivers'])))


if __name__ == '__main__':
    main()
