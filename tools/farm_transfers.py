"""Durable, explicitly started carousel delivery sessions. Never controls a phone."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from farm_media_transfer import MediaTransferServer, TransferPackage, checked_address


class TransferConflict(ValueError):
    pass


class _ListenerOwner:
    """OS lock survives competing backend instances, and releases on process exit."""
    def __init__(self, path):
        self.path, self.file = path, None

    def acquire(self):
        file = open(self.path, 'a+b')
        if file.tell() == 0:
            file.write(b'\0'); file.flush()
        file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            file.close()
            return False
        self.file = file
        return True

    def release(self):
        if self.file:
            self.file.close()
            self.file = None


class CarouselTransfers:
    def __init__(self, database: Path, drafts, *, videos=None, clock=time.monotonic):
        self.database, self.drafts, self.clock = Path(database), drafts, clock
        self.videos = videos
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.owner = _ListenerOwner(self.database.with_suffix('.listener-lock'))
        self.server = self.thread = self.stop_event = self.active_id = None
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS transfers (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, record TEXT NOT NULL, sequence INTEGER NOT NULL)')
        # A second process must not mark a still-serving first process interrupted.
        if self.owner.acquire():
            try:
                with self._db() as db:
                    for row in db.execute('SELECT id,record FROM transfers').fetchall():
                        value = json.loads(row[1])
                        if value['state'] in ('starting', 'serving', 'stopping'):
                            value.update(state='interrupted', error='Backend restarted. Delivery was not resumed; check the phone before starting a new session.')
                            db.execute('UPDATE transfers SET record=? WHERE id=?', (json.dumps(value), row[0]))
            finally:
                self.owner.release()

    @contextmanager
    def _db(self):
        connection = sqlite3.connect(self.database, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _read(self, session_id):
        with self._db() as db:
            row = db.execute('SELECT record FROM transfers WHERE id=?', (session_id,)).fetchone()
        if row is None:
            raise KeyError('Transfer session not found. Do not assume it completed.')
        return json.loads(row[0])

    def _write(self, value):
        with self._db() as db:
            db.execute('UPDATE transfers SET record=? WHERE id=?', (json.dumps(value), value['id']))

    def get(self, session_id):
        with self.lock:
            value = self._read(session_id)
            value['url'] = None
            value['secondsRemaining'] = 0
            if self.active_id == session_id and self.server is not None and value['state'] == 'serving':
                value['secondsRemaining'] = max(0, int(self.server.deadline - self.clock()))
                if value['secondsRemaining'] > 0:
                    value['url'] = self.server.url
            return value

    def current(self):
        with self.lock, self._db() as db:
            row = db.execute('SELECT id FROM transfers ORDER BY sequence DESC LIMIT 1').fetchone()
            return self.get(row[0]) if row else None

    def start(self, request):
        if not isinstance(request, dict) or any(not isinstance(request.get(k), str) for k in ('id', 'draft_id', 'account', 'bind', 'client')):
            raise ValueError('Transfer IDs, account and IP addresses must be text.')
        session_id = str(uuid.UUID(request.get('id', '')))
        draft_id = str(uuid.UUID(request.get('draft_id', '')))
        revision = request.get('revision')
        if type(revision) is not int or revision < 1:
            raise ValueError('Choose a saved draft revision.')
        if request.get('device_id') != 'C24C':
            raise ValueError('Media transfer is restricted to C24C.')
        account = request.get('account', '').strip().removeprefix('@')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,50}', account):
            raise ValueError('Enter the app account handle you will verify on C24C.')
        kind = request.get('kind', 'carousel')
        if kind not in ('carousel', 'video') or (kind == 'video' and self.videos is None):
            raise ValueError('Unsupported media draft kind.')
        bind, client = checked_address(request.get('bind', '')), checked_address(request.get('client', ''))
        port, minutes = request.get('port', 9916), request.get('minutes', 20)
        if type(port) is not int or port not in range(1024, 65536) or port in (9911, 9913, 9914, 9915):
            raise ValueError('Choose an unused media port between 1024 and 65535, separate from control services.')
        if type(minutes) is not int or not 1 <= minutes <= 60:
            raise ValueError('Transfer duration must be 1–60 minutes.')
        request = dict(id=session_id, draft_id=draft_id, revision=revision, device_id='C24C',
                       account=account, bind=bind, client=client, port=port, minutes=minutes, kind=kind)
        fingerprint_data = {k: v for k, v in request.items() if k != 'kind' or kind != 'carousel'}
        fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()
        with self.lock:
            with self._db() as db:
                old = db.execute('SELECT fingerprint FROM transfers WHERE id=?', (session_id,)).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise TransferConflict('This request ID belongs to different transfer settings.')
                return self.get(session_id)  # Never reopen a closed/failed/interrupted session.
            if self.active_id is not None:
                raise TransferConflict('A transfer is already open. Check or stop it before starting another.')
            if kind == 'video':
                from farm_video import VideoTransferPackage
                package = VideoTransferPackage(self.videos.export(draft_id, revision), self.videos.board)
            else:
                package = TransferPackage(self.drafts.export(draft_id, revision))
            value = {**request, 'state': 'starting', 'createdAt': datetime.now(timezone.utc).isoformat(),
                     'packageSha256': package.package_hash, 'slideCount': len(package.images), 'imagesDelivered': [],
                     'videoRequests': 0, 'platform': getattr(package, 'platform', 'Instagram'),
                     'deliveryMode': 'real_media_only', 'photosStatus': 'unverified', 'instagramStatus': 'unverified',
                     'publicationAttempted': False, 'error': None}
            if not self.owner.acquire():
                raise TransferConflict('Another backend owns the media transfer. Use its transfer controls.')
            try:
                with self._db() as db:
                    # Recheck after acquiring the cross-process lock.
                    old = db.execute('SELECT fingerprint FROM transfers WHERE id=?', (session_id,)).fetchone()
                    if old:
                        if old[0] != fingerprint:
                            raise TransferConflict('This request ID belongs to different transfer settings.')
                        self.owner.release()
                        return self.get(session_id)
                    db.execute('INSERT INTO transfers VALUES (?,?,?,(SELECT COALESCE(MAX(sequence),0)+1 FROM transfers))',
                               (session_id, fingerprint, json.dumps(value)))
            except Exception:
                self.owner.release()
                raise
            try:
                server = MediaTransferServer(package, bind, port, client, minutes=minutes,
                                             clock=self.clock, on_event=lambda event: self._delivered(session_id, event))
            except Exception as exc:
                self.owner.release()
                value.update(state='failed', error=f'Media listener could not start: {exc}')
                self._write(value)
                return self.get(session_id)
            self.active_id, self.server, self.stop_event = session_id, server, threading.Event()
            value['state'] = 'serving'
            try:
                self._write(value)
                self.thread = threading.Thread(target=self._serve, args=(session_id, server, self.stop_event), daemon=True)
                self.thread.start()
            except Exception:
                server.server_close()
                self.owner.release()
                self.active_id = self.server = self.stop_event = self.thread = None
                value.update(state='failed', error='Could not start or record the delivery worker.')
                self._write(value)
                raise
            return self.get(session_id)

    def _delivered(self, session_id, event):
        video = event['route'] == 'video.mp4'
        if event['status'] not in (200, 206) or event['method'] != 'GET' or not (video or re.fullmatch(r'\d{2}\.jpg', event['route'])):
            return
        with self.lock:
            value = self._read(session_id)
            if video: value['videoRequests'] += 1  # Partial ranges are requests, never completed saves.
            else: value['imagesDelivered'] = sorted(set(value['imagesDelivered']) | {event['route']})
            self._write(value)  # A GET is never a Photos save or an Instagram save.

    def _serve(self, session_id, server, stopped):
        error = None
        try:
            while not stopped.is_set() and self.clock() < server.deadline:
                server.handle_request()
        except Exception as exc:
            error = f'Delivery stopped: {exc}'
        finally:
            server.server_close()
            with self.lock:
                try:
                    value = self._read(session_id)
                    value.update(state='failed' if error else 'closed' if stopped.is_set() else 'expired', error=error)
                    self._write(value)
                finally:
                    self.active_id = self.server = self.stop_event = self.thread = None
                    self.owner.release()

    def stop(self, session_id):
        with self.lock:
            value = self._read(session_id)
            thread = self.thread if self.active_id == session_id else None
            if thread is not None:
                self.stop_event.set()
                self.server.close_clients()
                value['state'] = 'stopping'
                self._write(value)
        if thread is not None:
            thread.join(4)
        return self.get(session_id)

    def close(self):
        with self.lock:
            session_id = self.active_id
        if session_id:
            self.stop(session_id)
