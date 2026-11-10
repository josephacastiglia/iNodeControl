"""Bounded TikTok photo draft creation (tt_photo, 2-10 slides) on its window's phone, then a read-only verifier.

Draft only. The slides reach Photos from the shared image transfer page: Copy caption, then per
slide page a touch and hold on the image and Save to Photos (the pointer is reset before every
hold: on A20 a hold right after a tap selected page text or did nothing, 4 Nov). In TikTok: + ->
gallery -> the package slides' circles in slide order (each chosen by image match, never another
Photos item) -> Next (N) -> editor Next -> the empty description, a long press, Paste -> the
collapsed details must show the exact one-line description and the covers in order -> Drafts once.
The suggested sound TikTok attaches by itself is recorded and kept; its pill is never a target.
Post, Story, LIVE and Share are never targets. Unknown outcomes stop and nothing is repeated.

The verifier is a separate owned run that reads the Drafts grid only: exactly one draft whose
cover shows package slide 1. Nothing is reopened (saving a reopened draft dropped media on X, 23 Oct).
"""
import numpy as np

from farm_owned_capture import InspectionStopped
from farm_creation_layout import require, safari_blank, leftover_downloads, leftover_player
from farm_draft_creation import CreationWorkflow
from farm_draft_workflow import Workflow
from farm_live_verification import idle
from farm_screen_layout import pixels
from farm_transitions import wait_for_transition
import farm_reel_layout as reel
from farm_reel_creation import ReelVerification, LEFTOVER_ROUNDS
import farm_tiktok_creation as ttc
from farm_tiktok_creation import TikTokCreationWorkflow
import farm_tiktok_layout as tt
import farm_tiktok_photo_layout as ph

# Read-only waits before the first capture of screens that animate in (photo roles); the shared
# Safari and TikTok video roles keep their own values.
PHOTO_SETTLE = {'photo_index': .6, 'photo_copied': .6, 'photo_slide': .6, 'photo_menu': .8, 'photo_after_hold': .8,
                'tiktok_photo_picker': .8, 'tiktok_photo_editor': 1.0, 'tiktok_photo_details': .6,
                'tiktok_photo_description': .6, 'tiktok_photo_paste_menu': .4, 'tiktok_photo_drafts': .8,
                'tiktok_photo_profile': .6}
PRE_SETTLE = {**ttc.PRE_SETTLE, **PHOTO_SETTLE}
# A callout is captured once; every other screen needs two agreeing fresh frames.
SETTLED = set(PRE_SETTLE) - {'tiktok_paste_menu', 'tiktok_photo_paste_menu'}
# Regions allowed to change between two otherwise identical frames: the editor plays its slideshow,
# the caret blinks in the expanded description, a toast fades over the profile or Drafts.
MOVING = {**ttc.MOVING,
          'tiktok_photo_editor': ((0, 65, 500, 970),),
          'tiktok_photo_description': (ph.DESCRIPTION_BOX, (15, 120, 480, 240)),
          'tiktok_photo_profile': ((190, 135, 310, 170),),
          'tiktok_photo_drafts': ((0, 125, 500, 175),)}
# Publication controls that a tap may never land on, even if OCR misreads them.
FORBIDDEN = {**ttc.FORBIDDEN,
             'tiktok_photo_editor': ((16, 982, 245, 1034), (150, 90, 360, 140)),      # Story; the sound pill (kept)
             'tiktok_photo_details': ((255, 977, 485, 1034),),                        # Post
             'tiktok_photo_description': ((255, 977, 485, 1034),)}                    # Post
# Purposes after which a new request for the same content could duplicate photos or a draft.
# Absence of all of them means no Photos item or draft can exist from this run.
COMMITTING = ('save-photo-', 'select-package-photo-', 'open-tiktok-photo-editor', 'open-tiktok-photo-details',
              'paste-exact-caption', 'save-tiktok-photo-draft-once')


def compare(role):
    """Settling rule of the photo roles: protected pixels must stay put; other roles keep theirs."""
    if role in PHOTO_SETTLE and role.startswith('photo_'): return reel.reel_compare('reel_page')
    if role not in PHOTO_SETTLE: return ttc.compare(role)
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


class TikTokPhotoCreationWorkflow(TikTokCreationWorkflow):
    MEDIA_ROLES = ('tiktok_photo_picker',)
    PASTE_ROLES = ('tiktok_photo_description',)
    # Operator's standing instruction for A20 (4 Nov): iOS's full-access photos reminder is answered with the
    # policy answer ('Allow Full Access', keeps the current setting) by one pointer tap at the recognized
    # button, then the screen is read again; this run's journal is the validation evidence. Once per run:
    # a reminder that returns, or any other prompt, stops the run as before.
    validated_prompt_methods = {('photos_reminder', 'pointer_tap'): ('validated', 'operator instruction for A20, 4 Nov 2026')}
    PROMPT_LIMIT = 1

    def answer_prompt(self, decision, role):
        require(decision['kind'] == 'photos_reminder' and decision['answer'] == 'Allow Full Access'
                and not any(a['label'].startswith('answer-') for a in self.record['actions']),
                'Only one photos reminder per run is answered automatically; review the phone.')
        super().answer_prompt(decision, role)

    def __init__(self, folder, kernel, store, images, caption, templates, expected_hash, expected_uid, *,
                 transfer_url, transfer_title, package_name, slides, **kwargs):
        require(ph.caption_supported(caption), 'TikTok photo creation supports one visible ASCII description line up to 24 characters.')
        require(isinstance(slides, list) and slides == [f'{n:02}.jpg' for n in range(1, len(slides)+1)]
                and 2 <= len(slides) <= 10 and images.count == len(slides), 'The package slides and their reference differ.')
        require(transfer_title == ph.TITLE, 'This is not a TikTok photo transfer page.')
        CreationWorkflow.__init__(self, folder, kernel, store, [], caption, templates, expected_hash, expected_uid,
                                  transfer_url=transfer_url, transfer_title=transfer_title, **kwargs)
        self.images = self.video = images   # The shared Safari steps read self.video; nothing here is a video.
        self.download, self.slides, self.count = package_name, list(slides), len(slides)
        self.cell = None
        self.record.update(mode='create_tiktok_photo_draft', format='tt_photo', imageSha256s=list(images.hashes),
                           slideCount=self.count, downloadName=package_name, mediaMethod='safari_slide_pages_save_to_photos',
                           captionMethod='verified_safari_copy_and_tiktok_paste',
                           sound=dict(observed=None, label=None, kept=True, removed=False), pickerTiles=[],
                           draftsCount=dict(before=None, after=None))

    # -- recognition -------------------------------------------------------------
    def transfer_page(self, text):
        return ph.transfer_index(text, self.download, self.count)

    def verify_screen(self, role, value, frame, index=None, require_next=False):
        text = value['text']
        decision = self.check_prompt(role, value)
        if decision is not None: return decision
        if role == 'photo_index': return ph.transfer_index(text, self.download, self.count)
        if role == 'photo_copied': return ph.transfer_copied(text, self.count)
        if role == 'photo_slide': return ph.transfer_slide(frame, text, index, self.count, self.images)
        if role == 'photo_menu': return ph.save_menu(frame, text, index, self.images)
        if role == 'photo_after_hold':
            # The image menu, or the unchanged slide page when the press opened nothing.
            try: return dict(menu=True, **ph.save_menu(frame, text, index, self.images))
            except InspectionStopped: return dict(menu=False, **ph.transfer_slide(frame, text, index, self.count, self.images))
        if role == 'tiktok_photo_profile': return ph.profile(frame, text, self.account)
        if role == 'tiktok_photo_picker': return ph.photo_picker(frame, text, self.images, index)
        if role == 'tiktok_photo_editor': return ph.photo_editor(frame, text, self.images)
        if role == 'tiktok_photo_details': return ph.photo_details(frame, text, self.images, self.caption if index else None)
        if role == 'tiktok_photo_description': return ph.description_editor(frame, text, self.images, self.caption if index else None)
        if role == 'tiktok_photo_paste_menu': return ph.paste_menu(frame, text)
        if role == 'tiktok_photo_drafts': return ph.photo_drafts(frame, text, self.images)
        if role == 'app_result': return dict(target=ph.app_target(text, self.search_app, frame))
        if role == 'app_search_entry':
            # Spotlight can reopen with an earlier query's results: accepted when they show the app itself.
            try: return dict(restoredResult=ph.app_target(text, self.search_app, frame))
            except InspectionStopped: pass
        if role == 'tiktok_entry':
            # TikTok resumes where it was left: the exact profile, or the feed.
            try: return dict(screen='profile', **ph.profile(frame, text, self.account))
            except InspectionStopped: return dict(screen='feed', **tt.tiktok_feed(frame, text))
        return super().verify_screen(role, value, frame, index, require_next)

    def confirmation_compare(self, role):
        if role in PHOTO_SETTLE: return compare(role) if role in SETTLED else None
        return super().confirmation_compare(role)

    def settle_compare(self, role):
        return compare(role) if role in PHOTO_SETTLE else super().settle_compare(role)

    def observe_screen(self, role, index=None, require_next=False):
        if role not in PHOTO_SETTLE: return super().observe_screen(role, index, require_next)
        self.pause(PRE_SETTLE[role])
        if role not in SETTLED: return self.capture(role, index)
        def journal(event):
            self.record['transitionChecks'].append(event); self.save()
        value, frame, _ = wait_for_transition(role, lambda: self.capture(role, index), self.check, self.store.current_evidence,
            journal=journal, monotonic=self.monotonic, pause=self.pause, ready=lambda frame, text: None,
            compare=compare(role), platform=self.PLATFORM, require_recent=self.confirmation_compare(role) is None, phone=self.phone)
        return value, frame

    def check_target(self, role, point):
        """Every tap stays in the app area, away from shared publish labels and TikTok publishing controls."""
        def target(value, frame):
            x, y = point(value, frame) if callable(point) else point
            from farm_draft_transport import allowed_tap
            allowed_tap(value['text'], x, y, 'tiktok:' + role, frame=frame)
            for left, top, right, bottom in FORBIDDEN.get(role, ()):
                require(not (left <= x <= right and top <= y <= bottom), 'Target overlaps a TikTok publishing control.')
            ttc.tiktok_guard(value['text'], x, y, role)
            return x, y
        return target

    def tap(self, label, role, point, *, hold=False, index=None):
        self.step(label, role, index=index, point=self.check_target(role, point), hold=hold,
                  settle=not hold and role.startswith('tiktok_'))

    def screen(self, role, index=None):
        value, frame = self.observe(role, index)
        return self.verify_screen(role, value, frame, index), value, frame

    def hold(self, label, role, point, index=None):
        """A long press after a pointer reset (a hold right after a tap did nothing on A20, 4 Nov)."""
        self.command('/mouse/reset', purpose=label + '-pointer-reset')
        self.pause(.5)
        self.tap(label, role, point, hold=True, index=index)

    # -- steps -------------------------------------------------------------------
    def open_app(self, name, visit):
        """CreationWorkflow.open_app with the Top Hit label also read enlarged (ph.app_target)."""
        from farm_creation_layout import home_search, empty_search, search_clear
        from farm_draft_workflow import centre
        target = lambda v, f: ph.app_target(v['text'], name, f)
        self.search_app = name
        self.pause(1.0)   # Home's closing animation must end first.
        value, frame = self.observe('home')
        try: point = target(value, frame)
        except InspectionStopped: point = None
        if point:
            self.step(visit+'-open-'+name, 'home', point=target); return
        self.step(visit+'-search-'+name, 'home', point=lambda v, f: centre(home_search(f, v['text'])))
        value, frame = self.observe('app_search_entry')
        try: target(value, frame); desired = True
        except InspectionStopped: desired = False
        if not desired:
            try: empty_search(value['text'], frame); empty = True
            except InspectionStopped: empty = False
            if not empty:
                self.step(visit+'-clear-restored-search', 'restored_search', point=lambda v, f: centre(search_clear(f)))
            self.step(visit+'-query-'+name, 'search', text=name)
        self.step(visit+'-open-'+name, 'app_result', point=target)

    def admit(self):
        self.identity = self.runtime()
        require(idle(self.kernel.input_status().get(self.phone.device_id)), f'{self.phone.board} is not free; no takeover is allowed.')
        raw, _ = self.kernel.shot(self.phone.board)
        try: ph.profile(raw, self.store.ocr.read(raw), self.account)
        except InspectionStopped as error:
            raise InspectionStopped('Start on the authorized TikTok profile. No input was sent. (' + str(error) + ')')
        self.record['cleanup'] = 'unconfirmed'; self.save(); self.owned.acquire()
        self.command('/mouse/reset', purpose='initial_pointer_reset')

    def return_to_profile(self, label):
        self.await_launch()
        entry, _, _ = self.screen('tiktok_entry')
        if entry['screen'] == 'feed':
            self.tap(label, 'tiktok_entry', lambda v, f: tt.tiktok_feed(f, v['text'])['profileTarget'])
        profile, _, _ = self.screen('tiktok_photo_profile')
        return profile, entry

    def open_transfer(self):
        """Profile -> Home -> Safari (closing an earlier download's leftovers) -> the package page."""
        self.phase('open-transfer')
        self.observe('tiktok_photo_profile')
        self.step('home-from-profile', 'tiktok_photo_profile', key='Home')
        self.open_app('Safari', 'transfer')
        for round_ in range(1, LEFTOVER_ROUNDS + 1):
            entry = self.safari_entry()
            if not any(entry.get(k) for k in ('leftoverPlayer', 'leftoverShareSheet', 'leftoverLinkMenu', 'leftoverPreview', 'leftoverDownloads')): break
            require(round_ < LEFTOVER_ROUNDS, 'Safari still shows an earlier download after closing it; nothing else was sent.')
            if entry.get('leftoverPlayer'): self.close_leftover_player(entry, round_)
            elif entry.get('leftoverLinkMenu'): self.tap(f'close-leftover-link-menu-{round_}', 'reel_safari_entry', entry['closeTarget'])
            elif entry.get('leftoverShareSheet'):
                if entry.get('static'):
                    self.direct_click(f'close-leftover-share-sheet-{round_}', 'static_safari_entry', *entry['closeTarget'],
                                      'static_frame_leftover_share_sheet')
                else: self.tap(f'close-leftover-share-sheet-{round_}', 'reel_safari_entry', entry['closeTarget'])
            elif entry.get('static'):
                self.direct_click(f'close-leftover-preview-{round_}', 'static_safari_entry', 450, 85, 'static_frame_leftover_preview')
            elif entry.get('leftoverPreview'): self.tap(f'close-leftover-preview-{round_}', 'reel_safari_entry', (450, 85))
            else: self.tap(f'close-leftover-downloads-{round_}', 'reel_safari_entry', entry['doneTarget'])
            self.pause(1.5)
        if not entry.get('addressSelected'):
            self.tap('focus-safari-address', 'safari_or_blank', (245, 953))
        self.step('enter-transfer-url', 'address_selected', text=self.url)
        self.command('/key/sendkey', purpose='load-transfer-url', fn_key='Enter')   # Same address edit; never a caption.
        self.pause(1)
        self.await_transfer_page()

    def save_slides(self):
        """Copy caption, then each slide page: hold the image, Save to Photos, next. Home from the last page."""
        self.phase('copy-caption')
        self.tap('copy-caption', 'photo_index', lambda v, f: ph.transfer_index(v['text'], self.download, self.count)['copyTarget'])
        self.tap('open-slide-1', 'photo_copied', lambda v, f: ph.transfer_copied(v['text'], self.count)['openTarget'])
        saved = self.record.setdefault('photosSaved', [])
        for number in range(1, self.count+1):
            self.phase(f'save-slide-{number}')
            slide = lambda v, f, n=number: ph.transfer_slide(f, v['text'], n, self.count, self.images)
            self.hold(f'hold-slide-image-{number}', 'photo_slide', lambda v, f, s=slide: s(v, f)['holdTarget'], index=number)
            after, _, _ = self.screen('photo_after_hold', number)
            if not after['menu']:
                # The first press on a freshly loaded slide page opened nothing 3 times in 4 on A20 (4 Nov); the page
                # is unchanged and nothing is selected, so one more press is sent. A second miss stops the run.
                self.record.setdefault('holdRetries', []).append(number); self.save()
                self.hold(f'hold-slide-image-{number}-again', 'photo_slide', lambda v, f, s=slide: s(v, f)['holdTarget'], index=number)
            self.tap(f'save-photo-{number}', 'photo_menu', lambda v, f, n=number: ph.save_menu(f, v['text'], n, self.images)['target'],
                     index=number)
            saved.append(number); self.save()
            if number < self.count:
                self.tap(f'next-slide-{number}', 'photo_slide', lambda v, f, s=slide: s(v, f)['nextTarget'], index=number)
        # The slide page is not a text field, so Home's leading Tab is harmless here.
        self.step('home-from-transfer', 'photo_slide', index=self.count, key='Home')

    def select_photos(self):
        self.phase('select-tiktok-photos')
        self.tap('open-tiktok-create', 'tiktok_photo_profile', lambda v, f: ph.profile(f, v['text'], self.account)['createTarget'])
        self.tap('open-tiktok-gallery', 'tiktok_camera', lambda v, f: tt.tiktok_camera(f, v['text'])['galleryTarget'])
        for chosen in range(self.count):
            def choose(value, frame, k=chosen):
                found = ph.photo_picker(frame, value['text'], self.images, k)
                self.record['pickerTiles'].append(dict(slide=k+1, tile=found['tile'], mean=found['match']['mean'],
                                                       nearestOther=found['match']['nearestOther']))
                return found['target']
            self.tap(f'select-package-photo-{chosen+1}', 'tiktok_photo_picker', choose, index=chosen)
        self.tap('open-tiktok-photo-editor', 'tiktok_photo_picker',
                 lambda v, f: ph.photo_picker(f, v['text'], self.images, self.count)['target'], index=self.count)

    def editor_next(self, value, frame):
        found = ph.photo_editor(frame, value['text'], self.images)
        self.record['sound'].update(observed=found['sound'], label=found['soundLabel']); self.save()
        return found['nextTarget']

    def caption_and_save(self):
        self.phase('caption-and-save')
        self.tap('open-tiktok-photo-details', 'tiktok_photo_editor', self.editor_next)
        self.tap('focus-empty-description', 'tiktok_photo_details',
                 lambda v, f: ph.photo_details(f, v['text'], self.images)['descriptionTarget'], index=0)
        self.hold('open-paste-menu', 'tiktok_photo_description',
                  lambda v, f: ph.description_editor(f, v['text'], self.images)['pressTarget'], index=0)
        self.tap('paste-exact-caption', 'tiktok_photo_paste_menu', lambda v, f: ph.paste_menu(f, v['text'])['target'])
        self.pause(2)   # Let the OS paste banner leave the header; nothing is repeated.
        # Back only collapses the expanded editor (4 Nov); the counter proves the pasted length first.
        self.tap('collapse-description-editor', 'tiktok_photo_description',
                 lambda v, f: ph.description_editor(f, v['text'], self.images, self.caption)['collapseTarget'], index=1)
        # The single Drafts press is decided on the collapsed, caret-free details with the exact description.
        self.tap('save-tiktok-photo-draft-once', 'tiktok_photo_details',
                 lambda v, f: ph.photo_details(f, v['text'], self.images, self.caption)['draftsTarget'], index=1)

    def run(self):
        try:
            self.admit()
            self.open_transfer()
            self.save_slides()
            self.phase('open-tiktok')
            self.open_app('TikTok', 'return')
            profile, _ = self.return_to_profile('open-profile-tab')
            self.record['draftsCount']['before'] = profile['draftsCount']; self.save()
            self.select_photos()
            self.caption_and_save()
            after, landed = self.return_to_profile('open-profile-after-save')
            self.record.update(draftSavedToast=bool(landed.get('toastSeen')), landedAfterSave=landed['screen']); self.save()
            before = self.record['draftsCount']['before']
            self.record['draftsCount']['after'] = after['draftsCount']; self.save()
            if after['draftsCount'] is None:   # Unreadable over the new cover: record whether the cover is ours.
                try: self.record['draftsTileByCover'] = ph.drafts_tile_cover(self.store.current_evidence(
                        self.record['observations'][-1]['observationId'])[1], self.images)
                except Exception as error: self.record['draftsTileByCover'] = dict(error=str(error))
                self.save()
            if before is not None and after['draftsCount'] is not None:
                require(after['draftsCount'] == before+1, 'The TikTok drafts count did not increase by one; review before any further input.')
            self.record.update(state='created_unverified', meaning='Package slides saved to Photos and selected in order, the '
                               'suggested sound kept, exact description pasted and Drafts answered; an independent check is required.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record


class TikTokPhotoVerification(TikTokPhotoCreationWorkflow):
    """Separate owned run: the Drafts grid shows exactly one draft whose cover is package slide 1. Read only."""
    history = ReelVerification.history

    def __init__(self, folder, kernel, store, images, caption, templates, expected_hash, expected_uid, **kwargs):
        super().__init__(folder, kernel, store, images, caption, templates, expected_hash, expected_uid,
                         transfer_url='verification-only', transfer_title=ph.TITLE, package_name='verification-only',
                         slides=[f'{n:02}.jpg' for n in range(1, images.count+1)], **kwargs)
        self.record.update(mode='verify_tiktok_photo_draft', inspectionOnly=True, appRestartVerified=False, finalScreen='unknown')
        for key in ('transferUrl', 'downloadName', 'draftsCount', 'pickerTiles', 'sound'): self.record.pop(key, None)

    def run(self):
        try:
            self.admit()
            self.phase('verify-saved-tiktok-photo')
            profile, _, frame = self.screen('tiktok_photo_profile')
            if not profile['draftsTarget']:
                # 'Drafts: N' unreadable over the package cover; the cover itself marks the Drafts tile.
                self.record['draftsTileByCover'] = ph.drafts_tile_cover(frame, self.images); self.save()
            def drafts(value, frame):
                found = ph.profile(frame, value['text'], self.account)
                return found['draftsTarget'] or ph.drafts_tile_cover(frame, self.images)['target']
            self.tap('verify-open-drafts', 'tiktok_photo_profile', drafts)
            found, _, _ = self.screen('tiktok_photo_drafts')
            self.record['draftTile'] = dict(count=found['count'], tile=found['tile'], tiles=found['tiles'], match=found['match'],
                                            soundLabel=found['soundLabel'])
            self.tap('verify-close-drafts', 'tiktok_photo_drafts', ttc.DRAFTS_BACK)
            self.screen('tiktok_photo_profile')
            self.history()
            self.record.update(state='validation_passed', savedDraftVerified=True, finalScreen='tiktok_profile', reopened=False,
                meaning='On the signed-in profile, TikTok Drafts shows exactly one draft whose cover is package slide 1 '
                        '(sound label: ' + str(found['soundLabel']) + '). Not reopened; the description and the slide order were '
                        'checked on the details screen before the one Drafts press. No Post, Story, publishing or messaging.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record
