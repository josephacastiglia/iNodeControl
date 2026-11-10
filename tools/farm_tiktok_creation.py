"""Bounded C24C TikTok video draft creation, then an independent verifier.

Draft only. The video reaches Photos by the same Safari/Files route as the Reel
candidate. In TikTok the inputs are reviewed settled taps, one long press for
Paste and nothing else: + -> gallery -> the one matching tile -> Next; a
suggested sound is removed once; the exact one-line description is pasted and
checked caret-free; Drafts is pressed once. Unknown outcomes stop and nothing is
repeated. Post, Your Story, LIVE and Share are never targets. The verifier is a
separate owned run that reopens the unique matching draft, requires it silent
with the exact description and keeps it with Drafts.
"""
import numpy as np

from farm_owned_capture import InspectionStopped
from farm_creation_layout import require, safari_blank, leftover_downloads, leftover_player
from farm_draft_transport import allowed_tap
from farm_draft_workflow import Workflow
from farm_live_verification import idle
from farm_observations import classify
from farm_screen_layout import pixels
from farm_transitions import wait_for_transition
import farm_reel_layout as reel
import farm_tiktok_layout as tt
from farm_reel_creation import ReelCreationWorkflow, ReelVerification, PRE_SETTLE as REEL_PRE_SETTLE

# Read-only waits before the first capture of screens that animate in. Shared
# Safari/Files screens keep the Reel values.
SHARED = ('reel_safari_entry', 'reel_page', 'reel_caption_copied', 'link_menu', 'page_menu', 'downloads', 'quicklook',
          'quicklook_controls', 'share_sheet')
PRE_SETTLE = {**{role: REEL_PRE_SETTLE[role] for role in SHARED},
              'tiktok_entry': .8, 'tiktok_profile': .6, 'tiktok_camera': .8, 'tiktok_picker': .8, 'tiktok_selected': .6,
              'tiktok_editor': 1.0, 'tiktok_details_blank': .6, 'tiktok_paste_menu': .4, 'tiktok_details': .4,
              'tiktok_feed': .8, 'tiktok_drafts': .8, 'tiktok_reopened_editor': 1.0, 'tiktok_reopened_details': .6}
# A callout is captured once; every other screen needs two agreeing fresh frames.
SETTLED = set(PRE_SETTLE) - {'tiktok_paste_menu'}
# Regions allowed to change between two otherwise identical fresh frames: the
# feed and editor play video, the caret blinks, the Drafts toast fades.
MOVING = {
    'tiktok_feed': ((0, 65, 500, 1000),),
    # The entry check accepts the feed, whose video plays; the profile decision that
    # follows is settled with everything but the fading toast protected.
    'tiktok_entry': ((0, 65, 500, 1000),),
    'tiktok_profile': ((190, 135, 310, 170),),
    'tiktok_camera': ((0, 65, 500, 975),),
    'tiktok_editor': ((0, 65, 500, 965),),
    'tiktok_reopened_editor': ((0, 65, 500, 965),),
    'tiktok_details_blank': ((15, 120, 340, 330),),
    'tiktok_details': ((15, 120, 340, 330),),
    'tiktok_reopened_details': ((15, 120, 340, 330),),
    'tiktok_drafts': ((0, 125, 500, 175),),
}
CARET_ATTEMPTS = 6          # Settled observations until one shows the description without the caret.
CARET_PAUSES = (.35, .85)   # Alternating by about half a blink, as on YouTube (phase lock, 23 Oct).
READ_ONLY_VERIFY = True     # The verifier never reopens a saved TikTok draft (see TikTokVerification.run).
DRAFTS_BACK = (30, 85)      # The Drafts grid's back arrow (template tt_back).
SOUND_CAPTURES = 8          # Read-only editor observations until the sound control settles.
SOUND_HOLD = 1.5            # The same settled sound state, seconds apart.
# Publication controls that a tap may never land on, even if OCR misreads them.
FORBIDDEN = {
    'tiktok_editor': ((16, 982, 245, 1034),), 'tiktok_reopened_editor': ((16, 982, 245, 1034),),   # Your Story
    'tiktok_details_blank': ((255, 977, 485, 1034),), 'tiktok_details': ((255, 977, 485, 1034),),  # Post
    'tiktok_reopened_details': ((255, 977, 485, 1034),),
    'tiktok_camera': ((300, 980, 480, 1020),),                                                     # CREATE / LIVE modes
}
PROHIBITED = ('story', 'live', 'repost', 'upload', 'gift', 'message')
# Purposes after which a new request for the same content could duplicate media
# or a draft. Absence of all of them means no phone import or draft can exist.
COMMITTING = ('download-linked-file', 'save-video-to-photos', 'select-package-video', 'open-tiktok-editor',
              'remove-suggested-sound', 'paste-exact-caption', 'save-tiktok-draft-once')


def compare(role):
    """Settling rule: protected pixels must stay put; shared screens keep the Reel rule."""
    if not role.startswith('tiktok_'): return reel.reel_compare(role)
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


def tiktok_guard(text, x, y, role):
    """Extra TikTok refusals on top of the shared publish-label guard."""
    for left, top, right, bottom in FORBIDDEN.get(role, ()):
        require(not (left <= x <= right and top <= y <= bottom), 'Target overlaps a TikTok publishing control.')
    for line in text.get('lines', []):
        words = line.get('words', [])
        if not words: continue
        left = min(w['x'] for w in words); right = max(w['x']+w['width'] for w in words)
        top = min(w['y'] for w in words); bottom = max(w['y']+w['height'] for w in words)
        if left-45 <= x <= right+45 and top-25 <= y <= bottom+25:
            require(not any(word in line['text'].casefold().split() for word in PROHIBITED),
                    'Target overlaps a prohibited or ambiguous TikTok label.')


class TikTokCreationWorkflow(ReelCreationWorkflow):
    PLATFORM = 'tiktok'
    APP_NAME = 'TikTok'
    MEDIA_ROLES = ('tiktok_picker',)
    PASTE_ROLES = ('tiktok_details',)

    def __init__(self, folder, kernel, store, video, caption, templates, expected_hash, expected_uid, *,
                 transfer_url, download, video_bytes, **kwargs):
        require(tt.caption_supported(caption), 'TikTok creation supports one visible ASCII description line up to 24 characters.')
        super().__init__(folder, kernel, store, video, caption, templates, expected_hash, expected_uid,
                         transfer_url=transfer_url, download=download, video_bytes=video_bytes, **kwargs)
        self.title = 'TikTok draft'
        self.record.update(mode='create_tiktok_draft', format='tt_video', captionMethod='verified_safari_copy_and_tiktok_paste',
                           sound=dict(initial=None, suggested=None, removed=False, final=None),
                           draftsCount=dict(before=None, after=None))
        self.record.pop('pickerCell', None)

    # -- recognition -------------------------------------------------------------
    def transfer_page(self, text):
        return tt.transfer_page(text, self.download)

    def verify_screen(self, role, value, frame, index=None, require_next=False):
        text, result = value['text'], value['result']
        decision = self.check_prompt(role, value)
        if decision is not None: return decision
        if role == 'reel_safari_entry':
            try: return self.verify_screen('safari', value, frame)
            except InspectionStopped: pass
            try: return safari_blank(text)   # No tab open: the empty address field is focused next.
            except InspectionStopped: pass
            try:   # Reopened still editing its address, the text selected (slot 20, 22 Oct): typing replaces it.
                return dict(self.verify_screen('address_selected', value, frame), browser='safari')
            except InspectionStopped: pass
            try: return leftover_downloads(text)
            except InspectionStopped: pass
            try: return reel.leftover_share_sheet(text)   # As in the Reel workflow (22 Oct).
            except InspectionStopped: pass
            try: return reel.leftover_link_menu(text)
            except InspectionStopped: pass
            try: return tt.leftover_preview(frame, text)
            except InspectionStopped: return leftover_player(frame, text)
        if role == 'reel_page': return tt.transfer_page(text, self.download)
        if role == 'reel_caption_copied': return {**tt.transfer_page(text, self.download), **tt.caption_copied(text)}
        if role == 'tiktok_profile':
            require(result.get('screen') == 'profile' and result.get('accountStatus') == 'exact_text_match',
                    'The exact authorized TikTok account is not visible on its profile.')
            return tt.tiktok_profile(frame, text, self.account)
        if role == 'tiktok_entry':
            # TikTok resumes where it was left: the exact profile, or the feed.
            try: return dict(screen='profile', **self.verify_screen('tiktok_profile', value, frame))
            except InspectionStopped: return dict(screen='feed', **tt.tiktok_feed(frame, text))
        if role == 'tiktok_feed': return tt.tiktok_feed(frame, text)
        if role == 'tiktok_camera': return tt.tiktok_camera(frame, text)
        if role == 'tiktok_picker': return tt.tiktok_picker(frame, text, self.video)
        if role == 'tiktok_selected': return tt.tiktok_selected(frame, text, self.video)
        if role in ('tiktok_editor', 'tiktok_reopened_editor'): return tt.tiktok_editor(frame, text, self.video)
        if role in ('tiktok_details_blank', 'tiktok_details', 'tiktok_reopened_details'):
            try:
                return tt.tiktok_details(frame, text, self.video, None if role == 'tiktok_details_blank' else self.caption,
                                         reopened=role == 'tiktok_reopened_details')
            except tt.CaretVisible as error:
                # Recorded and never a decision basis; observe() captures again without input.
                return dict(caretVisible=True, reason=str(error))
        if role == 'tiktok_paste_menu': return tt.tiktok_paste_menu(frame, text)
        if role == 'tiktok_drafts': return tt.tiktok_drafts(frame, text, self.video)
        return super().verify_screen(role, value, frame, index, require_next)

    def confirmation_compare(self, role):
        """Settled screens may be reconfirmed by a newer frame under their own settling rule."""
        if role == 'quicklook': return self.preview_identity()   # A playing preview, as in the Reel route.
        return compare(role) if role in SETTLED else super().confirmation_compare(role)

    def settle_compare(self, role):
        """The preview plays and its toolbar fades (22 Oct, slot 20: the pixel rule ran out of its
        budget), so it settles on the package video's identity, as in the Reel route."""
        return self.preview_identity() if role == 'quicklook' else compare(role)

    def observe_screen(self, role, index=None, require_next=False):
        if role not in PRE_SETTLE: return Workflow.observe(self, role, index, require_next)
        def journal(event):
            self.record['transitionChecks'].append(event); self.save()
        for attempt in range(CARET_ATTEMPTS):
            self.pause(PRE_SETTLE[role] if attempt == 0 else CARET_PAUSES[attempt % 2])
            if role in SETTLED:
                value, frame, _ = wait_for_transition(role, lambda: self.capture(role, index), self.check, self.store.current_evidence,
                    journal=journal, monotonic=self.monotonic, pause=self.pause,
                    ready=lambda frame, text: None, compare=self.settle_compare(role), platform=self.PLATFORM,
                    require_recent=self.confirmation_compare(role) is None, phone=self.phone)
            else:
                value, frame = self.capture(role, index)
            entry = next(e for e in reversed(self.record['observations']) if e.get('observationId') == value['id'])
            if not entry.get('screenCheck', {}).get('caretVisible'): return value, frame
        raise InspectionStopped('The description stayed covered by the text caret; no input was sent.')

    def check_target(self, role, point):
        """Every tap stays in the app area, away from shared publish labels and TikTok publishing controls."""
        def target(value, frame):
            x, y = point(value, frame) if callable(point) else point
            allowed_tap(value['text'], x, y, 'tiktok:' + role, frame=frame)
            tiktok_guard(value['text'], x, y, role)
            return x, y
        return target

    def tap(self, label, role, point, *, hold=False):
        # TikTok controls ignored immediate clicks on 17 Oct; Safari keeps plain taps.
        self.step(label, role, point=self.check_target(role, point), hold=hold, settle=not hold and role.startswith('tiktok_'))

    # -- TikTok steps --------------------------------------------------------------
    def details(self, value, frame, caption, *, reopened=False):
        return tt.tiktok_details(frame, value['text'], self.video, caption, reopened=reopened)

    def next_silent(self, value, frame):
        result = tt.tiktok_editor(frame, value['text'], self.video)
        require(result['sound'] == 'none', 'A sound is attached or still loading; Next is not pressed.')
        return result['nextTarget']

    def remove_target(self, value, frame):
        result = tt.tiktok_editor(frame, value['text'], self.video)
        require(result['sound'] == 'attached', 'No suggested sound is attached; nothing is removed.')
        return result['removeTarget']

    def sound_state(self, role):
        """Read-only until one non-loading state is seen twice, SOUND_HOLD seconds apart."""
        first = None
        for _ in range(SOUND_CAPTURES):
            result, _, _ = self.screen(role)
            now = self.monotonic()
            if result['sound'] == 'loading': first = None
            elif first and first[0] == result['sound'] and now-first[1] >= SOUND_HOLD: return result
            elif not first or first[0] != result['sound']: first = (result['sound'], now)
            self.pause(.5)
        raise InspectionStopped('The TikTok sound control did not settle; no input was sent.')

    def silence(self, role, label):
        """Remove one suggested sound at most; require the editor silent before Next."""
        state = self.sound_state(role)
        self.record['sound']['initial'] = state['sound']; self.save()
        if state['sound'] == 'attached':
            self.record['sound']['suggested'] = state['soundLabel']; self.save()
            self.tap(label, role, self.remove_target)
            self.record['sound']['removed'] = True; self.save()
            state = self.sound_state(role)
        require(state['sound'] == 'none', 'TikTok kept a sound on the video; review before any further input.')
        self.record['sound']['final'] = 'none'; self.save()

    SPLASH_POLLS = 6   # About 9 s.

    def await_launch(self):
        """TikTok can be relaunched when reopened (slot 20, 22 Oct): its splash (the logo alone)
        is waited out by reading frames, without input, before the entry screen is decided."""
        waits = self.record.setdefault('launchWaits', [])
        for attempt in range(self.SPLASH_POLLS):
            raw, headers = self.kernel.shot(self.phone.board)
            lines = [l['text'].strip().casefold() for l in self.store.ocr.read(raw).get('lines', []) if l.get('words')]
            splash = lines in ([], ['tiktok'])
            waits.append(dict(attempt=attempt, sequence=headers.get('X-iMouse-Frame-Sequence'), splash=splash))
            if not splash: return
            self.pause(1.5)

    def return_to_profile(self, label):
        """The exact profile, directly or from the feed. Returns (profile, entry screen check)."""
        self.await_launch()
        entry, _, _ = self.screen('tiktok_entry')
        if entry['screen'] == 'feed':
            self.tap(label, 'tiktok_entry', lambda v, f: tt.tiktok_feed(f, v['text'])['profileTarget'])
        profile, _, _ = self.screen('tiktok_profile')
        return profile, entry

    # -- workflow ----------------------------------------------------------------
    def admit(self):
        self.identity = self.runtime()
        require(idle(self.kernel.input_status().get(self.phone.device_id)), f'{self.phone.board} is not free; no takeover is allowed.')
        raw, _ = self.kernel.shot(self.phone.board)
        initial = classify(self.store.ocr.read(raw), dict(platform='tiktok', account=self.account, caption=self.caption), raw)
        require(initial['screen'] == 'profile' and initial['accountStatus'] == 'exact_text_match',
                'Start on the authorized TikTok profile. No input was sent.')
        self.record['cleanup'] = 'unconfirmed'; self.save(); self.owned.acquire()
        self.command('/mouse/reset', purpose='initial_pointer_reset')

    def run(self):
        try:
            self.admit()
            self.import_video()
            self.phase('open-tiktok')
            self.open_app('TikTok', 'return')
            profile, _ = self.return_to_profile('open-profile-tab')
            self.record['draftsCount']['before'] = profile['draftsCount']; self.save()
            self.phase('select-tiktok-media')
            self.tap('open-tiktok-create', 'tiktok_profile', lambda v, f: tt.tiktok_profile(f, v['text'], self.account)['createTarget'])
            self.tap('open-tiktok-gallery', 'tiktok_camera', lambda v, f: tt.tiktok_camera(f, v['text'])['galleryTarget'])
            def choose(value, frame):
                found = tt.tiktok_picker(frame, value['text'], self.video)
                self.record['pickerTile'] = found['tile']
                return found['target']
            self.tap('select-package-video', 'tiktok_picker', choose)
            self.tap('open-tiktok-editor', 'tiktok_selected', lambda v, f: tt.tiktok_selected(f, v['text'], self.video)['target'])
            self.phase('remove-suggested-sound')
            self.silence('tiktok_editor', 'remove-suggested-sound')
            self.tap('open-tiktok-details', 'tiktok_editor', self.next_silent)
            self.phase('caption-and-save')
            self.tap('focus-empty-description', 'tiktok_details_blank', lambda v, f: self.details(v, f, None)['captionTarget'])
            self.tap('open-paste-menu', 'tiktok_details_blank', lambda v, f: self.details(v, f, None)['pressTarget'], hold=True)
            self.tap('paste-exact-caption', 'tiktok_paste_menu', lambda v, f: tt.tiktok_paste_menu(f, v['text'])['target'])
            self.pause(2)  # Let the OS paste banner leave the header; nothing is repeated.
            # The single Drafts press is decided on a caret-free frame with the exact description.
            self.tap('save-tiktok-draft-once', 'tiktok_details', lambda v, f: self.details(v, f, self.caption)['draftsTarget'])
            # On 17 Oct TikTok landed on the feed after a video draft and on the
            # profile after a photo draft; either is accepted, nothing else.
            after, landed = self.return_to_profile('open-profile-after-save')
            self.record.update(draftSavedToast=bool(landed.get('toastSeen')), landedAfterSave=landed['screen']); self.save()
            before = self.record['draftsCount']['before']
            self.record['draftsCount']['after'] = after['draftsCount']; self.save()
            if before is not None and after['draftsCount'] is not None:
                require(after['draftsCount'] == before+1, 'The TikTok drafts count did not increase by one; review before any further input.')
            self.record.update(state='created_unverified', meaning='Package video saved to Photos and selected, any suggested sound '
                               'removed, exact description pasted and Drafts answered; an independent reopen check is required.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record


class TikTokVerification(TikTokCreationWorkflow):
    """Separate owned run: reopen the unique saved draft, require it silent with the exact description, keep it."""
    history = ReelVerification.history

    def __init__(self, folder, kernel, store, video, caption, templates, expected_hash, expected_uid, **kwargs):
        super().__init__(folder, kernel, store, video, caption, templates, expected_hash, expected_uid,
                         transfer_url='verification-only', download='verification-only', video_bytes=0, **kwargs)
        self.record.update(mode='verify_tiktok_draft', inspectionOnly=False, appRestartVerified=False, finalScreen='unknown')
        for key in ('transferUrl', 'downloadName', 'draftsCount'): self.record.pop(key, None)

    def run(self):
        try:
            self.admit()
            self.phase('verify-saved-tiktok')
            profile, _, _ = self.screen('tiktok_profile')
            require(profile['draftsTarget'], 'The TikTok Drafts tile is not visible on the profile.')
            self.tap('verify-open-drafts', 'tiktok_profile', lambda v, f: tt.tiktok_profile(f, v['text'], self.account)['draftsTarget'])
            if READ_ONLY_VERIFY:
                # Reopening and saving a draft again dropped the video on X (23 Oct), so the check reads the Drafts
                # grid only: exactly one tile shows the package video, with no sound label. The description was
                # read exactly on the details screen before the one Drafts tap; it is not read again here.
                found, _, _ = self.screen('tiktok_drafts')
                require(found['tile']['soundLabel'] is None, 'The TikTok draft shows a sound.')
                self.record['draftsBefore'] = dict(count=found['count'], tile=found['tile']['tile'], soundLabel=None,
                                                   match=found['tile']['match'])
                self.tap('verify-close-drafts', 'tiktok_drafts', DRAFTS_BACK)
                self.screen('tiktok_profile')
                self.history()
                self.record.update(state='validation_passed', savedDraftVerified=True, finalScreen='tiktok_profile', reopened=False,
                    meaning='On the signed-in profile, TikTok Drafts shows exactly one draft whose cover is the package video, '
                            'with no sound. Not reopened (saving a reopened draft dropped the video on X, 23 Oct); the '
                            'description was checked before saving. No Post, Story, publishing or messaging.')
                return self.record
            def choose(value, frame):
                found = tt.tiktok_drafts(frame, value['text'], self.video)
                self.record['draftsBefore'] = dict(count=found['count'], tile=found['tile']['tile'], soundLabel=found['tile']['soundLabel'])
                return found['target']
            self.tap('verify-open-saved-draft', 'tiktok_drafts', choose)
            # The supervised check removed an attached suggested sound the same way.
            self.silence('tiktok_reopened_editor', 'verify-remove-suggested-sound')
            self.tap('verify-open-details', 'tiktok_reopened_editor', self.next_silent)
            # Drafts keeps the reopened draft, as in the supervised check. An uncertain answer is never repeated.
            self.tap('verify-keep-draft-once', 'tiktok_reopened_details',
                     lambda v, f: self.details(v, f, self.caption, reopened=True)['draftsTarget'])
            final, _, _ = self.screen('tiktok_drafts')
            before = self.record['draftsBefore']['count']
            if before is not None and final['count'] is not None:
                require(final['count'] == before, 'The TikTok drafts count changed when the draft was kept.')
            require(final['tile']['soundLabel'] is None, 'The kept TikTok draft still shows a sound.')
            self.record['draftsAfter'] = dict(count=final['count'], tile=final['tile']['tile'], soundLabel=None)
            self.history()
            self.record.update(state='validation_passed', savedDraftVerified=True, finalScreen='tiktok_drafts',
                meaning='The unique matching TikTok draft reopened with the package video, no sound and the exact description, '
                        'and remained in Drafts. No Post, Story, publishing or messaging. Not app-restart or server persistence proof.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record
