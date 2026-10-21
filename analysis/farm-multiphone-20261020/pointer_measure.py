"""Measures where one board's pointer lands on its own mirrored screen. Pointer moves only.

For each target the pointer is reset (so the kernel's position is known), moved there, and the
mirror captured. Between frames only the dot moves, so the dot of frame i is where frame i differs
from every other frame, whatever the background. Reports each landing point against its target and
fits a per-axis scale/offset.

No click, key or swipe. One lease, released at the end. Records under measure/<board>-<utc>/.

  python pointer_measure.py --board F215
"""
import argparse
import io
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from identify_phone import acquire, post, request  # noqa: E402

BASE = 'http://127.0.0.1:9916/api'
# Mirror pixels (500 x 1080), far enough apart that two dots never overlap.
TARGETS = [(120, 300), (380, 300), (250, 540), (120, 780), (380, 780), (250, 200), (250, 900)]
SETTLE_S = 0.8


def shot(device_id):
    with urllib.request.urlopen(f'{BASE}/pic/screenshot?id={device_id}', timeout=8) as response:
        return response.read()


def gray(raw): return np.asarray(Image.open(io.BytesIO(raw)).convert('L'), dtype=np.int16)


def dot(frames, i):
    """Centroid of where frame i differs from every other frame, ignoring anything that also
    changes between the other frames (an animated icon such as Clock's second hand)."""
    mask = np.ones(frames[i].shape, bool)
    noise = np.zeros(frames[i].shape, bool)
    others = [f for j, f in enumerate(frames) if j != i]
    for other in others: mask &= np.abs(frames[i] - other) > 18
    for a in range(len(others)):
        for b in range(a + 1, len(others)): noise |= np.abs(others[a] - others[b]) > 18
    # Widen the noise to whole animated icons: each frame draws Clock's hand at a new angle, so
    # the hand alone would pass as a dot. Other frames' dots also count, but sit elsewhere.
    noise = np.asarray(Image.fromarray(noise.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(41))) > 0
    ys, xs = np.nonzero(mask & ~noise)
    return None if len(xs) < 20 else (float(np.median(xs)), float(np.median(ys)), int(len(xs)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', required=True)
    parser.add_argument('--settle', type=float, default=SETTLE_S)
    args = parser.parse_args()
    board = args.board.upper()
    device = next(d for d in request(BASE, 'GET', '/device/get', timeout=8)['list'] if d.get('pid', '').upper() == board)
    status = {r['deviceid']: r for r in request(BASE, 'GET', '/kernel/status', timeout=8)['receivers']}
    if not status.get(device['deviceid'], {}).get('live'): raise SystemExit(f'{board} is not mirroring.')
    folder = HERE / 'measure' / f"{board}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    folder.mkdir(parents=True)
    record = dict(board=board, phone=device['name'], settleS=args.settle, points=[], phoneInput='pointer moves and resets only')
    token = acquire(BASE, device['deviceid'])

    def place(x, y, label):
        for fun, data in (('/input/renew', {}), ('/mouse/reset', {}), ('/mouse/move', dict(x=x, y=y))):
            got = post(BASE, fun, dict(id=device['deviceid'], token=token, **data))
            if got.get('code') != 0: raise RuntimeError(f'{fun} refused: {got}')
        time.sleep(args.settle)
        raw = shot(device['deviceid'])
        (folder / f'{label}.bmp').write_bytes(raw)
        return raw

    try:
        frames = [gray(place(x, y, f'{i:02d}-{x}-{y}')) for i, (x, y) in enumerate(TARGETS)]
        for i, target in enumerate(TARGETS):
            got = dot(frames, i)
            record['points'].append(dict(target=target, landed=None if got is None else [round(got[0]), round(got[1])],
                                         pixels=None if got is None else got[2]))
    finally:
        record['release'] = post(BASE, '/input/release', dict(id=device['deviceid'], token=token)).get('code')
    seen = [p for p in record['points'] if p['landed']]
    for axis, k in (('x', 0), ('y', 1)):
        t = np.array([p['target'][k] for p in seen], float); l = np.array([p['landed'][k] for p in seen], float)
        if len(set(t)) >= 2:
            scale, offset = np.polyfit(t, l, 1)
            record[f'fit_{axis}'] = dict(scale=round(float(scale), 4), offset=round(float(offset), 1))
    record['maxErrorPx'] = max((float(np.hypot(p['landed'][0] - p['target'][0], p['landed'][1] - p['target'][1])) for p in seen), default=None)
    record['found'] = f'{len(seen)}/{len(record["points"])}'
    (folder / 'record.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps({k: record[k] for k in ('board', 'phone', 'found', 'maxErrorPx') if k in record} |
                     {k: record[k] for k in ('fit_x', 'fit_y') if k in record} |
                     {'points': [(p['target'], p['landed']) for p in record['points']]}))


if __name__ == '__main__':
    main()
