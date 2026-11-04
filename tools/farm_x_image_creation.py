"""Bounded X image draft creation (x_image: one image) on the window's phone, then a read-only verifier.

Draft only, on the X account signed in first (read from the side menu before any app input and
required again on every later account read and by the verifier). The image reaches Photos from the
shared transfer page: Open slide 1 of 1, touch and hold the image, Save to Photos (once), Back to
caption, Copy caption. In X the text is pasted first, the one matching image is added through the
system photo picker, and the draft is kept with Cancel -> Save to drafts once. Post, Discard, the
media remove control, Share and Safari's other menu rows are never targets. Unknown outcomes stop and
nothing is repeated.

An X draft is created right before it is checked and X is not closed in between; the verifier reads
Drafts only (exactly one row with the exact text whose thumbnail shows the package image) and never
reopens a draft: saving a reopened X draft dropped its media (23 Oct).
"""
import numpy as np

from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import require, exact, home_search, empty_search, search_clear
from farm_draft_creation import still_compare
from farm_draft_workflow import Workflow, centre
from farm_reel_creation import ReelVerification, LEFTOVER_ROUNDS
from farm_screen_layout import pixels
from farm_transitions import wait_for_transition
import farm_reel_layout as reel
import farm_x_creation as xc
import farm_x_image_layout as xil
import farm_x_layout as xl

# Read-only waits before the first capture of each image-route screen; the X screens keep the video route's.
PRE_SETTLE = {**xc.PRE_SETTLE, 'xi_page': .6, 'xi_slide': .8, 'xi_save_menu': .8, 'xi_caption_copied': .4,
              'x_composer_image': 1.0}
IMAGE_ROLES = ('xi_page', 'xi_slide', 'xi_save_menu', 'xi_caption_copied', 'x_composer_image')
# Every screen here needs two agreeing fresh frames except a callout (as in the video route).
SETTLED = set(PRE_SETTLE) - {'x_paste_menu', 'x_composer_focused', 'x_playing'}
MOVING = {**xc.MOVING, 'x_composer_image': ((60, 115, 490, 165),)}   # Caret.
FORBIDDEN = {**xc.FORBIDDEN, 'x_composer_image': (xl.POST, xil.REMOVE, xil.CARD_BUTTONS)}
# Purposes after which a new request for the same content could duplicate a Photos item or a draft.
COMMITTING = ('save-photo-', 'select-package-image', 'add-package-image', 'paste-exact-caption', 'save-x-draft-once')


def compare(role):
    """Settling rule: protected pixels stay put outside the status bar, the parked pointer and moving parts."""
    if role.startswith('x_') and role not in MOVING: return xc.compare(role)
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


def guard(x, y, role):
    """The image route's own never-target boxes; the video route's guard (labels and its boxes) runs as well."""
    for left, top, right, bottom in FORBIDDEN.get(role, ()):
        require(not (left <= x <= right and top <= y <= bottom), 'Target overlaps an X publishing or removal control.')


def x_top_hit(frame, text):
    """X as the app search's Top Hit. OCR misses the one-letter label under the icon (slot 17, 4 Nov), so the
    icon itself decides: a black tile with a white glyph at the Top Hit position. Its centre is the target."""
    exact(text, 'Top Hit', (10, 65, 180, 125)); exact(text, 'Suggestions', (10, 260, 200, 300))
    icon = pixels(frame, exact=True)[132:196, 54:120].min(axis=2)
    require((icon < 40).mean() > .55 and (icon > 215).mean() > .08, 'X is not the app search Top Hit.')
    return 87, 163


class XImageCreationWorkflow(xc.XCreationWorkflow):
    """One package image -> Photos -> one X draft on the account signed in first."""

    def __init__(self, folder, kernel, store, images, caption, templates, expected_hash, expected_uid, *,
                 transfer_url, package_name, slides, transfer_title=xil.PAGE_TITLE, account=None, **kwargs):
        require(getattr(images, 'count', None) == 1 and list(slides) == ['01.jpg'], 'An X image draft has exactly one image.')
        super().__init__(folder, kernel, store, images, caption, templates, expected_hash, expected_uid,
                         transfer_url=transfer_url, download=package_name, video_bytes=0, account=account, **kwargs)
        self.images, self.package_name, self.slides, self.title = images, package_name, list(slides), transfer_title
        self.record.update(mode='create_x_image_draft', format='x_image', mediaMethod='safari_touch_hold_save_to_photos',
                           imageSha256=list(images.hashes), slides=self.slides, packageName=package_name)
        for key in ('videoSha256', 'videoSeconds', 'downloadName'): self.record.pop(key, None)

    # -- recognition -------------------------------------------------------------
    def transfer_page(self, text):
        return xil.transfer_index(text, self.package_name, self.title)

    def verify_screen(self, role, value, frame, index=None, require_next=False):
        text = value['text']
        if role in IMAGE_ROLES or role in ('x_picker', 'x_picker_selected', 'x_drafts'):
            decision = self.check_prompt(role, value)   # A permission prompt over any screen is decided first.
            if decision is not None: return decision
        if role in ('app_search_entry', 'restored_search'):
            try: return super().verify_screen(role, value, frame, index, require_next)
            except InspectionStopped as stop:
                if not str(stop).startswith('Only the known'): raise
                # Every X run types 'X' last (opening X again), so iOS restores that query with X as its Top Hit
                # (slot 17, 4 Nov). Only its clear button is then pressed, as for a restored Safari query.
                return dict(app='X', restoredQuery='X', target=x_top_hit(frame, text))
        if role == 'x_app_result': return dict(target=x_top_hit(frame, text))
        if role == 'xi_page': return self.transfer_page(text)
        if role == 'xi_caption_copied': return xil.caption_copied(text, self.package_name)
        if role == 'xi_slide': return xil.transfer_slide(frame, text, self.images)
        if role == 'xi_save_menu': return xil.save_menu(frame, text, self.images)
        if role == 'x_composer_image': return xil.composer_image(frame, text, self.images)
        if role in ('x_picker', 'x_picker_selected', 'x_drafts'):
            # The image route's picker and drafts list are the video route's, compared with the image's square crop.
            if role == 'x_picker': return xl.x_picker(frame, text, self.images)
            if role == 'x_picker_selected': return xl.x_picker_selected(frame, text, self.images, self.tile)
            return xl.x_drafts(frame, text, self.images, self.caption)
        if role in ('x_composer_media', 'x_after_add', 'x_video_editor', 'x_reopened', 'x_playing', 'reel_page', 'reel_caption_copied'):
            raise InspectionStopped('Not a screen of the X image route: ' + role)
        return super().verify_screen(role, value, frame, index, require_next)

    def confirmation_compare(self, role):
        if role in IMAGE_ROLES: return compare(role)
        if role == 'x_app_result': return still_compare('app_result')   # The Top Hit row only.
        return super().confirmation_compare(role)

    def observe_settled(self, role, index=None, require_next=False):
        if role not in PRE_SETTLE: return Workflow.observe(self, role, index, require_next)
        if role not in IMAGE_ROLES:
            return super().observe_settled(role, index, require_next)
        self.pause(PRE_SETTLE[role])
        def journal(event):
            self.record['transitionChecks'].append(event); self.save()
        value, frame, _ = wait_for_transition(role, lambda: self.capture(role, index), self.check, self.store.current_evidence,
            journal=journal, monotonic=self.monotonic, pause=self.pause, ready=lambda frame, text: None, compare=compare(role),
            platform=self.PLATFORM, require_recent=False, phone=self.phone)
        return value, frame

    def check_target(self, role, point):
        inner = super().check_target(role, point)
        def target(value, frame):
            x, y = inner(value, frame)
            guard(x, y, role)
            # Safari's menu row reads 'Share...' (or 'Share…'), which the shared label rule (whole word 'share')
            # does not catch: no target lands on any row that starts with Share.
            for row in value['text'].get('lines', []):
                words = row.get('words') or []
                if words and row['text'].casefold().lstrip().startswith('share'):
                    left, top = min(w['x'] for w in words), min(w['y'] for w in words)
                    bottom = max(w['y']+w['height'] for w in words)
                    require(not (left-45 <= x <= 490 and top-12 <= y <= bottom+12), 'Target overlaps Share.')
            if role == 'x_save_sheet':   # Discard moves with the sheet's layout (two rows since 4 Nov): never near it.
                left, top, right, bottom = xl.x_save_sheet(value['text'])['discard']
                require(not (left-40 <= x <= right+40 and top-20 <= y <= bottom+20), 'Target overlaps Discard.')
            return x, y
        return target

    # -- workflow ----------------------------------------------------------------
    def open_app(self, name, visit):
        """X is opened from the app search by its Top Hit icon (its label is unreadable); other apps as before."""
        if name != 'X': return super().open_app(name, visit)
        self.search_app = name
        self.pause(1.0)   # Home's closing animation must end first.
        value, frame = self.observe('home')
        self.step(visit+'-search-X', 'home', point=lambda v, f: centre(home_search(f, v['text'])))
        value, frame = self.observe('app_search_entry')
        try: x_top_hit(frame, value['text']); shown = True   # The restored query is already X.
        except InspectionStopped: shown = False
        if not shown:
            try: empty_search(value['text'], frame); empty = True
            except InspectionStopped: empty = False
            if not empty:
                self.step(visit+'-clear-restored-search', 'restored_search', point=lambda v, f: centre(search_clear(f)))
            self.step(visit+'-query-X', 'search', text='X')
        self.step(visit+'-open-X', 'x_app_result', point=lambda v, f: x_top_hit(f, v['text']))

    def leave_safari_leftovers(self):
        """An earlier stop can leave a preview, the player or the Downloads sheet open; each is closed with its own
        Done or close control, as in the video route, until Safari itself shows."""
        for round_ in range(1, LEFTOVER_ROUNDS + 1):
            entry = self.safari_entry()
            if not any(entry.get(k) for k in ('leftoverPlayer', 'leftoverShareSheet', 'leftoverLinkMenu', 'leftoverPreview', 'leftoverDownloads')):
                return entry
            require(round_ < LEFTOVER_ROUNDS, 'Safari still shows an earlier download after closing it; nothing else was sent.')
            if entry.get('leftoverPlayer'):
                self.close_leftover_player(entry, round_)
            elif entry.get('leftoverLinkMenu'):
                self.tap(f'close-leftover-link-menu-{round_}', 'reel_safari_entry', entry['closeTarget'])
            elif entry.get('leftoverShareSheet'):
                if entry.get('static'):
                    self.direct_click(f'close-leftover-share-sheet-{round_}', 'static_safari_entry', *entry['closeTarget'],
                                      'static_frame_leftover_share_sheet')
                else:
                    self.tap(f'close-leftover-share-sheet-{round_}', 'reel_safari_entry', entry['closeTarget'])
            elif entry.get('static'):
                self.direct_click(f'close-leftover-preview-{round_}', 'static_safari_entry', 450, 85, 'static_frame_leftover_preview')
            elif entry.get('leftoverPreview'):
                self.tap(f'close-leftover-preview-{round_}', 'reel_safari_entry', (450, 85))
            else:
                self.tap(f'close-leftover-downloads-{round_}', 'reel_safari_entry', entry['doneTarget'])
            self.pause(1.5)

    def import_image(self):
        """X feed -> Home -> Safari transfer page -> slide -> Save to Photos once -> Back to caption -> Copy caption -> Home."""
        self.phase('open-transfer')
        self.observe('x_feed')
        self.step('home-from-x-feed', 'x_feed', key='Home')
        self.open_app('Safari', 'transfer')
        entry = self.leave_safari_leftovers()
        if not entry.get('addressSelected'):
            self.tap('focus-safari-address', 'safari_or_blank', (245, 953))
        self.step('enter-transfer-url', 'address_selected', text=self.url)
        # Same Safari address edit session; never a caption.
        self.command('/key/sendkey', purpose='load-transfer-url', fn_key='Enter')
        self.pause(1)
        self.await_transfer_page()
        self.phase('save-image-to-photos')
        self.tap('open-slide-1', 'xi_page', lambda v, f: self.transfer_page(v['text'])['openTarget'])
        # As on the carousel route (17 Oct): a plain tap on the image first, then the press that opens its menu.
        self.tap('focus-transfer-image-1', 'xi_slide', lambda v, f: xil.transfer_slide(f, v['text'], self.images)['holdTarget'])
        self.tap('image-menu-1', 'xi_slide', lambda v, f: xil.transfer_slide(f, v['text'], self.images)['holdTarget'], hold=True)
        def save(value, frame):
            found = xil.save_menu(frame, value['text'], self.images)
            self.record['saveMenu'] = dict(preview=found['preview']['box'], match=found['preview']['mean']); self.save()
            return found['target']
        self.tap('save-photo-1', 'xi_save_menu', save)
        self.tap('back-to-caption', 'xi_slide', lambda v, f: xil.transfer_slide(f, v['text'], self.images)['backTarget'])
        self.phase('copy-caption')
        self.tap('copy-caption', 'xi_page', lambda v, f: self.transfer_page(v['text'])['copyTarget'])
        # A read-only page: Home's leading Tab only moves focus on it.
        self.step('home-from-transfer', 'xi_caption_copied', key='Home')

    def run(self):
        try:
            self.admit()
            self.phase('bind-account')
            self.account_menu('', bind=True)
            self.import_image()
            self.phase('open-x')
            self.open_app('X', 'return')
            self.screen('x_feed')
            self.account_menu('-again', bind=False)
            self.phase('compose-text')
            self.tap('open-composer', 'x_feed', lambda v, f: xl.x_feed(f, v['text'])['composeTarget'])
            self.tap('focus-empty-text', 'x_composer_empty', lambda v, f: xl.x_composer_empty(f, v['text'])['textTarget'])
            focused, _, _ = self.screen('x_composer_focused')
            if not focused['pasteMenu']:
                self.tap('open-paste-menu', 'x_composer_empty', lambda v, f: xl.x_composer_empty(f, v['text'])['pressTarget'], hold=True)
            self.tap('paste-exact-caption', 'x_paste_menu', lambda v, f: xl.x_paste_menu(f, v['text'])['target'])
            self.pause(2)  # Let the OS paste banner leave the header; nothing is repeated.
            self.phase('attach-image')
            self.tap('open-photo-picker', 'x_composer_text', lambda v, f: xl.x_composer_text(f, v['text'])['galleryTarget'])
            def choose(value, frame):
                found = xl.x_picker(frame, value['text'], self.images)
                self.tile = found['tile']; self.record['pickerTile'] = found['tile']
                return found['target']
            self.tap('select-package-image', 'x_picker', choose)
            self.tap('add-package-image', 'x_picker_selected', lambda v, f: xl.x_picker_selected(f, v['text'], self.images, self.tile)['target'])
            self.phase('save-draft')
            self.tap('cancel-to-save-sheet', 'x_composer_image', lambda v, f: xil.composer_image(f, v['text'], self.images)['cancelTarget'])
            self.tap('save-x-draft-once', 'x_save_sheet', lambda v, f: xl.x_save_sheet(v['text'])['target'])
            self.screen('x_feed')
            self.record.update(state='created_unverified', meaning='Package image saved to Photos from the transfer page, text '
                               'pasted, the matching image added and Save to drafts answered on the bound account; an independent '
                               'read-only Drafts check is required.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record


class XImageVerification(XImageCreationWorkflow):
    """Separate owned run on the same account: X Drafts lists exactly one draft with the exact text whose
    thumbnail shows the package image. Read-only: nothing is reopened, saved or removed."""
    history = ReelVerification.history

    def __init__(self, folder, kernel, store, images, caption, templates, expected_hash, expected_uid, *, account, **kwargs):
        require(account and account != xc.PENDING, 'The verifier needs the account bound by creation.')
        super().__init__(folder, kernel, store, images, caption, templates, expected_hash, expected_uid,
                         transfer_url='verification-only', package_name='verification-only', slides=['01.jpg'],
                         account=account, **kwargs)
        self.record.update(mode='verify_x_image_draft', inspectionOnly=True, appRestartVerified=False, finalScreen='unknown',
                           reopened=False)
        for key in ('transferUrl', 'packageName'): self.record.pop(key, None)

    def run(self):
        try:
            self.admit()
            self.phase('verify-saved-x-image-draft')
            self.account_menu('', bind=False)
            self.tap('verify-open-composer', 'x_feed', lambda v, f: xl.x_feed(f, v['text'])['composeTarget'])
            def drafts(value, frame):
                found = xl.x_composer_empty(frame, value['text'])
                require(found['draftsTarget'], 'The X composer shows no Drafts link.')
                return found['draftsTarget']
            self.tap('verify-open-drafts', 'x_composer_empty', drafts)
            found, _, _ = self.screen('x_drafts')
            self.record['draftRow'] = dict(rows=found['rows'], y=found['row']['y'], text=found['row']['text'], match=found['row']['match'])
            self.save()
            self.tap('verify-close-drafts', 'x_drafts', xc.DRAFTS_CANCEL)
            self.tap('verify-close-composer', 'x_composer_empty', xc.COMPOSER_CANCEL_TARGET)
            self.screen('x_feed')
            self.history()
            self.record.update(state='validation_passed', savedDraftVerified=True, finalScreen='x_feed',
                meaning='On the same signed-in account, X Drafts lists exactly one draft with the exact text whose thumbnail '
                        'shows the package image. Not reopened (saving a reopened X draft drops its media), no Post, '
                        'publishing or messaging. Not app-restart or server persistence proof.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record
