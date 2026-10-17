"""Real HTTP job lifecycle against an ephemeral simulation server only."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid

import imouse_farm_server as server
from farm_jobs import FarmJobs
from farm_test_network import allowed_ports as _allowed_ports


class FarmHttpJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="farm-http-jobs-")
        self.root = Path(self.temp.name)
        self.old_runtime = server.RUNTIME
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

    def request(self, path, data=None, *, raw=None, origin=None):
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(self.base + path, body, headers)
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw_response = response.read()
            value = json.loads(raw_response) if "json" in response.headers.get("Content-Type", "") else raw_response
            return response.status, value

    def submit(self, action, payload):
        request_id = str(uuid.uuid4())
        body = {"request_id": request_id, "action": action, "payload": payload}
        status, response = self.request("/api/farm/jobs", body)
        self.assertEqual(202, status, response)
        self.assertEqual(2, response["protocolVersion"])
        self.assertTrue(response["simulated"])
        return request_id, body

    def finish(self, request_id):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            status, body = self.request("/api/farm/jobs/" + request_id)
            self.assertEqual(200, status, body)
            if body["job"]["terminal"]:
                return body["job"]
            time.sleep(.01)
        self.fail("Job did not terminate")

    def test_async_submission_poll_and_duplicate_do_not_replay(self):
        job_id, request = self.submit("warmup-wave", {"device_id": "C24C", "clips": 1, "time_scale": 0})
        self.assertEqual("succeeded", self.finish(job_id)["status"])
        count = len(self.runtime.mock_kernel.commands_dispatched)
        status, body = self.request("/api/farm/jobs", request)
        self.assertEqual(202, status)
        self.assertTrue(body["job"]["terminal"])
        self.assertEqual(count, len(self.runtime.mock_kernel.commands_dispatched))
        self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_cancel_stops_active_work_and_cleanup_finishes(self):
        job_id, _ = self.submit("warmup-wave", {"device_id": "C24C", "clips": 50, "time_scale": 1})
        status, _ = self.request(f"/api/farm/jobs/{job_id}/cancel", {})
        self.assertEqual(200, status)
        self.assertEqual("cancelled", self.finish(job_id)["status"])
        self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_stop_latches_until_explicit_simulation_resume(self):
        job_id, _ = self.submit("warmup-wave", {"device_id": "C24C", "clips": 50, "time_scale": 1})
        status, _ = self.request("/api/farm/emergency-stop", {"device_id": "C24C"})
        self.assertEqual(200, status)
        self.assertIn(self.finish(job_id)["status"], ("cancelled", "failed"))
        self.assertIn("C24C", self.runtime.mock_kernel.stopped)
        before = len(self.runtime.mock_kernel.commands_dispatched)
        status, _ = self.request("/api/farm/resume-simulation", {})
        self.assertEqual(200, status)
        self.assertNotIn("C24C", self.runtime.mock_kernel.stopped)
        new_commands = self.runtime.mock_kernel.commands_dispatched[before:]
        self.assertFalse(any(fun.startswith(("/mouse/", "/key/")) for fun, _ in new_commands))

    def test_durable_status_survives_registry_restart(self):
        job_id, _ = self.submit("scheduler-tick", {"cohort": 1, "execute_actions": False})
        completed = self.finish(job_id)
        self.runtime.jobs = FarmJobs(journal_path=self.root / "jobs.db")
        status, response = self.request("/api/farm/jobs/" + job_id)
        self.assertEqual(200, status)
        self.assertEqual(completed, response["job"])
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_generated_media_and_manifest_can_be_downloaded(self):
        job_id, _ = self.submit("create-content", {"device_id": "C24C"})
        self.assertEqual("succeeded", self.finish(job_id)["status"])
        status, manifest = self.request("/stage/C24C/manifest.json")
        self.assertEqual(200, status)
        for asset in manifest["assets"]:
            status, media = self.request(asset["url"])
            self.assertEqual(200, status)
            self.assertEqual(asset["bytes"], len(media))
        status, response = self.request("/api/farm/drafts", {"id": str(uuid.uuid4()), "from_generated": True})
        self.assertEqual(200, status, response)
        draft = response["draft"]
        self.assertEqual(4, len(draft["slides"]))
        self.assertEqual(manifest["caption"], draft["caption"])
        self.assertEqual(manifest["generation"], draft["sourceGeneration"])
        self.assertEqual("ready_local", draft["status"])
        self.assertFalse(draft["savedInInstagram"])
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_bad_json_and_untrusted_origin_are_rejected(self):
        status, _ = self.request("/api/farm/jobs", raw=b"{broken")
        self.assertEqual(400, status)
        status, _ = self.request("/api/farm/emergency-stop", {"device_id": "C24C"}, origin="https://untrusted.invalid")
        self.assertEqual(403, status)
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

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
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_large_payload_is_not_permitted_on_control_routes(self):
        status, _ = self.request("/api/farm/emergency-stop", {"padding": "x" * 65536})
        self.assertEqual(413, status)
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)


if __name__ == "__main__":
    unittest.main()
