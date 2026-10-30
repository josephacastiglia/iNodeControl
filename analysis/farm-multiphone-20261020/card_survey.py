"""Reads the Screen Mirroring card on a phone that is already mirroring: where each receiver's row
sits and in which order iOS lists them, with more receivers advertised than the four rows
auto_connect.py was calibrated for (29 Oct, 16 rack A receivers). No row is tapped.

Home, ControlBar (Fn+C), the Screen Mirroring tile, one frame, then Home and the close tap below
Control Center's grid, as auto_connect.py does after a connection. One lease, released at the end.

  python card_survey.py --board C24C
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from auto_connect import BASE, OCR, control_center, read_screen  # noqa: E402
from farm_mirroring import CLOSE, TILE, browse  # noqa: E402
from identify_phone import acquire, post, request  # noqa: E402

# A long slow swipe up inside the card: the list stops at its end, so the result does not depend on
# how far the swipe carried (shared with auto_connect.py --survey).
SCROLL = dict(x1=250, y1=880, x2=250, y2=260, duration=600)

# Aim for a 4.7-inch phone (6s, 7, 8: rack A slots 2, 5-8, all of rack B) driven on the placeholder
# calibration (origin 14, 5.1 px per unit): its 375x667 screen is letterboxed in the 500x1080 frame
# from y 95, and the pointer lands at 5.61 px per unit from (0, 95) (pointer_measure.py on 1814,
# 30 Oct: five clean dots within 8 px). to_send turns a frame point into the point to send.
SMALL = dict(ox=0, oy=95, ppu=5.61)
SMALL_TILE = (194, 566)   # Control Center's Screen Mirroring tile on a 4.7-inch phone, frame pixels.
# The 4.7-inch card shows three name rows (69 px apart from y 483) and scrolls inside. A slow drag
# (500 ms: a 1500 ms drag did not scroll, 30 Oct) up by two rows brings rows 4-5 into view at the same place on every phone.
NUDGE = dict(x1=250, y1=640, x2=250, y2=501, duration=500)


def nudge(send, aim):
    (x1, y1), (x2, y2) = to_send((NUDGE['x1'], NUDGE['y1']), aim), to_send((NUDGE['x2'], NUDGE['y2']), aim)
    send('/mouse/reset', 'nudge (reset)')
    send('/mouse/swipe', 'drag the card up two rows', x1=x1, y1=y1, x2=x2, y2=y2, duration=NUDGE['duration'])
    time.sleep(1.5)


def to_send(point, aim=None):
    if aim is None: return point
    return (round(14 + (point[0] - aim['ox']) / aim['ppu'] * 5.1), round(14 + (point[1] - aim['oy']) / aim['ppu'] * 5.1))


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
    # --scroll: read the card scrolled to its end, for rows below the fold (slots 17-20 of 16 listed).
    parser.add_argument('--scroll', action='store_true')
    # --small: a 4.7-inch phone (6s/7/8) on the placeholder calibration; taps go through SMALL.
    parser.add_argument('--small', action='store_true')
    parser.add_argument('--nudge', action='store_true', help='with --small: read the card dragged up two rows (NUDGE)')
    args = parser.parse_args()
    board = args.board.upper()
    device = next(d for d in request(BASE, 'GET', '/device/get', timeout=8)['list'] if d.get('pid', '').upper() == board)
    status = next(r for r in request(BASE, 'GET', '/kernel/status', timeout=8)['receivers'] if r['deviceid'] == device['deviceid'])
    if not status['live']: raise SystemExit(f"{status['name']} is not mirroring; its card cannot be read.")
    folder = HERE / 'card-survey' / f"{board}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"; folder.mkdir(parents=True)
    # The card's layout depends on how many receivers it lists, so the advertised set is kept with it.
    record = dict(board=board, advertised=sorted(browse()[0]), scroll=args.scroll, small=args.small, nudge=args.nudge, steps=[])
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
        if record['scroll']:
            send('/mouse/reset', 'scroll (reset)'); send('/mouse/swipe', 'scroll the card to its end', **SCROLL); time.sleep(1.5)
        if record['nudge']: nudge(send, aim)
        raw = urllib.request.urlopen(f"{BASE}/pic/screenshot?id={device['deviceid']}", timeout=8).read()
        (folder / 'card.bmp').write_bytes(raw)
        text = OCR.read(raw)
        # cy: the line's vertical centre, where auto_connect.py --survey taps that row.
        record['lines'] = [dict(text=l['text'], y=min(w['y'] for w in l['words']), x=min(w['x'] for w in l['words']),
                                cy=round(sum(w['y'] + w['height'] / 2 for w in l['words']) / len(l['words'])))
                           for l in text.get('lines', []) if l.get('words')]
        send('/key/sendkey', 'home closes the card', fn_key='Home'); time.sleep(1.5)
        if args.small:
            # A Home button phone: a second Home closes Control Center (no tap near its bottom tiles).
            send('/key/sendkey', 'home closes Control Center', fn_key='Home'); time.sleep(1.5)
        elif control_center(read_screen(device['deviceid'])):
            tap(CLOSE, 'close Control Center below its grid'); time.sleep(1.5)
        record['controlCenterClosed'] = not control_center(read_screen(device['deviceid']))
    finally:
        record['release'] = post(BASE, '/input/release', dict(id=device['deviceid'], token=token)).get('code')
        (folder / 'record.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(dict(folder=str(folder.relative_to(HERE)), closed=record.get('controlCenterClosed'),
                          lines=[(l['y'], l['x'], l['text']) for l in record.get('lines', [])])))


if __name__ == '__main__':
    main()
