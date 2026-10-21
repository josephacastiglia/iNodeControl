"""Moves one board's pointer in a square for a few seconds so the operator can see which phone in
the box it drives, and checks that the move shows up on that board's own mirrored screen.

Pointer moves only: no click, key, swipe or reset. Uses the kernel's lease for that one phone and
releases it. Records every frame and result under identify/<board>-<utc>/.

  python pointer_identify.py --board C214
"""
import argparse
import hashlib
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from identify_phone import acquire, post, request  # noqa: E402

BASE = 'http://127.0.0.1:9916/api'
SQUARE = [(150, 450), (350, 450), (350, 650), (150, 650)]
ROUNDS = 4
STEP_S = 0.45


def shot(device_id):
    import urllib.request
    with urllib.request.urlopen(f'{BASE}/pic/screenshot?id={device_id}', timeout=8) as response:
        return response.read(), dict(response.headers)


def changed_fraction(a, b):
    x = np.asarray(Image.open(io.BytesIO(a)).convert('L'), dtype=np.int16)
    y = np.asarray(Image.open(io.BytesIO(b)).convert('L'), dtype=np.int16)
    return float((np.abs(x - y) > 24).mean()) if x.shape == y.shape else 1.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', required=True)
    board = parser.parse_args().board.upper()
    devices = request(BASE, 'GET', '/device/get', timeout=8)['list']
    device = next((d for d in devices if d.get('pid', '').upper() == board), None)
    if not device or device['deviceid'] in ('*', '') or device['deviceid'].startswith('unbound-'):
        raise SystemExit(f'{board} has no bound phone; it cannot be identified by its own screen.')
    receivers = {r['deviceid']: r for r in request(BASE, 'GET', '/kernel/status', timeout=8)['receivers']}
    others = [d for d in receivers if d != device['deviceid'] and receivers[d]['live'] and d not in ('*', '')]
    if not receivers.get(device['deviceid'], {}).get('live'): raise SystemExit(f'{board} is not mirroring.')
    folder = HERE / 'identify' / f"{board}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    folder.mkdir(parents=True)
    record = dict(board=board, deviceId=device['deviceid'], moves=[], frames=[], phoneInput='pointer moves only')

    def frame(role, device_id):
        raw, headers = shot(device_id)
        name = f"{len(record['frames']) + 1:02d}-{role}.bmp"
        (folder / name).write_bytes(raw)
        record['frames'].append(dict(role=role, device=device_id, file=name, sha256=hashlib.sha256(raw).hexdigest(),
                                     sequence=headers.get('X-iMouse-Frame-Sequence'), ageMs=headers.get('X-iMouse-Frame-Age-Ms')))
        return raw

    token = acquire(BASE, device['deviceid'])
    try:
        post(BASE, '/mouse/move', dict(id=device['deviceid'], token=token, x=SQUARE[0][0], y=SQUARE[0][1]))
        time.sleep(1.0)
        before = frame('before', device['deviceid'])
        before_others = {d: frame('other-before', d) for d in others}
        for _ in range(ROUNDS):
            for x, y in SQUARE[1:] + SQUARE[:1]:
                got = post(BASE, '/mouse/move', dict(id=device['deviceid'], token=token, x=x, y=y))
                record['moves'].append(dict(x=x, y=y, code=got.get('code')))
                if got.get('code') != 0: raise RuntimeError(f'move refused: {got}')
                time.sleep(STEP_S)
        post(BASE, '/mouse/move', dict(id=device['deviceid'], token=token, x=SQUARE[2][0], y=SQUARE[2][1]))
        time.sleep(0.6)
        after = frame('after', device['deviceid'])
        after_others = {d: frame('other-after', d) for d in others}
    finally:
        record['release'] = post(BASE, '/input/release', dict(id=device['deviceid'], token=token)).get('code')
    record['ownChange'] = changed_fraction(before, after)
    record['otherChange'] = {d: changed_fraction(before_others[d], after_others[d]) for d in others}
    # The pointer is a small dot: a pointer-only move changes a little of the frame, not the whole screen.
    record['ownScreenMoved'] = 0.0005 < record['ownChange'] < 0.2
    (folder / 'record.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(dict(board=board, ownChange=round(record['ownChange'], 5),
                          otherChange={k[-5:]: round(v, 5) for k, v in record['otherChange'].items()},
                          ownScreenMoved=record['ownScreenMoved'], folder=str(folder.relative_to(HERE)))))


if __name__ == '__main__':
    main()
