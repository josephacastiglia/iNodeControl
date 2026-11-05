"""Bounded recurring local preparation. Never takes a phone lease or deploys content."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from farm_transfers import _ListenerOwner


def read_prepared_packages(database):
    """Content items of succeeded runs, oldest first, each with its runId: the review queue's input.

    Opens the database read-only: never creates tables, recovers runs or takes the owner lock,
    so the operator's command line can read it while the backend is running."""
    path = Path(database)
    if not path.exists(): return []
    db = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True, timeout=10)
    try: rows = db.execute('SELECT document FROM preparation_runs ORDER BY rowid').fetchall()
    except sqlite3.OperationalError: return []
    finally: db.close()
    items = []
    for (document,) in rows:
        run = json.loads(document)
        if run.get('state') == 'succeeded':
            items += [{**item, 'runId': run['id']} for item in run.get('contentItems', [])]
    return items


class PreparationSchedule:
    def __init__(self, database, prepare, persona, operation_lock, clock=time.time):
        self.path = Path(database); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.prepare, self.persona, self.operation_lock, self.clock = prepare, persona, operation_lock, clock
        self.lock = threading.RLock(); self.owner = _ListenerOwner(self.path.with_suffix('.owner-lock'))
        self.stop_event = threading.Event(); self.thread = None; self.worker_error = None
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS preparation_config (id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS preparation_requests (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS preparation_runs (id TEXT PRIMARY KEY, document TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO preparation_config VALUES (1,?)', (json.dumps({'enabled': False, 'state': 'not_configured', 'reason': 'No recurring preparation configured.'}),))
        # Do not rewrite another active backend's running record.
        if self.owner.acquire():
            try:
                with self.connect() as db:
                    interrupted = False
                    for run_id, document in db.execute('SELECT id,document FROM preparation_runs').fetchall():
                        run = json.loads(document)
                        if run['state'] == 'running':
                            run.update(state='interrupted', error='Backend exited before completion was recorded. Inspect prepared content; no run was replayed.')
                            db.execute('UPDATE preparation_runs SET document=? WHERE id=?', (json.dumps(run), run_id)); interrupted = True
                    if interrupted:
                        config = self.config(db); config.update(enabled=False, state='needs_review', reason='Interrupted preparation. Review files before starting a new schedule.')
                        self.save(db, config)
            finally: self.owner.release()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db: yield db
        finally: db.close()

    @staticmethod
    def config(db): return json.loads(db.execute('SELECT document FROM preparation_config WHERE id=1').fetchone()[0])

    @staticmethod
    def save(db, config): db.execute('UPDATE preparation_config SET document=? WHERE id=1', (json.dumps(config),))

    def status(self):
        with self.connect() as db:
            config = self.config(db)
            runs = [json.loads(row[0]) for row in db.execute('SELECT document FROM preparation_runs ORDER BY rowid DESC LIMIT 30')]
        return {'config': config, 'runs': runs, 'workerRunning': bool(self.thread and self.thread.is_alive()),
                'workerError': self.worker_error, 'phoneInput': False, 'publishing': False, 'messaging': False}

    def prepared_packages(self): return read_prepared_packages(self.path)

    def configure(self, request):
        request_id = str(uuid.UUID(request.get('id', '')))
        minutes, limit = request.get('interval_minutes'), request.get('max_runs')
        if request.get('device_id') != 'C24C' or request.get('action') != 'create-content':
            raise ValueError('Only local C24C content preparation can be scheduled.')
        if type(minutes) is not int or not 60 <= minutes <= 10080 or type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError('Choose 60–10,080 minutes and 1–30 runs. The first local preparation is due immediately.')
        fingerprint = hashlib.sha256(json.dumps([minutes, limit, 'C24C', 'create-content']).encode()).hexdigest()
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT fingerprint FROM preparation_requests WHERE id=?', (request_id,)).fetchone()
            if existing:
                if existing[0] not in (fingerprint, 'cancelled'): raise ValueError('Schedule request ID belongs to different work.')
            else:
                if any(r['state'] == 'running' for r in self.status()['runs']):
                    raise ValueError('A local preparation is running. Pause can stop future runs; let this render finish.')
                config = {'id': request_id, 'enabled': True, 'state': 'scheduled', 'deviceId': 'C24C',
                          'intervalMinutes': minutes, 'maxRuns': limit, 'completedRuns': 0, 'attemptedRuns': 0,
                          'nextDue': self.clock(), 'reason': 'Local preparation only. Review generated media before transfer.'}
                db.execute('INSERT INTO preparation_requests VALUES (?,?)', (request_id, fingerprint)); self.save(db, config)
        return self.status()

    def pause(self, cancel_request_id=None):
        if cancel_request_id is not None: cancel_request_id = str(uuid.UUID(cancel_request_id))
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if cancel_request_id is not None:
                db.execute('INSERT OR REPLACE INTO preparation_requests VALUES (?,?)', (cancel_request_id, 'cancelled'))
            config = self.config(db)
            config.update(enabled=False, state='paused', reason='Future runs are paused. An already running local render may finish.')
            self.save(db, config)
        return self.status()

    def tick(self):
        # No schedule enabled: nothing to do, and the operation lock stays free. Taking it every second just to
        # find that out made a run request landing in that moment fail with 'already running' (A18, 5 Nov 16:24).
        with self.connect() as db:
            if not self.config(db).get('enabled'): return
        # Shares the same boundary as manual jobs. Never compete with an active render.
        if not self.operation_lock.acquire(blocking=False): return
        try:
            if not self.owner.acquire(): return
            try: self._tick_owned()
            finally: self.owner.release()
        finally: self.operation_lock.release()

    def _tick_owned(self):
        with self.lock, self.connect() as db:
            config = self.config(db); now = self.clock()
            if not config['enabled'] or now < config['nextDue']: return
            run_id = str(uuid.uuid5(uuid.UUID(config['id']), str(config['nextDue'])))
            if db.execute('SELECT 1 FROM preparation_runs WHERE id=?', (run_id,)).fetchone(): return
            if now - config['nextDue'] > 120:
                run = {'id': run_id, 'scheduleId': config['id'], 'due': config['nextDue'], 'state': 'missed', 'error': 'Missed run was skipped; no catch-up burst.'}
                config['nextDue'] = now + config['intervalMinutes'] * 60
                db.execute('INSERT INTO preparation_runs VALUES (?,?)', (run_id, json.dumps(run))); self.save(db, config); return
            persona = self.persona()
            if persona.get('paused_zero_view') or persona.get('account_day', 0) <= 3:
                config.update(enabled=False, state='held', reason='Profile phase or review pause prevents preparation. Review the profile before creating a new schedule.')
                self.save(db, config); return
            run = {'id': run_id, 'scheduleId': config['id'], 'due': config['nextDue'], 'startedAt': now, 'state': 'running'}
            config['attemptedRuns'] += 1
            config['nextDue'] = now + config['intervalMinutes'] * 60
            db.execute('INSERT INTO preparation_runs VALUES (?,?)', (run_id, json.dumps(run))); self.save(db, config)
        # Acceptance is durable before rendering. Exceptions or process death never retry this run.
        try:
            items = self.prepare()
            if (not isinstance(items, list) or not 1 <= len(items) <= 20 or
                    any(not isinstance(item, dict) or type(item.get('id')) is not int or item['id'] <= 0 or
                        any(not isinstance(item.get(key), str) or not item[key] for key in ('platform', 'format')) or
                        not isinstance(item.get('caption'), str) or not isinstance(item.get('stagedFiles'), list) or
                        not item['stagedFiles'] or any(not isinstance(name, str) or not name for name in item['stagedFiles'])
                        for item in items)):
                raise ValueError('No complete reviewable content record was produced.')
            # Retain references/copy for this run when a later slate replaces the current manifest.
            content = [{k: item[k] for k in ('id', 'platform', 'format', 'caption', 'stagedFiles', 'generation', 'manifest', 'manifestSha256', 'localDraft') if k in item}
                       for item in items]
            run.update(state='succeeded', itemCount=len(items), contentItems=content)
        except Exception as exc:
            run.update(state='failed', error=str(exc))
        run['finishedAt'] = self.clock()
        with self.lock, self.connect() as db:
            current = self.config(db)
            db.execute('UPDATE preparation_runs SET document=? WHERE id=?', (json.dumps(run), run_id))
            if current.get('id') == config['id']:
                if run['state'] == 'failed':
                    current.update(enabled=False, state='needs_review', reason='Local preparation failed; review before starting a new schedule.')
                else:
                    current['completedRuns'] += 1
                    if current['attemptedRuns'] >= current['maxRuns']:
                        current.update(enabled=False, state='complete', reason='Run limit reached. No further work is scheduled.')
                self.save(db, current)

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.stop_event.clear()
        def loop():
            while not self.stop_event.wait(1):
                try: self.tick()
                except Exception as exc:
                    # A storage failure cannot be treated as success; stop future polling.
                    self.worker_error = str(exc); self.stop_event.set()
                    return
        self.thread = threading.Thread(target=loop, daemon=True, name='farm-local-preparation')
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=2)
