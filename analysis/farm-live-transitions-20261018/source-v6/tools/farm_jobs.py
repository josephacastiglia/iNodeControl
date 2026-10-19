"""Single-owner farm jobs with idempotent submission and cooperative cancellation."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from farm_transfers import _ListenerOwner


class JobCancelled(RuntimeError):
    pass


@dataclass
class Job:
    id: str
    fingerprint: str
    action: str
    status: str = "queued"
    result: dict | None = None
    error: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    heartbeat: float = field(default_factory=time.monotonic)
    monitor_error: str | None = None

    def public(self):
        return {"id": self.id, "action": self.action, "status": self.status,
                "result": self.result, "error": self.error,
                "terminal": self.done.is_set()}


class FarmJobs:
    def __init__(self, heartbeat_seconds=30, journal_path=None):
        self._lock = threading.RLock()
        self._jobs = {}
        self._cancelled_ids = set()
        self._active = None
        self._local = threading.local()
        self.heartbeat_seconds = heartbeat_seconds
        self.journal_path = Path(journal_path) if journal_path else None
        self.owner = _ListenerOwner(self.journal_path.with_suffix('.worker-lock')) if self.journal_path else None
        if self.journal_path:
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.journal_path)
            try:
                with connection:
                    connection.execute("CREATE TABLE IF NOT EXISTS farm_jobs (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, record TEXT NOT NULL)")
                    connection.execute('CREATE TABLE IF NOT EXISTS farm_job_cancellations (id TEXT PRIMARY KEY)')
            finally:
                connection.close()

    @staticmethod
    def _cancelled_record(request_id):
        return dict(id=request_id, action='not_started', status='cancelled', result=None,
                    error='Cancelled before admission. No job ran and this ID cannot start later.', terminal=True)

    def _stored(self, request_id, *, owned=False):
        if not self.journal_path:
            return (None, self._cancelled_record(request_id)) if request_id in self._cancelled_ids else None
        connection = sqlite3.connect(self.journal_path)
        try:
            connection.execute('BEGIN')  # Job and cancellation must describe one journal snapshot.
            row = connection.execute("SELECT fingerprint, record FROM farm_jobs WHERE id = ?", (request_id,)).fetchone()
            cancelled = connection.execute('SELECT 1 FROM farm_job_cancellations WHERE id=?', (request_id,)).fetchone()
        finally:
            connection.close()
        if row:
            record = json.loads(row[1])
            if not record["terminal"]:
                probe = _ListenerOwner(self.owner.path)
                if owned or probe.acquire():
                    try:
                        # Completion can commit between the first read and lock
                        # acquisition. Do not replace that result with uncertainty.
                        connection = sqlite3.connect(self.journal_path)
                        try:
                            latest = connection.execute('SELECT record FROM farm_jobs WHERE id=?', (request_id,)).fetchone()
                            if latest: record = json.loads(latest[0])
                        finally: connection.close()
                        if not record['terminal']:
                            record.update(status="interrupted", terminal=True, error="Server restarted. Previous actions have an unknown outcome and will not be replayed.")
                    finally: probe.release()
                else:
                    record.update(status='running_elsewhere', error='Another backend still owns this job. Check that backend for completion; no work was replayed.')
            return row[0], record
        return (None, self._cancelled_record(request_id)) if cancelled else None

    def _admit(self, job):
        if not self.journal_path:
            return job.id not in self._cancelled_ids
        connection = sqlite3.connect(self.journal_path)
        try:
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                if connection.execute('SELECT 1 FROM farm_job_cancellations WHERE id=?', (job.id,)).fetchone(): return False
                connection.execute('INSERT INTO farm_jobs VALUES (?,?,?)', (job.id, job.fingerprint, json.dumps(job.public())))
                return True
        finally: connection.close()

    def _persist(self, job):
        if not self.journal_path:
            return
        connection = sqlite3.connect(self.journal_path)
        try:
            with connection:
                connection.execute("INSERT OR REPLACE INTO farm_jobs (id, fingerprint, record) VALUES (?, ?, ?)",
                                   (job.id, job.fingerprint, json.dumps(job.public())))
        finally:
            connection.close()

    def _cancel_requested(self, request_id):
        if not self.journal_path: return request_id in self._cancelled_ids
        connection = sqlite3.connect(self.journal_path)
        try: return bool(connection.execute('SELECT 1 FROM farm_job_cancellations WHERE id=?', (request_id,)).fetchone())
        finally: connection.close()

    @property
    def in_worker(self):
        return getattr(self._local, "job", None) is not None

    def assert_available(self):
        with self._lock:
            if self._active and not self.in_worker:
                raise ValueError("A farm job is already running. Wait or cancel it first.")

    def submit(self, request_id, action, payload, run):
        if not isinstance(request_id, str):
            raise ValueError("request_id must be a UUID string.")
        request_id = str(uuid.UUID(request_id))
        fingerprint = hashlib.sha256(json.dumps([action, payload], sort_keys=True, allow_nan=False).encode()).hexdigest()
        with self._lock:
            existing = self._jobs.get(request_id)
            if existing:
                if existing.fingerprint != fingerprint:
                    raise ValueError("Request ID was already used for different work.")
                return existing.public()  # Never replay a completed or uncertain request.
            stored = self._stored(request_id)
            if stored:
                if stored[0] is not None and stored[0] != fingerprint:
                    raise ValueError("Request ID was already used for different work.")
                return stored[1]
            self.assert_available()
            if len(self._jobs) >= 100:
                if not self.journal_path:
                    raise ValueError("Job history is full; a persistent journal is required.")
                self._jobs = {key: value for key, value in self._jobs.items() if not value.done.is_set()}
            job = Job(request_id, fingerprint, action)
            if self.owner and not self.owner.acquire(): raise ValueError('Another backend owns the job worker for this data folder.')
            try:
                # Recheck after acquiring the OS lock; another process may have
                # completed this ID while we were reading the journal.
                stored = self._stored(request_id, owned=True)
                if stored:
                    if stored[0] is not None and stored[0] != fingerprint: raise ValueError('Request ID was already used for different work.')
                    if self.owner: self.owner.release()
                    return stored[1]
                if not self._admit(job):
                    if self.owner: self.owner.release()
                    return self._cancelled_record(job.id)
                self._jobs[job.id] = job; self._active = job.id
                try: threading.Thread(target=self._run, args=(job, run), daemon=True).start()
                except Exception as exc:
                    job.status, job.error = 'failed', 'Worker did not start: ' + str(exc)
                    job.done.set(); self._active = None; self._persist(job)
                    raise
                return job.public()
            except BaseException:
                if self.owner: self.owner.release()
                raise

    def _run(self, job, run):
        self._local.job = job
        with self._lock:
            job.status = "running"
        watcher = threading.Thread(target=self._watch, args=(job,), daemon=True)
        try:
            watcher.start()
            if self._cancel_requested(job.id): job.cancel.set()
            if job.cancel.is_set():
                raise JobCancelled("Cancelled before starting.")
            result = run(job.cancel)
            with self._lock:
                job.result = result
                job.status = "cancelled" if job.cancel.is_set() else "succeeded"
        except JobCancelled as exc:
            with self._lock:
                job.status, job.error = "cancelled", str(exc)
        except Exception as exc:
            # Cleanup failures stay failures, even when cancellation was requested.
            with self._lock:
                job.status, job.error = "failed", str(exc)
        finally:
            with self._lock:
                if job.monitor_error: job.status, job.error = 'failed', job.monitor_error
                job.done.set()
                try:
                    self._persist(job)
                except Exception as exc:
                    job.status, job.error = "failed", "Job outcome could not be saved: " + str(exc)
                self._active = None
                if self.owner: self.owner.release()
            if watcher.ident is not None: watcher.join(timeout=2)
            self._local.job = None

    def _watch(self, job):
        while not job.done.wait(min(1, self.heartbeat_seconds / 2)):
            with self._lock:
                # Completion may land after wait() returns but before this lock.
                # A late monitor must never turn a terminal result into cancelling.
                if job.done.is_set(): return
                try:
                    if self._cancel_requested(job.id): job.cancel.set(); job.status = 'cancelling'; return
                except Exception as exc:
                    job.monitor_error = 'Cancellation monitor failed; work was cancelled: ' + str(exc)
                    job.cancel.set(); return
                if time.monotonic() - job.heartbeat > self.heartbeat_seconds:
                    job.cancel.set()
                    job.status = "cancelling"
                    return

    def get(self, request_id, heartbeat=True):
        request_id = str(uuid.UUID(request_id))
        with self._lock:
            if request_id not in self._jobs:
                stored = self._stored(request_id)
                if stored:
                    return stored[1]
                raise KeyError(request_id)
            job = self._jobs[request_id]
            if heartbeat:
                job.heartbeat = time.monotonic()
            return job.public()

    def cancel(self, request_id):
        request_id = str(uuid.UUID(request_id))
        with self._lock:
            job = self._jobs.get(request_id)
            if job and job.done.is_set(): return job.public()
            if job: job.cancel.set(); job.status = 'cancelling'
            if self.journal_path:
                connection = sqlite3.connect(self.journal_path)
                try:
                    with connection:
                        connection.execute('BEGIN IMMEDIATE')
                        row = connection.execute('SELECT record FROM farm_jobs WHERE id=?', (request_id,)).fetchone()
                        if row and json.loads(row[0])['terminal']: return json.loads(row[0])
                        connection.execute('INSERT OR IGNORE INTO farm_job_cancellations VALUES (?)', (request_id,))
                finally: connection.close()
            else: self._cancelled_ids.add(request_id)
            return job.public() if job else self.get(request_id, heartbeat=False)

    def cancel_active(self):
        with self._lock:
            if self._active:
                return self.cancel(self._active)
            return None

    def current(self):
        with self._lock:
            return self._jobs[self._active].public() if self._active else None
