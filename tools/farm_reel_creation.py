"""Bounded C24C Instagram Reel draft creation, then an independent verifier.

Draft only. The inputs are reviewed taps, one long press each for the download
link and Paste, Home, and one bounded URL entry. Unknown outcomes stop. A Save,
download, Photos save or caption entry is never repeated; a stopped run needs
review. Nothing taps Share, publishes or messages. The verifier is a separate
owned run that starts from the exact profile and finishes on Reels drafts.
"""
from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import require
from farm_draft_creation import CreationWorkflow
from farm_draft_transport import allowed_tap
from farm_live_verification import idle
from farm_observations import classify
from farm_transitions import wait_for_transition
import farm_reel_layout as reel
from imouse_social_automation import LIVE_TEST_DEVICE_ID

# Read-only waits for screens that are known to animate in. They delay the
# first capture only; a capture never repeats an action.
PRE_SETTLE = {'reel_safari_entry': .6, 'reel_page': .6, 'reel_caption_copied': .4, 'link_menu': .6, 'page_menu': .6,
              'downloads': .6, 'quicklook': .8, 'quicklook_controls': .4, 'share_sheet': .8, 'reel_create': .4,
              'reel_picker': .6, 'reel_selected': .6, 'reel_editor': 1.0, 'reel_details_blank': .6, 'reel_caption_blank': .6,
              'reel_paste_menu': .4, 'reel_caption_pasted': .2, 'reel_details': .6, 'reel_saved_picker': 1.0,
              'reels_drafts': .8, 'reel_reopened': .8, 'reel_preview': .8}
# A callout and a playing Preview are captured once; every other screen needs two
# agreeing fresh frames (the Preview check itself requires two different times).
SETTLED = set(PRE_SETTLE) - {'reel_paste_menu', 'reel_preview'}
# Purposes after which a new request for the same content could duplicate media
# or a draft. Absence of all of them means no phone import or draft can exist.
COMMITTING = ('download-linked-file', 'save-video-to-photos', 'select-package-video', 'open-reel-editor',
              'paste-exact-caption', 'save-reel-draft-once')


class ReelCreationWorkflow(CreationWorkflow):
    def __init__(self, folder, kernel, store, video, caption, templates, expected_hash, expected_uid, *,
                 transfer_url, download, video_bytes, **kwargs):
        require(reel.caption_supported(caption), 'Reel creation supports one visible ASCII caption line up to 40 characters.')
        super().__init__(folder, kernel, store, [], caption, templates, expected_hash, expected_uid,
                         transfer_url=transfer_url, transfer_title='Reel draft', **kwargs)
        self.video, self.download, self.video_bytes = video, download, video_bytes
        self.cell = None
        self.record.update(mode='create_reel_draft', format='ig_reel', videoSha256=video.sha256,
                           videoSeconds=video.seconds, downloadName=download, mediaMethod='safari_download_save_video',
                           captionMethod='verified_safari_copy_and_instagram_paste', draftsCount=dict(before=None, after=None))

    # -- recognition -------------------------------------------------------------
    def verify_screen(self, role, value, frame, index=None, require_next=False):
        text = value['text']
        if role == 'reel_safari_entry':
            try: return self.verify_screen('safari', value, frame)
            except InspectionStopped: return reel.leftover_preview(frame, text)
        if role == 'reel_page': return reel.reel_transfer_page(text, self.download)
        if role == 'reel_caption_copied':
            return {**reel.reel_transfer_page(text, self.download), **reel.caption_copied(text)}
        if role == 'link_menu': return reel.link_menu(text)
        if role == 'download_ready':
            super().verify_screen('safari', value, frame)
            return reel.download_badge(frame)
        if role == 'page_menu': return reel.page_menu(text)
        if role == 'downloads': return reel.downloads_list(text, self.download, self.video_bytes)
        if role in ('quicklook', 'quicklook_controls'):
            result = reel.quicklook(frame, text, self.download, self.video)
            if role == 'quicklook_controls': require(result['controls'], 'The preview controls are not visible.')
            return result
        if role == 'share_sheet': return reel.share_sheet(text, self.download)
        if role == 'reel_create': return reel.reel_create(frame, text)
        if role == 'reel_picker': return reel.reel_picker(frame, text, self.video)
        if role == 'reel_selected': return reel.reel_selected(frame, text, self.video, self.cell)
        if role == 'reel_editor': return reel.reel_editor(frame, text, self.video)
        if role == 'reel_details_blank': return reel.reel_details(frame, text, self.video)
        if role == 'reel_caption_blank': return reel.reel_caption(frame, text, blank=True)
        if role == 'reel_paste_menu': return reel.reel_paste_menu(frame, text)
        if role == 'reel_caption_pasted': return reel.reel_caption(frame, text, blank=False)
        if role == 'reel_details': return reel.reel_details(frame, text, self.video, self.caption)
        if role == 'reel_saved_picker': return reel.reel_saved_picker(frame, text)
        if role == 'reels_drafts': return reel.reels_drafts(frame, text, self.video)
        if role == 'reel_reopened': return reel.reel_details(frame, text, self.video, self.caption, reopened=True)
        if role == 'reel_preview': return reel.reel_preview(frame, text, self.video, self.account, self.caption)
        return super().verify_screen(role, value, frame, index, require_next)

    def observe(self, role, index=None, require_next=False):
        if role not in PRE_SETTLE: return super().observe(role, index, require_next)
        self.pause(PRE_SETTLE[role])
        if role not in SETTLED: return self.capture(role, index)
        def journal(event):
            self.record['transitionChecks'].append(event); self.save()
        value, frame, _ = wait_for_transition(role, lambda: self.capture(role, index), self.check, self.store.current_evidence,
            journal=journal, monotonic=self.monotonic, pause=self.pause,
            ready=lambda frame, text: None, compare=reel.reel_compare(role))
        return value, frame

    def check_target(self, role, point):
        """Every phone tap stays inside the app area and away from publish labels."""
        def target(value, frame):
            x, y = point(value, frame) if callable(point) else point
            allowed_tap(value['text'], x, y, 'reel:' + role, frame=frame)
            return x, y
        return target

    def tap(self, label, role, point, *, hold=False):
        self.step(label, role, point=self.check_target(role, point), hold=hold)

    def screen(self, role):
        value, frame = self.observe(role)
        return self.verify_screen(role, value, frame), value, frame

    # -- workflow ----------------------------------------------------------------
    def admit(self):
        self.identity = self.runtime()
        require(idle(self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)), 'C24C is not free; no takeover is allowed.')
        raw, _ = self.kernel.shot('C24C')
        initial = classify(self.store.ocr.read(raw), dict(platform='instagram', account=self.account, caption=self.caption), raw)
        require(initial['screen'] == 'profile' and initial['accountStatus'] == 'exact_text_match',
                'Start on the authorized Instagram profile. No input was sent.')
        self.record['cleanup'] = 'unconfirmed'; self.save(); self.owned.acquire()
        self.command('/mouse/reset', purpose='initial_pointer_reset')

    def transfer_page(self, text):
        return reel.reel_transfer_page(text, self.download)

    def import_video(self):
        """Profile -> Safari package page -> copy caption -> download -> Files -> Save Video -> Home."""
        self.phase('open-transfer')
        self.observe('profile')
        self.step('home-from-profile', 'profile', key='Home')
        self.open_app('Safari', 'transfer')
        entry, _, _ = self.screen('reel_safari_entry')
        if entry.get('leftoverPreview'):
            # A previous run leaves Safari on a read-only Files preview. Done
            # only closes it; the earlier media is not touched or replayed.
            self.tap('close-leftover-preview', 'reel_safari_entry', (450, 85))
        self.tap('focus-safari-address', 'safari', (245, 953))
        self.step('enter-transfer-url', 'address_selected', text=self.url)
        # Same Safari address edit session; never a caption.
        self.command('/key/sendkey', purpose='load-transfer-url', fn_key='Enter')
        self.pause(1)
        self.phase('copy-caption')
        self.tap('copy-caption', 'reel_page', lambda v, f: self.transfer_page(v['text'])['copyTarget'])
        self.phase('download-video')
        self.tap('hold-download-link', 'reel_caption_copied',
                 lambda v, f: self.transfer_page(v['text'])['downloadTarget'], hold=True)
        self.tap('download-linked-file', 'link_menu', lambda v, f: reel.link_menu(v['text'])['target'])
        self.tap('open-safari-menu', 'download_ready', (91, 955))
        self.tap('open-downloads', 'page_menu', lambda v, f: reel.page_menu(v['text'])['target'])
        self.tap('open-downloaded-video', 'downloads',
                 lambda v, f: reel.downloads_list(v['text'], self.download, self.video_bytes)['target'])
        self.phase('save-video-to-photos')
        preview, _, _ = self.screen('quicklook')
        if not preview['controls']:
            self.tap('reveal-preview-controls', 'quicklook', (250, 300))
        self.tap('open-share-sheet', 'quicklook_controls', (40, 1012))
        self.tap('save-video-to-photos', 'share_sheet', lambda v, f: reel.share_sheet(v['text'], self.download)['target'])
        # The Files preview is not a text field, so Home's leading Tab is harmless here.
        self.step('home-from-saved-video', 'quicklook', key='Home')

    def run(self):
        try:
            self.admit()
            self.import_video()
            self.phase('open-instagram')
            self.open_app('Instagram', 'return')
            self.account_profile('verify-returned-account')
            self.phase('select-reel-media')
            self.tap('open-create', 'profile', lambda v, f: self.target('profile_create', v, f))
            self.tap('choose-reel', 'reel_create', lambda v, f: reel.reel_create(f, v['text'])['target'])
            def choose(value, frame):
                # The tapped cell, the later selection check and the Drafts count
                # all come from this one decision frame.
                found = reel.reel_picker(frame, value['text'], self.video)
                self.cell = found['cell']; self.record['pickerCell'] = found['cell']
                self.record['draftsCount']['before'] = found['draftsCount']
                return found['target']
            self.tap('select-package-video', 'reel_picker', choose)
            self.tap('open-reel-editor', 'reel_selected', (444, 993))
            self.tap('open-reel-details', 'reel_editor', (444, 993))
            self.phase('caption-and-save')
            self.tap('focus-empty-caption', 'reel_details_blank', lambda v, f: reel.reel_details(f, v['text'], self.video)['captionTarget'])
            self.tap('open-paste-menu', 'reel_caption_blank', (80, 142), hold=True)
            self.tap('paste-exact-caption', 'reel_paste_menu', lambda v, f: reel.reel_paste_menu(f, v['text'])['target'])
            self.pause(2)  # Let the OS paste banner leave the Caption header; nothing is repeated.
            # OK only closes the editor. The exact caption is required on details,
            # where no caret can corrupt OCR, before the single Save draft.
            self.tap('close-caption-editor', 'reel_caption_pasted', (461, 84))
            self.tap('save-reel-draft-once', 'reel_details', lambda v, f: reel.reel_details(f, v['text'], self.video, self.caption)['saveTarget'])
            saved, _, _ = self.screen('reel_saved_picker')
            before, after = self.record['draftsCount']['before'], saved['draftsCount']
            self.record['draftsCount']['after'] = after; self.save()
            if before is not None and after is not None:
                require(after == before+1, 'The Reels drafts count did not increase by one; review before any further input.')
            self.tap('leave-reel-picker', 'reel_saved_picker', (42, 98))
            self.observe('profile')
            self.record.update(state='created_unverified', meaning='Package video saved to Photos, selected, exact caption '
                               'pasted and Save draft answered; an independent reopen check is required.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record


class ReelVerification(ReelCreationWorkflow):
    """Separate owned run: reopen the unique saved Reel, check caption and playback, keep it."""

    def __init__(self, folder, kernel, store, video, caption, templates, expected_hash, expected_uid, **kwargs):
        super().__init__(folder, kernel, store, video, caption, templates, expected_hash, expected_uid,
                         transfer_url='verification-only', download='verification-only', video_bytes=0, **kwargs)
        self.record.update(mode='verify_reel_draft', inspectionOnly=False, appRestartVerified=False, finalScreen='unknown')
        for key in ('transferUrl', 'downloadName'): self.record.pop(key, None)

    def playback(self):
        """Two fresh Preview frames that match the package video at different times."""
        first, _, _ = self.screen('reel_preview')
        self.pause(.8)
        second, _, _ = self.screen('reel_preview')
        indices = [first['media']['index'], second['media']['index']]
        require(indices[0] != indices[1], 'Preview did not visibly play the package video.')
        self.record['playback'] = dict(sampledFrameIndices=indices, sampleFps=reel.SAMPLE_FPS, byteIdentityVerified=False)

    def history(self):
        """Every stored capture in the run was recognized for its role, in one context."""
        observed = [e for e in self.record['observations'] if e.get('state') == 'observed']
        timeline = self.store.interval(observed[0]['observationId'], observed[-1]['observationId'])
        known = {e['observationId']: e for e in observed}
        blockers, previous, context = [], None, None
        for value, frame in timeline:
            entry = known.get(value['id'])
            if frame is None or entry is None or 'screenCheck' not in entry:
                blockers.append('An observation is unrecognized, pruned or outside this run.')
                continue
            evidence = value.get('frameEvidence', {})
            current = (value.get('observerSession'), value.get('receiverPid'), value.get('inputGeneration'),
                       evidence.get('session'), value.get('ownershipEvidence', {}).get('runId'))
            context = context or current
            if current != context or any(item is None for item in current): blockers.append('Observation context changed.')
            start, sequence = value.get('requestedAt'), evidence.get('sequence')
            if previous and (start - previous[0] > 15 or sequence <= previous[1]):
                blockers.append('Observation history has a gap or repeated frame.')
            previous = (value.get('completedAt'), sequence)
        result = dict(status='consistent_sampled_history' if not blockers else 'incomplete',
                      blockers=list(dict.fromkeys(blockers)), observations=len(timeline), continuousRecording=False)
        self.record['accountHistory'] = result
        require(not blockers, 'Sampled history is incomplete: ' + '; '.join(result['blockers']))

    def run(self):
        try:
            self.admit()
            self.phase('verify-saved-reel')
            self.observe('profile')
            self.tap('verify-open-create', 'profile', lambda v, f: self.target('profile_create', v, f))
            self.tap('verify-choose-reel', 'reel_create', lambda v, f: reel.reel_create(f, v['text'])['target'])
            self.tap('verify-open-drafts', 'reel_saved_picker', lambda v, f: reel.reel_saved_picker(f, v['text'])['chipTarget'])
            self.tap('verify-open-saved-reel', 'reels_drafts', lambda v, f: reel.reels_drafts(f, v['text'], self.video)['target'])
            self.tap('verify-open-preview', 'reel_reopened',
                     lambda v, f: reel.reel_details(f, v['text'], self.video, self.caption, reopened=True)['previewTarget'])
            self.playback()
            # The same Save draft exit the supervised check used; it keeps the
            # unchanged reopened draft. An uncertain answer is never repeated.
            self.tap('verify-keep-reel-once', 'reel_preview',
                     lambda v, f: reel.reel_preview(f, v['text'], self.video, self.account, self.caption)['saveTarget'])
            self.screen('reels_drafts')
            self.history()
            self.record.update(state='validation_passed', savedDraftVerified=True, finalScreen='reels_drafts',
                meaning='The unique matching Reel draft reopened with the exact caption and account, played the package video '
                        'and remained in Reels drafts. No Share, publishing or messaging. Not app-restart or server persistence proof.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record
