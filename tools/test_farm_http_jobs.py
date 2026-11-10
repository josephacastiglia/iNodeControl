"""Real HTTP job lifecycle against an ephemeral backend with no phone and no kernel."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid

import farm_test_network as network
import imouse_farm_server as server
import imouse_social_automation as engine
from farm_jobs import FarmJobs
from farm_test_network import allowed_ports as _allowed_ports


@contextmanager
def no_kernel():
    """Fails when the block builds a kernel client or tries to connect anywhere but a test's own server."""
    before = len(network.refused)
    with patch.object(engine.IMouseKernel, '__init__', side_effect=AssertionError('No kernel client may be built here.')) as built:
        yield
    assert not built.called, 'A kernel client was built.'
    assert network.refused[before:] == [], f'Outside connections were attempted: {network.refused[before:]}'


class FarmHttpJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="farm-http-jobs-")
        self.root = Path(self.temp.name)
        self.old_runtime = server.RUNTIME
        self.refused_before = len(network.refused)
        self.runtime = server.FarmBackendRuntime(self.root / "farm.db", self.root / "stage")
        server.RUNTIME = self.runtime
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.FarmRequestHandler)
        self.port = self.httpd.server_address[1]
        _allowed_ports.add(self.port)
        self.base = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.runtime.jobs.cancel_active()
        for job in self.runtime.jobs._jobs.values():
            self.assertTrue(job.done.wait(3), "Worker must stop before test cleanup")
        with self.runtime.jobs._lock:
            pass
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(2)
        _allowed_ports.discard(self.port)
        server.RUNTIME = self.old_runtime
        self.temp.cleanup()

    def request(self, path, data=None, *, raw=None, origin=None, timeout=5):
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(self.base + path, body, headers)
        try:
            response = self.opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw_response = response.read()
            value = json.loads(raw_response) if "json" in response.headers.get("Content-Type", "") else raw_response
            return response.status, value

    def outside_connections(self):
        """Every connection this test tried to make beyond its own loopback servers (the guard refused each)."""
        return network.refused[self.refused_before:]

    def submit(self, action, payload):
        request_id = str(uuid.uuid4())
        body = {"request_id": request_id, "action": action, "payload": payload}
        status, response = self.request("/api/farm/jobs", body)
        self.assertEqual(202, status, response)
        self.assertEqual(2, response["protocolVersion"])
        self.assertNotIn("simulated", response)
        return request_id, body

    def finish(self, request_id, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status, body = self.request("/api/farm/jobs/" + request_id)
            self.assertEqual(200, status, body)
            if body["job"]["terminal"]:
                return body["job"]
            time.sleep(.01)
        self.fail("Job did not terminate")

    def generations(self):
        return sorted(path.name for path in (self.root / "stage" / "C24C").glob("manifest_*.json")) if (self.root / "stage" / "C24C").exists() else []

    def held_render(self):
        """Stands in for a long render: create-content waits here until the test lets it go."""
        entered, release = threading.Event(), threading.Event()
        real = self.runtime.prepare_local_content
        def slow(device_id):
            entered.set()
            self.assertTrue(release.wait(10), "The test never released the render")
            return real(device_id)
        self.runtime.prepare_local_content = slow
        self.addCleanup(release.set)
        return entered, release

    def test_async_submission_poll_and_duplicate_do_not_replay(self):
        with no_kernel():
            job_id, request = self.submit("create-content", {"device_id": "C24C"})
            job = self.finish(job_id)
            self.assertEqual("succeeded", job["status"], job)
            self.assertEqual(5, len(job["result"]["slates"])); self.assertEqual("simulate", job["result"]["executionMode"])
            rendered = self.generations(); self.assertEqual(1, len(rendered))
            status, body = self.request("/api/farm/jobs", request)
            self.assertEqual(202, status)
            self.assertTrue(body["job"]["terminal"]); self.assertEqual(job, body["job"])
            self.assertEqual(rendered, self.generations())
            self.assertEqual(400, self.request("/api/farm/jobs", {**request, "payload": {"device_id": "C241"}})[0])
        self.assertEqual([], self.outside_connections())

    def test_cancel_during_a_render_is_recorded_and_the_worker_finishes(self):
        entered, release = self.held_render()
        job_id, _ = self.submit("create-content", {"device_id": "C24C"})
        self.assertTrue(entered.wait(3))
        self.assertEqual(job_id, self.request("/api/farm/state")[1]["activeJob"]["id"])
        status, body = self.request(f"/api/farm/jobs/{job_id}/cancel", {})
        self.assertEqual(200, status); self.assertEqual("cancelling", body["job"]["status"])
        self.assertEqual(400, self.request("/api/farm/create-content", {"device_id": "C24C"})[0])   # One job at a time.
        release.set()
        self.assertEqual("cancelled", self.finish(job_id)["status"])
        self.assertIsNone(self.request("/api/farm/state")[1]["activeJob"])
        self.assertEqual([], self.outside_connections())

    def test_a_job_cancelled_before_its_render_starts_renders_nothing(self):
        cancelled = threading.Event(); cancelled.set()
        with self.assertRaises(server.JobCancelled): self.runtime.create_content({"device_id": "C24C"}, cancelled)
        self.assertEqual([], self.generations())

    def test_cancel_can_arrive_before_http_submission_and_survives_restart(self):
        request_id = str(uuid.uuid4())
        status, stopped = self.request(f'/api/farm/jobs/{request_id}/cancel', {})
        self.assertEqual(200, status); self.assertEqual('cancelled', stopped['job']['status'])
        self.runtime.jobs = FarmJobs(journal_path=self.root / 'jobs.db')
        status, delayed = self.request('/api/farm/jobs', dict(request_id=request_id, action='create-content', payload={'device_id': 'C24C'}))
        self.assertEqual(202, status); self.assertEqual(stopped['job'], delayed['job'])
        self.assertEqual([], self.generations()); self.assertEqual([], self.outside_connections())

    def test_emergency_stop_cancels_the_job_pauses_preparation_and_claims_no_phone(self):
        entered, release = self.held_render()
        job_id, _ = self.submit("create-content", {"device_id": "C24C"})
        self.assertTrue(entered.wait(3))
        schedule = dict(id=str(uuid.uuid4()), device_id='C24C', action='create-content', interval_minutes=60, max_runs=1)
        # The render holds the operation lock: Stop is answered anyway, and ordinary work is refused.
        self.assertEqual(400, self.request("/api/farm/drafts", {"id": str(uuid.uuid4())})[0])
        status, stopped = self.request("/api/farm/emergency-stop", {"device_id": "C24C"})
        self.assertEqual(200, status, stopped)
        self.assertEqual(("ok", None, False, True), (stopped["status"], stopped["stopped"], stopped["phoneStopped"], stopped["preparationPaused"]))
        release.set()
        self.assertEqual("cancelled", self.finish(job_id)["status"])
        self.assertEqual(200, self.request('/api/farm/preparation-schedule', schedule)[0])
        self.assertEqual('scheduled', self.request('/api/farm/preparation-schedule')[1]['preparationSchedule']['config']['state'])
        self.assertEqual(200, self.request("/api/farm/emergency-stop", {})[0])
        config = self.request('/api/farm/preparation-schedule')[1]['preparationSchedule']['config']
        self.assertEqual((False, 'paused'), (config['enabled'], config['state']))
        self.assertEqual([], self.outside_connections())

    def test_durable_status_survives_registry_restart(self):
        job_id, _ = self.submit("create-content", {"device_id": "C24C"})
        completed = self.finish(job_id)
        rendered = self.generations()
        self.runtime.jobs = FarmJobs(journal_path=self.root / "jobs.db")
        status, response = self.request("/api/farm/jobs/" + job_id)
        self.assertEqual(200, status)
        self.assertEqual(completed, response["job"])
        self.assertEqual(rendered, self.generations()); self.assertEqual([], self.outside_connections())

    def test_generated_media_matches_its_manifest_and_opens_as_a_draft(self):
        job_id, _ = self.submit("create-content", {"device_id": "C24C"})
        self.assertEqual("succeeded", self.finish(job_id)["status"])
        folder = self.root / "stage" / "C24C"
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for asset in manifest["assets"]:
            media = (self.root / asset["url"].lstrip("/")).read_bytes()
            self.assertEqual(asset["bytes"], len(media)); self.assertEqual(asset["sha256"], hashlib.sha256(media).hexdigest())
            self.assertEqual(404, self.request(asset["url"])[0])   # Review media is read from disk; nothing serves it.
        self.assertEqual(404, self.request("/stage/C24C/manifest.json")[0])
        status, response = self.request("/api/farm/drafts", {"id": str(uuid.uuid4()), "from_generated": True})
        self.assertEqual(200, status, response)
        draft = response["draft"]
        self.assertEqual(4, len(draft["slides"]))
        self.assertEqual(manifest["caption"], draft["caption"])
        self.assertEqual(manifest["generation"], draft["sourceGeneration"])
        self.assertEqual("ready_local", draft["status"])
        self.assertFalse(draft["savedInInstagram"])
        self.assertEqual([], self.outside_connections())

    def test_scheduled_preparation_opens_its_saved_draft_through_http_after_next_render(self):
        body = dict(id=str(uuid.uuid4()), device_id='C24C', action='create-content', interval_minutes=60, max_runs=1)
        with no_kernel():
            self.assertEqual(200, self.request('/api/farm/preparation-schedule', body)[0])
            self.runtime.preparation.tick()
            status, result = self.request('/api/farm/preparation-schedule')
            self.assertEqual(200, status); run = result['preparationSchedule']['runs'][0]
            self.assertEqual('succeeded', run['state'], run)
            item = next(item for item in run['contentItems'] if item.get('localDraft'))
            saved_id = item['localDraft']['id']
            before = self.request('/api/farm/drafts/' + saved_id)[1]['draft']
            self.runtime.prepare_local_content('C24C')
            self.assertEqual(before, self.request('/api/farm/drafts/' + saved_id)[1]['draft'])
            self.assertEqual(item['manifestSha256'], hashlib.sha256((self.root / item['manifest'].lstrip('/')).read_bytes()).hexdigest())
            pinned = dict(id=str(uuid.uuid4()), from_generated=True, source_generation=item['generation'], manifest_sha256=item['manifestSha256'])
            status, opened = self.request('/api/farm/drafts', pinned)
            self.assertEqual(200, status, opened); self.assertEqual(before['slideIds'], opened['draft']['slideIds'])
            self.assertEqual(before['caption'], opened['draft']['caption'])
            self.assertFalse(opened['draft']['savedInInstagram'])
            query = '/api/farm/video-sources?generation=' + item['generation'] + '&manifest_sha256=' + item['manifestSha256']
            status, videos = self.request(query)
            self.assertEqual(200, status, videos); self.assertEqual(1, len(videos['sources']))
            source = videos['sources'][0]; self.assertEqual(item['generation'], source['sourceGeneration'])
            status, video = self.request('/api/farm/video-drafts', dict(id=str(uuid.uuid4()), device_id='C24C', format='tt_video',
                name=source['name'], sha256=source['sha256'], title='Earlier scheduled video', caption=source['caption'],
                source_generation=item['generation'], manifest_sha256=item['manifestSha256']))
            self.assertEqual(200, status, video); self.assertEqual(item['generation'], video['draft']['sourceGeneration'])
            self.assertFalse(video['draft']['savedInApp'])
        self.assertEqual([], self.outside_connections())

    def test_bad_json_and_untrusted_origin_are_rejected(self):
        status, _ = self.request("/api/farm/jobs", raw=b"{broken")
        self.assertEqual(400, status)
        status, _ = self.request("/api/farm/emergency-stop", {"device_id": "C24C"}, origin="https://untrusted.invalid")
        self.assertEqual(403, status)
        status, _ = self.request("/api/farm/create-content", {"device_id": "C24C"}, origin="https://untrusted.invalid")
        self.assertEqual(403, status)
        self.assertEqual([], self.generations()); self.assertEqual([], self.outside_connections())

    def test_carousel_import_save_export_over_real_http_without_phone_input(self):
        import base64
        import io
        import zipfile
        from PIL import Image
        import random
        draft_id = str(uuid.uuid4())
        status, result = self.request("/api/farm/drafts", {"id": draft_id})
        self.assertEqual(200, status, result)
        draft = result["draft"]
        # Encoded payload is >64 KiB; only the image-import route permits it.
        for seed in (1, 2):
            raw = random.Random(seed).randbytes(256 * 320 * 3)
            image = Image.frombytes("RGB", (256, 320), raw)
            buffer = io.BytesIO(); image.save(buffer, "PNG")
            status, result = self.request(f"/api/farm/drafts/{draft_id}/import", {"revision": draft["revision"], "name": f"slide-{seed}.png", "content": base64.b64encode(buffer.getvalue()).decode()})
            self.assertEqual(200, status, result)
            draft = result["draft"]
        status, result = self.request(f"/api/farm/drafts/{draft_id}/save", {"revision": draft["revision"], "title": "HTTP draft", "caption": "Preserve every space", "slide_ids": draft["slideIds"][::-1]})
        self.assertEqual(200, status, result)
        draft = result["draft"]
        status, result = self.request(f"/api/farm/drafts/{draft_id}/export", {"revision": draft["revision"]})
        self.assertEqual(200, status, result)
        self.assertFalse(result["savedInInstagram"])
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["content"]))) as archive:
            self.assertEqual(b"Preserve every space", archive.read("caption.txt"))
            self.assertEqual(draft["slideIds"], json.loads(archive.read("manifest.json"))["slideIds"])
        self.assertEqual([], self.outside_connections())

    def test_large_payload_is_not_permitted_on_control_routes(self):
        status, _ = self.request("/api/farm/emergency-stop", {"padding": "x" * 65536})
        self.assertEqual(413, status)
        self.assertEqual([], self.outside_connections())

    def test_state_and_health_report_only_what_this_backend_still_does(self):
        status, state = self.request("/api/farm/state")
        self.assertEqual(200, status)
        self.assertEqual({"status": "ok", "activeJob": None, "carouselDraftsVersion": 1, "protocolVersion": 2, "executionMode": "simulate"}, state)
        health = self.request("/health")[1]
        self.assertEqual({"status", "port", "sourceHash", "carouselDraftsVersion", "carouselTransfersVersion", "videoDraftsVersion",
                          "imageDraftsVersion", "observationsVersion", "draftVerificationVersion", "preparationScheduleVersion",
                          "draftCreation", "reelCreation", "tiktokCreation", "xCreation", "youtubeCreation", "xImageCreation",
                          "tiktokPhotoCreation", "protocolVersion", "executionMode"}, set(health))
        self.assertEqual(self.runtime.source_hash, health["sourceHash"])
        for name in ("draftCreation", "reelCreation", "tiktokCreation", "xCreation", "youtubeCreation", "xImageCreation", "tiktokPhotoCreation"):
            self.assertEqual((False, False, False), (health[name]["enabled"], health[name]["publishing"], health[name]["messaging"]), name)

    def test_the_simulated_automation_routes_are_gone(self):
        with no_kernel():
            for path in server.GONE_GET:
                with self.subTest(get=path): self.assertEqual(404, self.request(path)[0])
            for name in server.GONE_POST:
                with self.subTest(post=name):
                    self.assertEqual(404, self.request("/api/farm/" + name, {"device_id": "C24C"})[0])
                    status, body = self.request("/api/farm/jobs", {"request_id": str(uuid.uuid4()), "action": name, "payload": {"device_id": "C24C"}})
                    self.assertEqual(400, status, body)
            self.assertEqual(404, self.request("/kernel-proxy/", {"fun": "/input/stop", "data": {"id": "C24C"}})[0])
            self.assertEqual(404, self.request("/kernel-proxy/api/kernel/status")[0])
        self.assertEqual({"create-content"}, server.JOB_ACTIONS)
        self.assertEqual([], self.generations()); self.assertEqual([], self.outside_connections())

    def test_self_check_passes_offline_and_restores_the_running_backend(self):
        import contextlib
        import io
        output = io.StringIO()
        _allowed_ports.update(range(1024, 65536))   # The self-check picks its own free port and guards itself.
        try:
            with contextlib.redirect_stdout(output): server.self_check()
        finally:
            _allowed_ports.difference_update(set(range(1024, 65536)) - {self.port})
        self.assertIn("OK - farm backend self-check passed", output.getvalue())
        self.assertIn("No kernel was contacted", output.getvalue())
        self.assertIs(self.runtime, server.RUNTIME)
        self.assertEqual(200, self.request("/api/farm/state")[0])


if __name__ == "__main__":
    unittest.main()
