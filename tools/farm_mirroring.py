"""Guarded PC-initiated screen mirroring for C24C (the vendor's auto_connect_screen, made safe).

Until mirroring starts the PC cannot see the phone, so this is the farm's one bounded
sequence decided without a phone frame. It runs only when all of these hold:
- the private receiver is up but not live (otherwise there is nothing to do);
- C24C's input is free, and a lease is held for the whole sequence;
- Bonjour on this PC proves our receiver is the phone list's first row: it is advertised,
  every other AirPlay receiver sorts after it under every plausible collation, and there
  are at most four (the calibrated card). A Bedroom TV, for example, sorts first, so the
  run refuses rather than guess a row.

Sequence, each answered before the next and nothing repeated: ControlBar (Fn+C) opens
Control Center, then the Screen Mirroring tile, then row 1, at C24C's calibrated points
(from the 20 Oct screenshot of the not-yet-mirroring sheet). The receiver must then go
live within eight seconds. Once frames arrive, Control Center is closed by taps decided on
fresh frames. If the receiver does not go live it stops: no retry and no further input.

Usage: python farm_mirroring.py <journal folder>
"""
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from farm_carousel_inspection import InspectionStopped  # noqa: E402
from farm_live_verification import ReadOnlyKernel, NoRedirect, idle  # noqa: E402
from imouse_social_automation import IMouseKernel, LIVE_TEST_DEVICE_ID, KernelSafetyError  # noqa: E402

API = 'http://127.0.0.1:9916/api'
RECEIVER = 'iMouse2-C24C'
MAX_AGE_MS = 1500
# C24C calibration (500x1080 frame): Control Center's Screen Mirroring tile (16 Sep and 19 Oct
# captures), and the not-yet-mirroring sheet's rows (20 Oct screenshot; separators 458/520/583/645/709).
TILE = (199, 432)
ROWS = ((250, 489), (250, 551), (250, 614), (250, 677))
CLOSE = (250, 960)            # Below the mirroring sheet (card ends at y 755) and the Control Center grid.
MAX_RECEIVERS = len(ROWS)
LIVE_SECONDS = 8.0


class MirroringRefused(InspectionStopped):
    """The preconditions for a safe automatic connection do not hold; nothing was sent."""


def natural(name):
    return [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', name.casefold())]


COLLATIONS = (lambda n: n, str.casefold, natural)


def first_row(receiver, names):
    """Row 0 only when our receiver sorts first under every plausible collation, else refuse."""
    names = set(names)
    if receiver not in names:
        raise MirroringRefused(f'{receiver} is not advertised on this network; nothing was sent.')
    if len(names) > MAX_RECEIVERS:
        raise MirroringRefused(f'{len(names)} AirPlay receivers are listed; the calibrated card holds {MAX_RECEIVERS}.')
    before = sorted(other for other in names - {receiver}
                    if any(sorted([receiver, other], key=key)[0] != receiver for key in COLLATIONS))
    if before:
        raise MirroringRefused(f'{len(before)} other receiver(s) may sort before {receiver}, so its row cannot be '
                               'proven; connect by hand or remove them from the network.')
    return 0


LINE = re.compile(r'^\s*\S+\s+(Add|Rmv)\s+\d+\s+\d+\s+(\S+)\s+_airplay\._tcp\.\s+(.+?)\s*$')


def parse_browse(output):
    present = set()
    for line in output.splitlines():
        match = LINE.match(line)
        if not match: continue
        action, _, name = match.groups()
        (present.add if action == 'Add' else present.discard)(name)
    return present


def browse(seconds=3.0):
    """AirPlay receivers this PC currently sees over Bonjour (dns-sd)."""
    process = subprocess.Popen(['dns-sd', '-B', '_airplay._tcp', 'local.'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        time.sleep(seconds)
    finally:
        process.kill()
    output = process.communicate(timeout=5)[0].decode('utf-8', 'replace')
    return parse_browse(output), output


class MirroringKernel(IMouseKernel):
    """C24C only; ControlBar plus clicks at calibrated or verified points; no other keys or apps."""
    def __init__(self, url, transport=None, points=None):
        reader = ReadOnlyKernel(url, transport=transport)
        super().__init__(url)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        allowed_points = set(points or (TILE, *ROWS, CLOSE))
        def limited(method, target, body, timeout):
            if method == 'GET' or body == {'fun': '/input/status', 'data': {}}:
                return reader._transport(method, target, body, timeout)
            if method != 'POST' or target != self.url + '/' or not isinstance(body, dict) or not isinstance(body.get('data'), dict):
                raise KernelSafetyError('Unsupported mirroring request.')
            fun, data = body.get('fun'), body['data']
            if fun not in ('/input/acquire', '/input/renew', '/input/release', '/mouse/reset', '/mouse/move', '/mouse/click', '/key/sendkey'):
                raise KernelSafetyError('Mirroring cannot send that command.')
            if data.get('id') != LIVE_TEST_DEVICE_ID:
                raise KernelSafetyError('Only C24C is accepted.')
            if fun == '/key/sendkey' and set(data) - {'id', 'token'} != {'fn_key'} or fun == '/key/sendkey' and data['fn_key'] != 'ControlBar':
                raise KernelSafetyError('Mirroring sends only ControlBar.')
            if fun == '/mouse/click' and (data.get('x'), data.get('y')) not in allowed_points:
                raise KernelSafetyError('Mirroring clicks only its calibrated points.')
            if transport is not None: return transport(method, target, body, timeout)
            request = urllib.request.Request(target, data=json.dumps(body).encode('utf-8'), method=method,
                                             headers={'Content-Type': 'application/json'})
            with opener.open(request, timeout=min(timeout, 8)) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024: raise KernelSafetyError('Mirroring response exceeds its limit.')
                return raw, dict(response.headers)
        self._transport = limited
        self.devices = reader.devices


class AutoConnect:
    def __init__(self, folder, kernel=None, browse=browse, ocr=None, clock=time.monotonic, pause=time.sleep):
        self.folder = Path(folder); self.folder.mkdir(parents=True, exist_ok=True)
        self.kernel = kernel or MirroringKernel(API)
        self.browse, self.ocr, self.clock, self.pause = browse, ocr, clock, pause
        self.tokens, self.pointer = None, None
        self.record = dict(tool='farm_mirroring', receiver=RECEIVER, state='started', commands=[], observations=[],
                           blindInputs=0, phoneInput=False, publishing=False, messaging=False)

    def save(self):
        (self.folder / 'mirroring.json').write_text(json.dumps(self.record, indent=2), encoding='utf-8')

    def receiver(self):
        status = self.kernel.kernel_status()
        if status.get('allowed') != ['C24C']: raise MirroringRefused('The kernel is not restricted to C24C.')
        found = [r for r in status.get('receivers') or [] if r.get('name') == RECEIVER]
        if len(found) != 1: raise MirroringRefused(f'{RECEIVER} is not running in this kernel.')
        return found[0]

    def command(self, fun, purpose, blind=False, **data):
        item = dict(fun=fun, purpose=purpose, data=data, blind=blind, state='outcome_unknown')
        self.record['commands'].append(item); self.record['phoneInput'] = True
        if blind: self.record['blindInputs'] += 1
        self.save()
        self.kernel.send('C24C', self.tokens['C24C'], fun, **data)
        item['state'] = 'answered'; self.save()
        if fun in ('/mouse/move', '/mouse/click'): self.pointer = (data['x'], data['y'])
        if fun in ('/mouse/reset', '/key/sendkey'): self.pointer = None

    def fresh(self, role):
        for attempt in range(5):
            before = self.receiver()['frames']
            x = 450 if self.pointer == (480, 300) else 480
            self.command('/mouse/move', 'fresh_frame_challenge', x=x, y=300)
            self.pause(.3)
            raw, headers = self.kernel.shot('C24C'); taken = self.clock()
            sequence = int(headers.get('X-iMouse-Frame-Sequence', -1)); age = float(headers.get('X-iMouse-Frame-Age-Ms', 'nan'))
            entry = dict(role=role, attempt=attempt, sequence=sequence, ageMs=age, frameSha256=hashlib.sha256(raw).hexdigest(),
                         frame=f'{len(self.record["observations"])+1:02d}-{role}.bmp')
            (self.folder / entry['frame']).write_bytes(raw); self.record['observations'].append(entry); self.save()
            if sequence > before and math.isfinite(age) and age <= MAX_AGE_MS:
                return raw, taken, age
        raise InspectionStopped(f'No fresh frame for {role}; nothing more was sent.')

    def labels(self, raw):
        text = self.ocr.read(raw)
        return {line['text'].strip().casefold() for line in text.get('lines', []) if line.get('words')}

    def close_control_center(self):
        """Taps decided on fresh frames: outside the sheet, then on Control Center's empty lower area."""
        for step in ('collapse-mirroring-sheet', 'close-control-center'):
            raw, taken, age = self.fresh(step)
            labels = self.labels(raw)
            sheet = {'screen mirroring', 'stop mirroring'} <= labels
            if step == 'collapse-mirroring-sheet' and not sheet:
                continue   # Already back on the grid.
            if step == 'close-control-center' and sheet:
                raise InspectionStopped('The mirroring sheet did not collapse; no further input.')
            # Recognition is slow on a loaded PC: decide on a newer frame showing the same screen.
            confirm, confirm_taken, confirm_age = self.fresh(step + '-confirm')
            if not self.same(raw, confirm) or (self.clock() - confirm_taken) * 1000 + confirm_age > MAX_AGE_MS:
                raise InspectionStopped('Control Center changed or the decision aged out; no further input.')
            self.command('/mouse/click', step, x=CLOSE[0], y=CLOSE[1], button=1)
            self.pause(.8)

    @staticmethod
    def same(a_raw, b_raw):
        import numpy as np
        from PIL import Image
        def pixels(raw):
            with Image.open(io.BytesIO(raw)) as image: return np.asarray(image.convert('RGB'), dtype=float) / 255
        a, b = pixels(a_raw), pixels(b_raw)
        if a.shape != b.shape: return False
        mask = np.ones(a.shape[:2], dtype=bool); mask[:65] = False; mask[250:350, 400:500] = False
        return float(np.abs(a - b)[mask].mean()) <= .003

    def run(self):
        try:
            receiver = self.receiver()
            self.record['receiverBefore'] = dict(live=receiver.get('live'), frames=receiver.get('frames'))
            if receiver.get('live'):
                self.record['state'] = 'already_live'; return self.record
            if not idle(self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)):
                raise MirroringRefused('C24C is not free; no takeover is allowed.')
            names, raw_browse = self.browse()
            (self.folder / 'bonjour-browse.txt').write_text(raw_browse, encoding='utf-8')
            self.record['browse'] = dict(receivers=len(names), ours=RECEIVER in names)
            row = first_row(RECEIVER, names)
            self.tokens = self.kernel.acquire(['C24C'], 30000)
            self.command('/key/sendkey', 'open-control-center', blind=True, fn_key='ControlBar')
            self.pause(1.0)
            self.command('/mouse/click', 'open-screen-mirroring', blind=True, x=TILE[0], y=TILE[1], button=1)
            self.pause(2.0)
            self.command('/mouse/click', 'choose-' + RECEIVER, blind=True, x=ROWS[row][0], y=ROWS[row][1], button=1)
            deadline = self.clock() + LIVE_SECONDS
            while self.clock() < deadline:
                self.pause(.5)
                receiver = self.receiver()
                if receiver.get('live'): break
            else:
                raise InspectionStopped(f'{RECEIVER} did not go live within {LIVE_SECONDS:.0f} s; no retry and no further input. '
                                        'Check the phone: Control Center may still be open.')
            self.record['receiverAfter'] = dict(live=True, frames=receiver.get('frames'))
            if self.ocr is None:
                from farm_observations import WindowsOcr
                self.ocr = WindowsOcr()
            self.close_control_center()
            self.record['state'] = 'connected'
        except BaseException as error:
            self.record.update(state='stopped' if self.record['phoneInput'] else 'refused',
                               error=type(error).__name__ + ': ' + str(error))
            if not isinstance(error, InspectionStopped): raise
        finally:
            if self.tokens:
                try: self.kernel.release(self.tokens); self.record['leaseReleased'] = True
                except BaseException as error: self.record.update(leaseReleased=False, releaseError=str(error))
            self.save()
        return self.record


def main():
    record = AutoConnect(Path(sys.argv[1])).run()
    print(json.dumps({k: record.get(k) for k in ('state', 'error', 'browse', 'blindInputs', 'receiverBefore', 'receiverAfter', 'leaseReleased')}))


if __name__ == '__main__':
    main()
