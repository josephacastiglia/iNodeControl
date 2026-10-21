"""Offline: the held multi-phone setup with slot names and F215 locked to its phone. Starts nothing.

Copies the held run's mappings, receivers and calibrations, then changes only:
  * each phone's console name to 'Phone <slot>' and its receiver to 'iMouse2-<slot>';
  * F215's phone and receiver from '*' (any phone) to the phone that connected to it on
    20 Oct 21:40 (slot 16, an iPhone XR), which also enables F215 for input.
Slots come from phone-slots.json, which the operator confirmed. Writes its own run folder and
slots/preparation.json; refuses to overwrite either.
"""
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE / 'held' / 'preparation.json'
RUN = ROOT / 'output/candidate-runs/multiphone-slots-20261020'
OUT = HERE / 'slots'


def f215_phone():
    """The phone that connected to the unlocked iMouse2-F215 on 20 Oct 21:40:38 (iPhone11,8)."""
    log = ROOT / 'output/candidate-runs/multiphone-held-20261020/data/receiver-F215.log'
    ids = set(re.findall(r'connection request from iPhone \(iPhone11,8\) with deviceID = ([0-9A-F:]{17})', log.read_text(encoding='utf-8')))
    if len(ids) != 1: raise SystemExit(f'Expected one phone in the F215 receiver log, found {len(ids)}.')
    return ids.pop()


def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if RUN.exists() or (OUT / 'preparation.json').exists(): raise SystemExit('Slot preparation exists; never overwrite it.')
    held = load(SOURCE)
    source = Path(held['runDirectory']) / 'data'
    for name, digest in held['dataSha256'].items():
        if sha(source / name) != digest: raise SystemExit(f'Held {name} changed.')
    if sha(Path(held['kernel']).with_suffix('.dll')) != held['kernelSha256']: raise SystemExit('Held kernel changed.')
    slots = {v['board']: int(k) for k, v in load(HERE / 'phone-slots.json')['slots'].items()}
    devices, receivers = load(source / 'devices.json'), load(source / 'receivers.json')
    if sorted(slots) != sorted(d['pid'] for d in devices): raise SystemExit('Slots and boards differ.')
    for d in devices:
        d['name'] = f"Phone {slots[d['pid']]}"
        if d['pid'] == 'F215':
            if d['deviceid'] != '*': raise SystemExit('F215 binding changed.')
            d.update(deviceid=f215_phone(), device_name='iPhone XR')
    for r in receivers:
        r['Name'] = f"iMouse2-{slots[r['BoardPid']]}"
        if r['BoardPid'] == 'F215':
            if r['DeviceId'] != '*': raise SystemExit('F215 receiver binding changed.')
            r['DeviceId'] = f215_phone()
    data = RUN / 'data'; data.mkdir(parents=True)
    (data / 'devices.json').write_text(json.dumps(devices, indent=2), encoding='utf-8')
    (data / 'receivers.json').write_text(json.dumps(receivers, indent=2), encoding='utf-8')
    (data / 'pointer-calibration.json').write_bytes((source / 'pointer-calibration.json').read_bytes())
    enabled = [d['pid'] for d in devices]
    arguments, previous = [], None
    for a in held['arguments']:
        if a == str(source): a = str(data)
        elif a == str(source / 'receivers.json'): a = str(data / 'receivers.json')
        elif previous == '--input-pid': a = ','.join(enabled)
        arguments.append(a); previous = a
    if str(source) in ' '.join(arguments): raise SystemExit('Kernel arguments were not rewritten.')
    preparation = dict(held, runDirectory=str(RUN), arguments=arguments, inputEnabled=enabled,
                       receivers=[dict(board=r['BoardPid'], name=r['Name'], port=r['Port']) for r in receivers],
                       slots={b: s for b, s in sorted(slots.items(), key=lambda kv: kv[1])},
                       derivedFrom=str(SOURCE.relative_to(HERE)), f215BoundTo='slot 16 phone (receiver log 20 Oct 21:40)',
                       dataSha256={n: sha(data / n) for n in ('devices.json', 'receivers.json', 'pointer-calibration.json')})
    OUT.mkdir(exist_ok=True)
    (OUT / 'preparation.json').write_text(json.dumps(preparation, indent=2), encoding='utf-8')
    print(json.dumps(dict(prepared=True, inputEnabled=enabled, receivers=preparation['receivers'])))


if __name__ == '__main__':
    main()
