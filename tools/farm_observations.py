"""Read-only local frame observations. No input, publishing or messaging API."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager

from PIL import Image
from farm_frame_evidence import MAX_AGE_MS, delivery_evidence, workflow_review
from farm_screen_layout import NEXT_LABEL_BOX, NEXT_LABEL_SCALE, NEXT_CROP_SIZE, create_menu_controls, editor_controls, next_crop, next_label, picker_controls


def image_size(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 16 * 1024 * 1024:
        raise ValueError('Frame must be nonempty and at most 16 MiB.')
    with Image.open(io.BytesIO(raw)) as image:
        if image.width < 100 or image.height < 100 or image.width > 4096 or image.height > 4096:
            raise ValueError('Unsupported frame dimensions.')
        image.load()
        return image.size


class WindowsOcr:
    def _read_file(self, image_path, size, control_path=None):
        binary = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        if not binary.is_file():
            raise ValueError('Windows image-text recognition is unavailable on this machine.')
        script = Path(__file__).with_name('Read-FarmImageText.ps1')
        image_digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        command = [str(binary), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                   '-File', str(script), '-ImagePath', str(image_path)]
        if control_path is not None:
            control_digest = hashlib.sha256(control_path.read_bytes()).hexdigest()
            command.extend(['-ControlImagePath', str(control_path)])
        try:
            result = subprocess.run(command, capture_output=True, timeout=25,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired as exc:
            raise ValueError('Image-text recognition timed out; no screen state was verified.') from exc
        if result.returncode:
            raise ValueError('Windows OCR failed. Check that the English OCR language is installed; no screen state was verified.')
        value = json.loads(result.stdout.decode('utf-8-sig'))
        if value.get('imageSha256') != image_digest:
            raise ValueError('OCR process did not read the exact submitted image.')
        if (value.get('width'), value.get('height')) != size:
            raise ValueError('OCR result dimensions differ from the source frame.')
        if control_path is not None:
            detail = value.get('control', {})
            if not isinstance(detail, dict) or detail.get('imageSha256') != control_digest:
                raise ValueError('OCR process did not read the exact submitted control image.')
            if (detail.get('width'), detail.get('height')) != NEXT_CROP_SIZE:
                raise ValueError('OCR control dimensions differ from the submitted crop.')
        return value

    def read(self, raw):
        size = image_size(raw)
        with tempfile.TemporaryDirectory(prefix='farm-observation-') as directory:
            image_path = Path(directory) / 'frame.png'
            with Image.open(io.BytesIO(raw)) as image:
                image.convert('RGB').save(image_path)
            path = None
            if size == (500, 1080):
                crop, source_pixels = next_crop(raw)
                path = Path(directory) / 'next-control.png'; path.write_bytes(crop)
            # One WinRT engine/process reads both exact images. The optional crop
            # is used only for a recognized editor missing Next; it never repairs
            # account/caption text or supplies an independent screen decision.
            value = self._read_file(image_path, size, path)
            unrotate(value)
            detail = value.pop('control', None)
            value['frameSha256'] = hashlib.sha256(raw).hexdigest()
            if size == (500, 1080) and editor_controls(raw, value) and not next_label(raw, value):
                value['controlOcr'] = {'next': {**detail, 'sourceFrameSha256': value['frameSha256'],
                    'sourcePixelsSha256': source_pixels, 'bounds': list(NEXT_LABEL_BOX), 'scale': NEXT_LABEL_SCALE}}
            return value


def unrotate(value):
    """Windows OCR deskews a page it finds tilted and reports word boxes in that rotated frame. On
    YouTube's Drafts list (slot 16, 26 Oct, TextAngle 5.1) every word came back up to 40 px off. Each
    word's centre is rotated back about the image centre by the reported angle, its size kept; this
    matched an unrotated read within about 5 px. A level page is left unchanged."""
    angle = value.get('textAngle') or 0
    if abs(angle) < .5: return
    import math
    theta = math.radians(angle); cos, sin = math.cos(theta), math.sin(theta)
    cx, cy = value['width'] / 2, value['height'] / 2
    for line in value.get('lines', []):
        for word in line.get('words', []):
            x, y = word['x'] + word['width'] / 2 - cx, word['y'] + word['height'] / 2 - cy
            px, py = cx + x * cos - y * sin, cy + x * sin + y * cos
            word['x'] = max(0, min(value['width'] - word['width'], round(px - word['width'] / 2)))
            word['y'] = max(0, min(value['height'] - word['height'], round(py - word['height'] / 2)))
    value['unrotated'] = angle


PLATFORMS = ('instagram', 'tiktok', 'x', 'youtube')


def expectations(request, board='C24C'):
    """board is the window's own phone; the server's single-phone tools keep the C24C default."""
    if request.get('device_id') != board or request.get('platform') not in PLATFORMS:
        raise ValueError(f'Select {board} and a supported platform.')
    account = request.get('account', '').removeprefix('@') if isinstance(request.get('account', ''), str) else ''
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,50}', account):
        raise ValueError('Enter the expected signed-in handle; a display name is not enough.')
    caption = request.get('caption', '')
    if not isinstance(caption, str) or len(caption) > 2200 or any(ord(c) < 32 and c not in '\n\t' for c in caption):
        raise ValueError('Expected text must contain at most 2,200 characters and no control codes.')
    return {'device_id': board, 'platform': request['platform'], 'account': account, 'caption': caption}


def classify(text, expected, frame=None):
    """Conservative English UI patterns; matches are observations, not app authenticity."""
    width, height = text['width'], text['height']
    rows = []
    for line in text.get('lines', []):
        words = line.get('words', [])
        if not words: continue
        if any(not all(isinstance(w.get(k), (int, float)) for k in ('x', 'y', 'width', 'height')) for w in words):
            raise ValueError('OCR geometry missing.')
        if any(not all(math.isfinite(w[k]) for k in ('x', 'y', 'width', 'height'))
               or w['x'] < 0 or w['y'] < 0 or w['width'] <= 0 or w['height'] <= 0
               or w['x'] + w['width'] > width or w['y'] + w['height'] > height for w in words):
            raise ValueError('OCR geometry is outside the frame.')
        top = min(w['y'] for w in words)
        rows.append((str(line['text']), top / height))
    normalized = [' '.join(s.casefold().split()) for s, _ in rows]
    lower = [n for n, (_, y) in zip(normalized, rows) if y > .65]
    upper = [n for n, (_, y) in zip(normalized, rows) if y < .45]
    has = lambda phrase: any(phrase in n for n in normalized)
    def anchor(phrase, low, high, icon=False):
        return any(low <= y <= high and (n == phrase or (icon and n in (f'o {phrase}', f'0 {phrase}', f'# {phrase}', f'q {phrase}')))
                   for n, (_, y) in zip(normalized, rows))
    state, app, layout, layout_evidence = 'unknown', None, None, None
    # System interruptions always override an app pattern behind the overlay.
    if has("don't allow") and 'allow' in normalized:
        state = 'permission_prompt'
    elif has('new shared album') and has('participants'):
        state = 'sharing_dialog'
    elif has('airdrop') and has('save video') and has('save to files'):
        state = 'share_sheet'
    elif all(sum(n == label and lo <= y <= hi for n, (_, y) in zip(normalized, rows)) == 1
             for label, lo, hi in (('if you go back now, your edits will be discarded.', .71, .78),
                                   ('discard', .78, .83), ('save draft', .83, .89), ('cancel', .90, .96))):
        state, app = 'save_prompt', 'instagram'
    elif frame is not None and create_menu_controls(frame, text):
        # A sheet wins over background profile/account labels. Its Post control
        # chooses the content format; it never establishes a publishing target.
        state, app, layout = 'create_menu', 'instagram', 'post_create_sheet'
        layout_evidence = create_menu_controls(frame, text)
    elif (anchor('caption', .04, .15) and anchor('hashtags', .18, .35, True)
          and anchor('poll', .18, .35) and anchor('prompt', .18, .35)
          and anchor('save draft', .88, .98) and anchor('share', .88, .98)
          and anchor('original audio', .65, .85)):
        # This sheet covers the details screen; its background Save/Share buttons cannot be used.
        state, app = 'caption_editor', 'instagram'
    elif 'search' in lower and sum(name in upper for name in ('instagram', 'tiktok', 'youtube')) >= 3:
        state = 'home'
    elif has('following') and has('follower') and has('likes') and 'profile' in lower:
        state, app = 'profile', 'tiktok'
    elif has('edit profile') and has('share profile') and has('posts') and has('following'):
        state, app = 'profile', 'instagram'
    elif has('download grok') and has('communities') and has('following'):
        state, app = 'account_menu', 'x'
    elif has('view channel') and has('your videos') and has('youtube premium'):
        state, app = 'profile', 'youtube'
    elif has('uninstalling tiktok') and has('discard all drafts'):
        state, app = 'draft_library', 'tiktok'
    elif has('removing the youtube app') and has('draft videos created'):
        state, app = 'draft_library', 'youtube'
    elif has('reels drafts') and has('uninstall the instagram app'):
        state, app = 'draft_library', 'instagram'
    elif 'drafts' in upper and 'scheduled' in upper and 'cancel' in upper:
        state, app = 'draft_library', 'x'
    elif has('upload short') and 'save draft' in lower and has('select audience'):
        state, app = 'draft_details', 'youtube'
    elif 'new reel' in upper and 'save draft' in lower and 'share' in lower:
        state, app = 'draft_details', 'instagram'
    elif (all(anchor(label, .82, .87) for label in ('audio', 'overlay', 'filter', 'edit', 'ratio'))
          and (anchor('next', .89, .96) or anchor('suggested audio', .07, .13)
               or any(anchor(label, .07, .13) for label in ('suggested a...', 'suggested...', 'suggested a…', 'suggested…')))):
        # Instagram visibly truncates this UI label while the song title scrolls.
        # This exact variant still needs all five toolbar anchors; never repair
        # partial Next/account/caption OCR or infer that audio was selected.
        state, app, layout = 'draft_editor', 'instagram', 'carousel_editor'
    elif (anchor('new post', .04, .12) and anchor('add audio', .55, .65)
          and anchor('tag people', .65, .75) and anchor('add location', .72, .8)
          and (anchor('add ai label', .78, .85) or anchor('add al label', .78, .85))
          and anchor('share', .88, .98)):
        state, app, layout = 'draft_details', 'instagram', 'carousel_details'
    elif 'preview' in upper and 'save draft' in lower and 'share' in lower and has('original audio'):
        state, app = 'draft_preview', 'instagram'
    elif (anchor('everyone can view this post', .5, .85) and anchor('drafts', .88, .98)
          and ((anchor('edit cover', .2, .4) and anchor('preview', .08, .2)
                and anchor('cancel', .04, .15) and anchor('share to', .6, .8))
               or (anchor('preview', .04, .15) and anchor('share to', .8, .88)
                   and anchor('post', .88, .98, True) and anchor('more options', .7, .83, True)))):
        state, app = 'draft_details', 'tiktok'
    elif 'post' in upper and 'cancel' in upper and has('everyone can reply'):
        state, app = 'draft_details', 'x'

    if state == 'unknown' and frame is not None:
        # Corroborate the screen from independent controls; do not repair OCR text.
        layout_evidence = editor_controls(frame, text)
        if layout_evidence:
            state, app, layout = 'draft_editor', 'instagram', 'carousel_editor'
        else:
            layout_evidence = picker_controls(frame, text)
            if layout_evidence:
                state, app, layout = 'media_picker', 'instagram', 'post_media_picker'

    # Account identity is read only in designated identity regions, never from captions/comments.
    account_lines = []
    if state in ('profile', 'account_menu'):
        account_lines = [s for s, y in rows if y < .35]
    elif state == 'draft_details' and app == 'youtube':
        account_lines = [s for s, y in rows if .2 < y < .6]
    handles = []
    for line in account_lines:
        handles.extend(re.findall(r'(?<![\w.])@([A-Za-z0-9_.-]{1,50})(?![\w.])', line))
        if app == 'instagram' and re.fullmatch(r'[A-Za-z0-9_.]{1,30}', line) and '.' in line:
            handles.append(line)
        elif app == 'instagram' and line.casefold() == expected['account'].casefold():
            handles.append(line)
    handles = sorted(set(handles))
    account_match = len(handles) == 1 and handles[0].casefold() == expected['account'].casefold() and app == expected['platform']
    account_state = 'exact_text_match' if account_match else 'different_text' if handles else 'not_visible'
    caption = expected['caption']
    # No I/l substitutions, punctuation removal or invented whitespace. OCR may need human review.
    # Exclude navigation/footer text and content showing behind an editing sheet.
    caption_low, caption_high = (.40, .52) if layout == 'carousel_details' else (.10, .60)
    caption_match = (bool(caption) and app == expected['platform'] and any(caption == s and caption_low < y < caption_high for s, y in rows)
                     and state in ('draft_details', 'draft_preview'))
    reason = ('A system dialog needs inspection before continuing.' if state in ('permission_prompt', 'sharing_dialog', 'share_sheet')
              else 'The screen is not recognized.' if state == 'unknown'
              else 'Caption editor is still open; inspect and finish editing before draft review.' if state == 'caption_editor'
              else 'The expected app pattern is not visible.' if app != expected['platform']
              else 'OCR did not read the expected account exactly; inspect the frame.' if not account_match
              else 'Expected account text is visible. This does not certify media, saved state or app authenticity.')
    return {'screen': state, 'layout': layout, 'layoutEvidence': layout_evidence, 'appPattern': app, 'expectedAppMatches': app == expected['platform'],
            'accountStatus': account_state, 'observedHandles': handles,
            'captionStatus': 'exact_line_match' if caption_match else 'needs_review' if caption else 'not_requested',
            'reason': reason, 'automaticInputAllowed': False, 'savedDraftVerified': False,
            'metrics': None, 'metricsReason': 'A screen count has no verified post identity or observation interval.'}


class ObservationStore:
    """Idempotent read requests and review holds; a restart never replays a capture."""
    def __init__(self, path, ocr=None, clock=time.time, monotonic=time.monotonic, *, retained_limit=50):
        if type(retained_limit) is not int or not 1<=retained_limit<=160:
            raise ValueError('Observation retention must be between 1 and 160 frames.')
        self.retained_limit=retained_limit
        self.path, self.ocr, self.clock, self.monotonic = Path(path), ocr or WindowsOcr(), clock, monotonic
        self.session = uuid.uuid4().hex
        self.timings = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, document TEXT NOT NULL, frame BLOB)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db: yield db
        finally: db.close()

    def get(self, request_id):
        request_id = str(uuid.UUID(request_id))
        with self.connect() as db:
            row = db.execute('SELECT document FROM observations WHERE id=?', (request_id,)).fetchone()
        if row is None: raise KeyError('Observation not found. No request was replayed.')
        return self.with_age(json.loads(row[0]))

    def with_age(self, value):
        request_id = value['id']
        now, mono = self.clock(), self.monotonic()
        timing = self.timings.get(request_id)
        same_session = value.get('observerSession') == self.session and timing is not None
        monotonic_age = mono - timing[0] if same_session else 0
        value['ageSeconds'] = max(0, now - value['requestedAt'], monotonic_age)
        value['expired'] = not same_session or now < value['requestedAt'] or monotonic_age < 0 or value['ageSeconds'] > 15
        evidence = value.get('frameEvidence')
        if evidence:
            value['freshnessAtCapture'] = evidence['freshness']
            if not same_session:
                evidence.update(freshness='unavailable', reason='Saved observation belongs to an earlier observer session; capture again before use.')
            elif evidence.get('ageUpperBoundMs') is not None:
                elapsed = max(0, now - value['completedAt'], mono - timing[1]) * 1000
                evidence['currentAgeUpperBoundMs'] = evidence['ageUpperBoundMs'] + elapsed
                if value['expired'] or evidence['currentAgeUpperBoundMs'] > MAX_AGE_MS:
                    evidence.update(freshness='stale', reason='Saved frame aged beyond the receiver-delivery budget; capture again.')
            value['freshness'] = evidence['freshness']
        value['workflowReview'] = workflow_review(value)
        return value

    def list(self):
        with self.connect() as db:
            ids = [row[0] for row in db.execute('SELECT id FROM observations ORDER BY rowid DESC LIMIT 50')]
        return [self.get(i) for i in ids]

    def frame(self, request_id):
        with self.connect() as db:
            row = db.execute('SELECT frame FROM observations WHERE id=?', (str(uuid.UUID(request_id)),)).fetchone()
        if not row or row[0] is None: raise KeyError('Frame unavailable; older frames are pruned but review records remain.')
        return row[0]

    def evidence(self, request_id):
        """Immutable capture-time record and its paired review image, not current readiness."""
        with self.connect() as db:
            row = db.execute('SELECT document,frame FROM observations WHERE id=?', (str(uuid.UUID(request_id)),)).fetchone()
        if not row or row[1] is None: raise KeyError('Observation image is missing or pruned; capture new evidence explicitly.')
        value = json.loads(row[0])
        if value.get('reviewFrameSha256') != hashlib.sha256(row[1]).hexdigest():
            raise ValueError('Observation has no matching review-image checksum. Older records need a new explicit capture.')
        return value, row[1]

    def current_evidence(self, request_id):
        """One stored record/image pair, with integrity checked before applying age.

        A decision may reference this digest and recheck it without combining the
        metadata of one read with an image obtained by a different read.
        """
        value, frame = self.evidence(request_id)
        digest = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                           separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        current = self.with_age(value)
        current['evidenceRecordSha256'] = digest
        return current, frame

    def interval(self, start_id, end_id):
        """All stored C24C observations between two row IDs, including failed/pruned ones.

        Uses insertion order as well as timestamps so a bad clock cannot hide a record.
        This is a sampled observation history, not a continuous recording of phone actions.
        """
        with self.connect() as db:
            ends = [db.execute('SELECT rowid FROM observations WHERE id=?', (str(uuid.UUID(i)),)).fetchone()
                    for i in (start_id, end_id)]
            if any(row is None for row in ends) or ends[0][0] >= ends[1][0]:
                raise ValueError('Account boundary observations are missing or out of order.')
            rows = db.execute('SELECT document,frame FROM observations WHERE rowid BETWEEN ? AND ? ORDER BY rowid LIMIT 101',
                              (ends[0][0], ends[1][0])).fetchall()
        if len(rows) > 100: raise ValueError('Account observation interval exceeds 100 records; use a shorter review run.')
        output = []
        for document, frame in rows:
            value = json.loads(document)
            if value.get('expected', {}).get('device_id') != 'C24C': continue
            valid = frame is not None and value.get('reviewFrameSha256') == hashlib.sha256(frame).hexdigest()
            output.append((value, frame if valid else None))
        return output

    def capture(self, request, kernel, *, owned_run=None):
        desired = expectations(request, kernel.phone.board)
        request_id = str(uuid.UUID(request.get('id', '')))
        # owned_run is an internal lease guard, never a field accepted from HTTP.
        identity = desired if owned_run is None else {**desired, 'ownedRun': owned_run.run_id}
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        with self.lock:
            with self.connect() as db:
                prior = db.execute('SELECT fingerprint FROM observations WHERE id=?', (request_id,)).fetchone()
                if prior:
                    if prior[0] != fingerprint: raise ValueError('This observation ID has different expectations.')
                    return self.get(request_id)
                value = {'id': request_id, 'expected': desired, 'requestedAt': self.clock(), 'observerSession': self.session, 'state': 'review_required',
                         'reason': 'Capture outcome has not been recorded. A restart does not replay this request.',
                         'source': 'phone' if kernel._is_live_http else 'simulation', 'automaticInputAllowed': False}
                db.execute('INSERT INTO observations VALUES (?,?,?,NULL)', (request_id, fingerprint, json.dumps(value)))
            started = self.monotonic()
            self.timings[request_id] = (started, None)
            frame = None
            try:
                # The normal path remains read-only. A managed run authenticates its own
                # lease on both sides of the frame; it never accepts another owner's lease.
                resolved = kernel.resolve_device_id(kernel.phone.board)
                if owned_run is not None: owned_run.check(kernel)
                before = kernel.kernel_status()
                receiver = next((r for r in before.get('receivers', []) if r.get('deviceid') == resolved), None)
                if receiver is None or receiver.get('live') is not True: raise ValueError(f'{kernel.phone.board} video is offline.')
                input_before = kernel.input_status().get(resolved)
                raw, headers = kernel.shot(kernel.phone.board)
                width, height = image_size(raw)
                text = self.ocr.read(raw)
                if text.get('frameSha256') != hashlib.sha256(raw).hexdigest():
                    raise ValueError('OCR result does not identify the exact captured frame.')
                after = kernel.kernel_status()
                current = next((r for r in after.get('receivers', []) if r.get('deviceid') == resolved), {})
                input_after = kernel.input_status().get(resolved)
                if owned_run is not None: owned_run.check(kernel)
                if (text.get('width'), text.get('height')) != (width, height): raise ValueError('OCR frame dimensions changed.')
                result = classify(text, desired, raw)
                evidence = delivery_evidence(receiver, headers, current, (self.monotonic() - started) * 1000)
                stable = (current.get('live') is True and current.get('receiver_pid') == receiver.get('receiver_pid')
                          and current.get('receiver_restarts') == receiver.get('receiver_restarts')
                          and input_before is not None and input_before == input_after)
                input_idle = all(isinstance(s, dict) and type(s.get('generation')) is int
                                 and all(s.get(flag) is False for flag in ('owned', 'active', 'stopped', 'releasing', 'release_failed'))
                                 for s in (input_before, input_after))
                if owned_run is not None:
                    settled = owned_run.accepts(input_before, input_after)
                    stable = (current.get('live') is True and current.get('receiver_pid') == receiver.get('receiver_pid')
                              and current.get('receiver_restarts') == receiver.get('receiver_restarts') and settled)
                    value.update(inputSettled=settled, ownershipEvidence=owned_run.evidence())
                if not stable: result['reason'] = 'Phone ownership or receiver state changed during capture. Inspect again.'
                value.update(state='observed', result=result, text=text, frameSha256=hashlib.sha256(raw).hexdigest(),
                             width=width, height=height, freshness=evidence['freshness'], frameEvidence=evidence, stable=stable, inputIdle=input_idle,
                             reason=result['reason'], receiverPid=receiver.get('receiver_pid'),
                             inputGeneration=input_before.get('generation') if isinstance(input_before, dict) else None,
                             resolvedDeviceId=resolved)
                with Image.open(io.BytesIO(raw)) as image:
                    buffer = io.BytesIO(); image.convert('RGB').save(buffer, format='PNG'); frame = buffer.getvalue()
                    value['reviewFrameSha256'] = hashlib.sha256(frame).hexdigest()
            except Exception as exc:
                value.update(state='failed', reason=str(exc))
            finished = self.monotonic()
            if value['state'] == 'observed':
                evidence = delivery_evidence(receiver, headers, current, (finished - started) * 1000)
                value.update(freshness=evidence['freshness'], frameEvidence=evidence)
            value['completedAt'] = self.clock()
            self.timings[request_id] = (started, finished)
            with self.connect() as db:
                db.execute('UPDATE observations SET document=?,frame=? WHERE id=?', (json.dumps(value), frame, request_id))
                db.execute('UPDATE observations SET frame=NULL WHERE rowid NOT IN (SELECT rowid FROM observations ORDER BY rowid DESC LIMIT ?)',(self.retained_limit,))
            return self.get(request_id)
