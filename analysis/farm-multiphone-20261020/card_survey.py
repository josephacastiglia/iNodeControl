"""Reads the Screen Mirroring card on a phone that is already mirroring: where each receiver's row
sits and in which order iOS lists them (29 Oct, 16 rack A receivers). No row is tapped.

Home, ControlBar (Fn+C), the Screen Mirroring tile, one frame, then Home and the close tap below
Control Center's grid, as auto_connect.py does after a connection. One lease, released at the end.
auto_connect.py takes this module's card geometry and screen checks; nothing here imports it.

  python card_survey.py --board C24C [--small]
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
import farm_paths  # noqa: E402
STATE = farm_paths.rack_state(HERE)  # windows/, identify/ ...: beside this script in a checkout, the data folder when installed
from farm_mirroring import CLOSE, TILE, browse  # noqa: E402
from farm_observations import WindowsOcr  # noqa: E402
from identify_phone import acquire, post, request  # noqa: E402

# The rack kernel; rack_recovery.py's bring-up sets IMOUSE_RACK_API for the kernel it is bringing up.
BASE = os.environ.get('IMOUSE_RACK_API') or 'http://127.0.0.1:9916/api'
OCR = WindowsOcr()

# Aim for a 4.7-inch phone (6s, 7, 8: rack A slots 2, 5-8, all of rack B) driven on the placeholder
# calibration (origin 14, 5.1 px per unit): its 375x667 screen is letterboxed in the 500x1080 frame
# from y 95, and the pointer lands at 5.61 px per unit from (0, 95) (pointer_measure.py on 1814,
# 30 Oct: five clean dots within 8 px). to_send turns a frame point into the point to send.
SMALL = dict(ox=0, oy=95, ppu=5.61)
SMALL_TILE = (194, 566)   # Control Center's Screen Mirroring tile on a 4.7-inch phone, frame pixels.


def to_send(point, aim=None):
    if aim is None: return point
    return (round(14 + (point[0] - aim['ox']) / aim['ppu'] * 5.1), round(14 + (point[1] - aim['oy']) / aim['ppu'] * 5.1))


def read_screen(device_id):
    return OCR.read(urllib.request.urlopen(f'{BASE}/pic/screenshot?id={device_id}', timeout=8).read())


def control_center(text):
    """Control Center: its Focus tile and the battery percentage in the status row (as farm_start_screen)."""
    rows = [(line['text'].strip().casefold(), min(w['y'] for w in line['words'])) for line in text.get('lines', []) if line.get('words')]
    # The status row shows the battery percentage or, on the other rack phones, 'SOS only' / 'No SIM'.
    return (any(t.split()[:1] == ['focus'] and 480 < y < 580 for t, y in rows)
            and any(('%' in t or 'sos only' in t or 'no sim' in t) and y < 170 for t, y in rows))


def home_twice(send, first, second, pause=1.5):
    """Home, a pause, Home, on a Home-button phone: from the card the first closes it and the second
    closes Control Center (no tap near its bottom tiles; slot 2, 30 Oct); on a dark phone the first wakes
    it and the second opens it. The pause keeps the two from being read as a double press."""
    for purpose in (first, second):
        send('/key/sendkey', purpose, fn_key='Home'); time.sleep(pause)


def find_line(text, words):
    """Centre of the first OCR line whose text equals words (case-insensitive), or None."""
    for line in text.get('lines', []):
        if line.get('words') and line['text'].strip().casefold() == words.casefold():
            ws = line['words']
            return (round(sum(w['x'] + w['width'] / 2 for w in ws) / len(ws)), round(sum(w['y'] + w['height'] / 2 for w in ws) / len(ws)))
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', required=True)
    # --small: a 4.7-inch phone (6s/7/8) on the placeholder calibration; taps go through SMALL.
    parser.add_argument('--small', action='store_true')
    args = parser.parse_args()
    board = args.board.upper()
    device = next(d for d in request(BASE, 'GET', '/device/get', timeout=8)['list'] if d.get('pid', '').upper() == board)
    status = next(r for r in request(BASE, 'GET', '/kernel/status', timeout=8)['receivers'] if r['deviceid'] == device['deviceid'])
    if not status['live']: raise SystemExit(f"{status['name']} is not mirroring; its card cannot be read.")
    folder = STATE / 'card-survey' / f"{board}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"; folder.mkdir(parents=True)
    # The card's layout depends on how many receivers it lists, so the advertised set is kept with it.
    record = dict(board=board, advertised=sorted(browse()[0]), small=args.small, steps=[])
    token = acquire(BASE, device['deviceid'])

    def send(fun, purpose, **data):
        post(BASE, '/input/renew', dict(id=device['deviceid'], token=token))
        got = post(BASE, fun, dict(id=device['deviceid'], token=token, **data))
        record['steps'].append(dict(fun=fun, purpose=purpose, code=got.get('code')))
        if got.get('code') != 0: raise RuntimeError(f'{purpose}: {got}')

    aim = SMALL if args.small and device['deviceid'].startswith('pending-') else None   # As auto_connect.py.

    def tap(point, purpose):
        x, y = to_send(point, aim)
        send('/mouse/reset', purpose + ' (reset)')
        send('/mouse/click', purpose, x=x, y=y)

    try:
        send('/key/sendkey', 'home', fn_key='Home'); time.sleep(1.5)
        send('/key/sendkey', 'open Control Center', fn_key='ControlBar'); time.sleep(1.2)
        tile = TILE
        if args.small:
            # Control Center on these phones is laid out differently; its tile is found by its label.
            raw = urllib.request.urlopen(f"{BASE}/pic/screenshot?id={device['deviceid']}", timeout=8).read()
            (folder / 'control-center.bmp').write_bytes(raw)
            # iOS 15 shows the tile as an icon only, left of the second row (slot 2, 30 Oct); a label,
            # where an older iOS shows one, takes precedence.
            tile = find_line(OCR.read(raw), 'Screen Mirroring') or SMALL_TILE
            record['tile'] = tile
        tap(tile, 'Screen Mirroring tile'); time.sleep(2.5)
        raw = urllib.request.urlopen(f"{BASE}/pic/screenshot?id={device['deviceid']}", timeout=8).read()
        (folder / 'card.bmp').write_bytes(raw)
        text = OCR.read(raw)
        # cy: the line's vertical centre, where auto_connect.py taps that row.
        record['lines'] = [dict(text=l['text'], y=min(w['y'] for w in l['words']), x=min(w['x'] for w in l['words']),
                                cy=round(sum(w['y'] + w['height'] / 2 for w in l['words']) / len(l['words'])))
                           for l in text.get('lines', []) if l.get('words')]
        if args.small:
            home_twice(send, 'home closes the card', 'home closes Control Center')
        else:
            send('/key/sendkey', 'home closes the card', fn_key='Home'); time.sleep(1.5)
            if control_center(read_screen(device['deviceid'])):
                tap(CLOSE, 'close Control Center below its grid'); time.sleep(1.5)
        record['controlCenterClosed'] = not control_center(read_screen(device['deviceid']))
    finally:
        record['release'] = post(BASE, '/input/release', dict(id=device['deviceid'], token=token)).get('code')
        (folder / 'record.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(dict(folder=str(folder.relative_to(STATE)), closed=record.get('controlCenterClosed'),
                          lines=[(l['y'], l['x'], l['text']) for l in record.get('lines', [])])))


if __name__ == '__main__':
    main()
