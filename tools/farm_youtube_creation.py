"""Bounded YouTube Short draft creation on the configured phone, then an independent verifier.

Draft only. The phone (board, device ID, receiver) comes from the candidate
configuration, never a default; the route targets the rack phone in box slot 16.
The channel is whichever one YouTube shows on Add details: the run
reads its handle there before the title is entered, and every later details
screen (and the verifier) must show the same handle. The video reaches Photos
by the shared Safari/Files route. In YouTube: + -> Add -> the one matching
gallery video -> Next -> the untrimmed trim review -> Done -> Next -> the exact
one-line title by Paste, checked without the caret -> Save draft once. Upload
Short, Post, Live, recording and a draft's menu are never targets. Unknown
outcomes stop and nothing is repeated. The verifier reopens the draft whose
exact title and thumbnail match, sees it play, keeps it with Save draft and
finds it once again in Drafts.
"""
import re

import numpy as np

from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import require
from farm_draft_transport import allowed_tap
from farm_draft_workflow import Workflow
from farm_live_verification import idle
from farm_screen_layout import pixels
from farm_transitions import wait_for_transition, HOME_INDICATOR
import farm_reel_layout as reel
import farm_tiktok_layout as tt
import farm_youtube_layout as yl
from farm_reel_creation import ReelCreationWorkflow, ReelVerification, PRE_SETTLE as REEL_PRE_SETTLE
from imouse_social_automation import DEFAULT_SAFE_TEST_DEVICE, LIVE_TEST_DEVICE_ID

PENDING = 'pending-youtube-channel'   # Expected-account placeholder until Add details is read.
SHARED = ('reel_safari_entry', 'reel_page', 'reel_caption_copied', 'link_menu', 'page_menu', 'downloads', 'quicklook',
          'quicklook_controls', 'share_sheet')
PRE_SETTLE = {**{role: REEL_PRE_SETTLE[role] for role in SHARED},
              'yt_home': .8, 'yt_camera': .8, 'yt_picker': .8, 'yt_picker_selected': .6, 'yt_trim': 1.0, 'yt_editor': 1.0,
              'yt_details_blank': .6, 'yt_details_focused': .4, 'yt_paste_menu': .4, 'yt_details': .6, 'yt_drafts': .8,
              'yt_reopened_editor': 1.0, 'yt_playing': .8, 'yt_reopened_details': .6}
# A callout and the playing editor are captured once; every other screen needs two agreeing fresh frames.
SETTLED = set(PRE_SETTLE) - {'yt_paste_menu', 'yt_playing'}
CARET_ROLES = ('yt_details_focused', 'yt_details', 'yt_reopened_details')
CARET_ATTEMPTS = 4          # Settled observations until one shows the title without the caret.
TITLE = (125, 130, 495, 190)
# iOS dims the home indicator over the dark full-screen views (148/after against 149/before).
INDICATOR = HOME_INDICATOR
MOVING = {
    'yt_home': ((0, 110, 500, 980),),                                   # Feed plays; header and bar protected.
    'yt_camera': ((0, 65, 500, 975), INDICATOR),                        # Live camera preview, fading tool labels.
    'yt_picker': (INDICATOR,), 'yt_picker_selected': (INDICATOR,),
    'yt_trim': ((50, 154, 450, 868), (15, 70, 485, 92), (15, 875, 485, 965), INDICATOR),   # Video, its progress bar, the playhead.
    'yt_editor': ((0, 71, 500, 958), INDICATOR), 'yt_reopened_editor': ((0, 71, 500, 958), INDICATOR),
    'yt_details_blank': (TITLE,), 'yt_details_focused': (TITLE,), 'yt_details': (TITLE,), 'yt_reopened_details': (TITLE,),
    'yt_drafts': ((160, 180, 455, 1040),),                              # Relative save times.
}
UPLOAD, FEEDBACK = (250, 960, 490, 1035), (285, 315, 490, 375)
FORBIDDEN = {
    'yt_camera': ((195, 790, 305, 900), (120, 965, 440, 1020), (425, 95, 490, 155)),   # record, Video/Short/Live/Post, AI
    'yt_picker': ((11, 150, 489, 226),),                                                 # Create video (AI)
    'yt_picker_selected': ((11, 150, 489, 226), (20, 965, 250, 1028)),                   # Create video, Edit with AI
    'yt_editor': ((170, 78, 330, 125), (20, 980, 245, 1030)), 'yt_reopened_editor': ((170, 78, 330, 125), (20, 980, 245, 1030)),
    'yt_playing': ((170, 78, 330, 125), (20, 980, 245, 1030)),
    'yt_details_blank': (UPLOAD, FEEDBACK), 'yt_details_focused': (UPLOAD, FEEDBACK), 'yt_details': (UPLOAD, FEEDBACK),
    'yt_reopened_details': (UPLOAD, FEEDBACK),
    'yt_drafts': ((445, 180, 500, 1040),),                                               # a draft's menu
}
PROHIBITED = ('upload', 'live', 'subscribe', 'install', 'remix', 'premium', 'record', 'feedback')
COMMITTING = ('download-linked-file', 'save-video-to-photos', 'select-package-video', 'open-youtube-trim',
              'keep-whole-video', 'open-youtube-details', 'paste-exact-caption', 'save-youtube-draft-once')


PHONE_KEYS = ('board', 'deviceId', 'receiver')


def phone_from_config(config):
    """The phone a YouTube run drives: the configuration's 'phone' block, or None when it names none."""
    phone = (config or {}).get('phone')
    if phone is None: return None
    if (not isinstance(phone, dict) or set(phone) - set(PHONE_KEYS) - {'slot'} or any(not isinstance(phone.get(k), str) for k in PHONE_KEYS)
            or not re.fullmatch(r'[A-Z0-9]{4}', phone['board']) or not re.fullmatch(r'[0-9A-F]{2}(:[0-9A-F]{2}){5}', phone['deviceId'])
            or not re.fullmatch(r'iMouse2-[A-Za-z0-9]{1,16}', phone['receiver'])
            or ('slot' in phone and (type(phone['slot']) is not int or not 1 <= phone['slot'] <= 99))):
        raise ValueError('The YouTube phone needs its board, device ID and receiver name (and optionally its box slot).')
    return dict(phone)


def transport_drives(phone):
    """Whether this backend's shared phone transport can drive the phone.

    The shared transport, observation store and lease still drive one phone; the
    multi-phone farm generalizes them and replaces this check.
    """
    return bool(phone) and phone['board'] == DEFAULT_SAFE_TEST_DEVICE and phone['deviceId'] == LIVE_TEST_DEVICE_ID


def compare(role):
    if not role.startswith('yt_'): return reel.reel_compare(role)
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
        require(not (left <= x <= right and top <= y <= bottom), 'Target overlaps a YouTube publishing, recording or menu control.')
    for line in text.get('lines', []):
        words = line.get('words', [])
        if not words: continue
        left = min(w['x'] for w in words); right = max(w['x']+w['width'] for w in words)
        top = min(w['y'] for w in words); bottom = max(w['y']+w['height'] for w in words)
        if left-45 <= x <= right+45 and top-25 <= y <= bottom+25:
            require(not any(word in line['text'].casefold().split() for word in PROHIBITED),
                    'Target overlaps a prohibited or ambiguous YouTube label.')


class YouTubeCreationWorkflow(ReelCreationWorkflow):
    PLATFORM = 'youtube'
    APP_NAME = 'YouTube'
    MEDIA_ROLES = ('yt_picker',)          # YouTube's own gallery needs Photos access.
    PASTE_ROLES = ('yt_details',)

    def __init__(self, folder, kernel, store, video, caption, templates, expected_hash, expected_uid, *,
                 transfer_url, download, video_bytes, phone, account=None, **kwargs):
        require(yl.caption_supported(caption), 'YouTube creation supports one visible ASCII title line up to 24 characters.')
        require(transport_drives(phone), 'This backend cannot drive the configured YouTube phone; no input is sent.')
        self.phone = dict(phone)
        super().__init__(folder, kernel, store, video, caption, templates, expected_hash, expected_uid,
                         transfer_url=transfer_url, download=download, video_bytes=video_bytes, account=account or PENDING, **kwargs)
        self.title, self.tile = 'YouTube draft', None
        self.record.update(mode='create_youtube_draft', format='yt_short', captionMethod='verified_safari_copy_and_youtube_paste',
                           titleField='youtube_short_title', account=None if self.account == PENDING else self.account,
                           accountBinding=None, phone={k: v for k, v in self.phone.items() if k != 'deviceId'})
        for key in ('draftsCount', 'pickerCell'): self.record.pop(key, None)

    # -- channel binding -------------------------------------------------------------
    def validate(self, value, frame, require_recent=True):
        if value.get('result', {}).get('accountStatus') == 'different_text':
            # Before binding, Add details necessarily shows a handle other than the placeholder.
            require(self.account == PENDING, 'A different YouTube channel (or more than one handle) is shown; no further input is sent.')
            value = {**value, 'result': {**value['result'], 'accountStatus': 'binding'}}
        super().validate(value, frame, require_recent)

    def bind_channel(self, details, value):
        require(self.account == PENDING, 'The YouTube channel is already bound for this run.')
        self.account = details['channel']
        self.record.update(account=self.account, accountBinding=dict(observationId=value['id'], method='add_details_channel_handle'))
        self.save()

    # -- recognition -------------------------------------------------------------
    def transfer_page(self, text):
        return tt.transfer_page(text, self.download, title='YouTube draft')

    def details(self, role, value, frame):
        state = {'yt_details_blank': 'blank', 'yt_details_focused': 'focused'}.get(role, 'titled')
        try:
            result = yl.yt_details(frame, value['text'], self.video, None if state != 'titled' else self.caption, state=state)
        except yl.CaretVisible as error:
            # Recorded and never a decision basis; observe() captures again without input.
            return dict(caretVisible=True, reason=str(error))
        if self.account != PENDING:
            require(result['channel'] == self.account, 'A different YouTube channel is shown on Add details; no further input is sent.')
        return result

    def verify_screen(self, role, value, frame, index=None, require_next=False):
        text = value['text']
        decision = self.check_prompt(role, value)
        if decision is not None: return decision
        if role == 'reel_safari_entry':
            try: return self.verify_screen('safari', value, frame)
            except InspectionStopped: return tt.leftover_preview(frame, text)
        if role == 'reel_page': return self.transfer_page(text)
        if role == 'reel_caption_copied': return {**self.transfer_page(text), **tt.caption_copied(text, app='YouTube')}
        if role == 'yt_home': return yl.yt_home(frame, text)
        if role == 'yt_camera': return yl.yt_camera(frame, text)
        if role == 'yt_picker': return yl.yt_picker(frame, text, self.video)
        if role == 'yt_picker_selected': return yl.yt_picker_selected(frame, text, self.video, self.tile)
        if role == 'yt_trim': return yl.yt_trim(frame, text, self.video)
        if role in ('yt_editor', 'yt_reopened_editor', 'yt_playing'): return yl.yt_editor(frame, text, self.video)
        if role in ('yt_details_blank', 'yt_details_focused', 'yt_details', 'yt_reopened_details'): return self.details(role, value, frame)
        if role == 'yt_paste_menu': return yl.yt_paste_menu(frame, text)
        if role == 'yt_drafts': return yl.yt_drafts(frame, text, self.video, self.caption)
        return super().verify_screen(role, value, frame, index, require_next)

    def confirmation_compare(self, role):
        """Settled screens may be reconfirmed by a newer frame under their own settling rule."""
        return compare(role) if role in SETTLED else None

    def observe_screen(self, role, index=None, require_next=False):
        if role not in PRE_SETTLE: return Workflow.observe(self, role, index, require_next)
        def journal(event):
            self.record['transitionChecks'].append(event); self.save()
        for attempt in range(CARET_ATTEMPTS if role in CARET_ROLES else 1):
            self.pause(PRE_SETTLE[role] if attempt == 0 else .35)
            if role in SETTLED:
                value, frame, _ = wait_for_transition(role, lambda: self.capture(role, index), self.check, self.store.current_evidence,
                    journal=journal, monotonic=self.monotonic, pause=self.pause,
                    ready=lambda frame, text: None, compare=compare(role), platform=self.PLATFORM,
                    require_recent=self.confirmation_compare(role) is None)
            else:
                value, frame = self.capture(role, index)
            entry = next(e for e in reversed(self.record['observations']) if e.get('observationId') == value['id'])
            if not entry.get('screenCheck', {}).get('caretVisible'): return value, frame
        raise InspectionStopped('The YouTube title stayed covered by the text caret; no input was sent.')

    def check_target(self, role, point):
        def target(value, frame):
            x, y = point(value, frame) if callable(point) else point
            text = yl.chrome_only(value['text'], role)
            allowed_tap(text, x, y, 'youtube:' + role, frame=frame)
            guard(text, x, y, role)
            return x, y
        return target

    def tap(self, label, role, point, *, hold=False):
        # The 17 Oct YouTube MP4 route used settled taps throughout; Safari keeps plain taps.
        self.step(label, role, point=self.check_target(role, point), hold=hold, settle=not hold and role.startswith('yt_'))

    # -- workflow ----------------------------------------------------------------
    def admit(self):
        self.identity = self.runtime()
        phone = self.phone
        mirrors = [r for r in self.kernel.kernel_status().get('receivers', []) if r.get('deviceid') == phone['deviceId']]
        require(len(mirrors) == 1 and mirrors[0].get('name') == phone['receiver'],
                'The configured receiver ' + phone['receiver'] + ' is not mirroring the configured phone. No input was sent.')
        require(idle(self.kernel.input_status().get(phone['deviceId'])), phone['board'] + ' is not free; no takeover is allowed.')
        raw, _ = self.kernel.shot(phone['board'])
        text = self.store.ocr.read(raw)
        # YouTube asks for local-network access on launch (17 Oct steps 132-135); name it before anything else.
        decision = self.prompt_decision(dict(text=text, id=None), 'admission')
        if decision:
            raise InspectionStopped((decision.get('request') or 'A permission prompt covers YouTube; start on the home feed.')
                                    + ' No input was sent.')
        try: yl.yt_home(raw, text)
        except InspectionStopped as error: raise InspectionStopped('Start on the YouTube home feed. No input was sent.') from error
        self.record['cleanup'] = 'unconfirmed'; self.save(); self.owned.acquire()
        self.command('/mouse/reset', purpose='initial_pointer_reset')

    def run(self):
        try:
            self.admit()
            self.import_video(start_role='yt_home', label='home-from-youtube')
            self.phase('open-youtube')
            self.open_app('YouTube', 'return')
            self.screen('yt_home')
            self.phase('select-youtube-media')
            self.tap('open-youtube-create', 'yt_home', lambda v, f: yl.yt_home(f, v['text'])['createTarget'])
            self.tap('open-youtube-gallery', 'yt_camera', lambda v, f: yl.yt_camera(f, v['text'])['addTarget'])
            def choose(value, frame):
                found = yl.yt_picker(frame, value['text'], self.video)
                self.tile = found['tile']; self.record['pickerTile'] = found['tile']
                return found['target']
            self.tap('select-package-video', 'yt_picker', choose)
            self.tap('open-youtube-trim', 'yt_picker_selected', lambda v, f: yl.yt_picker_selected(f, v['text'], self.video, self.tile)['target'])
            # Done is pressed only on a frame whose selection covers the whole package video.
            self.tap('keep-whole-video', 'yt_trim', lambda v, f: yl.yt_trim(f, v['text'], self.video)['target'])
            self.tap('open-youtube-details', 'yt_editor', lambda v, f: yl.yt_editor(f, v['text'], self.video)['target'])
            self.phase('title-and-save')
            details, value, _ = self.screen('yt_details_blank')
            self.bind_channel(details, value)
            self.tap('focus-empty-title', 'yt_details_blank', lambda v, f: self.details('yt_details_blank', v, f)['titleTarget'])
            self.tap('open-paste-menu', 'yt_details_focused', lambda v, f: self.details('yt_details_focused', v, f)['pressTarget'], hold=True)
            self.tap('paste-exact-caption', 'yt_paste_menu', lambda v, f: yl.yt_paste_menu(f, v['text'])['target'])
            self.pause(2)  # Let the OS paste banner leave the header; nothing is repeated.
            # The single Save draft is decided on a caret-free frame with the exact title and the bound channel.
            self.tap('save-youtube-draft-once', 'yt_details', lambda v, f: self.details('yt_details', v, f)['saveTarget'])
            home, _, _ = self.screen('yt_home')
            self.record.update(draftSavedToast=home['toastSeen'], state='created_unverified',
                               meaning='Package video saved to Photos, selected untrimmed, the exact title pasted and Save draft '
                                       'answered on the bound channel; an independent reopen check is required.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record


class YouTubeVerification(YouTubeCreationWorkflow):
    """Separate owned run: the exact-title draft with the package video, on the same channel, played, kept and found again."""
    history = ReelVerification.history

    def __init__(self, folder, kernel, store, video, caption, templates, expected_hash, expected_uid, *, account, **kwargs):
        require(account and account != PENDING, 'The verifier needs the channel bound by creation.')
        super().__init__(folder, kernel, store, video, caption, templates, expected_hash, expected_uid,
                         transfer_url='verification-only', download='verification-only', video_bytes=0, account=account, **kwargs)
        self.record.update(mode='verify_youtube_draft', inspectionOnly=False, appRestartVerified=False, finalScreen='unknown')
        for key in ('transferUrl', 'downloadName'): self.record.pop(key, None)

    def open_drafts(self, label):
        self.tap(label + '-open-create', 'yt_home', lambda v, f: yl.yt_home(f, v['text'])['createTarget'])
        def drafts(value, frame):
            found = yl.yt_camera(frame, value['text'])
            require(found['draftsTarget'], 'The YouTube camera shows no Drafts button.')
            return found['draftsTarget']
        self.tap(label + '-open-drafts', 'yt_camera', drafts)

    def playback(self):
        """Two fresh frames of the reopened editor that match the package video at different times."""
        first, _, _ = self.screen('yt_playing')
        self.pause(.8)
        second, _, _ = self.screen('yt_playing')
        indices = [first['media']['index'], second['media']['index']]
        require(indices[0] != indices[1], 'The reopened YouTube draft did not visibly play the package video.')
        self.record['playback'] = dict(sampledFrameIndices=indices, byteIdentityVerified=False)

    def run(self):
        try:
            self.admit()
            self.phase('verify-saved-youtube-draft')
            self.open_drafts('verify')
            def choose(value, frame):
                found = yl.yt_drafts(frame, value['text'], self.video, self.caption)
                self.record['draftsBefore'] = dict(rows=found['rows'], top=found['row']['top'], title=found['row']['title'])
                return found['target']
            self.tap('verify-open-saved-draft', 'yt_drafts', choose)
            self.screen('yt_reopened_editor')
            self.playback()
            self.tap('verify-open-details', 'yt_playing', lambda v, f: yl.yt_editor(f, v['text'], self.video)['target'])
            # Keep the reopened draft with the same single Save draft; an uncertain answer is never repeated.
            self.tap('verify-keep-draft-once', 'yt_reopened_details',
                     lambda v, f: self.details('yt_reopened_details', v, f)['saveTarget'])
            self.screen('yt_home')
            self.phase('verify-draft-kept')
            self.open_drafts('final')
            final, _, _ = self.screen('yt_drafts')
            require(final['rows'] == self.record['draftsBefore']['rows'], 'The number of YouTube drafts changed when the draft was kept.')
            self.record['draftsAfter'] = dict(rows=final['rows'], top=final['row']['top'], title=final['row']['title'])
            self.history()
            self.record.update(state='validation_passed', savedDraftVerified=True, finalScreen='yt_drafts',
                meaning='On the same channel, the unique YouTube draft with the exact title and the package video reopened, played, '
                        'was kept with Save draft and was listed once in Drafts. No Upload Short, publishing or messaging. '
                        'Not app-restart or server persistence proof.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record
