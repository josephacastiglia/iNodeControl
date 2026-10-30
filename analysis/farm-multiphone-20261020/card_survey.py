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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', required=True)
    # --scroll: read the card scrolled to its end, for rows below the fold (slots 17-20 of 16 listed).
    parser.add_argument('--scroll', action='store_true')
    args = parser.parse_args()
    board = args.board.upper()
    device = next(d for d in request(BASE, 'GET', '/device/get', timeout=8)['list'] if d.get('pid', '').upper() == board)
    status = next(r for r in request(BASE, 'GET', '/kernel/status', timeout=8)['receivers'] if r['deviceid'] == device['deviceid'])
    if not status['live']: raise SystemExit(f"{status['name']} is not mirroring; its card cannot be read.")
    folder = HERE / 'card-survey' / f"{board}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"; folder.mkdir(parents=True)
    # The card's layout depends on how many receivers it lists, so the advertised set is kept with it.
    record = dict(board=board, advertised=sorted(browse()[0]), scroll=args.scroll, steps=[])
    token = acquire(BASE, device['deviceid'])

    def send(fun, purpose, **data):
        post(BASE, '/input/renew', dict(id=device['deviceid'], token=token))
        got = post(BASE, fun, dict(id=device['deviceid'], token=token, **data))
        record['steps'].append(dict(fun=fun, purpose=purpose, code=got.get('code')))
        if got.get('code') != 0: raise RuntimeError(f'{purpose}: {got}')

    def tap(point, purpose):
        send('/mouse/reset', purpose + ' (reset)')
        send('/mouse/click', purpose, x=point[0], y=point[1])

    try:
        send('/key/sendkey', 'home', fn_key='Home'); time.sleep(1.5)
        send('/key/sendkey', 'open Control Center', fn_key='ControlBar'); time.sleep(1.2)
        tap(TILE, 'Screen Mirroring tile'); time.sleep(2.5)
        if record['scroll']:
            send('/mouse/reset', 'scroll (reset)'); send('/mouse/swipe', 'scroll the card to its end', **SCROLL); time.sleep(1.5)
        import urllib.request
        raw = urllib.request.urlopen(f"{BASE}/pic/screenshot?id={device['deviceid']}", timeout=8).read()
        (folder / 'card.bmp').write_bytes(raw)
        text = OCR.read(raw)
        # cy: the line's vertical centre, where auto_connect.py --survey taps that row.
        record['lines'] = [dict(text=l['text'], y=min(w['y'] for w in l['words']), x=min(w['x'] for w in l['words']),
                                cy=round(sum(w['y'] + w['height'] / 2 for w in l['words']) / len(l['words'])))
                           for l in text.get('lines', []) if l.get('words')]
        send('/key/sendkey', 'home closes the card', fn_key='Home'); time.sleep(1.5)
        if control_center(read_screen(device['deviceid'])):
            tap(CLOSE, 'close Control Center below its grid'); time.sleep(1.5)
        record['controlCenterClosed'] = not control_center(read_screen(device['deviceid']))
    finally:
        record['release'] = post(BASE, '/input/release', dict(id=device['deviceid'], token=token)).get('code')
        (folder / 'record.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(dict(folder=str(folder.relative_to(HERE)), closed=record.get('controlCenterClosed'),
                          lines=[(l['y'], l['x'], l['text']) for l in record.get('lines', [])])))


if __name__ == '__main__':
    main()
