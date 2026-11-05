"""Opens one supported app on the Small phone lane's 4.7-inch phone from its Home screen, reads its sign-in
state, and returns Home. Read-only intent: Home, a 100 ms page swipe, one icon tap, Home.

Every input is decided on a fresh recognized frame (farm_small_layout); anything unrecognized stops
with nothing further sent. Signed-out screens are recorded and left: nothing on them is ever tapped.
Frames and OCR are kept under output/small-phone/<run>/ (never committed); the printed summary has no
OCR text.

  python tools/farm_small_start.py <run> <Instagram|TikTok|X|YouTube>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from farm_carousel_inspection import InspectionStopped  # noqa: E402
import farm_small_layout as L  # noqa: E402

ROOT = HERE.parent / 'output' / 'small-phone'
SETTLE_POLLS = 4
HOME_TRIES = 2      # TikTok's splash took about 7 s on the 6s (4 Nov).


class LivePhone:
    """B5 through the kernel: one lease per input, renewed before each command, released at once."""
    def __init__(self):
        from farm_small_drive import BASE, device_id
        from identify_phone import acquire, post
        self.base, self.id, self._acquire, self._post = BASE, device_id(), acquire, post

    def send(self, commands):
        token = self._acquire(self.base, self.id)
        try:
            for fun, data in commands:
                self._post(self.base, '/input/renew', dict(id=self.id, token=token))
                got = self._post(self.base, fun, dict(id=self.id, token=token, **data))
                if got.get('code') != 0: raise InspectionStopped(f'{fun} was refused: {got}')
                time.sleep(.3 if fun != '/mouse/move' else 1.2)
        finally:
            self._post(self.base, '/input/release', dict(id=self.id, token=token))

    def shot(self):
        import urllib.request
        return urllib.request.urlopen(f'{self.base}/pic/screenshot?id={self.id}', timeout=8).read()


class SmallStart:
    def __init__(self, folder, phone, ocr, reader=None, pause=time.sleep):
        self.folder = Path(folder); self.folder.mkdir(parents=True, exist_ok=True)
        self.phone, self.ocr, self.reader, self.pause = phone, ocr, reader, pause
        self.record = dict(tool='farm_small_start', steps=[], state='started', publishing=False, signIn=False)

    def save(self):
        (self.folder / 'small-start.json').write_text(json.dumps(self.record, indent=1), encoding='utf-8')

    def look(self, role):
        raw = self.phone.shot(); text = self.ocr(raw)
        name = f"{len(self.record['steps']) + 1:02d}-{role}"
        (self.folder / f'{name}.bmp').write_bytes(raw)
        (self.folder / f'{name}.json').write_text(json.dumps(text), encoding='utf-8')
        self.record['steps'].append(dict(role=role, frame=f'{name}.bmp', sha256=hashlib.sha256(raw).hexdigest()))
        self.save()
        return raw, text

    def act(self, purpose, commands, wait):
        self.record['steps'].append(dict(purpose=purpose, commands=[c[0] for c in commands])); self.save()
        self.phone.send(commands); self.pause(wait)

    def page(self, raw, text):
        try: return L.home_page(text, raw, self.reader)
        except InspectionStopped: return None

    def home(self, purpose):
        """Home only after a look: never over Control Center (4 Nov: that opened Settings) and never on
        the Home screen itself (4 Nov: a Home on page 2 opened Control Center once)."""
        raw, text = self.look('before-' + purpose)
        if L.control_center(text): raise InspectionStopped('Control Center is open; Home is not sent over it.')
        page = self.page(raw, text)
        for attempt in range(HOME_TRIES if page is None else 0):
            # A Home on YouTube's welcome screen was ignored once (4 Nov); one bounded retry, only while
            # the screen is still not Home and not Control Center.
            self.act(f'{purpose}-{attempt}', [('/mouse/reset', {}), ('/key/sendkey', dict(fn_key='Home'))], 1.5)
            raw, text = self.look(f'after-{purpose}-{attempt}')
            if L.control_center(text): raise InspectionStopped('Home opened Control Center; nothing else was sent.')
            page = self.page(raw, text)
            if page is None:
                self.pause(2); raw, text = self.look(f'reread-{purpose}-{attempt}'); page = self.page(raw, text)
                if L.control_center(text): raise InspectionStopped('Home opened Control Center; nothing else was sent.')
            if page is not None: break
        return raw, text, page

    def to_social_page(self):
        raw, text, page = self.home('home')
        if page is None:
            raise InspectionStopped('The Home screen is not recognized after Home; nothing else was sent.')
        if page == 1:
            self.act('page-left', [('/mouse/reset', {}), ('/mouse/swipe', L.PAGE_LEFT)], 1.5)
            raw, text = self.look('page-2')
            if self.page(raw, text) != 2: raise InspectionStopped('Home page 2 is not recognized after the page swipe.')
        return raw, text

    def open(self, app):
        try:
            raw, text = self.to_social_page()
            x, y = L.app_icon(text, app, raw, self.reader)
            self.act('open-' + app.casefold(), [('/mouse/reset', {}), ('/mouse/move', dict(x=x, y=y)),
                                                ('/mouse/click', dict(x=x, y=y, button=1)), ('/mouse/move', dict(x=480, y=300))], 5)
            for poll in range(SETTLE_POLLS):
                raw, text = self.look(f'{app.casefold()}-{poll}')
                state = L.app_state(text, app)
                if state['state'] != 'splash': break
                self.pause(3)
            self.record['app'] = state
            raw, text, page = self.home('home-out')
            self.record['returnedHome'] = page is not None
            self.record['state'] = 'done'
        except InspectionStopped as stop:
            self.record['state'] = 'stopped'; self.record['error'] = str(stop)
        self.save()
        return dict(state=self.record['state'], app=self.record.get('app'), returnedHome=self.record.get('returnedHome'),
                    error=self.record.get('error'))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('run'); p.add_argument('app', choices=L.SUPPORTED)
    a = p.parse_args()
    from farm_observations import WindowsOcr
    ocr = WindowsOcr()
    print(json.dumps(SmallStart(ROOT / a.run, LivePhone(), ocr.read).open(a.app)))


if __name__ == '__main__':
    main()
