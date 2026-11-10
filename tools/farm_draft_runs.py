"""Durable admission and retrieval shared by every draft creation route.

DraftRuns is the base: a route's class (CreationRuns, ReelCreationRuns and the lanes) says what
content it supports, what it reports as its capability and how it executes. GET never connects to
the phone. Reusing an ID only retrieves its journal, even after a process dies between admission
and execution. No startup resumes work.
"""
from contextlib import contextmanager
import errno
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
import zipfile

from farm_drafts import DraftConflict, identifier
from farm_observations import ObservationStore
from imouse_social_automation import KernelSafetyError
from farm_phone_identity import LEGACY_C24C, PhoneIdentity, PhoneIdentityError


from farm_paths import ARCHIVE


def _private_account():
    """The v1 C24C candidate's account handle: per-machine private data, never in Git or a package
    (<evidence archive>/privacy/farm-accounts.json, "v1CandidateAccount"). '' when this machine has none,
    so a v1 workflow naming an account never matches."""
    try:
        return str(json.loads((ARCHIVE / 'privacy' / 'farm-accounts.json').read_text(encoding='utf-8'))['v1CandidateAccount'])
    except (OSError, ValueError, KeyError):
        return ''


ACCOUNT = _private_account()
API = 'http://127.0.0.1:9916/api'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_journal(path):
    # Reader side of the race atomic_json retries: a status read that opens the
    # journal during its replacement is refused for a moment. open() reports
    # winerror 5, 32 or 33 only as errno EACCES. Retry just this local read for
    # the writer's budget, never a phone command; a lasting refusal still raises.
    deadline = time.monotonic() + .5
    while True:
        try:
            return path.read_bytes()
        except OSError as error:
            code = getattr(error, 'winerror', None)
            transient = code in (5, 32, 33) if code is not None else error.errno == errno.EACCES
            if not transient or time.monotonic() >= deadline:
                raise
            time.sleep(.01)


def source_content(package):
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assets = [archive.read(row['file']) for row in manifest['assets']]
    identity = dict(caption=manifest['caption'], slides=[sha(raw) for raw in assets])
    digest = sha(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8'))
    return assets, manifest['caption'], digest


CORE_V1 = {'version', 'api', 'kernelSha256', 'expectedUid'}
# Version 2 is one window of the multi-phone kernel: its own phone, the kernel's prepared
# allow-list (which must match the running kernel exactly) and the account signed in on that
# phone, or null where creation binds the signed-in account itself (X).
CORE_V2 = CORE_V1 | {'phone', 'allowed', 'account'}


def load_config(path, mode):
    if path is None: return None
    if mode != 'live': raise ValueError('A phone draft configuration requires explicit live mode.')
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if (not isinstance(config, dict) or set(config) not in (CORE_V1, CORE_V2)
            or type(config['version']) is not int or config['version'] != (1 if set(config) == CORE_V1 else 2) or config['api'] != API
            or not isinstance(config['kernelSha256'], str) or not re.fullmatch('[0-9a-f]{64}', config['kernelSha256'])
            or not isinstance(config['expectedUid'], str) or not 1 <= len(config['expectedUid']) <= 64):
        raise ValueError('Draft candidate needs version 1 or 2, the isolated 9916 API, kernel SHA-256 and the board UID.')
    if config['version'] == 2:
        try: phone = PhoneIdentity.from_config(config['phone'])
        except PhoneIdentityError as error: raise ValueError(str(error)) from error
        allowed = config['allowed']
        if (not isinstance(allowed, list) or not allowed or len(set(allowed)) != len(allowed) or phone.board not in allowed
                or not all(isinstance(b, str) and re.fullmatch('[0-9A-F]{4}', b) for b in allowed)):
            raise ValueError("The kernel allow-list must be distinct board IDs that include this window's phone.")
        account = config['account']
        if account is not None and not (isinstance(account, str) and re.fullmatch(r'[A-Za-z0-9_.]{1,30}', account)):
            raise ValueError('Account must be a signed-in handle without @, or null for a signed-in binding.')
    return config


def phone_of(config):
    """The one phone this window drives; a version 1 config is the pre-rack C24C window."""
    return LEGACY_C24C if config['version'] == 1 else PhoneIdentity.from_config(config['phone'])


def allowed_of(config):
    return None if config['version'] == 1 else list(config['allowed'])


def account_of(config):
    return ACCOUNT if config['version'] == 1 else config['account']


class DraftRuns:
    action_name = 'draft-save-reopen'
    def __init__(self, folder, drafts, jobs, config=None):
        self.folder = Path(folder); self.folder.mkdir(parents=True, exist_ok=True)
        self.drafts, self.jobs, self.config = drafts, jobs, config
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS identity(id TEXT PRIMARY KEY)')
            db.execute('INSERT INTO identity SELECT ? WHERE NOT EXISTS (SELECT 1 FROM identity)', (str(uuid.uuid4()),))
            self.store_id = db.execute('SELECT id FROM identity').fetchone()[0]
            db.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, request TEXT, package BLOB, package_hash TEXT)')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.folder / 'runs.db', timeout=10)
        try:
            with connection: yield connection
        finally: connection.close()

    # A route's class provides capability(), supports(package), content_reason(supported) and
    # execute(folder, assets, caption, package_hash, cancelled).

    def eligibility(self, draft_id, revision):
        package = self.drafts.export(identifier(draft_id), revision)
        _, _, content = source_content(package)
        supported = self.supports(package)
        return dict(**self.capability(), eligible=self.config is not None and supported,
            supportedContent=supported, draftId=draft_id, revision=revision,
            packageSha256=sha(package),
            contentReason=self.content_reason(supported))

    @staticmethod
    def validate_request(spec):
        if not isinstance(spec, dict) or set(spec) != {'id', 'draft_id', 'revision', 'store_id'}:
            raise ValueError('Choose a saved draft revision; account, device, actions and endpoint cannot be overridden.')
        spec = dict(spec)
        for key in ('id', 'draft_id', 'store_id'): spec[key] = identifier(spec[key])
        if type(spec['revision']) is not int or spec['revision'] < 1: raise ValueError('Invalid saved revision.')
        return spec

    def row(self, run_id):
        with self.connect() as db:
            row = db.execute('SELECT request,package,package_hash FROM runs WHERE id=?', (identifier(run_id),)).fetchone()
        if row is None: raise KeyError('Draft run not found. Absence does not authorize resubmission.')
        if sha(row[1]) != row[2]: raise ValueError('Retained draft package is damaged.')
        return json.loads(row[0]), row[1], row[2]

    def package_for_request(self, spec):
        return self.drafts.export(spec['draft_id'], spec['revision'])

    def start(self, spec):
        spec = self.validate_request(spec)
        if spec['store_id'] != self.store_id: raise DraftConflict('The candidate data store changed. No new run was admitted.')
        with self.lock:
            try: previous, _, _ = self.row(spec['id'])
            except KeyError: previous = None
            if previous is not None:
                if previous != spec: raise DraftConflict('This request ID belongs to another draft or revision.')
                return self.get(spec['id'])
            if not self.config: raise KernelSafetyError('Prepare the isolated candidate; phone draft execution is disabled.')
            self.jobs.assert_available()
            package = self.package_for_request(spec)
            assets, caption, content = source_content(package)
            if not self.supports(package):
                raise ValueError('Saved content is outside the currently verified draft candidate.')
            # Reserve the ID before any worker can send input. An orphaned
            # admission is review-only, never an instruction to start it again.
            with self.connect() as db:
                try: db.execute('INSERT INTO runs VALUES (?,?,?,?)', (spec['id'], json.dumps(spec), package, sha(package)))
                except sqlite3.IntegrityError: raise DraftConflict('This request was admitted concurrently; retrieve its saved result.')
            folder = self.folder / spec['id']; folder.mkdir(exist_ok=False)
            def run(cancelled):
                result = self.execute(folder, assets, caption, sha(package), cancelled)
                return dict(recordSha256=sha((folder / 'record.json').read_bytes()), state=result['state'])
            self.jobs.submit(spec['id'], self.action_name, spec, run)
            return self.get(spec['id'])

    def get(self, run_id):
        run_id = identifier(run_id)
        spec, package, package_hash = self.row(run_id)
        try: job = self.jobs.get(run_id)
        except KeyError:
            job = dict(status='interrupted', terminal=True, result=None,
                error='Admission was interrupted before a durable job result. No action will be replayed.')
        result = None; folder = self.folder / run_id; path = folder / 'record.json'
        if path.exists():
            raw = read_journal(path); result = json.loads(raw)
            if result.get('packageSha256') != package_hash: raise ValueError('Run source no longer matches its saved package.')
            if job.get('result') and sha(raw) != job['result']['recordSha256']:
                raise ValueError('Completed draft run journal is damaged.')
            if job['terminal']:
                # Verify the retained bytes before displaying a completion claim.
                store = ObservationStore(folder / 'observations.sqlite3')
                for entry in result.get('observations', []):
                    if entry.get('state') != 'observed': continue
                    value, frame = store.evidence(entry['observationId'])
                    digest = sha(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
                    if (sha(frame) != entry['observation']['reviewFrameSha256']
                            or digest != entry['observation']['evidenceRecordSha256']):
                        raise ValueError('Retained run evidence changed.')
        accepted = bool(job['status'] == 'succeeded' and job['terminal'] and result
            and result.get('state') == 'validation_passed' and result.get('cleanup') == 'confirmed'
            and result.get('evidenceExport') == 'confirmed' and result.get('source') == 'candidate_phone_workflow'
            and all(action.get('state') == 'answered' for action in result.get('actions', []))
            and result.get('savedDraftVerified') is True)
        state = ('verified' if accepted else 'review_required') if job['terminal'] else 'running'
        try: changed = self.drafts.get(spec['draft_id'])['revision'] != spec['revision']
        except KeyError: changed = True
        return dict(id=run_id, storeId=self.store_id, request=spec, packageSha256=package_hash,
            state=state, terminal=job['terminal'], jobStatus=job['status'],
            reason=(result.get('error') if result else None) or job.get('error') or
                   ('The matching draft was saved, reopened and checked.' if accepted else
                    'Inspect the retained result; unknown phone actions are never replayed.' if job['terminal'] else
                    'Checking the existing C24C test draft. Keep this window open.'),
            savedDraftVerified=accepted, draftChangedSinceRun=changed,
            cleanup=result.get('cleanup', 'unconfirmed') if result else 'not_started_or_unknown',
            workflow=result, publishing=False, messaging=False, desktopControl=False,
            automaticResume=False, integratedLiveValidated=False)

    def list(self, draft_id):
        draft_id = identifier(draft_id)
        with self.connect() as db: rows = db.execute('SELECT id,request FROM runs ORDER BY rowid DESC').fetchall()
        # Full evidence is checked on explicit retrieval, not every history poll.
        return [dict(id=key, revision=json.loads(request)['revision']) for key, request in rows
                if json.loads(request)['draft_id'] == draft_id]

    def cancel(self, run_id):
        # Cancellation before POST admission creates a durable tombstone as well.
        return self.jobs.cancel(identifier(run_id))

    def frame(self, run_id, observation_id):
        run_id, observation_id = identifier(run_id), identifier(observation_id)
        result = self.get(run_id)
        if not result['terminal']: raise ValueError('Wait for cleanup before opening retained frames.')
        workflow = result.get('workflow') or {}
        entries = [e for e in workflow.get('observations', []) if e.get('observationId') == observation_id and e.get('state') == 'observed']
        if len(entries) != 1: raise KeyError('This capture does not belong to the selected draft run.')
        _, raw = ObservationStore(self.folder / run_id / 'observations.sqlite3').evidence(observation_id)
        if sha(raw) != entries[0]['observation']['reviewFrameSha256']: raise ValueError('Capture is damaged.')
        return raw
