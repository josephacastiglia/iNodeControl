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
  python auto_connect.py --rack B --board CD51 ...   on rack B's own kernel (rack-b/preparation.json's port)
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

BASE = 'http://127.0.0.1:9916/api'   # The single kernel, or rack A's (rack_kernels.py keeps it on 9916).


def rack_api(rack):
    """The API of one rack's own kernel, from its preparation (rack_kernels.py prepare)."""
    prep = json.loads((HERE / f'rack-{rack.lower()}' / 'preparation.json').read_text(encoding='utf-8-sig'))
    if prep.get('rack') != rack.upper() or not prep.get('api', '').startswith('http://127.0.0.1:'):
        raise SystemExit(f'rack-{rack.lower()}/preparation.json is not a rack {rack.upper()} kernel preparation.')
    return prep['api']


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


def ocr_name(text):
    """A receiver name as OCR may read it: rack B's names are hex (iMouse2-0C6D), and OCR confuses
    0/O, 1/I/l, 5/S and 8/B; the board IDs differ in more than such a pair, so this stays unique."""
    return text.strip().upper().translate(str.maketrans('OILSB', '01158'))


def unread_row(receiver, names, survey):
    """OCR drops a lone trailing digit ('iMouse2-5' read as 'iMouse2-', 30 Oct). The receiver's row is
    the one row whose name was not read, if there is exactly one, and only when the receiver sorts
    (natural order, as iOS lists them) between the read rows above and below it."""
    from farm_mirroring import natural
    listed = {ocr_name(n): n for n in names}
    rows = [l for l in survey['lines'] if ocr_name(l['text']).startswith('1M0U5E2')]
    unread = [l for l in rows if ocr_name(l['text']) not in listed]
    if len(unread) != 1: return None
    i = rows.index(unread[0])
    above = [listed[ocr_name(l['text'])] for l in rows[:i]]
    below = [listed[ocr_name(l['text'])] for l in rows[i + 1:]]
    if receiver in above + below: return None
    if all(natural(a) < natural(receiver) for a in above) and all(natural(receiver) < natural(b) for b in below): return unread[0]
    return None


def surveyed_point(receiver, names, survey):
    """The receiver's row on a card read by card_survey.py on a mirroring phone (29 Oct: iOS lists
    receivers in natural order and, with 16 listed, the card fills the screen at fixed rows), valid
    only while the same receivers are advertised. A wrong row is refused by that row's receiver,
    which is locked to its own phone."""
    if set(names) != set(survey['advertised']): raise SystemExit('Advertised receivers differ from the surveyed card; nothing was sent.')
    line = next((l for l in survey['lines'] if ocr_name(l['text']) == ocr_name(receiver)), None)
    if line is None: line = unread_row(receiver, names, survey)
    if line is None: raise SystemExit(f'{receiver} is not visible on the surveyed card; nothing was sent.')
    if not survey.get('scroll'): return 250, line['cy']
    # Scrolled to its end, the surveyed (mirroring) card ends in its Stop Mirroring button; a phone not
    # yet mirroring has none, so its rows end one row lower: C241's tap at iMouse2-19's surveyed row
    # reached iMouse2-18 (29 Oct).
    rows = [l for l in survey['lines'] if l['text'].strip() in survey['advertised']]
    stop = next(l for l in survey['lines'] if l['text'].strip() == 'Stop Mirroring')
    return 250, line['cy'] + stop['cy'] - rows[-1]['cy']


def main():
    from card_survey import SMALL, SMALL_TILE, to_send   # card_survey imports this module.
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', required=True)
    # Without --phone-ip (rack B, 29 Oct: addresses not known yet) the card proof is the first AirPlay
    # question from any address but this PC's; valid only while no other phone is being driven.
    parser.add_argument('--phone-ip')
    parser.add_argument('--survey', help="card_survey.py's record.json, for more receivers than the four calibrated rows")
    # --small: a 4.7-inch phone (6s/7/8) on the placeholder calibration, with a --survey read on one
    # (card_survey.py --small): its tile, aim and Home-button close.
    parser.add_argument('--small', action='store_true')
    parser.add_argument('--rack', choices=['A', 'B'], help="a rack's own kernel; default the kernel on 9916")
    args = parser.parse_args()
    global BASE
    if args.rack: BASE = rack_api(args.rack)
    if args.small and not args.survey: raise SystemExit('--small needs a --survey read on a 4.7-inch phone.')
    board = args.board.upper()
    device = next(d for d in request(BASE, 'GET', '/device/get', timeout=8)['list'] if d.get('pid', '').upper() == board)
    status = next(r for r in request(BASE, 'GET', '/kernel/status', timeout=8)['receivers'] if r['deviceid'] == device['deviceid'])
    if status['live']: raise SystemExit(f"{status['name']} is already mirroring.")
    if status['receiver_pid'] <= 0: raise SystemExit(f"{status['name']} is not running ({status['receiver_state']}).")
    names, _ = browse()
    if args.survey:
        survey = json.loads(Path(args.survey).read_text(encoding='utf-8'))
        point = surveyed_point(status['name'], names, survey)
        # The row number is for the record only: the surveyed name row nearest the tap.
        rows = [l['cy'] for l in survey['lines'] if ocr_name(l['text']).startswith('1M0U5E2')]
        row = min(range(len(rows)), key=lambda i: abs(rows[i] - point[1]))
        if args.small and not survey.get('scroll'):
            # The short card on these phones has fixed rows 69 px apart and, on the surveyed (mirroring)
            # phone, a Stop Mirroring row; without it the card may sit up to half a row lower. A quarter
            # row below the surveyed centre is inside the row either way (slot 2, 30 Oct).
            point = (point[0], point[1] + 17)
    else:
        row = row_of(status['name'], names)
        point = ROWS[row]
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

    # Only a placeholder board still has the placeholder calibration; a bound 4.7-inch phone has the
    # measured one (prepare_rack_b.py bound), so its points go as they are.
    aim = SMALL if args.small and device['deviceid'].startswith('pending-') else None

    def tap(point, purpose):
        x, y = to_send(point, aim)
        send('/mouse/reset', purpose + ' (reset)')
        send('/mouse/click', purpose, x=x, y=y)

    def home_twice(purpose):
        # A Home-button phone: Home from the card and again leaves the home screen clean (slot 2,
        # 30 Oct); the close tap below Control Center's grid would land on its bottom tiles.
        for i in (1, 2): send('/key/sendkey', f'{purpose} ({i})', fn_key='Home'); time.sleep(1.5)

    try:
        send('/key/sendkey', 'home', fn_key='Home'); time.sleep(1.5)
        send('/key/sendkey', 'open Control Center', fn_key='ControlBar'); time.sleep(1.2)
        watcher.drain()
        tap(SMALL_TILE if args.small else TILE, 'Screen Mirroring tile')
        own = lan_address()
        proof = next((q for q in watcher.airplay_queries(4.0, args.phone_ip) if q[1] != own), None)
        record['cardProof'] = None if proof is None else dict(t=round(proof[0], 2), sender=proof[1])
        if proof is None:
            send('/key/sendkey', 'home after no card proof', fn_key='Home')
            record['result'] = 'stopped: no AirPlay query from the phone after the tile tap'
            return
        time.sleep(1.5)
        if args.survey and survey.get('scroll'):
            from card_survey import SCROLL
            send('/mouse/reset', 'scroll (reset)'); send('/mouse/swipe', 'scroll the card to its end', **SCROLL); time.sleep(1.5)
        if args.survey and survey.get('nudge'):
            from card_survey import nudge
            nudge(send, aim)
        tap(point, f'row {row + 1} ({status["name"]})')
        deadline = time.monotonic() + 10
        live = False
        while time.monotonic() < deadline and not live:
            time.sleep(0.5)
            live = next(r for r in request(BASE, 'GET', '/kernel/status', timeout=5)['receivers'] if r['deviceid'] == device['deviceid'])['live']
        record['result'] = 'mirroring' if live else 'stopped: receiver did not go live within 10 s'
        if args.small:
            time.sleep(1.0); home_twice('home closes the card and Control Center')
        elif live:
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
