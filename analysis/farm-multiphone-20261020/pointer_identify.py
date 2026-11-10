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
import farm_paths  # noqa: E402
STATE = farm_paths.rack_state(HERE)  # windows/, identify/ ...: beside this script in a checkout, the data folder when installed
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


# Traced in 20 px steps: jumps of 200 px or more timed out the board's 2 s HID write midway on
# rack A's added boards (3523, 28 Oct), while runs of 20 px moves passed on all of them.
def _edge(a, b, step=20):
    n = max(abs(b[0] - a[0]), abs(b[1] - a[1])) // step
    return [(a[0] + (b[0] - a[0]) * i // n, a[1] + (b[1] - a[1]) * i // n) for i in range(1, n + 1)]


# Near the top-left corner, around the first home-screen icon (FaceTime on most phones): the part of
# each phone the operator sees most easily in the box (28 Oct).
WATCH_CORNER = [(12, 55), (112, 55), (112, 155), (12, 155)]   # Hugging the left and top edges.
WATCH_SQUARE = [p for a, b in zip(WATCH_CORNER, WATCH_CORNER[1:] + WATCH_CORNER[:1]) for p in _edge(a, b)]
WATCH_ROUNDS = 4
WATCH_STEP_S = 0.08


def page(board, device_id):
    """Reset, then one swipe from right to left across the middle of the home screen."""
    folder = STATE / 'identify' / f"{board}-page-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    folder.mkdir(parents=True)
    row = next(p for p in request(BASE, 'GET', '/input/status', timeout=5)['phones'] if p['id'] == device_id)
    if row['stopped'] and device_id.startswith('pending-'):
        post(BASE, '/input/resume', dict(id=device_id, expected_generations={device_id: row['generation']}))
    token = acquire(BASE, device_id)
    record = dict(board=board, mode='page', commands=[], phoneInput='pointer reset and one swipe')
    try:
        for fun, data in (('/mouse/reset', {}), ('/mouse/swipe', dict(x1=430, y1=500, x2=70, y2=500, duration=250))):
            got = post(BASE, fun, dict(id=device_id, token=token, **data))
            record['commands'].append(dict(fun=fun, code=got.get('code')))
            time.sleep(0.8)
    finally:
        record['release'] = post(BASE, '/input/release', dict(id=device_id, token=token)).get('code')
        (folder / 'record.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(dict(board=board, mode='page', codes=[c['code'] for c in record['commands']], released=record['release'] == 0)))


def watch(board, device_id, home=False):
    """Pointer moves only, for the operator's eyes: about 15 s of the square, then the lease goes."""
    folder = STATE / 'identify' / f"{board}-watch-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    folder.mkdir(parents=True)
    record = dict(board=board, mode='watch', moves=[], phoneInput='pointer moves only')
    # An added board stopped by an earlier timed-out move (never an operator stop: these phones
    # carry no farm work yet) is resumed, generation-checked.
    row = next(p for p in request(BASE, 'GET', '/input/status', timeout=5)['phones'] if p['id'] == device_id)
    if row['stopped'] and device_id.startswith('pending-'):
        post(BASE, '/input/resume', dict(id=device_id, expected_generations={device_id: row['generation']}))
    token = acquire(BASE, device_id)
    if home:
        try:
            for _ in range(3):
                got = post(BASE, '/key/sendkey', dict(id=device_id, token=token, fn_key='Home'))
                record['moves'].append(dict(key='Home', code=got.get('code')))
                time.sleep(2.0)
        finally:
            record['release'] = post(BASE, '/input/release', dict(id=device_id, token=token)).get('code')
            (folder / 'record.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        print(json.dumps(dict(board=board, mode='home', presses=[m['code'] for m in record['moves']], released=record['release'] == 0)))
        return
    try:
        for _ in range(WATCH_ROUNDS):
            post(BASE, '/input/renew', dict(id=device_id, token=token))   # The lease is 15 s; a round is about 4 s.
            for x, y in WATCH_SQUARE:
                got = post(BASE, '/mouse/move', dict(id=device_id, token=token, x=x, y=y))
                record['moves'].append(dict(x=x, y=y, code=got.get('code')))
                if got.get('code') != 0: raise RuntimeError(f'move refused: {got}')
                time.sleep(WATCH_STEP_S)
    finally:
        record['release'] = post(BASE, '/input/release', dict(id=device_id, token=token)).get('code')
        (folder / 'record.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(dict(board=board, mode='watch', moves=len(record['moves']), released=record['release'] == 0)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', required=True)
    # --watch: a phone not mirroring yet (rack A's added boards, 28 Oct). A larger square for longer,
    # for the operator to spot in the box; no frames and no screen check.
    parser.add_argument('--watch', action='store_true')
    # --home (with --watch): Home pressed three times instead, for a phone whose pointer does not show
    # (AssistiveTouch off): its screen wakes and shows the home screen.
    parser.add_argument('--home', action='store_true')
    # --page (with --watch): one swipe left on the home screen, to its second page: every phone in the
    # box rests on its home screen, so the one that turns its page is plain to see (28 Oct).
    parser.add_argument('--page', action='store_true')
    args = parser.parse_args()
    board = args.board.upper()
    devices = request(BASE, 'GET', '/device/get', timeout=8)['list']
    device = next((d for d in devices if d.get('pid', '').upper() == board), None)
    if not device or device['deviceid'] in ('*', '') or device['deviceid'].startswith('unbound-'):
        raise SystemExit(f'{board} has no bound phone; it cannot be identified by its own screen.')
    if args.watch and args.page: return page(board, device['deviceid'])
    if args.watch: return watch(board, device['deviceid'], home=args.home)
    receivers = {r['deviceid']: r for r in request(BASE, 'GET', '/kernel/status', timeout=8)['receivers']}
    others = [d for d in receivers if d != device['deviceid'] and receivers[d]['live'] and d not in ('*', '')]
    if not receivers.get(device['deviceid'], {}).get('live'): raise SystemExit(f'{board} is not mirroring.')
    folder = STATE / 'identify' / f"{board}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
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
                          ownScreenMoved=record['ownScreenMoved'], folder=str(folder.relative_to(STATE)))))


if __name__ == '__main__':
    main()
