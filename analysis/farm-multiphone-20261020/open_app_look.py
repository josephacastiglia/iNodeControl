"""Opens one app on one rack phone from its home screen and saves what it shows. Read-only intent:
Home, Search pill, clear any leftover query, type the app name, tap the Top Hit icon, wait, capture.
Every step's frame is saved under look/<board>-<app>-<utc>/. One lease, released at the end.

  python open_app_look.py --board C214 --app TikTok [--tab x,y]
"""
import argparse
import io
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from identify_phone import acquire, post, request  # noqa: E402

BASE = 'http://127.0.0.1:9916/api'
SEARCH_PILL = (250, 898)
CLEAR_QUERY = (444, 1006)     # The ⓧ in Spotlight's bottom search field.
TOP_HIT = (88, 182)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', required=True)
    parser.add_argument('--app', required=True)
    parser.add_argument('--tab', help='optional x,y tap after the app opens, e.g. its profile tab')
    args = parser.parse_args()
    device = next(d for d in request(BASE, 'GET', '/device/get', timeout=8)['list'] if d.get('pid', '').upper() == args.board.upper())
    i = device['deviceid']
    folder = HERE / 'look' / f"{args.board.upper()}-{args.app}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    folder.mkdir(parents=True)

    def frame(label):
        raw = urllib.request.urlopen(f'{BASE}/pic/screenshot?id={i}', timeout=8).read()
        (folder / f'{len(list(folder.iterdir())):02d}-{label}.bmp').write_bytes(raw)
        return np.asarray(Image.open(io.BytesIO(raw)).convert('L'), dtype=np.int16)

    t = acquire(BASE, i)

    def send(fun, **data):
        post(BASE, '/input/renew', dict(id=i, token=t))
        got = post(BASE, fun, dict(id=i, token=t, **data))
        if got.get('code') != 0: raise RuntimeError(f'{fun}: {got}')

    def tap(point):
        send('/mouse/move', x=point[0], y=point[1]); time.sleep(1.2)   # Slow phones finish moving first.
        send('/mouse/click', x=point[0], y=point[1])

    try:
        send('/key/sendkey', fn_key='Home'); time.sleep(1.5); frame('home')
        send('/mouse/reset'); tap(SEARCH_PILL); time.sleep(1.5); frame('search')
        tap(CLEAR_QUERY); time.sleep(1.0); frame('cleared')
        send('/key/sendkey', key=args.app); time.sleep(2.0); frame('typed')
        tap(TOP_HIT); time.sleep(6.0); frame('opened')
        if args.tab:
            x, y = (int(v) for v in args.tab.split(','))
            tap((x, y)); time.sleep(3.0); frame('tab')
    finally:
        post(BASE, '/input/release', dict(id=i, token=t))
    print(folder.relative_to(HERE))


if __name__ == '__main__':
    main()
