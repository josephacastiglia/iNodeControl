"""Starts screen mirroring on one rack phone from the PC, through its own board. No operator step.

The phone is not mirroring yet, so the PC cannot see it. Each blind step therefore needs evidence
from outside the screen before the next one is sent:
  1. Where this phone's receiver sits on the Screen Mirroring card comes from a survey: the card as
     card_survey.py read it on a phone that is already mirroring, or the row rack_recovery.py
     computes for the first phone of a group. It holds only while the same receivers are advertised.
  2. Home, then ControlBar (Fn+C) to open Control Center, then the Screen Mirroring tile.
  3. Proof the card opened: an mDNS question for AirPlay receivers from this phone's own address
     (iOS browses when the card appears). Without it, Home is sent and the run stops.
  4. The phone's row; the receiver must go live within ten seconds. Then Home closes the card.
Only this phone's receiver can accept it (each receiver is locked to its phone's device ID), so a
live receiver also proves this board drives this phone. Every tap is a reset then a click; no step
repeats. One lease, released at the end.

  python auto_connect.py --board C214 --survey card-survey/<run>/record.json [--phone-ip 192.168.4.27] [--small]
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from card_survey import BASE, SMALL, SMALL_TILE, STATE, control_center, home_twice, read_screen, to_send  # noqa: E402
from farm_mirroring import CLOSE, TILE, browse, natural  # noqa: E402
from identify_phone import acquire, post, request  # noqa: E402
from mdns_watch import Watcher, lan_address  # noqa: E402


def ocr_name(text):
    """A receiver name as OCR may read it: rack B's names are hex (iMouse2-0C6D), and OCR confuses
    0/O, 1/I/l, 5/S and 8/B; the board IDs differ in more than such a pair, so this stays unique."""
    return text.strip().upper().translate(str.maketrans('OILSB', '01158'))


def unread_row(receiver, names, survey):
    """OCR drops a lone trailing digit ('iMouse2-5' read as 'iMouse2-', 30 Oct). The receiver's row is
    the one row whose name was not read, if there is exactly one, and only when the receiver sorts
    (natural order, as iOS lists them) between the read rows above and below it."""
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
    """The receiver's row on a surveyed card (29 Oct: iOS lists receivers in natural order and, with 16
    listed, the card fills the screen at fixed rows), valid only while the same receivers are
    advertised. A wrong row is refused by that row's receiver, which is locked to its own phone."""
    if survey.get('scroll') or survey.get('nudge'):
        raise SystemExit('This survey was read on a scrolled card, which is no longer supported; nothing was sent.')
    if set(names) != set(survey['advertised']): raise SystemExit('Advertised receivers differ from the surveyed card; nothing was sent.')
    line = next((l for l in survey['lines'] if ocr_name(l['text']) == ocr_name(receiver)), None)
    if line is None: line = unread_row(receiver, names, survey)
    if line is None: raise SystemExit(f'{receiver} is not visible on the surveyed card; nothing was sent.')
    return 250, line['cy']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--board', required=True)
    parser.add_argument('--survey', required=True, help="card_survey.py's record.json, or a bring-up's crafted survey")
    # Without --phone-ip (rack B, 29 Oct: addresses not known yet) the card proof is the first AirPlay
    # question from any address but this PC's; valid only while no other phone is being driven.
    parser.add_argument('--phone-ip')
    # --small: a 4.7-inch phone (6s/7/8) on the placeholder calibration, with a survey read on one
    # (card_survey.py --small): its tile, aim and Home-button close.
    parser.add_argument('--small', action='store_true')
    args = parser.parse_args()
    board = args.board.upper()
    device = next(d for d in request(BASE, 'GET', '/device/get', timeout=8)['list'] if d.get('pid', '').upper() == board)
    status = next(r for r in request(BASE, 'GET', '/kernel/status', timeout=8)['receivers'] if r['deviceid'] == device['deviceid'])
    if status['live']: raise SystemExit(f"{status['name']} is already mirroring.")
    if status['receiver_pid'] <= 0: raise SystemExit(f"{status['name']} is not running ({status['receiver_state']}).")
    names, _ = browse()
    survey = json.loads(Path(args.survey).read_text(encoding='utf-8'))
    point = surveyed_point(status['name'], names, survey)
    # The row number is for the record only: the surveyed name row nearest the tap.
    rows = [l['cy'] for l in survey['lines'] if ocr_name(l['text']).startswith('1M0U5E2')]
    row = min(range(len(rows)), key=lambda i: abs(rows[i] - point[1]))
    if args.small:
        # The short card on these phones has fixed rows 69 px apart and, on the surveyed (mirroring)
        # phone, a Stop Mirroring row; without it the card may sit up to half a row lower. A quarter
        # row below the surveyed centre is inside the row either way (slot 2, 30 Oct).
        point = (point[0], point[1] + 17)
    folder = STATE / 'autoconnect'; folder.mkdir(exist_ok=True)
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
        tap(point, f'row {row + 1} ({status["name"]})')
        deadline = time.monotonic() + 10
        live = False
        while time.monotonic() < deadline and not live:
            time.sleep(0.5)
            live = next(r for r in request(BASE, 'GET', '/kernel/status', timeout=5)['receivers'] if r['deviceid'] == device['deviceid'])['live']
        record['result'] = 'mirroring' if live else 'stopped: receiver did not go live within 10 s'
        if args.small:
            # A Home-button phone: Home from the card and again leaves the home screen clean; the close
            # tap below Control Center's grid would land on its bottom tiles.
            time.sleep(1.0)
            home_twice(send, 'home closes the card and Control Center (1)', 'home closes the card and Control Center (2)')
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
