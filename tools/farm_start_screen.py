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
from farm_creation_layout import control, require  # noqa: E402
from farm_draft_runs import phone_of  # noqa: E402
from farm_phone_identity import own_receiver  # noqa: E402

API = 'http://127.0.0.1:9916/api'
MAX_AGE_MS = 1500
PROFILE_TAB = (447, 1010)       # Instagram's tab bar, own-profile avatar (C24C, 20 Oct frames).
FRESH_TRIES = 5
FEED_BARS = ((0, 65, 500, 120), (0, 982, 500, 1045))   # Instagram's header and tab bar; the feed between moves (and into y 979, 21 Oct).
NEW_REEL_CLOSE = (41, 98)        # The New reel picker's close (x), slot 18, 21 Oct.
DETAILS_BACK = (30, 84)          # The Reel details' back arrow, slot 18, 22 Oct.
CONTROL_CENTER_EMPTY = (250, 960)   # Below C24C's Control Center grid (16 Sep and 20 Oct frames).


def pointer_blob(a, b, mask):
    """The pointer still settling from its reset spot, which differs per phone (C24C about (106, 70),
    724E about (172, 111), 22 Oct): one changed blob no larger than the dot, grey in one frame."""
    import numpy as np
    changed = (np.abs(a - b).max(axis=2) > 35 / 255) & mask
    ignore = np.zeros(mask.shape, dtype=bool)
    ys, xs = np.nonzero(changed)
    if not len(ys) or ys.max() - ys.min() > 34 or xs.max() - xs.min() > 34: return ignore
    top, bottom, left, right = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    def dot(frame):
        patch = frame[top:bottom, left:right][changed[top:bottom, left:right]]
        return bool(len(patch)) and float(((np.abs(patch[:, 0] - patch[:, 2]) < 12 / 255)
                                            & (patch.min(axis=1) > 110 / 255) & (patch.max(axis=1) < 200 / 255)).mean()) > .6
    if dot(a) or dot(b): ignore[max(0, top - 4):bottom + 4, max(0, left - 4):right + 4] = True
    return ignore


class StartScreen:
    def __init__(self, folder, kernel=None, ocr=None, clock=time.monotonic, pause=time.sleep, phone=None):
        self.folder = Path(folder); self.folder.mkdir(parents=True, exist_ok=True)
        if kernel is None and phone is None: raise InspectionStopped('The start screen needs the window phone or its kernel.')
        self.kernel = kernel or CreationKernel(API, phone=phone)
        self.phone = self.kernel.phone
        self.ocr, self.clock, self.pause = ocr or WindowsOcr(), clock, pause
        self.tokens, self.pointer = None, None
        self.record = dict(tool='farm_start_screen', target=None, commands=[], observations=[], state='started',
                           phoneInput=False, publishing=False, messaging=False)

    def save(self):
        (self.folder / 'start-screen.json').write_text(json.dumps(self.record, indent=2), encoding='utf-8')

    def command(self, fun, purpose, **data):
        item = dict(fun=fun, purpose=purpose, data=data, state='outcome_unknown')
        self.record['commands'].append(item); self.record['phoneInput'] = True; self.save()
        self.kernel.send(self.phone.board, self.tokens[self.phone.board], fun, **data)
        item['state'] = 'answered'; self.save()
        if fun in ('/mouse/move', '/mouse/click'): self.pointer = (data['x'], data['y'])
        if fun == '/mouse/reset': self.pointer = None

    def await_frame(self, before, polls=25):
        """With four phones mirroring, 1 in 4 nudges took 0.8-1.7 s to bring a frame (21 Oct): wait,
        bounded, for this receiver's newer delivery. The frame's own age is still checked."""
        for _ in range(polls):
            if own_receiver(self.kernel.kernel_status(), self.phone)['frames'] > before: return
            self.pause(.08)

    def fresh(self, role):
        """A new frame within the age limit: move the pointer somewhere new, then capture."""
        for attempt in range(FRESH_TRIES):
            before = own_receiver(self.kernel.kernel_status(), self.phone)['frames']
            x = 450 if self.pointer == (480, 300) else 480
            self.command('/mouse/move', 'fresh_frame_challenge', x=x, y=300)
            self.pause(.3)
            self.await_frame(before)
            raw, headers = self.kernel.shot(self.phone.board)
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

    def confirm_unchanged(self, recognized, role, only=None):
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
            before = own_receiver(self.kernel.kernel_status(), self.phone)['frames']
            x = 450 if self.pointer == (480, 300) else 480
            self.command('/mouse/move', 'fresh_frame_challenge', x=x, y=300)
            self.pause(.3)
            self.await_frame(before)
            raw, headers = self.kernel.shot(self.phone.board)
            taken = self.clock()
            sequence = int(headers.get('X-iMouse-Frame-Sequence', -1)); age = float(headers.get('X-iMouse-Frame-Age-Ms', 'inf'))
            b = pixels(raw)
            mask = np.ones(a.shape[:2], dtype=bool); mask[:65] = False; mask[250:350, 400:500] = False
            mask[45:100, 80:135] = False   # Where /mouse/reset leaves the pointer (about 106, 70; 22 Oct, slot 18).
            if only is not None:   # Screens with moving content: compare only the app's own fixed bars.
                keep = np.zeros(a.shape[:2], dtype=bool)
                for left, top, right, bottom in only: keep[top:bottom, left:right] = True
                mask &= keep
            if a.shape == b.shape: mask &= ~pointer_blob(a, b, mask)
            mean = float(np.abs(a - b)[mask].mean()) if a.shape == b.shape else 1.0
            # A live camera view adds low-amplitude sensor noise everywhere (TikTok camera, 22 Oct: mean
            # .005, no pixel off by 35 levels); real screen changes move pixels strongly.
            strong = float((np.abs(a - b).max(axis=2)[mask] > 35 / 255).mean()) if a.shape == b.shape else 1.0
            entry = dict(role=role + '-confirm', attempt=attempt, sequence=sequence, ageMs=age, before=before, mean=mean,
                         frame=f'{len(self.record["observations"])+1:02d}-{role}-confirm.bmp', frameSha256=hashlib.sha256(raw).hexdigest())
            (self.folder / entry['frame']).write_bytes(raw)
            self.record['observations'].append(entry); self.save()
            if sequence > before and age <= MAX_AGE_MS and (mean <= .003 or (mean <= .012 and strong <= .0005)):
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
        # The status row shows the battery percentage or, on the other rack phones, 'SOS only' / 'No SIM'.
        return (any(t.split()[:1] == ['focus'] and 480 < y < 580 for t, y in rows)
                and any(('%' in t or 'sos only' in t or 'no sim' in t) and y < 170 for t, y in rows))

    def new_reel_picker(self, text):
        """Instagram's 'New reel' media picker, which a stopped run can leave open; it reopens there."""
        return any(line['text'].strip().casefold() == 'new reel' and min(w['y'] for w in line['words']) < 130
                   for line in text.get('lines', []) if line.get('words'))

    def reel_editor(self, text):
        """Instagram's Reel editor ('Edit video' and Next along the bottom), where a stopped run can
        leave it; Instagram reopens there (22 Oct, slot 18)."""
        rows = [(line['text'].strip().casefold(), min(w['x'] for w in line['words']), min(w['y'] for w in line['words']))
                for line in text.get('lines', []) if line.get('words')]
        return (any(t == 'edit video' and x < 120 and 960 < y < 1020 for t, x, y in rows)
                and any(t.startswith('next') and x > 380 and 960 < y < 1020 for t, x, y in rows))

    def start_over_dialog(self, text):
        """Instagram's 'Start over?' dialog over the editor: Start over, Save draft, Keep editing, in
        that order. Returns the centre of 'Start over', or None."""
        rows = {}
        for line in text.get('lines', []):
            words = line.get('words') or []
            if not words: continue
            box = (min(w['x'] for w in words), min(w['y'] for w in words), max(w['x']+w['width'] for w in words), max(w['y']+w['height'] for w in words))
            rows.setdefault(line['text'].strip().casefold(), []).append(box)
        found = [rows.get(label, []) for label in ('start over?', 'start over', 'save draft', 'keep editing')]
        if any(len(boxes) != 1 for boxes in found): return None
        title, start, save, keep = (boxes[0] for boxes in found)
        if not (title[3] < start[1] < save[1] < keep[1] and all(150 <= b[0] and b[2] <= 350 for b in (start, save, keep))): return None
        return (round((start[0]+start[2])/2), round((start[1]+start[3])/2))

    def reel_details(self, text):
        """The new Reel's details screen ('New reel' title, Save draft and Share at the bottom), where a
        stopped run can leave Instagram (22 Oct, slot 18). Neither bottom button is ever tapped here."""
        rows = [(line['text'].strip().casefold(), min(w['x'] for w in line['words']), min(w['y'] for w in line['words']))
                for line in text.get('lines', []) if line.get('words')]
        return (any(t == 'new reel' and 180 < x < 240 and 60 < y < 110 for t, x, y in rows)
                and any(t == 'save draft' and x < 200 and 970 < y < 1020 for t, x, y in rows)
                and any(t == 'share' and x > 300 and 970 < y < 1020 for t, x, y in rows))

    def close_reel_details(self, raw, text):
        """The details' back arrow (top left) returns to the editor, which is then closed as below."""
        if not self.reel_details(text): return raw, text
        self.tap(raw, text, DETAILS_BACK, 'reel_details', 'details-back', only=((0, 60, 500, 110),))
        self.pause(1.5)
        raw, text, _, _ = self.fresh('after-details-back')
        if not self.reel_editor(text): raise InspectionStopped('The Reel details did not return to the editor; no further input.')
        return raw, text

    def close_reel_editor(self, raw, text):
        """The editor's close (x, top left) leaves an unedited selection for the New reel picker, which
        is then closed as below. Anything else (such as a discard dialog) stops with no further input."""
        if not self.reel_editor(text): return raw, text
        target = self.start_over_dialog(text)   # Already up when an earlier close stopped there.
        if not target:
            self.tap(raw, text, NEW_REEL_CLOSE, 'reel_editor', 'close-reel-editor', only=((0, 65, 500, 130),))
            self.pause(1.5)
            raw, text, _, _ = self.fresh('after-reel-editor')
            target = self.start_over_dialog(text)
        # 'Start over' drops only the unsaved editor session a stopped run left (22 Oct, slot 18);
        # 'Save draft' would turn that leftover into a draft, so it is never chosen. The first tap on
        # this dialog did not always register (22 Oct), so it is sent at most twice, each time only
        # while a fresh frame still shows the dialog.
        for attempt in range(2):
            if not target: break
            self.tap(raw, text, target, 'start_over_dialog', f'start-over-{attempt + 1}', only=((80, 360, 420, 720),))
            self.pause(1.5)
            raw, text, _, _ = self.fresh(f'after-start-over-{attempt + 1}')
            target = self.start_over_dialog(text)
        if not self.new_reel_picker(text): raise InspectionStopped('The Reel editor did not return to the New reel picker; no further input.')
        return raw, text

    def close_new_reel(self, raw, text):
        """Its close (x, top left) only leaves the picker; nothing is selected or saved there."""
        raw, text = self.close_reel_details(raw, text)
        raw, text = self.close_reel_editor(raw, text)
        if not self.new_reel_picker(text): return raw, text
        self.tap(raw, text, NEW_REEL_CLOSE, 'new_reel_picker', 'close-new-reel', only=((0, 65, 500, 130),))
        self.pause(1.5)
        raw, text, _, _ = self.fresh('after-new-reel')
        if self.new_reel_picker(text): raise InspectionStopped('The New reel picker did not close; no further input.')
        return raw, text

    def instagram_feed(self, text, raw=None):
        """Instagram's Home feed: its own story tray label near the top, or, when OCR misses that
        label (21 Oct, slot 18), the fixed Instagram logo and feed tab bar templates."""
        if any(line['text'].strip().casefold() == 'your story' and min(w['y'] for w in line['words']) < 300
               for line in text.get('lines', []) if line.get('words')):
            return True
        if raw is None: return False
        try:
            for name in ('instagram_logo', 'feed_home', 'feed_reels', 'feed_search'): control(raw, name)
            return True
        except InspectionStopped:
            return False

    def own_profile_scrolled(self, text):
        labels = {line['text'].strip().casefold() for line in text.get('lines', []) if line.get('words')}
        return {'edit profile', 'share profile'} <= labels

    def tap(self, raw, text, point, role, purpose, only=None):
        """One tap on a point recognized in `raw`, decided on a newer fresh frame showing the same screen."""
        allowed_tap(text, *point, 'open_app')
        taken, age = self.confirm_unchanged(raw, role, only)
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

    def to_tiktok_profile(self, account):
        """TikTok on the window's signed-in profile: from anywhere, Home, open TikTok, and when it lands
        on its For You feed, its own Profile tab (the creation workflow's route). One tap each."""
        import farm_tiktok_layout as tt
        def profile(raw, text):
            try: tt.tiktok_profile(raw, text, account); return True
            except InspectionStopped: return False
        self.record['target'] = 'tiktok_profile'
        self.tokens = self.kernel.acquire([self.phone.board], 30000)
        try:
            self.command('/mouse/reset', 'initial_pointer_reset')
            raw, text, _, _ = self.fresh('before')
            self.record['before'] = dict(screen='profile' if profile(raw, text) else 'other')
            if profile(raw, text):
                self.record.update(state='already_at_start'); return self.record
            raw, text, _, _ = self.open_from_home('TikTok')
            for wait in range(4):   # Its launch splash (the logo alone) can outlast the open pause (slot 20, 22 Oct).
                if [l['text'].strip().casefold() for l in text.get('lines', []) if l.get('words')] not in ([], ['tiktok']): break
                self.pause(1.5)
                raw, text, _, _ = self.fresh(f'after-splash-{wait + 1}')
            if not profile(raw, text):
                target = tt.tiktok_feed(raw, text)['profileTarget']   # Stops unless the feed is recognized.
                # Only the Profile tab: the video plays down to y 980 and an activity bubble can appear beside Inbox
                # (slot 20, 22 Oct).
                self.tap(raw, text, target, 'tiktok_feed', 'open-profile-tab', only=((400, 985, 500, 1040),))
                self.pause(1.5)
                raw, text, _, _ = self.fresh('after-profile-tab')
            require(profile(raw, text), 'TikTok did not show the authorized profile; no further input.')
            self.record.update(state='at_start', after=dict(screen='profile')); return self.record
        except BaseException as error:
            self.record.update(state='stopped', error=type(error).__name__ + ': ' + str(error)); raise
        finally:
            try: self.kernel.release(self.tokens); self.record['leaseReleased'] = True
            except BaseException as error: self.record['leaseReleased'] = False; self.record['releaseError'] = str(error)
            self.save()

    def to_x_timeline(self):
        """X on its home timeline: from anywhere, Home, then open X. No tap inside X."""
        import farm_x_layout as xl
        return self.to_app_home('X', 'x_timeline', xl.x_feed)

    def to_youtube_home(self):
        """YouTube on its home feed: from anywhere, Home, then open YouTube. A permission prompt there
        stops for the creation run's own prompt handling.

        YouTube can reopen on its Short camera (slot 16, 26 Oct), or on the camera's 'Continue your draft
        video?' prompt after a cold start. The prompt is answered with Start over, which saves that draft
        and starts a new Short; the empty camera is closed with its X. Nothing is recorded or posted."""
        import farm_youtube_layout as yl
        def back_out(raw, text):
            try: return yl.yt_draft_prompt(text)['target'], 'youtube_draft_prompt', 'start-over-saves-draft', ((78, 450, 422, 648),)
            except InspectionStopped: pass
            # A stopped verifier can leave the Drafts list or the gallery open (26 Oct); each closes with its X.
            if yl.drafts_notice(text) and yl.words_at(text, 'drafts', (60, 60, 150, 105)):
                return (44, 77), 'youtube_drafts', 'close-drafts-list', ((0, 60, 500, 175),)
            try: return yl.yt_gallery(raw, text)['closeTarget'], 'youtube_gallery', 'close-gallery', ((0, 60, 500, 205),)
            except InspectionStopped: pass
            try: yl.yt_camera(raw, text)
            except InspectionStopped: return None
            # Only the X's corner and the mode labels: the bar beside them animates (26 Oct).
            return (44, 125), 'youtube_camera', 'close-short-camera', ((0, 95, 120, 160), (120, 965, 440, 1020))
        return self.to_app_home('YouTube', 'youtube_home', yl.yt_home, back_out=back_out)

    def to_app_home(self, name, target, check, back_out=None):
        def ready(raw, text):
            try: check(raw, text); return True
            except InspectionStopped: return False
        self.record['target'] = target
        self.tokens = self.kernel.acquire([self.phone.board], 30000)
        try:
            self.command('/mouse/reset', 'initial_pointer_reset')
            raw, text, _, _ = self.fresh('before')
            self.record['before'] = dict(screen=target if ready(raw, text) else 'other')
            if ready(raw, text):
                self.record.update(state='already_at_start'); return self.record
            raw, text, _, _ = self.open_from_home(name)
            for wait in range(3):   # A relaunched app can still be drawing its first screen.
                if ready(raw, text): break
                self.pause(1.5)
                raw, text, _, _ = self.fresh(f'after-launch-{wait + 1}')
            done = set()   # Each back-out tap at most once, on a recognized screen; none is repeated.
            while back_out and not ready(raw, text):
                move = back_out(raw, text)
                if move is None or move[2] in done: break
                point, role, purpose, only = move; done.add(purpose)
                # Several back-outs outlast one 30 s lease (26 Oct: the lease expired mid-tap); renew first.
                self.kernel.renew_if_needed(self.tokens, 20000)
                self.tap(raw, text, point, role, purpose, only=only)
                for wait in range(3):
                    self.pause(1.5)
                    raw, text, _, _ = self.fresh(f'after-{purpose}-{wait + 1}')
                    if ready(raw, text) or back_out(raw, text) != move: break
            require(ready(raw, text), f'{name} did not open on its start screen; no further input.')
            self.record.update(state='at_start', after=dict(screen=target)); return self.record
        except BaseException as error:
            self.record.update(state='stopped', error=type(error).__name__ + ': ' + str(error)); raise
        finally:
            try: self.kernel.release(self.tokens); self.record['leaseReleased'] = True
            except BaseException as error: self.record['leaseReleased'] = False; self.record['releaseError'] = str(error)
            self.save()

    def to_instagram_profile_top(self):
        self.record['target'] = 'instagram_profile_top'
        status = self.kernel.preflight_phone(self.phone.board)
        self.record['preflight'] = dict(receiverLive=status['receiver'].get('live'), generation=status['input_status'].get('generation'))
        self.tokens = self.kernel.acquire([self.phone.board], 30000)
        try:
            self.command('/mouse/reset', 'initial_pointer_reset')
            raw, text, taken, age = self.fresh('before')
            if self.control_center(text):
                # Left open (for example by a manual or automatic mirroring connection); Home does not close it.
                self.tap(raw, text, CONTROL_CENTER_EMPTY, 'control_center', 'close-control-center')
                self.pause(1.0)
                raw, text, taken, age = self.fresh('after-control-center')
                if self.control_center(text): raise InspectionStopped('Control Center did not close; no further input.')
            raw, text = self.close_new_reel(raw, text)
            ready, result = self.instagram_profile(raw, text)
            self.record['before'] = dict(screen=result['screen'], accountStatus=result['accountStatus'])
            if ready:
                self.record.update(state='already_at_start'); return self.record
            if self.instagram_feed(text, raw) and not self.own_profile_scrolled(text):
                self.tap(raw, text, PROFILE_TAB, 'instagram_feed', 'open-profile-tab', only=FEED_BARS)
                self.pause(1.5)
                raw, text, taken, age = self.fresh('after-profile-tab')
                ready, result = self.instagram_profile(raw, text)
                if ready:
                    self.record.update(state='at_start', after=dict(screen=result['screen'], accountStatus=result['accountStatus'])); return self.record
            if not self.own_profile_scrolled(text):
                raw, text, taken, age = self.open_from_home('Instagram')
                raw, text = self.close_new_reel(raw, text)
                ready, result = self.instagram_profile(raw, text)
                self.record['afterOpen'] = dict(screen=result['screen'], accountStatus=result['accountStatus'])
                if ready:
                    self.record.update(state='at_start', after=self.record['afterOpen']); return self.record
                if self.instagram_feed(text, raw):
                    # A relaunched Instagram opens on its feed; the profile tab is the workflow's own route.
                    self.tap(raw, text, PROFILE_TAB, 'instagram_feed', 'open-profile-tab', only=FEED_BARS)
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
    # farm_start_screen.py instagram-profile|tiktok-profile|x-timeline|youtube-home <journal folder> <window creation config>
    target, folder, config = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if target not in ('instagram-profile', 'tiktok-profile', 'x-timeline', 'youtube-home'):
        raise SystemExit('Supported start screens: instagram-profile, tiktok-profile, x-timeline, youtube-home')
    settings = json.loads(config.read_text(encoding='utf-8-sig'))
    tool = StartScreen(folder, phone=phone_of(settings))
    try:
        if target == 'tiktok-profile': tool.to_tiktok_profile(settings['account'])
        elif target == 'x-timeline': tool.to_x_timeline()
        elif target == 'youtube-home': tool.to_youtube_home()
        else: tool.to_instagram_profile_top()
    except InspectionStopped: pass
    r = tool.record
    print(json.dumps(dict(state=r['state'], error=r.get('error'), before=r.get('before'), after=r.get('after'),
                          commands=[(c['purpose'], c['state']) for c in r['commands'] if c['purpose'] != 'fresh_frame_challenge'],
                          challenges=sum(c['purpose'] == 'fresh_frame_challenge' for c in r['commands']),
                          leaseReleased=r.get('leaseReleased'))))


if __name__ == '__main__':
    main()
