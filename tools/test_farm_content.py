"""Content preservation, validation and request isolation. No real transport."""
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid

import imouse_farm_server as server
import imouse_social_automation as engine


class FarmContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="farm-content-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")))
        self.runtime = server.FarmBackendRuntime(self.root / "data/farm.db", self.root / "stage")
        self.enterContext(patch.object(server, "RUNTIME", self.runtime))

    def request(self, path, body=None, method="POST"):
        handler = object.__new__(server.FarmRequestHandler)
        handler.path = path
        handler.headers = Message()
        raw = json.dumps(body or {}).encode()
        handler.headers["Content-Length"] = str(len(raw))
        handler.rfile = io.BytesIO(raw)
        handler._send_bytes = Mock()
        getattr(handler, "do_" + method)()
        status, kind, data = handler._send_bytes.call_args.args
        return status, json.loads(data) if "json" in kind else data

    def generate(self):
        self.runtime.factory.generate_daily_slate_for_device("C24C")
        return json.loads((self.root / "stage/C24C/manifest.json").read_text(encoding="utf-8"))

    def test_new_generation_keeps_every_previously_exported_asset(self):
        first = self.generate()
        old_bytes = {url: (self.root / url.lstrip("/")).read_bytes() for url in first["files"]}
        second = self.generate()
        archived = self.root / 'stage/C24C' / f"manifest_{first['generation']}.json"
        self.assertEqual(first, json.loads(archived.read_bytes()))
        self.assertNotEqual(first["generation"], second["generation"])
        self.assertTrue(set(first["files"]).isdisjoint(second["files"]))
        for url, data in old_bytes.items():
            self.assertEqual(data, (self.root / url.lstrip("/")).read_bytes())

    def test_failed_render_preserves_previous_manifest_and_media(self):
        first = self.generate()
        with patch.object(self.runtime.factory.code_animator, "compile_code_spec_to_mp4", side_effect=RuntimeError("Codec failed")):
            with self.assertRaisesRegex(RuntimeError, "Codec failed"):
                self.generate()
        self.assertEqual(first, json.loads((self.root / "stage/C24C/manifest.json").read_text(encoding="utf-8")))
        self.assertTrue(all((self.root / path.lstrip("/")).exists() for path in first["files"]))

    def test_manifest_assets_have_real_checksums_and_review_is_escaped(self):
        self.runtime.db.update_persona("C24C", niche='<script>alert("x")</script>')
        manifest = self.generate()
        for asset in manifest["assets"]:
            raw = (self.root / asset["url"].lstrip("/")).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), asset["sha256"])
            self.assertEqual(len(raw), asset["bytes"])
        review = (self.root / "stage/C24C/review.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>", review)
        self.assertIn("&lt;script&gt;", review)
        self.assertTrue(manifest["reviewRequired"])
        self.assertEqual("local_templates", manifest["contentSource"])

    def test_reading_missing_stage_does_not_generate_or_write_files(self):
        for name in ("manifest.json", "iMousePull.shortcut.plist"):
            status, _ = self.request("/stage/C24C/" + name, method="GET")
            self.assertEqual(404, status)
        self.assertFalse((self.root / "stage/C24C").exists())

    def test_calibration_cannot_choose_an_arbitrary_output_path(self):
        destination = self.root / "operator-settings.json"
        status, _ = self.request("/api/farm/calibrate-box", {"key": "ig_carousel_aspect_ratio_btn", "coords": [22, 516, 74, 568], "config_path": str(destination)})
        self.assertEqual(400, status)
        self.assertFalse(destination.exists())

    def test_calibration_rejects_invalid_rectangles(self):
        for coords in ([0, 0, 501, 1080], [3, 4, 2, 6], [0, 0, 2, 1081], [False, 0, 1, 1]):
            with self.subTest(coords=coords):
                status, _ = self.request("/api/farm/calibrate-box", {"key": "ig_carousel_aspect_ratio_btn", "coords": coords})
                self.assertEqual(400, status)

    def test_proxy_cannot_acquire_while_a_job_is_running(self):
        started, release = threading.Event(), threading.Event()
        def run(cancel):
            started.set()
            release.wait(2)
            return {}
        self.runtime.jobs.submit(str(uuid.uuid4()), "test", {}, run)
        self.assertTrue(started.wait(1))
        try:
            status, _ = self.request("/kernel-proxy/api", {"fun": "/input/acquire", "data": {"ids": ["C24C"]}})
            self.assertEqual(400, status)
            self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)
        finally:
            release.set()
            # Wait for the durable terminal record before TemporaryDirectory cleanup.
            for job in self.runtime.jobs._jobs.values():
                self.assertTrue(job.done.wait(2))
            with self.runtime.jobs._lock:
                pass

    def test_upload_rejects_untypable_caption_before_any_input(self):
        for text in ("x" * 201, "Hello 👋"):
            status, _ = self.request("/api/farm/single-upload", {"device_id": "C24C", "caption": text})
            self.assertEqual(400, status)
            self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_single_image_carousel_does_not_select_an_extra_image(self):
        status, data = self.request("/api/farm/single-upload", {"device_id": "C24C", "format": "ig_carousel", "media_count": 1, "caption": "Sample"})
        self.assertEqual(200, status)
        targets = [row[0] for row in data["result"]["clickCoordinates"]]
        self.assertNotIn("ig_gallery_slot_2", targets)

    def test_new_personas_have_unknown_not_invented_view_counts(self):
        self.assertTrue(all(p["views_24h"] == -1 for p in self.runtime.db.list_personas()))
        self.assertEqual([], self.runtime.factory.clone_winning_hooks())

    def test_no_winner_is_invented_when_every_record_is_below_threshold(self):
        with self.runtime.db._lock, self.runtime.db._connect() as connection:
            connection.execute("UPDATE personas SET views_24h = 12 WHERE device_id = 'C24C'")
            connection.commit()
        self.assertEqual([], self.runtime.factory.clone_winning_hooks(threshold_views=10000))

    def test_legacy_mutations_are_excluded_while_an_operation_holds_the_lock(self):
        locked, release = threading.Event(), threading.Event()
        def hold():
            with self.runtime.operation_lock:
                locked.set()
                release.wait(2)
        worker = threading.Thread(target=hold)
        worker.start()
        self.assertTrue(locked.wait(1))
        try:
            status, _ = self.request("/api/farm/update-persona", {"device_id": "C24C", "niche": "Overlapping"})
            self.assertEqual(400, status)
            self.assertNotEqual("Overlapping", self.runtime.db.get_persona("C24C")["niche"])
            # The emergency path stays responsive while ordinary work holds the lock.
            status, _ = self.request("/api/farm/emergency-stop", {"device_id": "C24C"})
            self.assertEqual(200, status)
        finally:
            release.set()
            worker.join(2)

    def test_profile_validation_leaves_previous_values_unchanged(self):
        before = self.runtime.db.get_persona("C24C")
        for changes in ({"niche": " "}, {"cta_keyword": []}, {"account_day": -1}, {"paused_zero_view": "no"}, {"offer_url": "javascript:alert(1)"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.runtime.db.update_persona("C24C", **changes)
        self.assertEqual(before, self.runtime.db.get_persona("C24C"))

    def test_invalid_observed_view_counts_remain_unknown(self):
        for views in ([1], [1, -1, 3], [1, "2", 3], [1, True, 3]):
            vision = engine.VlmComputerUseAdapter(external_vlm_fn=lambda frame, query: {"views": views})
            self.assertEqual([], vision.extract_profile_grid_views(b""))


if __name__ == "__main__":
    unittest.main()
