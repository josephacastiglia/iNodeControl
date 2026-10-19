"""Bounded, journalled carousel inspection; live movement is not enabled yet.

The only movement is a horizontal swipe within a recognized full-size editor.
No tap, text, Back, Save, Share or account-selection action is available here.
Matching all slides is visual evidence, not proof of account or draft persistence.
"""
from contextlib import contextmanager
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid
import zipfile

from farm_drafts import DraftConflict, identifier
from farm_draft_media import media_comparison
from farm_observations import expectations


class InspectionStopped(Exception):
    pass


class OwnedCaptureRun:
    """In-memory capability. Tokens are never returned as observation evidence."""
    def __init__(self, kernel, run_id, cancelled, monotonic=time.monotonic):
        self.kernel, self.run_id, self.cancelled = kernel, run_id, cancelled
        self.monotonic, self.deadline = monotonic, monotonic() + 90
        self.tokens, self.generation, self.resolved, self.stream = {}, None, None, None

    def check_budget(self):
        if self.cancelled.is_set(): raise InspectionStopped('Inspection cancelled; no action will be replayed.')
        if self.monotonic() >= self.deadline: raise InspectionStopped('Inspection exceeded its 90-second budget.')

    def acquire(self):
        self.check_budget()
        preflight = self.kernel.preflight_phone('C24C')
        self.resolved = preflight['resolved_id']
        self.stream = self.receiver_context(preflight['receiver'])
        self.tokens = self.kernel.acquire(['C24C'], lease_ms=30000)
        state = self.kernel.input_status().get(self.resolved)
        if not self.settled(state): raise InspectionStopped('Acquired input state was not settled.')
        self.generation = state['generation']
        self.check(self.kernel)

    @staticmethod
    def settled(state):
        return (isinstance(state, dict) and type(state.get('generation')) is int and state.get('owned') is True
                and all(state.get(flag) is False for flag in ('active', 'stopped', 'releasing', 'release_failed')))

    @staticmethod
    def receiver_context(receiver):
        return tuple(receiver.get(k) for k in ('deviceid', 'receiver_pid', 'receiver_restarts', 'frame_session'))

    def check(self, kernel):
        self.check_budget()
        if kernel is not self.kernel or not self.tokens: raise InspectionStopped('This capture has no matching owned run.')
        try:
            # Always authenticate the token, not just a status field saying "owned".
            kernel.renew_if_needed(self.tokens, min_remaining_ms=1_000_000)
        except Exception as error:
            raise InspectionStopped('The inspection lease could not be authenticated; input stopped.') from error
        state = kernel.input_status().get(self.resolved)
        if not self.accepts(state): raise InspectionStopped('Inspection ownership changed or input is not settled.')
        receiver = next((r for r in kernel.kernel_status().get('receivers', []) if r.get('deviceid') == self.resolved), {})
        if receiver.get('live') is not True or self.receiver_context(receiver) != self.stream:
            raise InspectionStopped('Receiver or stream changed during inspection.')
        self.check_budget()

    def accepts(self, *states):
        return bool(states) and all(self.settled(s) and s['generation'] == self.generation for s in states)

    def evidence(self):
        return dict(runId=self.run_id, generation=self.generation, authenticatedBeforeAndAfter=True,
                    source='owned_capture_guard', continuousPhoneActivityKnown=False)

    def release(self):
        if self.tokens:
            # Cleanup is deliberately independent of cancellation/deadline checks.
            self.kernel.release(self.tokens)
            self.tokens = {}


class CarouselInspections:
    def __init__(self, path, observations, drafts, clock=time.time, monotonic=time.monotonic):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.observations, self.drafts = observations, drafts
        self.clock, self.monotonic = clock, monotonic
        self.lock = threading.Lock()
        self.active_lock = threading.Lock()
        self.active = {}
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS inspections(id TEXT PRIMARY KEY, fingerprint TEXT, document TEXT, package BLOB)')
            db.execute('CREATE TABLE IF NOT EXISTS frames(run_id TEXT, observation_id TEXT, document TEXT, frame BLOB, PRIMARY KEY(run_id,observation_id))')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db: yield db
        finally: db.close()

    def get(self, run_id):
        with self.connect() as db:
            db.execute('BEGIN')  # Record and evidence must come from one SQLite read snapshot.
            row = db.execute('SELECT document,package FROM inspections WHERE id=?', (identifier(run_id),)).fetchone()
            frames = db.execute('SELECT observation_id,document,frame FROM frames WHERE run_id=?', (identifier(run_id),)).fetchall()
        if row is None: raise KeyError('Inspection not found.')
        value = json.loads(row[0])
        if hashlib.sha256(row[1]).hexdigest() != value['packageSha256']:
            raise ValueError('Inspection source package is damaged.')
        if value.get('inspectionVersion') != 2:
            value.update(state='review_required', reason='Historical inspection lacks the evidence manifest required for current acceptance.')
        else:
            manifest = value.get('evidenceManifest', {})
            if set(manifest) != {item[0] for item in frames}:
                raise ValueError('Inspection evidence is missing or damaged.')
            for observation_id, document, frame in frames:
                evidence = json.loads(document)
                if (evidence.get('id') != observation_id or observation_id not in value['observationIds']
                        or self.record_hash(evidence) != manifest[observation_id]['recordSha256']
                        or hashlib.sha256(frame).hexdigest() != manifest[observation_id]['frameSha256']
                        or evidence.get('reviewFrameSha256') != manifest[observation_id]['frameSha256']):
                    raise ValueError('Inspection evidence record or image is damaged.')
        # An incomplete durable record cannot be interpreted as permission to retry.
        with self.active_lock: in_progress = value['id'] in self.active
        if value['state'] == 'running' and not in_progress:
            value.update(state='review_required', reason='Inspection outcome is incomplete. Do not replay or take over its lease.')
        return value

    def frame(self, run_id, observation_id):
        record = self.get(run_id)
        with self.connect() as db:
            row = db.execute('SELECT document,frame FROM frames WHERE run_id=? AND observation_id=?',
                             (identifier(run_id), identifier(observation_id))).fetchone()
        if not row: raise KeyError('Inspection frame is unavailable.')
        evidence = json.loads(row[0])
        frame_hash = hashlib.sha256(row[1]).hexdigest()
        if frame_hash != evidence['reviewFrameSha256']:
            raise ValueError('Inspection image is damaged.')
        if record.get('inspectionVersion') == 2:
            expected = record['evidenceManifest'].get(observation_id)
            if not expected or expected != dict(recordSha256=self.record_hash(evidence), frameSha256=frame_hash):
                raise ValueError('Inspection evidence changed or is damaged.')
        return row[1]

    def save(self, record):
        with self.connect() as db:
            db.execute('UPDATE inspections SET document=? WHERE id=?', (json.dumps(record), record['id']))

    @staticmethod
    def record_hash(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()

    def cancel(self, run_id):
        run_id = identifier(run_id)
        with self.active_lock:
            event = self.active.get(run_id)
            if event is not None: event.set()
        # Cancellation of an already finished/unknown run never sends a phone command.
        return dict(id=run_id, cancellationRequested=event is not None)

    def retain(self, record, value, frame):
        """Atomically retain one immutable capture and its manifest for managed runs."""
        observation_id = value['id']
        digest = self.record_hash(value)
        size = len(frame) + len(json.dumps(value).encode('utf-8'))
        record['evidenceBytes'] += size
        if record['evidenceBytes'] > 32 * 1024 * 1024: raise InspectionStopped('Inspection evidence exceeds 32 MiB.')
        record['evidenceManifest'][observation_id] = dict(recordSha256=digest, frameSha256=value['reviewFrameSha256'])
        with self.connect() as db:
            db.execute('INSERT INTO frames VALUES (?,?,?,?)', (record['id'], observation_id, json.dumps(value), frame))
            db.execute('UPDATE inspections SET document=? WHERE id=?', (json.dumps(record), record['id']))
        return digest

    def capture(self, record, kernel, assets, index, owned=None, *, purpose='slide'):
        observation_id = str(uuid.uuid4())
        record['observationIds'].append(observation_id)
        record['captureRoles'][observation_id] = purpose if owned else 'preflight'
        self.save(record)
        request = {**record['request'], 'id': observation_id}
        value = self.observations.capture(request, kernel, owned_run=owned)
        if value.get('state') != 'observed': raise InspectionStopped('Screen observation failed; no further movement.')
        value, frame = self.observations.evidence(observation_id)
        digest = self.retain(record, value, frame)
        if (value.get('freshness') != 'recent' or value.get('stable') is not True
                or value.get('frameEvidence', {}).get('pairedMetadata') is not True):
            raise InspectionStopped('Recent paired frame evidence is missing or changed; no movement is allowed.')
        if (value.get('inputSettled') if owned else value.get('inputIdle')) is not True:
            raise InspectionStopped('Input was not settled in the expected ownership state.')
        if value.get('result', {}).get('layout') != 'carousel_editor':
            raise InspectionStopped('The expected Instagram carousel editor is not visible.')
        if (value.get('width'), value.get('height')) != (500, 1080):
            raise InspectionStopped('This inspection gesture is validated only for a 500 by 1080 frame.')
        result = media_comparison(frame, assets, 'carousel_editor')
        position = result.get('position', {})
        if result.get('matchedIndex') != index or position.get('index') != index or position.get('count') != len(assets):
            raise InspectionStopped('Carousel media, order or visible slide count differs from the source package.')
        record['captureChecks'][observation_id] = dict(expectedIndex=index, comparison=result)
        stream = (value['receiverPid'], value['frameEvidence']['session'])
        if owned:
            if stream != (owned.stream[1], owned.stream[3]): raise InspectionStopped('Frame stream does not belong to this inspection.')
            previous_sequence = record.get('lastFrameSequence')
            if previous_sequence is not None and value['frameEvidence']['sequence'] <= previous_sequence:
                raise InspectionStopped('Frame sequence did not advance after movement.')
            record['lastFrameSequence'] = value['frameEvidence']['sequence']
            if purpose == 'slide':
                record['slides'].append(dict(index=index, observationId=observation_id,
                    sequence=value['frameEvidence']['sequence'], comparison=result))
            self.save(record)
        return {**value, 'evidenceRecordSha256': digest}

    def action_for(self, record, value, index):
        return dict(fromSlide=index-1, toSlide=index, state='not_sent',
            gesture=dict(function='/mouse/swipe', x1=400, y1=480, x2=100, y2=480, duration=350),
            basis=dict(observationId=value['id'], recordSha256=value['evidenceRecordSha256'],
                frameSha256=value['reviewFrameSha256'], rawFrameSha256=value['frameSha256'],
                frameSequence=value['frameEvidence']['sequence'], frameSession=value['frameEvidence']['session'],
                inputGeneration=value['inputGeneration'], runId=record['id'], packageSha256=record['packageSha256']))

    def validate_action(self, record, action, owned, kernel):
        owned.check(kernel)
        basis = action['basis']
        current, frame = self.observations.current_evidence(basis['observationId'])
        if (current.get('freshness') != 'recent' or current.get('expired')
                or current.get('evidenceRecordSha256') != basis['recordSha256']
                or hashlib.sha256(frame).hexdigest() != basis['frameSha256']
                or current.get('frameSha256') != basis['rawFrameSha256']
                or current.get('inputGeneration') != owned.generation
                or basis['inputGeneration'] != owned.generation
                or current.get('frameEvidence', {}).get('sequence') != basis['frameSequence']
                or current.get('frameEvidence', {}).get('session') != basis['frameSession']
                or current.get('ownershipEvidence', {}).get('runId') != owned.run_id
                or basis['runId'] != owned.run_id or basis['packageSha256'] != record['packageSha256']
                or record['captureRoles'].get(basis['observationId']) != 'before_swipe'):
            raise InspectionStopped('The exact decision frame expired or changed; nothing was sent.')
        if (record['captureChecks'][basis['observationId']]['expectedIndex'] != action['fromSlide']
                or action['toSlide'] != action['fromSlide'] + 1):
            raise InspectionStopped('The movement does not follow its verified slide.')
        owned.check_budget()

    def run(self, request, kernel, cancelled=None):
        if set(request) - {'id', 'draft_id', 'revision', 'device_id', 'platform', 'account'}:
            raise ValueError('Inspection accepts a saved draft revision and expectations only; no coordinates or commands.')
        desired = expectations(request)
        if desired['platform'] != 'instagram': raise ValueError('Only Instagram carousel inspection is implemented.')
        if type(request.get('revision')) is not int or request['revision'] < 1: raise ValueError('Choose a saved draft revision.')
        spec = dict(id=identifier(request.get('id')), draft_id=identifier(request.get('draft_id')), revision=request['revision'], **desired)
        fingerprint = json.dumps(spec, sort_keys=True)
        if not self.lock.acquire(blocking=False): raise DraftConflict('An inspection is already running.')
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                prior = db.execute('SELECT fingerprint FROM inspections WHERE id=?', (spec['id'],)).fetchone()
                if prior:
                    if prior[0] != fingerprint: raise DraftConflict('Inspection ID already has different expectations.')
                    return self.get(spec['id'])
                package = self.drafts.export(spec['draft_id'], spec['revision'])
                if len(package) > 32 * 1024 * 1024: raise ValueError('Source package exceeds 32 MiB.')
                with zipfile.ZipFile(io.BytesIO(package)) as files:
                    manifest = json.loads(files.read('manifest.json'))
                    assets = [files.read(a['file']) for a in manifest['assets']]
                    if not 2 <= len(assets) <= 10: raise ValueError('Inspection supports 2 to 10 slides.')
                    if any(hashlib.sha256(a).hexdigest() != meta['sha256'] for a, meta in zip(assets, manifest['assets'])):
                        raise ValueError('Source asset checksum mismatch.')
                record = dict(id=spec['id'], request=spec, state='running', startedAt=self.clock(), inspectionVersion=2,
                    observationIds=[], captureRoles={}, captureChecks={}, evidenceManifest={}, slides=[], actions=[], evidenceBytes=len(package),
                    packageSha256=hashlib.sha256(package).hexdigest(), source='phone' if kernel._is_live_http else 'simulation',
                    leaseAcquisitionAttempted=False, cleanup='not_needed', savedDraftVerified=False,
                    accountContinuityProven=False, automaticInputAllowed=False,
                    reason='Collecting visual evidence only. Account, caption and saved-draft identity are not established.')
                db.execute('INSERT INTO inspections VALUES (?,?,?,?)', (spec['id'], fingerprint, json.dumps(record), package))
            event = cancelled or threading.Event()
            with self.active_lock: self.active[spec['id']] = event
            owned = OwnedCaptureRun(kernel, spec['id'], event, self.monotonic)
            try:
                owned.check_budget()
                # Read-only preflight rejects old installed kernels before any lease or input.
                self.capture(record, kernel, assets, 1)
                if kernel._is_live_http:
                    raise InspectionStopped('Live carousel movement remains disabled pending candidate validation. No lease was acquired.')
                record.update(leaseAcquisitionAttempted=True, cleanup='unconfirmed'); self.save(record)
                owned.acquire()
                self.capture(record, kernel, assets, 1, owned)
                for index in range(2, len(assets) + 1):
                    # A still-recent previous slide is not evidence that a new dialog
                    # has not appeared. Re-recognize a fresh frame before every swipe.
                    current = self.capture(record, kernel, assets, index-1, owned, purpose='before_swipe')
                    action = self.action_for(record, current, index)
                    record['actions'].append(action); self.save(record)
                    try:
                        self.validate_action(record, action, owned, kernel)
                        action['state'] = 'outcome_unknown'; self.save(record)
                        self.validate_action(record, action, owned, kernel)
                    except Exception:
                        action['state'] = 'not_sent'; self.save(record)
                        raise
                    # Only this fixed horizontal gesture; never a tap on a publish control.
                    kernel.send('C24C', owned.tokens['C24C'], '/mouse/swipe', x1=400, y1=480, x2=100, y2=480, duration=350)
                    action['state'] = 'answered'; self.save(record)
                    if owned.cancelled.wait(.4): owned.check_budget()
                    self.capture(record, kernel, assets, index, owned)
                owned.check(kernel)
                record.update(state='visual_match', reason='Every full-size slide and position matched under one lease. Saved-draft and account acceptance remain open.')
            except InspectionStopped as error:
                record.update(state='review_required', reason=str(error))
            except Exception as error:
                # Transport exceptions can contain lease secrets; keep only their type.
                record.update(state='review_required', reason=type(error).__name__ + ': inspection interrupted; uncertain input is never retried.')
            finally:
                if owned.tokens:
                    try:
                        owned.release(); record['cleanup'] = 'confirmed'
                    except Exception:
                        record.update(cleanup='unconfirmed', state='review_required', reason='Lease release was not confirmed. Inspect C24C before any further input.')
                record['completedAt'] = self.clock(); self.save(record)
            return self.get(spec['id'])
        finally:
            with self.active_lock: self.active.pop(spec['id'], None)
            self.lock.release()
