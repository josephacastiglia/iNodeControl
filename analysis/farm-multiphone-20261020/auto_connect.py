"""Starts screen mirroring on one rack phone from the PC, through its own board. No operator step.

The phone is not mirroring yet, so the PC cannot see it. Each blind step therefore needs evidence
from outside the screen before the next one is sent:
  1. Bonjour on this PC lists at most four AirPlay receivers, and this phone's receiver has the same
     row under every plausible collation, so its row in the Screen Mirroring card is known.
  2. Home, then ControlBar (Fn+C) to open Control Center, then the Screen Mirroring tile.
  3. Proof the card opened: an mDNS question for AirPlay receivers from this phone's own address
     (iOS browses when the card appears). Without it, Home is sent and the run stops.
  4. The phone's row; the receiver must go live within ten seconds. Then Home closes the card.
Only this phone's receiver can accept it (each receiver is locked to its phone's device ID), so a
live receiver also proves this board drives this phone. Every tap is a reset then a click at
C24C's calibrated points; no step repeats. One lease, released at the end.

  python auto_connect.py --board C214 --phone-ip 192.168.4.27
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from farm_mirroring import CLOSE, COLLATIONS, ROWS, TILE, browse  # noqa: E402
from farm_observations import WindowsOcr  # noqa: E402
from identify_phone import acquire, post, request  # noqa: E402
from mdns_watch import Watcher, lan_address  # noqa: E402

BASE = 'http://127.0.0.1:9916/api'


OCR = WindowsOcr()


def read_screen(device_id):
    import urllib.request
    return OCR.read(urllib.request.urlopen(f'{BASE}/pic/screenshot?id={device_id}', timeout=8).read())


def control_center(text):
    """Control Center: its Focus tile and the battery percentage in the status row (as farm_start_screen)."""
    rows = [(line['text'].strip().casefold(), min(w['y'] for w in line['words'])) for line in text.get('lines', []) if line.get('words')]
    # The status row shows the battery percentage or, on the other rack phones, 'SOS only' / 'No SIM'.
    return (any(t.split()[:1] == ['focus'] and 480 < y < 580 for t, y in rows)
            and any(('%' in t or 'sos only' in t or 'no sim' in t) and y < 170 for t, y in rows))


def row_of(receiver, names):
    names = set(names)
    if receiver not in names: raise SystemExit(f'{receiver} is not advertised; nothing was sent.')
    if len(names) > len(ROWS): raise SystemExit(f'{len(names)} AirPlay receivers listed; the calibrated card holds {len(ROWS)}.')
    ranks = {sorted(names, key=key).index(receiver) for key in COLLATIONS}
    if len(ranks) != 1: raise SystemExit(f'{receiver} has no single row under every collation; nothing was sent.')
    return ranks.pop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', required=True)
    parser.add_argument('--phone-ip', required=True)
    args = parser.parse_args()
    board = args.board.upper()
    device = next(d for d in request(BASE, 'GET', '/device/get', timeout=8)['list'] if d.get('pid', '').upper() == board)
    status = next(r for r in request(BASE, 'GET', '/kernel/status', timeout=8)['receivers'] if r['deviceid'] == device['deviceid'])
    if status['live']: raise SystemExit(f"{status['name']} is already mirroring.")
    if status['receiver_pid'] <= 0: raise SystemExit(f"{status['name']} is not running ({status['receiver_state']}).")
    names, _ = browse()
    row = row_of(status['name'], names)
    folder = HERE / 'autoconnect'; folder.mkdir(exist_ok=True)
    record = dict(board=board, receiver=status['name'], phoneIp=args.phone_ip, advertised=sorted(names), row=row + 1, steps=[],
                  utc=datetime.now(timezone.utc).isoformat())
    watcher = Watcher(lan_address())
    token = acquire(BASE, device['deviceid'])

    def renew():
        # The lease is 15 s and a reconnect can take 25 s; an expired lease marks the board stopped
        # (C214 and F215, 22 Oct), so it is renewed before every command and before the release.
        got = post(BASE, '/input/renew', dict(id=device['deviceid'], token=token))
        if got.get('code') != 0: raise RuntimeError(f'lease renewal: {got}')

    def send(fun, purpose, **data):
        renew()
        got = post(BASE, fun, dict(id=device['deviceid'], token=token, **data))
        record['steps'].append(dict(t=round(time.time(), 2), fun=fun, purpose=purpose, code=got.get('code')))
        if got.get('code') != 0: raise RuntimeError(f'{purpose}: {got}')

    def tap(point, purpose):
        send('/mouse/reset', purpose + ' (reset)')
        send('/mouse/click', purpose, x=point[0], y=point[1])

    try:
        send('/key/sendkey', 'home', fn_key='Home'); time.sleep(1.5)
        send('/key/sendkey', 'open Control Center', fn_key='ControlBar'); time.sleep(1.2)
        watcher.drain()
        tap(TILE, 'Screen Mirroring tile')
        proof = next(watcher.airplay_queries(4.0, args.phone_ip), None)
        record['cardProof'] = None if proof is None else dict(t=round(proof[0], 2), sender=proof[1])
        if proof is None:
            send('/key/sendkey', 'home after no card proof', fn_key='Home')
            record['result'] = 'stopped: no AirPlay query from the phone after the tile tap'
            return
        time.sleep(1.5)
        tap(ROWS[row], f'row {row + 1} ({status["name"]})')
        deadline = time.monotonic() + 10
        live = False
        while time.monotonic() < deadline and not live:
            time.sleep(0.5)
            live = next(r for r in request(BASE, 'GET', '/kernel/status', timeout=5)['receivers'] if r['deviceid'] == device['deviceid'])['live']
        record['result'] = 'mirroring' if live else 'stopped: receiver did not go live within 10 s'
        if live:
            time.sleep(1.0); send('/key/sendkey', 'home closes the card', fn_key='Home'); time.sleep(1.5)
            # Home closes the Screen Mirroring card but not Control Center. Now frames exist, so the
            # close tap below Control Center's grid is decided on, and confirmed by, a real frame.
            if control_center(read_screen(device['deviceid'])):
                tap(CLOSE, 'close Control Center below its grid'); time.sleep(1.5)
                record['controlCenterClosed'] = not control_center(read_screen(device['deviceid']))
                if not record['controlCenterClosed']: record['result'] = 'mirroring; Control Center did not close'
    finally:
        try: renew()
        except RuntimeError as error: record['renewBeforeRelease'] = str(error)
        record['release'] = post(BASE, '/input/release', dict(id=device['deviceid'], token=token)).get('code')
        watcher.close()
        (folder / f"{board}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json").write_text(json.dumps(record, indent=2), encoding='utf-8')
        print(json.dumps({k: record.get(k) for k in ('board', 'receiver', 'row', 'cardProof', 'result', 'controlCenterClosed')}))


if __name__ == '__main__':
    main()
