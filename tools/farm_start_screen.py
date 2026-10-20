"""Guarded "go to the start screen" helper for a live C24C window.

Brings the phone to a window's verified start screen before a run, so the
operator does not have to. Every input is decided on a fresh, recognized frame
under a held lease; nothing is sent blind, and an uncertain answer is never
repeated. It refuses on any screen it does not recognize. Supported now: the
Instagram profile scrolled to the top (one tap on the active profile tab).

Usage: python farm_start_screen.py instagram-profile <journal folder>
Writes a private journal (frames and OCR stay in that folder); prints a summary
without OCR text.
"""
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from farm_carousel_inspection import InspectionStopped  # noqa: E402
from farm_draft_transport import CreationKernel, allowed_tap  # noqa: E402
from farm_observations import WindowsOcr, classify  # noqa: E402
from imouse_social_automation import LIVE_TEST_DEVICE_ID  # noqa: E402

API = 'http://127.0.0.1:9916/api'
MAX_AGE_MS = 1500
PROFILE_TAB = (447, 1010)       # Instagram's tab bar, own-profile avatar (C24C, 20 Oct frames).
FRESH_TRIES = 5
CONTROL_CENTER_EMPTY = (250, 960)   # Below C24C's Control Center grid (16 Sep and 20 Oct frames).


class StartScreen:
    def __init__(self, folder, kernel=None, ocr=None, clock=time.monotonic, pause=time.sleep):
        self.folder = Path(folder); self.folder.mkdir(parents=True, exist_ok=True)
        self.kernel = kernel or CreationKernel(API)
        self.ocr, self.clock, self.pause = ocr or WindowsOcr(), clock, pause
        self.tokens, self.pointer = None, None
        self.record = dict(tool='farm_start_screen', target=None, commands=[], observations=[], state='started',
                           phoneInput=False, publishing=False, messaging=False)

    def save(self):
        (self.folder / 'start-screen.json').write_text(json.dumps(self.record, indent=2), encoding='utf-8')

    def command(self, fun, purpose, **data):
        item = dict(fun=fun, purpose=purpose, data=data, state='outcome_unknown')
        self.record['commands'].append(item); self.record['phoneInput'] = True; self.save()
        self.kernel.send('C24C', self.tokens['C24C'], fun, **data)
        item['state'] = 'answered'; self.save()
        if fun in ('/mouse/move', '/mouse/click'): self.pointer = (data['x'], data['y'])
        if fun == '/mouse/reset': self.pointer = None

    def fresh(self, role):
        """A new frame within the age limit: move the pointer somewhere new, then capture."""
        for attempt in range(FRESH_TRIES):
            before = self.kernel.kernel_status()['receivers'][0]['frames']
            x = 450 if self.pointer == (480, 300) else 480
            self.command('/mouse/move', 'fresh_frame_challenge', x=x, y=300)
            self.pause(.3)
            raw, headers = self.kernel.shot('C24C')
            taken = self.clock()
            sequence = int(headers.get('X-iMouse-Frame-Sequence', -1))
            age = float(headers.get('X-iMouse-Frame-Age-Ms', 'inf'))
            entry = dict(role=role, attempt=attempt, sequence=sequence, ageMs=age, before=before,
                         frame=f'{len(self.record["observations"])+1:02d}-{role}.bmp', frameSha256=hashlib.sha256(raw).hexdigest())
            (self.folder / entry['frame']).write_bytes(raw)
            self.record['observations'].append(entry); self.save()
            if sequence > before and age <= MAX_AGE_MS:
                text = self.ocr.read(raw)
                (self.folder / entry['frame'].replace('.bmp', '.json')).write_text(json.dumps(text), encoding='utf-8')
                entry['state'] = 'fresh'; self.save()
                return raw, text, taken, age
            entry['state'] = 'stale_or_old'; self.save()
        raise InspectionStopped(f'No fresh frame for {role} after {FRESH_TRIES} pointer challenges; nothing was tapped.')

    def confirm_unchanged(self, recognized, role):
        """Recognition (OCR) is slow on a loaded PC; a decision uses a newer frame that shows the same screen.

        Frame B must be fresh and match recognized frame A outside the status bar and the
        pointer's challenge area; then B's age budget, not A's, governs the decision.
        """
        import io
        import numpy as np
        from PIL import Image
        def pixels(raw):
            with Image.open(io.BytesIO(raw)) as image: return np.asarray(image.convert('RGB'), dtype=float) / 255
        a = pixels(recognized)
        for attempt in range(FRESH_TRIES):
            before = self.kernel.kernel_status()['receivers'][0]['frames']
            x = 450 if self.pointer == (480, 300) else 480
            self.command('/mouse/move', 'fresh_frame_challenge', x=x, y=300)
            self.pause(.3)
            raw, headers = self.kernel.shot('C24C')
            taken = self.clock()
            sequence = int(headers.get('X-iMouse-Frame-Sequence', -1)); age = float(headers.get('X-iMouse-Frame-Age-Ms', 'inf'))
            b = pixels(raw)
            mask = np.ones(a.shape[:2], dtype=bool); mask[:65] = False; mask[250:350, 400:500] = False
            mean = float(np.abs(a - b)[mask].mean()) if a.shape == b.shape else 1.0
            entry = dict(role=role + '-confirm', attempt=attempt, sequence=sequence, ageMs=age, before=before, mean=mean,
                         frame=f'{len(self.record["observations"])+1:02d}-{role}-confirm.bmp', frameSha256=hashlib.sha256(raw).hexdigest())
            (self.folder / entry['frame']).write_bytes(raw)
            self.record['observations'].append(entry); self.save()
            if sequence > before and age <= MAX_AGE_MS and mean <= .003:
                entry['state'] = 'fresh_unchanged'; self.save()
                return taken, age
            entry['state'] = 'stale_or_changed'; self.save()
        raise InspectionStopped(f'No fresh frame matching the recognized {role} screen; nothing was tapped.')

    def instagram_profile(self, raw, text):
        result = classify(text, dict(platform='instagram', account='xs.halle.xo', caption=''), raw)
        return result['screen'] == 'profile' and result['accountStatus'] == 'exact_text_match', result

    def control_center(self, text):
        """C24C's Control Center: its Focus tile and the battery percentage in the status row."""
        rows = [(line['text'].strip().casefold(), min(w['y'] for w in line['words'])) for line in text.get('lines', []) if line.get('words')]
        # OCR reads the tile as 'Focus' plus its chevron and the status row with stray icon glyphs.
        return (any(t.split()[:1] == ['focus'] and 480 < y < 580 for t, y in rows)
                and any('%' in t and y < 170 for t, y in rows))

    def instagram_feed(self, text):
        """Instagram's Home feed: its own story tray label near the top."""
        return any(line['text'].strip().casefold() == 'your story' and min(w['y'] for w in line['words']) < 300
                   for line in text.get('lines', []) if line.get('words'))

    def own_profile_scrolled(self, text):
        labels = {line['text'].strip().casefold() for line in text.get('lines', []) if line.get('words')}
        return {'edit profile', 'share profile'} <= labels

    def tap(self, raw, text, point, role, purpose):
        """One tap on a point recognized in `raw`, decided on a newer fresh frame showing the same screen."""
        allowed_tap(text, *point, 'open_app')
        taken, age = self.confirm_unchanged(raw, role)
        if (self.clock() - taken) * 1000 + age > MAX_AGE_MS:
            raise InspectionStopped(f'The {role} decision aged past the limit; nothing was tapped.')
        self.command('/mouse/click', purpose, x=point[0], y=point[1], button=1)
        self.command('/mouse/move', 'park_after_answered_action', x=480, y=300)

    def open_from_home(self, name):
        """The workflow's own route: Home, then the app icon, or Spotlight's Search pill and its Top Hit."""
        from farm_creation_layout import app_target, control, empty_search, home_search
        from farm_draft_workflow import centre
        # Home only leaves the current app for the home screen; it is never an app action.
        self.command('/key/sendkey', 'home-before-start-screen', fn_key='Home')
        self.pause(1.2)
        raw, text, _, _ = self.fresh('home')
        try: point = app_target(text, name, raw)
        except InspectionStopped: point = None
        if point is None:
            self.tap(raw, text, centre(home_search(raw, text)), 'home', 'open-app-search')
            self.pause(1.2)
            raw, text, _, _ = self.fresh('app_search_entry')
            try: point = app_target(text, name, raw)
            except InspectionStopped: point = None
            if point is None:
                try: empty = empty_search(text, raw)
                except InspectionStopped: empty = False
                if not empty:
                    self.tap(raw, text, centre(control(raw, 'search_clear')), 'app_search_entry', 'clear-restored-search')
                    self.pause(.8)
                    raw, text, _, _ = self.fresh('app_search_cleared')
                    empty_search(text, raw)
                self.command('/key/sendkey', 'query-' + name.casefold(), key=name)
                self.pause(1.5)
                raw, text, _, _ = self.fresh('app_result')
                point = app_target(text, name, raw)
        self.tap(raw, text, point, 'app_result', 'open-' + name.casefold())
        self.pause(2.5)
        return self.fresh('after-open')

    def to_instagram_profile_top(self):
        self.record['target'] = 'instagram_profile_top'
        status = self.kernel.preflight_phone('C24C')
        self.record['preflight'] = dict(receiverLive=status['receiver'].get('live'), generation=status['input_status'].get('generation'))
        self.tokens = self.kernel.acquire(['C24C'], 30000)
        try:
            self.command('/mouse/reset', 'initial_pointer_reset')
            raw, text, taken, age = self.fresh('before')
            if self.control_center(text):
                # Left open (for example by a manual or automatic mirroring connection); Home does not close it.
                self.tap(raw, text, CONTROL_CENTER_EMPTY, 'control_center', 'close-control-center')
                self.pause(1.0)
                raw, text, taken, age = self.fresh('after-control-center')
                if self.control_center(text): raise InspectionStopped('Control Center did not close; no further input.')
            ready, result = self.instagram_profile(raw, text)
            self.record['before'] = dict(screen=result['screen'], accountStatus=result['accountStatus'])
            if ready:
                self.record.update(state='already_at_start'); return self.record
            if not self.own_profile_scrolled(text):
                raw, text, taken, age = self.open_from_home('Instagram')
                ready, result = self.instagram_profile(raw, text)
                self.record['afterOpen'] = dict(screen=result['screen'], accountStatus=result['accountStatus'])
                if ready:
                    self.record.update(state='at_start', after=self.record['afterOpen']); return self.record
                if self.instagram_feed(text):
                    # A relaunched Instagram opens on its feed; the profile tab is the workflow's own route.
                    self.tap(raw, text, PROFILE_TAB, 'instagram_feed', 'open-profile-tab')
                    self.pause(1.5)
                    raw, text, taken, age = self.fresh('after-profile-tab')
                    ready, result = self.instagram_profile(raw, text)
                    self.record['afterProfileTab'] = dict(screen=result['screen'], accountStatus=result['accountStatus'])
                    if ready:
                        self.record.update(state='at_start', after=self.record['afterProfileTab']); return self.record
                if not self.own_profile_scrolled(text):
                    raise InspectionStopped('Instagram did not open on the authorized profile; no further input.')
            allowed_tap(text, *PROFILE_TAB, 'instagram_profile_tab')
            taken, age = self.confirm_unchanged(raw, 'before')
            if (self.clock() - taken) * 1000 + age > MAX_AGE_MS:
                raise InspectionStopped('The decision frame aged past the limit; nothing was tapped.')
            self.command('/mouse/click', 'scroll-profile-to-top', x=PROFILE_TAB[0], y=PROFILE_TAB[1], button=1)
            self.command('/mouse/move', 'park_after_answered_action', x=480, y=300)
            for check in range(3):
                self.pause(1.0)
                raw, text, _, _ = self.fresh('after')
                ready, result = self.instagram_profile(raw, text)
                if ready:
                    self.record.update(state='at_start', after=dict(screen=result['screen'], accountStatus=result['accountStatus']))
                    return self.record
            raise InspectionStopped('The profile header did not appear after one tap; no tap is repeated.')
        except BaseException as error:
            self.record.update(state='stopped', error=type(error).__name__ + ': ' + str(error)); raise
        finally:
            try: self.kernel.release(self.tokens); self.record['leaseReleased'] = True
            except BaseException as error: self.record['leaseReleased'] = False; self.record['releaseError'] = str(error)
            self.save()


def main():
    target, folder = sys.argv[1], Path(sys.argv[2])
    if target != 'instagram-profile': raise SystemExit('Supported start screen: instagram-profile')
    tool = StartScreen(folder)
    try: tool.to_instagram_profile_top()
    except InspectionStopped: pass
    r = tool.record
    print(json.dumps(dict(state=r['state'], error=r.get('error'), before=r.get('before'), after=r.get('after'),
                          commands=[(c['purpose'], c['state']) for c in r['commands'] if c['purpose'] != 'fresh_frame_challenge'],
                          challenges=sum(c['purpose'] == 'fresh_frame_challenge' for c in r['commands']),
                          leaseReleased=r.get('leaseReleased'))))


if __name__ == '__main__':
    main()
