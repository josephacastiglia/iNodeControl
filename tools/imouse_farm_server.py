#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iMouse 2.0 Marketing Farm backend (loopback only, default port 9914).

Draft-only: it prepares content, keeps drafts and their evidence, and runs one phone's draft
creation routes when it is started as that phone's window. Nothing here publishes, messages or
engages, and there is no simulated version of any of that.

  GET  /health                         identity (sourceHash) and each creation route's capability
  GET  /api/farm/state                 whether a job is running
  POST /api/farm/create-content        render one batch of review media from local templates (no phone)
  POST /api/farm/jobs, GET /api/farm/jobs/{id}, POST /api/farm/jobs/{id}/cancel
  POST /api/farm/emergency-stop        cancel the job and pause preparation
  /api/farm/drafts*, image-drafts*, video-drafts*, video-sources, transfers*
  /api/farm/draft-creations*, reel-creations*, tiktok-creations*, x-creations*, youtube-creations*,
            x-image-creations*, tiktok-photo-creations*    (enabled only with --draft-creation-config)
  /api/farm/draft-verifications*, observations*, preparation-schedule*, schedule-queue*

--mode names the data folder (output/farm-data/v2/<mode>) and gates the phone configuration: a
creation config is accepted only with --mode live. Neither mode simulates anything.
"""

from __future__ import annotations

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import random
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import imouse_social_automation as engine
from farm_jobs import FarmJobs, JobCancelled
from farm_drafts import CarouselDrafts, DraftConflict
from farm_transfers import CarouselTransfers, TransferConflict
from farm_video import VideoDrafts
from farm_image import ImageDrafts
from farm_observations import ObservationStore, WindowsOcr
from farm_draft_verification import DraftVerifications
from farm_draft_runs import phone_of
from farm_creation_runs import CreationRuns, creation_config
from farm_reel_runs import ReelCreationRuns
from farm_tiktok_runs import TikTokCreationRuns
from farm_tiktok_photo_runs import TikTokPhotoCreationRuns
from farm_x_runs import XCreationRuns, XImageCreationRuns
from farm_youtube_runs import YouTubeCreationRuns
from farm_preparation_schedule import PreparationSchedule
from farm_schedule_queue import ReviewQueue
from farm_paths import MAIN as FARM_MAIN

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9914
# The pre-rack single-phone kernel, read only by the observations route.
KERNEL_BASE_URL = "http://127.0.0.1:9913/api"
JOB_ACTIONS = {"create-content"}


class FarmControlServer(ThreadingHTTPServer):
    """The control API never shares a port or exposes itself on the LAN."""
    allow_reuse_address = False

    def server_bind(self):
        if self.server_address[0] not in ('127.0.0.1', 'localhost'):
            raise ValueError('The farm control server must use loopback. Use the media transfer service for phone downloads.')
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class FarmBackendRuntime:
    """One backend's stores and services, all under one data folder."""

    def __init__(
        self,
        db_path: Path | None = None,
        stage_root: Path | None = None,
        port: int = DEFAULT_PORT,
        execution_mode: str = "simulate",
        draft_creation_config: Path | None = None,
    ) -> None:
        if execution_mode not in ("simulate", "live"):
            raise ValueError("Execution mode must be simulate or live.")
        self.execution_mode = execution_mode
        create_config = creation_config(draft_creation_config, execution_mode)
        self.operation_lock = threading.RLock()
        source = Path(__file__).resolve().parent
        import hashlib
        self.source_hash = hashlib.sha256(b"".join((source / name).read_bytes() for name in ("imouse_farm_server.py", "imouse_social_automation.py", "farm_jobs.py", "farm_drafts.py", "farm_media_transfer.py", "farm_transfers.py", "farm_video.py", "farm_image.py", "farm_observations.py", "Read-FarmImageText.ps1", "farm_preparation_schedule.py", "farm_frame_evidence.py", "farm_draft_verification.py", "farm_draft_media.py", "farm_owned_capture.py", "farm_screen_layout.py", "farm_transitions.py", "farm_live_verification.py", "farm_draft_transport.py", "farm_draft_workflow.py", "farm_draft_runs.py", "farm_draft_anchors.json", "farm_draft_creation.py", "farm_creation_runs.py", "farm_creation_layout.py", "farm_home_edit.py", "farm_creation_badges.json", "farm_creation_browser.json", "farm_creation_controls.json", "farm_reel_layout.py", "farm_reel_controls.json", "farm_reel_creation.py", "farm_reel_runs.py", "farm_tiktok_layout.py", "farm_tiktok_controls.json", "farm_tiktok_creation.py", "farm_tiktok_runs.py", "farm_permission_prompts.py", "farm_x_layout.py", "farm_x_creation.py", "farm_x_runs.py", "farm_youtube_layout.py", "farm_youtube_controls.json", "farm_youtube_creation.py", "farm_youtube_runs.py"))).hexdigest()
        db_path = db_path or Path("output/farm-data/v2") / execution_mode / "imouse_farm.db"
        stage_root = stage_root or Path("output/media-stage/v2") / execution_mode
        self.db = engine.FarmDatabase(db_path=db_path)
        self.jobs = FarmJobs(journal_path=db_path.parent / "jobs.db")
        self.stage_root = stage_root
        self.drafts = CarouselDrafts(db_path.parent / "carousel-drafts.db", stage_root)
        # A window's videos are staged and stamped for its own phone.
        self.videos = VideoDrafts(db_path.parent / "video-drafts.db", stage_root, phone_of(create_config).board if create_config else "C24C")
        # Image drafts (X image, TikTok photo) are staged and stamped for the window's phone the same way.
        self.images = ImageDrafts(db_path.parent / "image-drafts.db", stage_root, phone_of(create_config).board if create_config else "C24C")
        # The carousel's reviews read the editor's Next label from its own crop, as its creation flow does.
        self.observations = ObservationStore(db_path.parent / 'observations.db', WindowsOcr(next_control=True))
        self.verifications = DraftVerifications(db_path.parent / 'draft-verifications.db', self.observations, self.drafts)
        self.draft_creations = CreationRuns(db_path.parent / 'draft-creations', self.drafts, self.jobs, create_config)
        # Same explicit isolated kernel/media configuration as carousel creation.
        self.reel_creations = ReelCreationRuns(db_path.parent / 'reel-creations', self.videos, self.jobs, create_config)
        self.tiktok_creations = TikTokCreationRuns(db_path.parent / 'tiktok-creations', self.videos, self.jobs, create_config)
        self.x_creations = XCreationRuns(db_path.parent / 'x-creations', self.videos, self.jobs, create_config)
        self.youtube_creations = YouTubeCreationRuns(db_path.parent / 'youtube-creations', self.videos, self.jobs, create_config)
        self.x_image_creations = XImageCreationRuns(db_path.parent / 'x-image-creations', self.images, self.jobs, create_config)
        self.tiktok_photo_creations = TikTokPhotoCreationRuns(db_path.parent / 'tiktok-photo-creations', self.images, self.jobs, create_config)
        self.transfers = CarouselTransfers(db_path.parent / "transfers.db", self.drafts, videos=self.videos)
        self.port = port
        self.rng = random.Random()
        self.spinner = engine.AntiDuplicateSpinEngine(rng=self.rng)
        self.factory = engine.ContentFactoryEngine(
            db=self.db,
            spinner=self.spinner,
            stage_root=self.stage_root,
            rng=self.rng,
        )
        # The operator's review queue (farm_schedule_cli.py uses the same file). Review only here:
        # nothing in this server runs a planned slot on a phone.
        self.schedule_queue_path = FARM_MAIN / 'output/farm-schedule/queue.json'
        self.preparation = PreparationSchedule(db_path.parent / 'preparation-schedule.db',
            lambda: self.prepare_local_content('C24C'),
            lambda: self.db.get_persona('C24C'), self.operation_lock)

    def prepare_local_content(self, device_id):
        """Render locally, then retain this exact batch as an editable carousel.

        A failure after rendering leaves files for inspection, not a successful
        schedule result. Repeated snapshot requests never overwrite local edits.
        """
        items = self.factory.generate_daily_slate_for_device(device_id)
        if not items or device_id != 'C24C': return items
        import uuid
        carousels = [item for item in items if item.get('platform') == 'instagram' and item.get('format') == 'ig_carousel']
        if len(carousels) != 1: raise ValueError('Generated batch needs exactly one Instagram carousel for review.')
        item = carousels[0]
        generation, checksum = item.get('generation'), item.get('manifestSha256')
        if (not generation or not checksum or any(row.get('generation') != generation or row.get('manifestSha256') != checksum
                or row.get('manifest') != f'/stage/C24C/manifest_{generation}.json' for row in items)):
            raise ValueError('Generated slate records do not identify one immutable C24C batch.')
        draft_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'imouse:prepared-carousel:{generation}:{checksum}'))
        draft = self.drafts.create(draft_id, f'Prepared carousel {generation}', True,
                                   source_generation=generation, manifest_sha256=checksum)
        if draft['status'] != 'ready_local': raise ValueError('Generated carousel is not ready for local review.')
        item['localDraft'] = {key: draft[key] for key in ('id', 'revision', 'sourceGeneration', 'sourceManifestSha256')}
        return items

    def create_content(self, payload, cancelled=None):
        """Render one batch of review media from local templates and keep its carousel as a local draft.
        No phone and no kernel: the files land in the stage folder for a person to review."""
        device = engine.persona_device_id(payload.get("device_id", "C24C"))
        self.db.get_persona(device)
        if cancelled is not None and cancelled.is_set():
            raise JobCancelled("Farm job cancelled; previous actions will not be replayed.")
        slate = self.prepare_local_content(device)
        if not slate:
            raise ValueError("This profile is in warmup or paused; no content was generated.")
        return {"status": "ok", "slates": slate, "manifest": f"/stage/{device}/manifest.json",
                "contentSource": "local_templates", "reviewRequired": True}

    def submit_job(self, request_id, action, payload):
        if action not in JOB_ACTIONS or not isinstance(payload, dict):
            raise ValueError("Unknown action or invalid job payload.")
        def run(cancelled):
            # The same single-operation boundary every other request takes.
            if not self.operation_lock.acquire(blocking=False):
                raise ValueError("A farm operation is already running. Wait or cancel it first.")
            try:
                return {**self.create_content(payload, cancelled), "executionMode": self.execution_mode}
            finally:
                self.operation_lock.release()
        return self.jobs.submit(request_id, action, payload, run)


RUNTIME: FarmBackendRuntime | None = None
# Every draft creation route has the same shape: GET the list, eligibility, one run and its retained frames;
# POST to start a run or to stop one. Route -> (runtime attribute, its key in /health, and the three messages
# its refusals have always used).
CREATION_ROUTES = {
    'draft-creations': ('draft_creations', 'draftCreation', 'Draft run evidence is local-only.', 'Unknown draft run route.',
                        'Stop needs this candidate store and the original request ID.'),
    **{name: (attribute, health, label + ' draft evidence is local-only.', 'Unknown ' + label + ' draft route.',
              'Stop needs this ' + label + ' candidate store and the original request ID.')
       for name, attribute, health, label in (
           ('reel-creations', 'reel_creations', 'reelCreation', 'Reel'),
           ('tiktok-creations', 'tiktok_creations', 'tiktokCreation', 'TikTok'),
           ('x-creations', 'x_creations', 'xCreation', 'X'),
           ('youtube-creations', 'youtube_creations', 'youtubeCreation', 'YouTube'),
           ('x-image-creations', 'x_image_creations', 'xImageCreation', 'X image'),
           ('tiktok-photo-creations', 'tiktok_photo_creations', 'tiktokPhotoCreation', 'TikTok photo'))},
}
CREATION_PATHS = tuple('/api/farm/' + name for name in CREATION_ROUTES)
# Never answered to another origin or another host name: media, evidence and preparation controls.
LOCAL_ONLY = ('/api/farm/transfers', '/api/farm/observations', '/api/farm/preparation-schedule', '/api/farm/schedule-queue',
              '/api/farm/draft-verifications') + CREATION_PATHS


class FarmRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[iMouse-Farm-9914] {self.address_string()} - {fmt % args}")

    def _is_origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "")
        if not origin:
            return True
        parsed = urllib.parse.urlparse(origin)
        return parsed.hostname in ("localhost", "127.0.0.1", "::1")

    def _transfer_access_allowed(self) -> bool:
        # Secret URLs are returned only to local clients addressed to this listener.
        return (self.client_address[0] in ('127.0.0.1', '::1') and self._is_origin_allowed()
                and self.headers.get('Host', '') in {f'127.0.0.1:{self.server.server_port}',
                    f'localhost:{self.server.server_port}', f'[::1]:{self.server.server_port}'})

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if RUNTIME is not None:
            self.send_header("X-Farm-Execution-Mode", RUNTIME.execution_mode)
        origin = self.headers.get("Origin", "")
        if origin and self._is_origin_allowed():
            self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        if RUNTIME is not None:
            payload = {**payload, "protocolVersion": 2, "executionMode": RUNTIME.execution_mode}
        raw = json.dumps(payload, indent=2).encode("utf-8")
        self._send_bytes(status, "application/json; charset=utf-8", raw)

    def do_OPTIONS(self) -> None:
        if not self._is_origin_allowed():
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        origin = self.headers.get("Origin", "")
        if origin and self._is_origin_allowed():
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        assert RUNTIME is not None
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        route = next((name for name in CREATION_ROUTES if path == '/api/farm/' + name or path.startswith('/api/farm/' + name + '/')), None)
        if route:
            attribute, _, local_only, unknown, _ = CREATION_ROUTES[route]
            if not self._transfer_access_allowed():
                self._send_json(403, {'error': local_only}); return
            try:
                parts = path.split('/')
                query = urllib.parse.parse_qs(parsed.query)
                service = getattr(RUNTIME, attribute)
                if path == '/api/farm/' + route + '/eligibility':
                    self._send_json(200, {'eligibility': service.eligibility(query.get('draft_id', [''])[0], int(query.get('revision', ['0'])[0]))})
                elif path == '/api/farm/' + route:
                    self._send_json(200, {'runs': service.list(query.get('draft_id', [''])[0])})
                elif len(parts) == 7 and parts[5] == 'frames':
                    self._send_json(200, {'frame': base64.b64encode(service.frame(parts[4], parts[6])).decode('ascii')})
                elif len(parts) == 5: self._send_json(200, {'run': service.get(parts[4])})
                else: raise ValueError(unknown)
            except (ValueError, KeyError) as error: self._send_json(404, {'error': str(error)})
            return

        if path == '/api/farm/draft-verifications' or path.startswith('/api/farm/draft-verifications/'):
            if not self._transfer_access_allowed():
                self._send_json(403, {'error': 'Draft evidence is local-only.'}); return
            try:
                if path == '/api/farm/draft-verifications':
                    draft_id = urllib.parse.parse_qs(parsed.query).get('draft_id', [''])[0]
                    self._send_json(200, {'verifications': RUNTIME.verifications.list(draft_id)})
                elif '/frames/' in path:
                    parts = path.split('/')
                    if len(parts) != 7 or parts[5] != 'frames': raise ValueError('Invalid review frame route.')
                    self._send_json(200, {'frame': base64.b64encode(RUNTIME.verifications.frame(parts[4], parts[6])).decode('ascii')})
                else: self._send_json(200, {'verification': RUNTIME.verifications.get(path.rsplit('/', 1)[-1])})
            except (ValueError, KeyError) as error: self._send_json(404, {'error': str(error)})
            return

        if path == '/api/farm/schedule-queue':
            if not self._transfer_access_allowed():
                self._send_json(403, {'error': 'The review queue is local-only.'}); return
            queue = ReviewQueue(RUNTIME.schedule_queue_path)
            self._send_json(200, {'scheduleQueue': {'schedule': queue.schedule(), 'plan': queue.plan(), 'pending': queue.pending()},
                                  'startsRuns': False, 'phoneInput': False, 'publishing': False})
            return

        if path == '/api/farm/preparation-schedule':
            if not self._transfer_access_allowed():
                self._send_json(403, {'error': 'Preparation schedule is local-only.'}); return
            self._send_json(200, {'preparationSchedule': RUNTIME.preparation.status()})
            return

        if path == '/api/farm/observations' or path.startswith('/api/farm/observations/'):
            if not self._transfer_access_allowed():
                self._send_json(403, {'error': 'Observations are local-only.'})
                return
            try:
                if path == '/api/farm/observations':
                    self._send_json(200, {'observations': RUNTIME.observations.list()})
                elif path.endswith('/frame'):
                    self._send_json(200, {'frame': base64.b64encode(RUNTIME.observations.frame(path.split('/')[-2])).decode('ascii')})
                else:
                    self._send_json(200, {'observation': RUNTIME.observations.get(path.rsplit('/', 1)[-1])})
            except (KeyError, ValueError) as exc:
                self._send_json(404, {'error': str(exc)})
            return

        if path == '/api/farm/video-sources':
            try:
                query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
                self._send_json(200, {'sources': RUNTIME.videos.sources(query.get('generation', [None])[0], query.get('manifest_sha256', [None])[0])})
            except (ValueError, KeyError, OSError) as ex: self._send_json(400, {'error': str(ex)})
            return
        if path == '/api/farm/video-drafts':
            self._send_json(200, {'drafts': RUNTIME.videos.list()})
            return
        if path == '/api/farm/image-drafts':
            self._send_json(200, {'drafts': RUNTIME.images.list()})
            return
        if path.startswith('/api/farm/image-drafts/'):
            try: self._send_json(200, {'draft': RUNTIME.images.get(path.rsplit('/', 1)[1])})
            except (ValueError, KeyError) as ex: self._send_json(404, {'error': str(ex)})
            return
        if path.startswith('/api/farm/video-drafts/'):
            try: self._send_json(200, {'draft': RUNTIME.videos.get(path.rsplit('/', 1)[1])})
            except (ValueError, KeyError) as ex: self._send_json(404, {'error': str(ex)})
            return
        if path == "/api/farm/transfers/current" or path.startswith("/api/farm/transfers/"):
            if not self._transfer_access_allowed():
                self._send_json(403, {"error": "Cross-origin transfer access refused."})
                return
            try:
                transfer = RUNTIME.transfers.current() if path.endswith("/current") else RUNTIME.transfers.get(path.rsplit("/", 1)[1])
                self._send_json(200, {"transfer": transfer})
            except KeyError as exc:
                self._send_json(404, {"error": str(exc)})
            return

        if path == "/api/farm/drafts" or path.startswith("/api/farm/drafts/"):
            try:
                if path == "/api/farm/drafts":
                    self._send_json(200, {"drafts": RUNTIME.drafts.list()})
                else:
                    self._send_json(200, {"draft": RUNTIME.drafts.get(path[len('/api/farm/drafts/'):])})
            except (KeyError, ValueError) as exc:
                self._send_json(404, {"error": str(exc)})
            return

        if path.startswith("/api/farm/jobs/"):
            try:
                self._send_json(200, {"job": RUNTIME.jobs.get(path.rsplit("/", 1)[1])})
            except KeyError:
                self._send_json(404, {"error": "Job not found. Its outcome must not be assumed or replayed."})
            return

        if path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "port": RUNTIME.port,
                    "sourceHash": RUNTIME.source_hash,
                    "carouselDraftsVersion": 1,
                    "carouselTransfersVersion": 1,
                    "videoDraftsVersion": 1,
                    "observationsVersion": 2,
                    "draftVerificationVersion": 2,
                    **{health: getattr(RUNTIME, attribute).capability() for attribute, health, *_ in CREATION_ROUTES.values()},
                    "imageDraftsVersion": 1,
                    "preparationScheduleVersion": 2,
                },
            )
            return

        if path == "/api/farm/state":
            self._send_json(200, {"status": "ok", "activeJob": RUNTIME.jobs.current(), "carouselDraftsVersion": 1})
            return

        self._send_json(404, {"error": f"Unknown GET path: {path}"})

    def do_POST(self) -> None:
        assert RUNTIME is not None
        if not self._is_origin_allowed():
            self.close_connection = True
            self._send_json(403, {"error": "Cross-origin request forbidden. Only localhost allowed."})
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path.startswith(LOCAL_ONLY) and not self._transfer_access_allowed():
            self.close_connection = True
            self._send_json(403, {"error": "Media, observation and preparation controls are local-only."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            limit = 12 * 1024 * 1024 if path.startswith("/api/farm/drafts/") and path.endswith("/import") else 65536
            if length < 0 or length > limit:
                self._send_json(413, {"error": f"Request body exceeds the {limit}-byte limit."})
                self.close_connection = True
                return
            raw_body = self.rfile.read(length) if length > 0 else b"{}"
            data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            if not isinstance(data, dict):
                raise ValueError("Request must be a JSON object.")
            self._handle_post(path, data, raw_body)
        except (DraftConflict, TransferConflict) as ex:
            self._send_json(409, {"status": "draft_conflict", "error": str(ex)})
        except (ValueError, KeyError, UnicodeError) as ex:
            self._send_json(400, {"status": "invalid_request", "error": str(ex)})
        except engine.KernelSafetyError as ex:
            self._send_json(409, {"status": "safety_refused", "error": str(ex)})
        except JobCancelled as ex:
            self._send_json(409, {"status": "cancelled", "error": str(ex)})
        except Exception as ex:
            self._send_json(500, {"status": "error", "error": str(ex)})

    def _handle_post(self, path: str, data: dict, raw_body: bytes) -> None:
        assert RUNTIME is not None
        # Every request shares one single-operation boundary.
        # Stop and cancellation must remain available while work is in progress.
        interrupt = path == "/api/farm/emergency-stop" or (path.startswith("/api/farm/jobs/") and path.endswith("/cancel"))
        interrupt = interrupt or path == '/api/farm/preparation-schedule/pause'
        interrupt = interrupt or (path.startswith(tuple(route + '/' for route in CREATION_PATHS)) and path.endswith('/cancel'))
        if interrupt or path == "/api/farm/jobs" or (path.startswith("/api/farm/transfers/") and path.endswith("/stop")):
            self._dispatch_post(path, data, raw_body)
            return
        if not RUNTIME.operation_lock.acquire(blocking=False):
            if path in ('/api/farm/video-drafts', '/api/farm/image-drafts'):
                self._send_json(409, {'status': 'preparation_busy', 'error': 'Another preparation is running. Check the saved draft before retrying.'})
                return
            raise ValueError("A farm operation is already running. Wait or cancel it first.")
        try:
            self._dispatch_post(path, data, raw_body)
        finally:
            RUNTIME.operation_lock.release()

    def _dispatch_post(self, path: str, data: dict, raw_body: bytes) -> None:
        assert RUNTIME is not None
        data = dict(data)
        for route, (attribute, _, _, _, stop_refused) in CREATION_ROUTES.items():
            service = getattr(RUNTIME, attribute)
            if path == '/api/farm/' + route:
                self._send_json(202, {'run': service.start(data)}); return
            if path.startswith('/api/farm/' + route + '/') and path.endswith('/cancel'):
                parts = path.split('/')
                if len(parts) != 6 or set(data) != {'store_id'} or data['store_id'] != service.store_id:
                    raise ValueError(stop_refused)
                self._send_json(200, {'job': service.cancel(parts[4])}); return
        if path == '/api/farm/draft-verifications':
            self._send_json(200, {'verification': RUNTIME.verifications.create(data)}); return
        if path == '/api/farm/preparation-schedule':
            self._send_json(200, {'preparationSchedule': RUNTIME.preparation.configure(data)}); return
        if path in ('/api/farm/schedule-queue/approve', '/api/farm/schedule-queue/reject'):
            # Review decisions only; a slot runs only from the operator's runner (farm_schedule_cli.py run).
            package = data.get('id')
            if isinstance(package, str) and package.isdigit(): package = int(package)
            queue = ReviewQueue(RUNTIME.schedule_queue_path)
            if path.endswith('/approve'):
                if set(data) - {'id', 'account'}: raise ValueError('Approve takes only id and account.')
                result = queue.approve(package, data.get('account'))
            else:
                if set(data) - {'id', 'reason'}: raise ValueError('Reject takes only id and reason.')
                result = queue.reject(package, str(data.get('reason', '')))
            self._send_json(200, {'package': result, 'startsRuns': False, 'phoneInput': False}); return
        if path == '/api/farm/preparation-schedule/pause':
            self._send_json(200, {'preparationSchedule': RUNTIME.preparation.pause(data.get('cancel_request_id'))}); return
        if path == '/api/farm/observations':
            if data.get('read_only') is not True or data.get('source') != 'phone':
                raise ValueError('Choose an explicit read-only C24C phone observation. It never sends input.')
            self._send_json(200, {'observation': RUNTIME.observations.capture(data, engine.IMouseKernel(url=KERNEL_BASE_URL))})
            return
        if path == '/api/farm/video-drafts':
            self._send_json(200, {'draft': RUNTIME.videos.create(data)})
            return
        if path == '/api/farm/image-drafts':
            self._send_json(200, {'draft': RUNTIME.images.create(data)})
            return
        if path == "/api/farm/transfers":
            self._send_json(200, {"transfer": RUNTIME.transfers.start(data)})
            return
        if path.startswith("/api/farm/transfers/") and path.endswith("/stop"):
            parts = path.split("/")
            if len(parts) != 6:
                raise ValueError("Unknown transfer operation.")
            self._send_json(200, {"transfer": RUNTIME.transfers.stop(parts[4])})
            return
        if path == "/api/farm/drafts":
            draft = RUNTIME.drafts.create(data.get("id"), data.get("title", "Instagram carousel"), data.get("from_generated", False),
                                         source_generation=data.get('source_generation'), manifest_sha256=data.get('manifest_sha256'))
            self._send_json(200, {"draft": draft})
            return
        if path.startswith("/api/farm/drafts/"):
            parts = path.split("/")
            if len(parts) != 6:
                raise ValueError("Unknown draft operation.")
            draft_id, action = parts[4:]
            revision = data.get("revision")
            if action == "import":
                draft = RUNTIME.drafts.import_image(draft_id, revision, data.get("name"), data.get("content"))
            elif action == "save":
                draft = RUNTIME.drafts.save(draft_id, revision, data.get("title"), data.get("caption"), data.get("slide_ids"))
            elif action == "export":
                archive = RUNTIME.drafts.export(draft_id, revision)
                self._send_json(200, {"filename": f"instagram-carousel-{draft_id}-r{revision}.zip", "content": base64.b64encode(archive).decode("ascii"), "savedInInstagram": False, "published": False})
                return
            else:
                raise ValueError("Unknown draft operation.")
            self._send_json(200, {"draft": draft})
            return
        if path == "/api/farm/jobs":
            job = RUNTIME.submit_job(data.get("request_id", ""), data.get("action", ""), data.get("payload"))
            self._send_json(202, {"job": job})
            return
        if path.startswith("/api/farm/jobs/") and path.endswith("/cancel"):
            self._send_json(200, {"job": RUNTIME.jobs.cancel(path.split("/")[-2])})
            return
        if path == "/api/farm/create-content":
            RUNTIME.jobs.assert_available()
            self._send_json(200, RUNTIME.create_content(data))
            return
        if path == "/api/farm/emergency-stop":
            RUNTIME.jobs.cancel_active()
            if RUNTIME.draft_creations.config is not None:
                status, payload = 409, {"status": "safety_refused", "error": "This isolated draft candidate exposes only its bounded draft workflow. General rack commands are unavailable."}
            else:
                status, payload = 200, {"status": "ok", "stopped": None, "phoneStopped": False}
            try:
                RUNTIME.preparation.pause()
                payload['preparationPaused'] = True
            except Exception as ex:
                payload['preparationPaused'] = False
                payload['preparationPauseError'] = str(ex)
                if status == 200:
                    status = 500
                    payload.update(status='partial', error='The job was cancelled, but recurring preparation could not be paused. Check its status.')
            self._send_json(status, payload)
            return

        self._send_json(404, {"error": f"Unknown POST path: {path}"})


STAY_ROUTES = ('state', 'create-content', 'jobs', 'emergency-stop', 'drafts', 'image-drafts', 'video-drafts', 'video-sources',
               'transfers', 'draft-creations', 'reel-creations', 'tiktok-creations', 'x-creations', 'youtube-creations',
               'x-image-creations', 'tiktok-photo-creations', 'draft-verifications', 'observations', 'preparation-schedule',
               'schedule-queue')
# Removed with the simulated automation surface. The self-check proves each one is gone.
GONE_GET = ('/', '/index.html', '/dashboard', '/api/farm/capabilities', '/api/farm/scheduler-status', '/api/farm/image-sources',
            '/stage/C24C/manifest.json', '/kernel-proxy/api/kernel/status', '/api/farm/carousel-inspections/x',
            '/api/farm/draft-recoveries', '/api/farm/draft-rehearsals', '/api/farm/draft-runs')
GONE_POST = ('auto-create-and-deploy', 'upload-single', 'single-upload', 'warmup-wave', 'funnel-action', 'funnel-suite',
             'clone-winners', 'shadowban-scan', 'scan-profile-views', 'scheduler-tick', 'calibrate-box', 'update-persona',
             'resume-simulation', 'carousel-inspections', 'draft-recoveries', 'draft-rehearsals', 'draft-runs')
_SELF_CHECK = {'port': None, 'refused': []}


def _self_check_guard(event, args):
    """While a self-check runs, this process may connect only to the self-check's own listener."""
    if event == 'socket.connect' and _SELF_CHECK['port'] is not None:
        address = args[1]
        if not isinstance(address, tuple) or address[0] != '127.0.0.1' or address[1] != _SELF_CHECK['port']:
            _SELF_CHECK['refused'].append(str(address))
            raise ConnectionRefusedError('The self-check connects only to its own listener.')


def self_check() -> None:
    """Start this backend on a free loopback port, with no phone and no creation config, and ask it for
    everything it still serves. Nothing outside a temporary folder is written, no process is started, and
    any connection other than to the check's own listener is refused and fails the check."""
    import re
    import tempfile
    import uuid

    global RUNTIME
    previous = RUNTIME
    if not _SELF_CHECK.get('hooked'):
        sys.addaudithook(_self_check_guard); _SELF_CHECK['hooked'] = True
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        tmp_path = Path(tmpdir)
        RUNTIME = runtime = FarmBackendRuntime(db_path=tmp_path / "data" / "farm.db", stage_root=tmp_path / "stage")
        runtime.schedule_queue_path = tmp_path / "data" / "queue.json"   # Never the operator's own review queue.
        runtime.factory.code_animator.llm_api_key = None                  # Local templates only: no outside service.
        srv = ThreadingHTTPServer(("127.0.0.1", 0), FarmRequestHandler)
        port = srv.server_address[1]
        _SELF_CHECK.update(port=port, refused=[])
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base = f"http://127.0.0.1:{port}"

        def call(path, body=None):
            data = None if body is None else json.dumps(body).encode("utf-8")
            request = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
            try:
                response = opener.open(request, timeout=30.0)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                raw = response.read()
                return response.status, (json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw)

        def expect(path, status, body=None):
            got, value = call(path, body)
            assert got == status, f"{'POST' if body is not None else 'GET'} {path}: expected {status}, got {got}: {str(value)[:300]}"
            assert isinstance(value, dict) and value.get("protocolVersion") == 2, f"{path}: not a protocol 2 reply"
            return value

        try:
            checked = set()
            health = expect("/health", 200)
            assert health["executionMode"] == "simulate" and health["port"] == DEFAULT_PORT
            assert re.fullmatch("[0-9a-f]{64}", health["sourceHash"]) and health["sourceHash"] == runtime.source_hash
            state = expect("/api/farm/state", 200); checked.add('state')
            assert state["status"] == "ok" and state["activeJob"] is None

            # Content preparation and the job plumbing, without a phone.
            job_id = str(uuid.uuid4())
            job = expect("/api/farm/jobs", 202, {"request_id": job_id, "action": "create-content", "payload": {"device_id": "C24C"}})["job"]
            deadline = time.monotonic() + 120
            while not job["terminal"] and time.monotonic() < deadline:
                time.sleep(.05)
                job = expect("/api/farm/jobs/" + job_id, 200)["job"]
            assert job["status"] == "succeeded", f"create-content job: {job}"
            assert (tmp_path / "stage" / "C24C" / "manifest.json").is_file() and len(job["result"]["slates"]) == 5
            assert expect("/api/farm/jobs", 202, {"request_id": job_id, "action": "create-content", "payload": {"device_id": "C24C"}})["job"] == job
            unknown = str(uuid.uuid4())
            assert expect(f"/api/farm/jobs/{unknown}/cancel", 200, {})["job"]["status"] == "cancelled"
            assert call("/api/farm/jobs", {"request_id": str(uuid.uuid4()), "action": "warmup-wave", "payload": {}})[0] == 400
            assert call("/api/farm/create-content", {"device_id": "no-such-profile"})[0] == 400
            checked.update(('jobs', 'create-content'))
            stopped = expect("/api/farm/emergency-stop", 200, {})
            assert stopped["phoneStopped"] is False and stopped["preparationPaused"] is True
            checked.add('emergency-stop')

            # Drafts: the prepared carousel is there; the others are empty lists.
            drafts = expect("/api/farm/drafts", 200)["drafts"]
            assert len(drafts) == 1 and expect("/api/farm/drafts/" + drafts[0]["id"], 200)["draft"]["status"] == "ready_local"
            assert expect("/api/farm/image-drafts", 200)["drafts"] == [] and expect("/api/farm/video-drafts", 200)["drafts"] == []
            assert len(expect("/api/farm/video-sources", 200)["sources"]) == 1
            assert expect("/api/farm/transfers/current", 200)["transfer"] is None
            assert call("/api/farm/transfers", {})[0] == 400
            checked.update(('drafts', 'image-drafts', 'video-drafts', 'video-sources', 'transfers'))

            # Every creation route answers, reports itself disabled and refuses to start.
            for name, (_, capability, *_) in CREATION_ROUTES.items():
                route, value = "/api/farm/" + name, health[capability]
                assert value["enabled"] is False and value["publishing"] is False and value["messaging"] is False, name
                spec = {"id": str(uuid.uuid4()), "draft_id": str(uuid.uuid4()), "revision": 1, "store_id": value["storeId"]}
                assert expect(route + "?draft_id=" + spec["draft_id"], 200)["runs"] == []
                assert expect(route, 409, spec)["status"] == "safety_refused"
                expect(route + "/" + spec["id"], 404)
                assert expect(f"{route}/{spec['id']}/cancel", 200, {"store_id": value["storeId"]})["job"]["status"] == "cancelled"
                checked.add(name)

            assert expect("/api/farm/draft-verifications?draft_id=" + str(uuid.uuid4()), 200)["verifications"] == []
            assert expect("/api/farm/observations", 200)["observations"] == []
            assert call("/api/farm/observations", {"read_only": False})[0] == 400   # Refused before any kernel is asked.
            schedule = expect("/api/farm/preparation-schedule", 200)["preparationSchedule"]
            assert isinstance(schedule, dict)
            queue = expect("/api/farm/schedule-queue", 200)
            assert queue["scheduleQueue"]["pending"] == [] and queue["startsRuns"] is False and queue["phoneInput"] is False
            checked.update(('draft-verifications', 'observations', 'preparation-schedule', 'schedule-queue'))
            assert checked == set(STAY_ROUTES), sorted(set(STAY_ROUTES) ^ checked)

            for path in GONE_GET:
                assert call(path)[0] == 404, f"GET {path} still answers"
            for name in GONE_POST:
                assert call("/api/farm/" + name, {"device_id": "C24C"})[0] == 404, f"POST {name} still answers"
            assert call("/kernel-proxy/", {"fun": "/input/stop", "data": {"id": "C24C"}})[0] == 404
            assert not _SELF_CHECK['refused'], "Something tried to connect outside the self-check: " + ", ".join(_SELF_CHECK['refused'])
            print(f"OK - farm backend self-check passed on {base}: {len(STAY_ROUTES)} route families answer without a phone, "
                  f"{len(GONE_GET) + len(GONE_POST) + 1} removed routes return 404, source hash {runtime.source_hash[:12]}. No kernel was contacted.")
        finally:
            _SELF_CHECK['port'] = None
            srv.shutdown()
            srv.server_close()
            runtime.jobs.close()
            runtime.preparation.close()
            runtime.transfers.close()
            RUNTIME = previous


def main() -> int:
    global RUNTIME
    ap = argparse.ArgumentParser(description="Start the iMouse 2.0 Marketing Farm backend on loopback (default port 9914).")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-browser", action="store_true", help="Accepted and ignored: the launchers still pass it, and there is no page to open.")
    ap.add_argument("--self-check", action="store_true", help="Check every route this backend serves, offline, then exit.")
    ap.add_argument('--data-dir', type=Path, help='Separate candidate backend data; no operator settings are read.')
    ap.add_argument('--draft-creation-config', type=Path, help="One phone window's kernel and media configuration (prepare_window.py writes it); needs --mode live.")
    ap.add_argument("--mode", choices=("simulate", "live"), default="simulate",
                    help="names the data folder (output/farm-data/v2/<mode>); a creation config is accepted only with live")
    args = ap.parse_args()

    if args.self_check:
        self_check()
        return 0

    srv = FarmControlServer((args.host, args.port), FarmRequestHandler)
    try:
        RUNTIME = FarmBackendRuntime(port=args.port, execution_mode=args.mode,
            db_path=args.data_dir / 'farm.db' if args.data_dir else None,
            stage_root=args.data_dir / 'stage' if args.data_dir else None,
            draft_creation_config=args.draft_creation_config)
    except Exception:
        srv.server_close()
        raise
    window = RUNTIME.draft_creations.config
    print(f"iMouse 2.0 Marketing Farm backend on http://127.0.0.1:{args.port} (mode {args.mode}; "
          + (f"window for {phone_of(window).board}" if window else "no phone, content preparation only") + ")")
    try:
        RUNTIME.preparation.start()
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if not RUNTIME.jobs.close():
                print('Worker cleanup is unconfirmed. Its saved request requires review; no automatic resume.')
        finally:
            RUNTIME.preparation.close()
            RUNTIME.transfers.close()
            srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
