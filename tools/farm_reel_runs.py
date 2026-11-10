"""Explicit candidate admission: a saved Reel video copy -> verified Instagram draft.

ImageCreationRuns (below) is the same admission for image packages (X image, TikTok photo).

GET never connects to the phone. A request ID only retrieves its journal, even
after a restart. A new request for the same video and caption is refused once
any earlier attempt could have imported media or saved a draft; nothing resumes.
"""
import io
import json
import sqlite3
import threading
import zipfile

from farm_draft_runs import DraftRuns, ACCOUNT, sha, phone_of, allowed_of, account_of
from farm_drafts import DraftConflict, identifier
from farm_draft_transport import CreationKernel
from farm_draft_workflow import references, atomic_json
from farm_image import CANVAS, SLIDES, ImageReference
from farm_media_transfer import MediaTransferServer, TransferPackage, image_delivery
from farm_observations import ObservationStore
from farm_reel_creation import ReelCreationWorkflow, ReelVerification, COMMITTING
from farm_reel_layout import VideoReference, caption_supported
from farm_video import VideoTransferPackage
from imouse_social_automation import KernelSafetyError

MAX_SECONDS = 15


def reel_content(package):
    """Manifest, caption and the content identity used for duplicate holds."""
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        caption = archive.read('caption.txt').decode('utf-8')
        video = archive.read('video.mp4')
    identity = dict(format=manifest.get('format'), caption=caption, video=sha(video))
    return manifest, caption, sha(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8'))


class ReelCreationRuns(DraftRuns):
    """One saved single-video copy -> one app draft. A subclass names another app's route."""
    action_name = 'create-reel-draft'
    FORMAT, LABEL = 'ig_reel', 'Reel'
    workflow, verifier, reference, committing = ReelCreationWorkflow, ReelVerification, VideoReference, COMMITTING
    caption_supported = staticmethod(caption_supported)
    # False: no fixed account; creation binds the signed-in one and the verifier must see it again.
    PINNED_ACCOUNT = True
    ENABLED_REASON = ('Saves one prepared Reel video as an Instagram draft: Safari downloads it, Files saves it to Photos, the exact '
                      'one-line caption is pasted, Save draft is pressed once, then a separate check finds it once in Reels drafts by the video thumbnail, without reopening it. Start on @'
                      "{account}'s profile. The video stays in Photos and Safari Downloads, and the phone clipboard is replaced.")
    DISABLED_REASON = 'Reel draft creation is disabled. Prepare the isolated C24C candidate first.'
    SUPPORTED_REASON = 'This saved Reel copy fits the candidate.'
    UNSUPPORTED_REASON = ('The Reel candidate needs a saved C24C Instagram Reel copy of 2-15 seconds and one ASCII caption line of up to '
                          '40 characters, with no leading, trailing or double spaces. Nothing is trimmed or truncated.')
    HELD_REASON = ('This exact video and caption already have a Reel request. '
                   'Select its saved result; an uncertain import or Save is never repeated.')
    RUNNING_REASON = 'Creating a C24C Reel draft from the saved video and exact caption. No publishing or messaging.'
    VERIFIED_REASON = 'The Reel draft was saved and found once in Reels drafts with the package video thumbnail. Nothing was published.'
    MEANING = ('Package video imported to Photos, selected, exact caption pasted, Reel draft saved, then '
               'independently found once in Reels drafts with the package video thumbnail (not reopened: saving a '
               'reopened draft dropped the video on X, 23 Oct). No publication or app-restart persistence claim.')

    def capability(self):
        account = (account_of(self.config) if self.config else ACCOUNT) if self.PINNED_ACCOUNT else None
        return dict(version=1, storeId=self.store_id, enabled=self.config is not None,
            device=phone_of(self.config).board if self.config else 'C24C', account=account,
            accountPolicy='fixed' if self.PINNED_ACCOUNT else 'first_signed_in', format=self.FORMAT, candidateOnly=True, integratedLiveValidated=False, publishing=False, messaging=False,
            desktopControl=False, automaticResume=False,
            reason=self.ENABLED_REASON.format(account=account) if self.config else self.DISABLED_REASON)

    # Hooks an image subclass replaces (ImageCreationRuns below); video behaviour is unchanged.
    content = staticmethod(reel_content)
    MEDIA = 'video'

    def supports(self, package):
        manifest, caption, _ = reel_content(package)
        video = manifest.get('video') or {}
        seconds = video.get('seconds')
        return (manifest.get('format') == self.FORMAT and manifest.get('deviceId') == (phone_of(self.config).board if self.config else 'C24C') and self.caption_supported(caption)
                and (video.get('width'), video.get('height')) == (720, 1280)
                and type(seconds) in (int, float) and 2 <= seconds <= MAX_SECONDS)

    def content_reason(self, supported):
        return self.SUPPORTED_REASON if supported else self.UNSUPPORTED_REASON

    @classmethod
    def retry_allowed(cls, value):
        """True only when no command that could import media or save a draft was dispatched."""
        workflow = value.get('workflow') or {}
        return bool(value.get('terminal') and value.get('state') == 'review_required'
                    and workflow.get('source') == 'candidate_phone_workflow'
                    and workflow.get('cleanup') in ('confirmed', 'not_needed') and workflow.get('evidenceExport') == 'confirmed'
                    and not any(c.get('state') != 'not_sent' and c.get('purpose', '').startswith(cls.committing)
                                for c in workflow.get('commands', []))
                    and not workflow.get('verification'))

    def holds(self, content):
        with self.connect() as db: rows = db.execute('SELECT id,package FROM runs ORDER BY rowid').fetchall()
        return [key for key, package in rows if self.content(package)[2] == content and not self.retry_allowed(self.get(key))]

    def eligibility(self, draft_id, revision):
        package = self.drafts.export(identifier(draft_id), revision)
        supported = self.supports(package)
        held = self.holds(self.content(package)[2])
        result = dict(**self.capability(), eligible=self.config is not None and supported and not held,
                      supportedContent=supported, draftId=draft_id, revision=revision, packageSha256=sha(package),
                      contentReason=self.content_reason(supported))
        if held:
            result.update(previousRunId=held[-1], contentReason=self.HELD_REASON)
        return result

    def start(self, spec):
        spec = self.validate_request(spec)
        if spec['store_id'] != self.store_id: raise DraftConflict('The candidate data store changed. No new run was admitted.')
        with self.lock:
            try: previous, _, _ = self.row(spec['id'])
            except KeyError: previous = None
            if previous is not None:
                if previous != spec: raise DraftConflict('This request ID belongs to another video or revision.')
                return self.get(spec['id'])
            if not self.config: raise KernelSafetyError(self.LABEL + ' draft creation is disabled.')
            self.jobs.assert_available()
            package = self.drafts.export(spec['draft_id'], spec['revision'])
            if not self.supports(package): raise ValueError('Saved ' + self.MEDIA + ' is outside the ' + self.LABEL + ' draft candidate.')
            _, caption, content = self.content(package)
            if self.holds(content):
                raise DraftConflict('This exact ' + self.MEDIA + ' and caption already have a ' + self.LABEL + ' request. Retrieve its result; '
                                    'do not duplicate an uncertain import or Save.')
            # Reserve the ID before any worker can send input. An orphaned
            # admission is review-only, never an instruction to start it again.
            with self.connect() as db:
                try: db.execute('INSERT INTO runs VALUES (?,?,?,?)', (spec['id'], json.dumps(spec), package, sha(package)))
                except sqlite3.IntegrityError: raise DraftConflict('This request was admitted concurrently; retrieve its saved result.')
            folder = self.folder / spec['id']; folder.mkdir(exist_ok=False)
            def run(cancelled):
                result = self.execute(folder, None, caption, sha(package), cancelled)
                return dict(recordSha256=sha((folder / 'record.json').read_bytes()), state=result['state'])
            self.jobs.submit(spec['id'], self.action_name, spec, run)
            return self.get(spec['id'])

    def get(self, run_id):
        result = super().get(run_id)
        # Same meaning as the carousel field the native window already reads.
        result['retryBeforeImportAllowed'] = self.retry_allowed(result)
        result['continueImportedAllowed'] = False
        verified = (result.get('workflow') or {}).get('verification')
        if result['terminal'] and isinstance(verified, dict) and 'finalInput' in verified:
            workflow = dict(result['workflow'])
            workflow['creationFinalInput'] = workflow.get('finalInput'); workflow['finalInput'] = verified['finalInput']
            result['workflow'] = workflow
        if not result['terminal']:
            result['reason'] = self.RUNNING_REASON
        if result['savedDraftVerified']:
            result['reason'] = self.VERIFIED_REASON
        return result

    # Media hooks used by execute(): one saved video served as video.mp4.
    def transfer_package(self, package):
        return VideoTransferPackage(package, phone_of(self.config).board)

    def media_reference(self, parsed):
        return self.reference(parsed.video)

    def workflow_media(self, parsed):
        """Media keywords for the creation workflow, beside transfer_url and the account arguments."""
        return dict(download=parsed.download_name, video_bytes=len(parsed.video))

    def delivery(self, delivered, parsed, *, stopped):
        """(mediaDelivery record, whether the phone requested the media at all)."""
        requests = [e for e in delivered if e.get('route') == 'video.mp4' and e.get('status') in (200, 206)]
        return dict(stopped=stopped, events=delivered, videoRequests=len(requests), photosSaveProvenByHttp=False), bool(requests)

    def execute(self, folder, assets, caption, package_hash, cancelled):
        spec, package, digest = self.row(folder.name)
        if digest != package_hash: raise ValueError(self.LABEL + ' source package changed.')
        parsed = self.transfer_package(package)
        video = self.media_reference(parsed)  # Decoded locally before any transport or lease.
        delivered = []
        server = MediaTransferServer(parsed, self.config['mediaBind'], self.config['mediaPort'], self.config['mediaClient'],
                                     minutes=15, on_event=delivered.append)
        stopped = threading.Event()
        def serve():
            while not stopped.is_set() and server.clock() < server.deadline: server.handle_request()
        worker = threading.Thread(target=serve, daemon=True)
        arguments = dict(account=account_of(self.config) if self.PINNED_ACCOUNT else None, package_hash=package_hash,
                         cancelled=cancelled, allowed=allowed_of(self.config))
        try:
            worker.start()
            kernel = CreationKernel(self.config['api'], phone=phone_of(self.config))
            store = ObservationStore(folder / 'observations.sqlite3', retained_limit=160)
            result = self.workflow(folder, kernel, store, video, caption, references(), self.config['kernelSha256'],
                self.config['expectedUid'], transfer_url=server.url, **self.workflow_media(parsed), **arguments).run()
        finally:
            stopped.set(); server.close_clients()
            if worker.ident is not None: worker.join(timeout=4)
            server.server_close()
        result['mediaDelivery'], requested = self.delivery(delivered, parsed, stopped=not worker.is_alive())
        if (worker.is_alive() or result['state'] != 'created_unverified' or result.get('cleanup') != 'confirmed'
                or result.get('evidenceExport') != 'confirmed' or not requested):
            result.update(state='review_required', savedDraftVerified=False,
                          error=result.get('error') or 'Creation or media cleanup is unconfirmed; no automatic retry.')
        else:
            child = folder / 'verification'; child.mkdir(exist_ok=False)
            checking = arguments if self.PINNED_ACCOUNT else dict(arguments, account=result.get('account'))
            verified = self.verifier(child, kernel, store, video, caption, references(), self.config['kernelSha256'],
                                        self.config['expectedUid'], **checking).run()
            result['creationState'] = 'created_unverified'; result['verification'] = verified
            result['actions'] += [{**a, 'label': 'verification-'+a['label']} for a in verified['actions']]
            result['observations'] += [{**e, 'frame': 'verification/'+e['frame']} for e in verified['observations']]
            result.update(state=verified['state'], savedDraftVerified=verified['savedDraftVerified'],
                          cleanup=verified['cleanup'], evidenceExport=verified.get('evidenceExport', 'failed'),
                          createdDraftVerified=verified['savedDraftVerified'],
                          meaning=self.MEANING)
            if verified.get('error'): result['error'] = verified['error']
        atomic_json(folder / 'record.json', result)
        return result


def image_content(package):
    """Manifest, caption and the content identity (format, caption, ordered image hashes) of an image package."""
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        caption = archive.read('caption.txt').decode('utf-8')
        assets = manifest.get('assets')
        if not isinstance(assets, list) or any(not isinstance(a, dict) or not isinstance(a.get('file'), str) for a in assets):
            raise ValueError('Image package manifest has no ordered image list.')
        images = [sha(archive.read(a['file'])) for a in assets]
    identity = dict(format=manifest.get('format'), caption=caption, images=images)
    return manifest, caption, sha(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8'))


class ImageCreationRuns(ReelCreationRuns):
    """One saved image package (farm_image: x_image, tt_photo) -> one app draft; the same durable rules as video.

    A lane subclass names FORMAT, LABEL, action_name, workflow, verifier, committing, caption_supported and
    its reasons. `drafts` is a farm_image.ImageDrafts. The workflow and verifier are called as
        workflow(folder, kernel, store, images, caption, references(), kernelSha256, expectedUid,
                 transfer_url=..., transfer_title=..., package_name=..., slides=[...'01.jpg'...],
                 account=..., package_hash=..., cancelled=..., allowed=...)
        verifier(folder, kernel, store, images, caption, references(), kernelSha256, expectedUid,
                 account=..., package_hash=..., cancelled=..., allowed=...)
    with `images` a farm_image.ImageReference of the package slides in order. The transfer page is the
    carousel layout: 'Open slide N of M', then per slide 'Slide N of M', touch and hold the image, Save to
    Photos, 'Next slide' / 'Back to caption'. The verifier runs only when every image was requested over HTTP.
    """
    FORMAT, LABEL, MEDIA = None, 'Image', 'image set'
    workflow = verifier = committing = None
    PINNED_ACCOUNT = False

    reference = ImageReference
    content = staticmethod(image_content)
    # Generic wording; a lane replaces each with its app's route.
    ENABLED_REASON = 'Saves one prepared image set as a draft. Nothing is posted or messaged.'
    DISABLED_REASON = 'Image draft creation is disabled. Prepare the isolated window for this phone first.'
    SUPPORTED_REASON = 'This saved image set fits the candidate.'
    UNSUPPORTED_REASON = 'This saved image set does not fit the candidate. Nothing is cropped, trimmed or truncated.'
    HELD_REASON = ('These exact images and caption already have a request. '
                   'Select its saved result; an uncertain Photos save or draft save is never repeated.')
    RUNNING_REASON = 'Creating a draft from the saved images and exact caption. No posting or messaging.'
    VERIFIED_REASON = 'The draft was saved and found once with the package images. Nothing was posted.'
    MEANING = ('Package images saved to Photos from the transfer page, selected in order, exact caption pasted and the draft '
               'saved once, then independently found once with the package images. No post or app-restart claim.')

    def supports(self, package):
        try: manifest, caption, _ = image_content(package)
        except (ValueError, KeyError, zipfile.BadZipFile): return False
        if self.FORMAT not in SLIDES: return False
        low, high = SLIDES[self.FORMAT]
        assets = manifest['assets']
        board = phone_of(self.config).board if self.config else 'C24C'
        return (manifest.get('format') == self.FORMAT and manifest.get('deviceId') == board
                and manifest.get('published') is False and manifest.get('savedInApp') is False
                and low <= len(assets) <= high and self.caption_supported(caption)
                and all((a.get('width'), a.get('height')) == CANVAS[self.FORMAT][0] for a in assets))

    # Media hooks: the package's ordered images, each saved to Photos from its own slide page.
    def transfer_package(self, package):
        return TransferPackage(package, phone_of(self.config).board)

    def media_reference(self, parsed):
        return self.reference(list(parsed.images.values()))

    def workflow_media(self, parsed):
        return dict(transfer_title=parsed.title, package_name=parsed.download_name, slides=list(parsed.images))

    def delivery(self, delivered, parsed, *, stopped):
        record = image_delivery(delivered, parsed.images)
        return dict(stopped=stopped, events=delivered, **record), record['everyImageDelivered']
