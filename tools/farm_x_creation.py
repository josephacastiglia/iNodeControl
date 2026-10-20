"""Bounded C24C X video draft creation, then an independent verifier.

Draft only. The account is whichever X account is signed in first: the run reads
its handle from the side menu before any app input, and every later observation
(and the verifier) must show the same handle. The video reaches Photos by the
shared Safari/Files route. In X the text is pasted first, the one matching video
is added through the system photo picker, and the draft is kept with Cancel ->
Save to drafts once. Post, Discard and the media remove control are never
targets. Unknown outcomes stop and nothing is repeated. The verifier reopens the
draft whose exact text and thumbnail match, plays it and keeps it.
"""
import numpy as np

from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import require
from farm_draft_transport import allowed_tap
from farm_draft_workflow import Workflow
from farm_live_verification import idle
from farm_screen_layout import pixels
from farm_transitions import wait_for_transition
import farm_reel_layout as reel
import farm_tiktok_layout as tt
import farm_x_layout as xl
from farm_reel_creation import ReelCreationWorkflow, ReelVerification, PRE_SETTLE as REEL_PRE_SETTLE
from imouse_social_automation import LIVE_TEST_DEVICE_ID

PENDING = 'pending-x-account'   # Expected-account placeholder until the side menu is read.
LOADING_ATTEMPTS = 6           # Read-only picker observations while it shows Loading...
SHARED = ('reel_safari_entry', 'reel_page', 'reel_caption_copied', 'link_menu', 'page_menu', 'downloads', 'quicklook',
          'quicklook_controls', 'share_sheet')
PRE_SETTLE = {**{role: REEL_PRE_SETTLE[role] for role in SHARED},
              'x_feed': .8, 'x_menu': .6, 'x_composer_empty': .6, 'x_paste_menu': .4, 'x_composer_text': .6,
              'x_picker': 1.0, 'x_picker_selected': .4, 'x_composer_media': 1.0, 'x_save_sheet': .6, 'x_drafts': .8,
              'x_reopened': 1.0, 'x_playing': .8}
# A callout and the playing card are captured once; every other screen needs two agreeing fresh frames.
SETTLED = set(PRE_SETTLE) - {'x_paste_menu', 'x_playing'}
MOVING = {
    'x_feed': ((0, 160, 500, 895), (0, 895, 415, 980)),          # Timeline content plays; compose button protected.
    'x_menu': ((425, 100, 500, 1000),),                            # The timeline edge beside the menu.
    'x_composer_empty': ((240, 110, 445, 160), (20, 975, 350, 1015), (320, 945, 490, 980)),   # First-use tips.
    'x_composer_text': ((60, 115, 490, 165),),                     # Caret.
    'x_composer_media': ((60, 115, 490, 165), (196, 595, 470, 640)),
    'x_reopened': ((60, 115, 490, 165),),
}
FORBIDDEN = {
    'x_composer_empty': (xl.POST,), 'x_composer_text': (xl.POST,), 'x_composer_media': (xl.POST, xl.REMOVE),
    'x_reopened': (xl.POST, xl.REMOVE), 'x_playing': (xl.POST, xl.REMOVE), 'x_save_sheet': ((180, 515, 320, 565),),   # Discard
}
PROHIBITED = ('repost', 'quote', 'reply', 'like', 'bookmark', 'message', 'grok', 'premium', 'subscribe')
COMMITTING = ('download-linked-file', 'save-video-to-photos', 'select-package-video', 'add-package-video',
              'paste-exact-caption', 'save-x-draft-once')


def compare(role):
    if not role.startswith('x_'): return reel.reel_compare(role)
    def check(first, first_text, second, second_text):
        a, b = pixels(first, exact=True).astype(float), pixels(second, exact=True).astype(float)
        difference = np.abs(a-b)/255
        mask = np.ones((1080, 500), dtype=bool); mask[:65] = False
        for left, top, right, bottom in MOVING.get(role, ()) + (reel.POINTER,): mask[top:bottom, left:right] = False
        mean = float(difference[mask].mean()); changed = float((difference.max(axis=2) > 35/255)[mask].mean())
        if mean <= .002 and changed <= .005:
            return dict(state='ready', mean=mean, changed=changed, automaticInputAllowed=False)
        return dict(state='wait', mean=mean, changed=changed, automaticInputAllowed=False,
                    reason='Protected screen content is still changing; capture again without input.')
    return check


def guard(text, x, y, role):
    for left, top, right, bottom in FORBIDDEN.get(role, ()):
        require(not (left <= x <= right and top <= y <= bottom), 'Target overlaps an X publishing or removal control.')
    for line in text.get('lines', []):
        words = line.get('words', [])
        if not words: continue
        left = min(w['x'] for w in words); right = max(w['x']+w['width'] for w in words)
        top = min(w['y'] for w in words); bottom = max(w['y']+w['height'] for w in words)
        if left-45 <= x <= right+45 and top-25 <= y <= bottom+25:
            require(not any(word in line['text'].casefold().split() for word in PROHIBITED),
                    'Target overlaps a prohibited or ambiguous X label.')


def chrome_only(text, role):
    """Timeline posts are content, never controls: the guards read only the app chrome there."""
    if role not in ('x_feed', 'x_menu'): return text
    return {**text, 'lines': [r for r in text.get('lines', []) if not r.get('words')
                              or not (160 <= min(w['y'] for w in r['words']) < 980 and min(w['x'] for w in r['words']) > 60
                                      if role == 'x_feed' else min(w['x'] for w in r['words']) >= 425)]}


class XCreationWorkflow(ReelCreationWorkflow):
    PLATFORM = 'x'
    APP_NAME = 'X'
    MEDIA_ROLES = ()                       # The system photo picker needs no Photos permission.
    PASTE_ROLES = ('x_composer_text',)

    def __init__(self, folder, kernel, store, video, caption, templates, expected_hash, expected_uid, *,
                 transfer_url, download, video_bytes, account=None, **kwargs):
        require(xl.caption_supported(caption), 'X creation supports one visible ASCII text line up to 32 characters.')
        super().__init__(folder, kernel, store, video, caption, templates, expected_hash, expected_uid,
                         transfer_url=transfer_url, download=download, video_bytes=video_bytes, account=account or PENDING, **kwargs)
        self.title, self.tile = 'X draft', None
        self.record.update(mode='create_x_draft', format='x_video', captionMethod='verified_safari_copy_and_x_paste',
                           account=None if self.account == PENDING else self.account, accountBinding=None)
        for key in ('draftsCount', 'pickerCell'): self.record.pop(key, None)

    # -- account binding --------------------------------------------------------------
    def validate(self, value, frame, require_recent=True):
        if value.get('result', {}).get('accountStatus') == 'different_text':
            # Before binding, the menu necessarily shows a handle other than the placeholder.
            require(self.account == PENDING, 'A different X account (or more than one handle) is shown; no further input is sent.')
            value = {**value, 'result': {**value['result'], 'accountStatus': 'binding'}}
        super().validate(value, frame, require_recent)

    def account_menu(self, label, *, bind):
        self.tap('open-account-menu' + label, 'x_feed', lambda v, f: xl.x_feed(f, v['text'])['menuTarget'])
        menu, value, _ = self.screen('x_menu')
        if bind:
            require(self.account == PENDING, 'The X account is already bound for this run.')
            self.account = menu['handle']
            self.record.update(account=self.account, accountBinding=dict(observationId=value['id'], method='side_menu_handle'))
            self.save()
        else:
            require(menu['handle'] == self.account, 'A different X account is signed in; no further input is sent.')
        self.tap('close-account-menu' + label, 'x_menu', lambda v, f: xl.x_menu(f, v['text'])['closeTarget'])
        self.screen('x_feed')

    # -- recognition -------------------------------------------------------------
    def transfer_page(self, text):
        return tt.transfer_page(text, self.download, title='X draft')

    def verify_screen(self, role, value, frame, index=None, require_next=False):
        text = value['text']
        decision = self.check_prompt(role, value)
        if decision is not None: return decision
        if role == 'reel_safari_entry':
            try: return self.verify_screen('safari', value, frame)
            except InspectionStopped: return tt.leftover_preview(frame, text)
        if role == 'reel_page': return self.transfer_page(text)
        if role == 'reel_caption_copied': return {**self.transfer_page(text), **tt.caption_copied(text, app='X')}
        if role == 'x_feed': return xl.x_feed(frame, text)
        if role == 'x_menu':
            menu = xl.x_menu(frame, text)
            if self.account != PENDING: require(menu['handle'] == self.account, 'A different X account is signed in.')
            return menu
        if role == 'x_composer_empty': return xl.x_composer_empty(frame, text)
        if role == 'x_paste_menu': return xl.x_paste_menu(frame, text)
        if role == 'x_composer_text': return xl.x_composer_text(frame, text)
        if role == 'x_picker': return xl.x_picker(frame, text, self.video)
        if role == 'x_picker_selected': return xl.x_picker_selected(frame, text, self.video, self.tile)
        if role == 'x_composer_media': return xl.x_composer_media(frame, text, self.video)
        if role == 'x_save_sheet': return xl.x_save_sheet(text)
        if role == 'x_drafts': return xl.x_drafts(frame, text, self.video, self.caption)
        if role in ('x_reopened', 'x_playing'):
            result = xl.x_composer_media(frame, text, self.video, reopened=True)
            if role == 'x_playing': require(not result['blank'], 'The reopened X video did not start playing.')
            return result
        return super().verify_screen(role, value, frame, index, require_next)

    def confirmation_compare(self, role):
        """Settled screens may be reconfirmed by a newer frame under their own settling rule."""
        return compare(role) if role in SETTLED else None

    def observe_screen(self, role, index=None, require_next=False):
        if role != 'x_picker': return self.observe_settled(role, index, require_next)
        for attempt in range(LOADING_ATTEMPTS):
            try: return self.observe_settled(role, index, require_next)
            except xl.Loading:
                if attempt == LOADING_ATTEMPTS-1: raise
                self.pause(1)   # Read-only; the picker opened from one answered tap.

    def observe_settled(self, role, index=None, require_next=False):
        if role not in PRE_SETTLE: return Workflow.observe(self, role, index, require_next)
        self.pause(PRE_SETTLE[role])
        if role not in SETTLED: return self.capture(role, index)
        def journal(event):
            self.record['transitionChecks'].append(event); self.save()
        value, frame, _ = wait_for_transition(role, lambda: self.capture(role, index), self.check, self.store.current_evidence,
            journal=journal, monotonic=self.monotonic, pause=self.pause,
            ready=lambda frame, text: None, compare=compare(role), platform=self.PLATFORM,
            require_recent=self.confirmation_compare(role) is None)
        return value, frame

    def check_target(self, role, point):
        def target(value, frame):
            x, y = point(value, frame) if callable(point) else point
            text = chrome_only(value['text'], role)
            allowed_tap(text, x, y, 'x:' + role, frame=frame)
            guard(text, x, y, role)
            return x, y
        return target

    def tap(self, label, role, point, *, hold=False):
        self.step(label, role, point=self.check_target(role, point), hold=hold, settle=not hold and role.startswith('x_'))

    # -- workflow ----------------------------------------------------------------
    def admit(self):
        self.identity = self.runtime()
        require(idle(self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)), 'C24C is not free; no takeover is allowed.')
        raw, _ = self.kernel.shot('C24C')
        try: xl.x_feed(raw, self.store.ocr.read(raw))
        except InspectionStopped as error: raise InspectionStopped('Start on the X home timeline. No input was sent.') from error
        self.record['cleanup'] = 'unconfirmed'; self.save(); self.owned.acquire()
        self.command('/mouse/reset', purpose='initial_pointer_reset')

    def run(self):
        try:
            self.admit()
            self.phase('bind-account')
            self.account_menu('', bind=True)
            self.import_video(start_role='x_feed', label='home-from-x-feed')
            self.phase('open-x')
            self.open_app('X', 'return')
            self.screen('x_feed')
            self.account_menu('-again', bind=False)
            self.phase('compose-text')
            self.tap('open-composer', 'x_feed', lambda v, f: xl.x_feed(f, v['text'])['composeTarget'])
            self.tap('focus-empty-text', 'x_composer_empty', lambda v, f: xl.x_composer_empty(f, v['text'])['textTarget'])
            self.tap('open-paste-menu', 'x_composer_empty', lambda v, f: xl.x_composer_empty(f, v['text'])['pressTarget'], hold=True)
            self.tap('paste-exact-caption', 'x_paste_menu', lambda v, f: xl.x_paste_menu(f, v['text'])['target'])
            self.pause(2)  # Let the OS paste banner leave the header; nothing is repeated.
            self.phase('attach-video')
            self.tap('open-photo-picker', 'x_composer_text', lambda v, f: xl.x_composer_text(f, v['text'])['galleryTarget'])
            def choose(value, frame):
                found = xl.x_picker(frame, value['text'], self.video)
                self.tile = found['tile']; self.record['pickerTile'] = found['tile']
                return found['target']
            self.tap('select-package-video', 'x_picker', choose)
            self.tap('add-package-video', 'x_picker_selected', lambda v, f: xl.x_picker_selected(f, v['text'], self.video, self.tile)['target'])
            self.phase('save-draft')
            self.tap('cancel-to-save-sheet', 'x_composer_media', lambda v, f: xl.x_composer_media(f, v['text'], self.video)['cancelTarget'])
            self.tap('save-x-draft-once', 'x_save_sheet', lambda v, f: xl.x_save_sheet(v['text'])['target'])
            self.screen('x_feed')
            self.record.update(state='created_unverified', meaning='Package video saved to Photos, text pasted, the matching video '
                               'added and Save to drafts answered on the bound account; an independent reopen check is required.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record


class XVerification(XCreationWorkflow):
    """Separate owned run: the same account, the exact-text draft with the package video, played and kept."""
    history = ReelVerification.history

    def __init__(self, folder, kernel, store, video, caption, templates, expected_hash, expected_uid, *, account, **kwargs):
        require(account and account != PENDING, 'The verifier needs the account bound by creation.')
        super().__init__(folder, kernel, store, video, caption, templates, expected_hash, expected_uid,
                         transfer_url='verification-only', download='verification-only', video_bytes=0, account=account, **kwargs)
        self.record.update(mode='verify_x_draft', inspectionOnly=False, appRestartVerified=False, finalScreen='unknown')
        for key in ('transferUrl', 'downloadName'): self.record.pop(key, None)

    def playback(self):
        """Two fresh frames of the reopened card that match the package video at different times."""
        first, _, _ = self.screen('x_playing')
        self.pause(.8)
        second, _, _ = self.screen('x_playing')
        indices = [first['media']['index'], second['media']['index']]
        require(indices[0] != indices[1], 'The reopened X draft did not visibly play the package video.')
        self.record['playback'] = dict(sampledFrameIndices=indices, byteIdentityVerified=False)

    def run(self):
        try:
            self.admit()
            self.phase('verify-saved-x-draft')
            self.account_menu('', bind=False)
            self.tap('verify-open-composer', 'x_feed', lambda v, f: xl.x_feed(f, v['text'])['composeTarget'])
            def drafts(value, frame):
                found = xl.x_composer_empty(frame, value['text'])
                require(found['draftsTarget'], 'The X composer shows no Drafts link.')
                return found['draftsTarget']
            self.tap('verify-open-drafts', 'x_composer_empty', drafts)
            def choose(value, frame):
                found = xl.x_drafts(frame, value['text'], self.video, self.caption)
                self.record['draftRow'] = dict(rows=found['rows'], y=found['row']['y'], text=found['row']['text'])
                return found['target']
            self.tap('verify-open-saved-draft', 'x_drafts', choose)
            reopened, _, _ = self.screen('x_reopened')
            if reopened['blank']:
                self.tap('verify-play-video', 'x_reopened', lambda v, f: xl.x_composer_media(f, v['text'], self.video, reopened=True)['playTarget'])
            self.playback()
            self.tap('verify-cancel-to-save-sheet', 'x_playing',
                     lambda v, f: xl.x_composer_media(f, v['text'], self.video, reopened=True)['cancelTarget'])
            # Keep the reopened draft with the same single Save to drafts; an uncertain answer is never repeated.
            self.tap('verify-keep-draft-once', 'x_save_sheet', lambda v, f: xl.x_save_sheet(v['text'])['target'])
            self.screen('x_feed')
            self.history()
            self.record.update(state='validation_passed', savedDraftVerified=True, finalScreen='x_feed',
                meaning='On the same signed-in account, the unique X draft with the exact text and the package video reopened, '
                        'played and was kept. No Post, publishing or messaging. Not app-restart or server persistence proof.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record
