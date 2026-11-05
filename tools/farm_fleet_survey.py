"""Fleet lane: read-only survey of one rack A phone outside the farm's four (5 Nov 2026).

Reads Home pages 1-2, then opens Instagram, TikTok, X and YouTube once each, reads whether an account is
signed in, and returns Home. Navigation only: Home, page swipes, one icon tap per app (or, on the XRs,
Spotlight's Search pill, the app name and its Top Hit, as farm_start_screen does). Nothing on an app's
screen is tapped except an iOS permission prompt's policy answer (farm_permission_prompts, families whose
answer changes nothing), once, recorded with its point and outcome. Signed-out screens are left untouched.

Every input is decided on a fresh frame under this phone's own lease (farm_start_screen.StartScreen).
Home is never sent over Control Center. Frames and OCR stay under output/fleet/<run>/ (not committed);
the printed summary carries no OCR text, so no handles.

  python tools/farm_fleet_survey.py <board> [--run name] [--apps Instagram,TikTok,X,YouTube]
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from farm_carousel_inspection import InspectionStopped  # noqa: E402

ROOT = HERE.parent / 'output' / 'fleet'
API = 'http://127.0.0.1:9916/api'
# The Fleet lane's phones (orchestrator brief, 5 Nov): rack A outside A16-A18 and A20. Model None = read from the frame.
FLEET = {'1814': ('A2', 'small'), '704E': ('A5', 'small'), '694E': ('A6', 'small'), '1248': ('A7', 'small'),
         'D446': ('A8', 'small'), '374C': ('A10', 'xr'), 'E414': ('A11', 'xr'), '3523': ('A12', 'xr'),
         'C415': ('A13', 'xr'), '764E': ('A14', 'xr'), '9515': ('A15', 'xr'), 'C241': ('A19', 'xr'),
         '3848': ('3848', None), '7949': ('7949', None), 'D142': ('D142', None)}
APPS = ('Instagram', 'TikTok', 'X', 'YouTube')
# Home grid label rows (OCR line tops). XR: farm_creation_layout.home. 4.7-inch: farm_small_layout ROWS + LABEL_DROP.
LABEL_ROWS = {'xr': (171, 298, 425, 552, 679, 806), 'small': (225, 342, 460, 577, 694, 811)}
ICON_DROP = {'xr': 62, 'small': 50}      # Label top -> icon centre.
SWIPE_MS = {'xr': 250, 'small': 100}     # 4.7-inch: slower swipes count as a long press (icons wiggle, 30 Oct).
SWIPE_Y = {'xr': 500, 'small': 560}
SETTLE_LOOKS = 4

# What each app shows (OCR, case-folded). Signed out: farm_small_layout.SIGNED_OUT plus the XR wording.
SIGNED_OUT = {
    'Instagram': ('username, email or mobile number', 'create new account', 'log into another account', 'i already have an account'),
    'TikTok': ('log in to tiktok', 'sign up for tiktok', 'use phone / email / username', "don't have an account? sign up"),
    'X': ("see what's happening in the world right now", 'create account', 'have an account already? log in'),
    'YouTube': ('welcome to youtube', 'sign in with google', 'use youtube signed out', "you're not signed in"),
}
# Signed in: the platform's own logged-in chrome. Anything else is 'unknown' (never read as signed in).
SIGNED_IN = {
    'Instagram': (('your story',), ('your story',)),   # The tab bar is icons only (A11, A12: feed with 'Your story').
    'TikTok': (('inbox',), ('profile', 'friends')),
    'X': (('for you',), ('following',)),
    'YouTube': (('subscriptions',), ('shorts', 'you')),
}
SPLASH = ('it starts on', 'tiktok.')


def rows(text):
    out = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        out.append(dict(fold=' '.join(line.get('text', '').replace('’', "'").casefold().split()),
                        box=(min(w['x'] for w in words), min(w['y'] for w in words),
                             max(w['x'] + w['width'] for w in words), max(w['y'] + w['height'] for w in words))))
    return out


def grid_labels(text, model):
    """{label: (x, label_top)} for OCR lines on the Home icon grid rows."""
    found = {}
    for r in rows(text):
        left, top, right, bottom = r['box']
        if right - left > 140 or not r['fold']: continue
        if any(abs(top - line) < 18 for line in LABEL_ROWS[model]):
            found[r['fold']] = ((left + right) // 2, top)
    return found


def home_like(text, model):
    return len(grid_labels(text, model)) >= 4


def model_of(raw):
    """'small' when the mirror frame is letterboxed (4.7-inch: screen y 95-985), 'xr' when content fills it."""
    import numpy as np
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:
        grey = np.asarray(image.convert('L'), dtype=float)
    h = grey.shape[0]
    bands = np.concatenate([grey[5:int(h * .08)], grey[int(h * .92):h - 5]])
    middle = grey[int(h * .2):int(h * .8)]
    if middle.max() < 30: return None   # Dark screen: asleep or black.
    return 'small' if bands.max() < 25 else 'xr'


def dark(raw):
    import numpy as np
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:
        return float(np.asarray(image.convert('L'), dtype=float).max()) < 30


def label_matches(fold, name):
    fold = re.sub(r'[^a-z0-9 ]', '', fold)
    name = name.casefold()
    if name == 'x': return fold == 'x'
    return fold == name or (len(name) > 4 and fold in (name[1:], name[:-1]))


def app_state(text, app):
    joined = ' '.join(r['fold'] for r in rows(text))
    folds = {r['fold'] for r in rows(text)}
    if any(phrase in joined for phrase in SIGNED_OUT[app]): return 'signed_out'
    if app == 'TikTok' and all(part in joined for part in SPLASH): return 'splash'
    need, extra = SIGNED_IN[app]
    if all(n in folds or n in joined for n in need) and any(e in folds for e in extra): return 'signed_in'
    return 'unknown'


ALERT_COLUMN = (85, 415)    # An iOS alert's x span in the mirror frame (A11 photos reminder: about 95-405).
ALERT_HEIGHT = 600          # The tallest alert (photos reminder with thumbnails) is about 520 px above its last button.


def alert_only(text):
    """The OCR lines of a centred iOS alert, without the dimmed Home labels behind it. Over the Home screen the
    labels interleave with the alert's sentence (A11, 5 Nov: '...allow full yah access?') and the shared
    recognizer misses it. With no alert button read, the text is returned unchanged."""
    import farm_permission_prompts as P
    lines = [l for l in text.get('lines', []) if l.get('words')]
    def box(l): return (min(w['x'] for w in l['words']), min(w['y'] for w in l['words']),
                        max(w['x'] + w['width'] for w in l['words']), max(w['y'] + w['height'] for w in l['words']))
    buttons = [box(l) for l in lines if any(' '.join(l['text'].replace('’', "'").split()).casefold() == b.casefold() for b in P.BUTTONS)]
    if not buttons: return text
    bottom = max(b[3] for b in buttons)
    keep = [l for l in lines if ALERT_COLUMN[0] <= box(l)[0] and box(l)[2] <= ALERT_COLUMN[1]
            and bottom - ALERT_HEIGHT <= box(l)[1] <= bottom]
    return dict(text, lines=keep)


def control_center(survey, text):
    import farm_small_layout as L
    return survey.control_center(text) or L.control_center(text)


class FleetSurvey:
    """One phone. `screen` is a StartScreen (lease, fresh frames, confirmed taps, record)."""
    def __init__(self, screen, label, model):
        self.s, self.label, self.model = screen, label, model
        self.record = screen.record
        self.record.update(tool='farm_fleet_survey', phoneLabel=label, model=model, pages={}, apps={}, prompts=[],
                           homes=0, signIn=False)

    def look(self, role, app=None):
        """A fresh frame. An iOS prompt on it is answered first (A11, 5 Nov: Instagram's photos reminder came up
        over the Home screen after Home, and the page swipes and Search pill tap behind it did nothing)."""
        raw, text, _, _ = self.s.fresh(role)
        answered = self.answer_prompt(app or 'system', raw, text)
        return answered if answered else (raw, text)

    def home(self, purpose, raw=None, text=None):
        """Home only after a look; never over Control Center; never on the Home screen itself. At most two."""
        if raw is None: raw, text = self.look('before-' + purpose)
        for attempt in range(2):
            if control_center(self.s, text): raise InspectionStopped('Control Center is open; Home is never sent over it.')
            if home_like(text, self.model or 'xr') and not dark(raw): return raw, text
            self.s.command('/key/sendkey', f'{purpose}-home-{attempt}', fn_key='Home')
            self.record['homes'] += 1
            self.s.pause(1.6)
            raw, text = self.look(f'after-{purpose}-{attempt}')
            if self.model is None: self.model = self.record['model'] = model_of(raw)
            if control_center(self.s, text): raise InspectionStopped('Home opened Control Center; nothing else was sent.')
        if not home_like(text, self.model or 'xr'):
            raise InspectionStopped(f'The Home screen is not recognized after Home ({purpose}); nothing else was sent.')
        return raw, text

    def swipe(self, direction, purpose):
        y = SWIPE_Y[self.model]
        x1, x2 = (430, 70) if direction == 'left' else (70, 430)
        self.s.command('/mouse/reset', 'reset-before-swipe')
        self.s.command('/mouse/swipe', purpose, x1=x1, y1=y, x2=x2, y2=y, duration=SWIPE_MS[self.model])
        self.s.pause(1.2)
        return self.look(purpose)

    def to_page_one(self, raw, text):
        """Swipe right until the screen is no longer a Home page (Today View), then one page back."""
        for n in range(4):
            before = set(grid_labels(text, self.model))
            raw2, text2 = self.swipe('right', f'page-right-{n}')
            if control_center(self.s, text2): raise InspectionStopped('Control Center opened on a page swipe.')
            if not home_like(text2, self.model):
                return self.swipe('left', 'back-to-page-1')
            if set(grid_labels(text2, self.model)) == before:
                return raw2, text2   # The swipe changed nothing: already the first page (no Today View).
            raw, text = raw2, text2
        raise InspectionStopped('Page 1 was not reached in four swipes.')

    def read_pages(self):
        raw, text = self.home('start')
        raw, text = self.to_page_one(raw, text)
        if not home_like(text, self.model): raise InspectionStopped('Page 1 is not a recognized Home page.')
        page1 = grid_labels(text, self.model)
        raw2, text2 = self.swipe('left', 'page-2')
        page2 = grid_labels(text2, self.model) if home_like(text2, self.model) else {}
        if set(page2) == set(page1): page2 = {}
        self.pages = {1: page1, 2: page2}
        self.record['pages'] = {str(k): dict(icons=len(v), apps=[a for a in APPS if any(label_matches(f, a) for f in v)])
                                for k, v in self.pages.items()}
        self.current = 2 if page2 else 1
        return raw2, text2

    def go_page(self, page, raw, text):
        while self.current != page:
            direction = 'left' if page > self.current else 'right'
            raw, text = self.swipe(direction, f'to-page-{page}')
            self.current += 1 if direction == 'left' else -1
            if not home_like(text, self.model): raise InspectionStopped(f'Page {page} is not a recognized Home page.')
        return raw, text

    def open_app(self, app, raw, text):
        page = next((p for p, labels in self.pages.items() if any(label_matches(f, app) for f in labels)), None)
        if page is None:
            if self.model != 'xr':
                return dict(state='not_on_pages_1_2', opened=False), raw, text
            try: raw, text, _, _ = self.s.open_from_home(app)   # XR: Spotlight's Search pill and its Top Hit.
            except InspectionStopped as stop:
                if app != 'X' or 'Exact visible label missing' not in str(stop): raise
                # OCR misses X's one-letter Top Hit label (A12, 5 Nov; A17, 4 Nov): the X lane's icon recognizer decides.
                from farm_x_image_creation import x_top_hit
                raw, text = self.look('x_app_result')
                self.s.tap(raw, text, x_top_hit(raw, text), 'x_app_result', 'open-x')
                self.s.pause(2.5)
                raw, text = self.look('after-open-x')
            return dict(route='spotlight', opened=True), raw, text
        raw, text = self.go_page(page, raw, text)
        labels = grid_labels(text, self.model)
        hits = [point for fold, point in labels.items() if label_matches(fold, app)]
        if len(hits) != 1: raise InspectionStopped(f'{app} label is missing or ambiguous on page {page}.')
        x, top = hits[0]
        self.s.tap(raw, text, (x, top - ICON_DROP[self.model]), 'home', 'open-' + app.casefold())
        self.s.pause(3)
        return dict(route=f'page-{page}', opened=True), raw, text

    def answer_prompt(self, app, raw, text):
        import farm_permission_prompts as P
        prompt = P.detect(alert_only(text))
        if prompt is None: return None
        answer = P.POLICY.get(prompt['kind'])
        entry = dict(app=app, promptApp=prompt.get('app'), kind=prompt['kind'], answer=answer, method=None, point=None, outcome=None)
        self.record['prompts'].append(entry)
        if prompt['kind'] not in P.ALWAYS_SAFE or answer is None or prompt.get('ambiguous') or answer not in prompt['buttons']:
            entry['outcome'] = 'stopped_not_in_policy'
            raise InspectionStopped(f"{app}: a {prompt['kind']} prompt has no policy answer here; nothing was tapped.")
        point = prompt['buttons'][answer]
        entry.update(method='pointer_tap', point=list(point))
        self.s.tap(raw, text, point, 'prompt', f"prompt-{prompt['kind']}")
        self.s.pause(1.5)
        raw, text, _, _ = self.s.fresh(f'{app.casefold()}-after-prompt')
        entry['frame'] = self.record['observations'][-1]['frame']
        again = P.detect(alert_only(text))
        entry['outcome'] = 'ignored' if again and again['kind'] == prompt['kind'] else 'answered'
        if entry['outcome'] == 'ignored': raise InspectionStopped(f"{app}: the {prompt['kind']} prompt ignored its tap.")
        return raw, text

    def survey_app(self, app, raw, text):
        result, raw, text = self.open_app(app, raw, text)
        self.record['apps'][app] = result
        if not result['opened']: return raw, text
        state = 'unknown'
        for n in range(SETTLE_LOOKS):
            raw, text = self.look(f'{app.casefold()}-{n}', app)
            state = app_state(text, app)
            if state in ('signed_in', 'signed_out'): break
            self.s.pause(3)
        result['state'] = state
        result['frame'] = self.record['observations'][-1]['frame']
        self.s.save()
        raw, text = self.home('leave-' + app.casefold(), raw, text)
        self.current = None
        # Home returns to the page the app was opened from; read which one it is.
        labels = set(grid_labels(text, self.model))
        self.current = next((p for p, v in self.pages.items() if v and len(labels & set(v)) >= max(3, len(v) // 2)), 1)
        return raw, text

    def to_instagram_profile(self):
        """Instagram on the signed-in account's own profile, for a Reel window on this phone: Home, open Instagram,
        then its own profile tab (farm_start_screen.PROFILE_TAB, decided on the recognized feed). The shared
        instagram-profile start screen compares against A18's account, so it cannot bring another phone there."""
        from farm_start_screen import PROFILE_TAB, FEED_BARS
        raw, text = self.home('home')
        raw, text, _, _ = self.s.open_from_home('Instagram')
        for n in range(SETTLE_LOOKS):
            raw, text = self.look(f'instagram-{n}', 'Instagram')
            if self.s.instagram_feed(text, raw): break
            self.s.pause(2)
        if not self.s.instagram_feed(text, raw): raise InspectionStopped('Instagram did not open on its feed; nothing was tapped in it.')
        self.s.tap(raw, text, PROFILE_TAB, 'instagram_feed', 'open-profile-tab', only=FEED_BARS)
        self.s.pause(1.5)
        raw, text = self.look('instagram-profile', 'Instagram')
        # The own profile: its Edit profile and Share profile buttons (A14, 5 Nov). The shared classifier needs the
        # account to call it a profile, and the account is what this step is for (it stays in the run folder).
        own = {'edit profile', 'share profile'} <= {r['fold'] for r in rows(text)}
        self.record['apps']['Instagram'] = dict(route='profile', screen='own_profile' if own else 'other',
                                                frame=self.record['observations'][-1]['frame'])
        if not own: raise InspectionStopped('The profile tab did not open the own profile; no tap is repeated.')
        self.record['state'] = 'done'

    def to_tiktok_profile(self):
        """TikTok on its own Profile tab, to read the signed-in handle for a TikTok window (the shared tiktok-profile
        start screen needs that handle first). Home, open TikTok, one tap on the feed's Profile tab."""
        import farm_tiktok_layout as tt
        raw, text = self.home('home')
        raw, text, _, _ = self.s.open_from_home('TikTok')
        for n in range(SETTLE_LOOKS):
            raw, text = self.look(f'tiktok-{n}', 'TikTok')
            try: target = tt.tiktok_feed(raw, text)['profileTarget']; break
            except InspectionStopped: target = None
            self.s.pause(2)
        if target is None: raise InspectionStopped('TikTok did not open on its For You feed; nothing was tapped in it.')
        self.s.tap(raw, text, target, 'tiktok_feed', 'open-profile-tab', only=((400, 985, 500, 1040),))
        self.s.pause(1.5)
        raw, text = self.look('tiktok-profile', 'TikTok')
        folds = {r['fold'] for r in rows(text)}   # TikTok's own profile: Edit (A14, 5 Nov) or Edit profile, Followers, @handle.
        own = bool(folds & {'edit', 'edit profile'}) and 'followers' in folds and any(f.startswith('@') for f in folds)
        self.record['apps']['TikTok'] = dict(route='profile', screen='own_profile' if own else 'other',
                                             frame=self.record['observations'][-1]['frame'])
        if not own: raise InspectionStopped('The Profile tab did not open the own profile; no tap is repeated.')
        self.record['state'] = 'done'

    def run(self, apps):
        raw, text = self.read_pages()
        for app in apps:
            raw, text = self.survey_app(app, raw, text)
        self.record['state'] = 'done'


LEASE_MS = 30000
RENEW_BELOW_MS = 20000


def renewing(screen):
    """StartScreen sends on one 30 s lease and never renews it: enough for one start screen, not for a survey
    (A11, 5 Nov 17:28: the lease expired at the Instagram step and the kernel stopped that phone's input).
    Every command renews first while less than 20 s remain."""
    send = screen.command
    def command(fun, purpose, **data):
        screen.kernel.renew_if_needed(screen.tokens, RENEW_BELOW_MS)
        return send(fun, purpose, **data)
    screen.command = command
    return screen


def pointer_landing(screen, point, record):
    """Where the pointer actually lands for `point`: moves only, never a click. The parked frame and the frame with
    the pointer at `point` differ only in the pointer's dot; its centroid near `point` is the landing (orchestrator,
    5 Nov: check an 'ignored' tap against the button's OCR box before blaming iOS; 26 Oct a tap was 33 px off)."""
    import numpy as np
    from PIL import Image
    def grab(role):
        raw, _, _, _ = screen.fresh(role)   # fresh() itself moves the pointer to (480|450, 300) first.
        return raw
    screen.command('/mouse/reset', 'measure-reset')
    parked = grab('measure-parked')
    before = screen.kernel.kernel_status()
    screen.command('/mouse/move', 'measure-move', x=point[0], y=point[1])
    screen.pause(1.5)
    raw, headers = screen.kernel.shot(screen.phone.board)
    (screen.folder / 'measure-at-point.bmp').write_bytes(raw)
    a = np.asarray(Image.open(io.BytesIO(parked)).convert('L'), dtype=float)
    b = np.asarray(Image.open(io.BytesIO(raw)).convert('L'), dtype=float)
    diff = np.abs(a - b) > 40
    diff[250:350, 400:500] = False   # The parked pointer's own spot.
    window = np.zeros_like(diff); x, y = point
    window[max(0, y - 120):y + 120, max(0, x - 120):x + 120] = True
    ys, xs = np.nonzero(diff & window)
    landing = (int(xs.mean()), int(ys.mean())) if len(xs) >= 20 else None
    record['measure'] = dict(point=list(point), landing=list(landing) if landing else None, pixels=int(len(xs)),
                             offset=[landing[0] - x, landing[1] - y] if landing else None,
                             frameSequence=headers.get('X-iMouse-Frame-Sequence'))
    screen.command('/mouse/move', 'measure-park', x=480, y=300)
    return record['measure']


def contact_sheet(folder, record):
    """Small side-by-side of the page and app frames, for the lane's own review (output only)."""
    from PIL import Image
    fresh = [o for o in record['observations'] if o.get('state') == 'fresh']
    names = [o['frame'] for o in fresh if o['role'].startswith(('page-', 'back-to-page'))][-3:]
    for app in APPS:   # Each app's last look (also when the survey stopped there).
        looks = [o['frame'] for o in fresh if re.fullmatch(app.casefold() + r'-(\d|after-prompt)', o['role'])]
        names += looks[-1:]
    if not names: return None
    tiles = [Image.open(folder / n).convert('RGB').resize((200, 432)) for n in names]
    sheet = Image.new('RGB', (200 * len(tiles), 432), 'white')
    for i, tile in enumerate(tiles): sheet.paste(tile, (200 * i, 0))
    path = folder / 'sheet.png'; sheet.save(path)
    return path


class _Measured(Exception):
    pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument('board'); p.add_argument('--run'); p.add_argument('--apps', default=','.join(APPS))
    p.add_argument('--instagram-profile', action='store_true', help='only bring Instagram to its own profile (Reel window start)')
    p.add_argument('--tiktok-profile', action='store_true', help='only bring TikTok to its own Profile tab (to read its handle)')
    p.add_argument('--measure', help='x,y: move the pointer there (never click) and record where it lands')
    a = p.parse_args()
    board = a.board.upper()
    if board not in FLEET: raise SystemExit(f'{board} is not a Fleet lane phone; refused.')
    apps = [x for x in a.apps.split(',') if x]
    if any(x not in APPS for x in apps): raise SystemExit(f'Apps must be among {APPS}.')
    from farm_phone_identity import PhoneIdentity
    from farm_start_screen import StartScreen
    from identify_phone import request
    status = request(API, 'GET', '/kernel/status', timeout=8)
    devices = [d for d in request(API, 'GET', '/device/get', timeout=8)['list'] if str(d.get('pid', '')).upper() == board]
    if len(devices) != 1: raise SystemExit(f'Expected one {board} device, found {len(devices)}.')
    receiver = [r for r in status['receivers'] if r['deviceid'] == devices[0]['deviceid']]
    if len(receiver) != 1 or not receiver[0]['live']: raise SystemExit(f'{board} is not mirroring; not surveyed.')
    name = receiver[0]['name']
    slot = int(name.rsplit('-', 1)[1]) if re.fullmatch(r'iMouse2-\d{1,2}', name) else 0
    phone = PhoneIdentity(board=board, device_id=devices[0]['deviceid'], receiver=name, slot=slot)
    label, model = FLEET[board]
    folder = ROOT / (a.run or f'survey-{label}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}')
    screen = StartScreen(folder, phone=phone)
    renewing(screen)
    survey = FleetSurvey(screen, label, model)
    screen.tokens = screen.kernel.acquire([board], LEASE_MS)
    try:
        if a.measure:   # Moves only: no prompt is answered, nothing is tapped.
            pointer_landing(screen, tuple(int(v) for v in a.measure.split(',')), survey.record)
            survey.record['state'] = 'done'
            raise _Measured()
        try: raw, text = survey.look('first')
        except InspectionStopped as stop:
            if not str(stop).startswith('No fresh frame'): raise   # A prompt stop is final (A11, 5 Nov 17:31).
            # An asleep phone sends no new frame for a pointer move. Wake it with one Home only when the last
            # frame is dark (never over Control Center, which a dark frame cannot show); else it is a stall.
            last, _ = screen.kernel.shot(board)
            if not dark(last): raise InspectionStopped('No fresh frame and the screen is not dark: mirror stall; no input.')
            screen.command('/key/sendkey', 'wake-home', fn_key='Home'); survey.record['homes'] += 1
            screen.pause(2)
            raw, text = survey.look('after-wake')
        if survey.model is None: survey.model = survey.record['model'] = model_of(raw)
        if a.instagram_profile:
            if survey.model != 'xr': raise InspectionStopped('Reel windows run on XR phones only.')
            survey.to_instagram_profile()
        elif a.tiktok_profile:
            if survey.model != 'xr': raise InspectionStopped('TikTok windows run on XR phones only.')
            survey.to_tiktok_profile()
        else: survey.run(apps)
    except _Measured: pass
    except Exception as error:   # Every stop is recorded; nothing further is sent.
        survey.record.update(state='stopped', error=type(error).__name__ + ': ' + str(error))
    finally:
        try: screen.kernel.release(screen.tokens); survey.record['leaseReleased'] = True
        except Exception as error: survey.record['leaseReleased'] = f'{type(error).__name__}: {error}'
        screen.save()
    sheet = contact_sheet(folder, survey.record)
    r = survey.record
    print(json.dumps(dict(board=board, phone=label, model=r.get('model'), state=r['state'], error=r.get('error'),
                          pages=r.get('pages'), apps={k: {x: v.get(x) for x in ('route', 'state')} for k, v in r['apps'].items()},
                          prompts=r['prompts'], homes=r['homes'], leaseReleased=r.get('leaseReleased'), measure=r.get('measure'),
                          folder=str(folder.relative_to(HERE.parent)), sheet=bool(sheet))))
    if r['state'] != 'done': raise SystemExit(1)


if __name__ == '__main__':
    main()
