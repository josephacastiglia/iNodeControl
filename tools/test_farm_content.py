"""Content preparation: what is rendered, what is kept and how requests are isolated. No real transport."""
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

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
        with self.runtime.db._lock, self.runtime.db._connect() as connection:
            connection.execute("UPDATE personas SET niche = ? WHERE device_id = 'C24C'", ('<script>alert("x")</script>',))
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

    def test_reading_never_generates_or_writes_stage_files(self):
        for path in ("/stage/C24C/manifest.json", "/api/farm/state", "/health", "/api/farm/video-sources", "/api/farm/drafts"):
            self.request(path, method="GET")
        self.assertEqual(404, self.request("/stage/C24C/manifest.json", method="GET")[0])   # Nothing serves the stage folder.
        self.assertFalse((self.root / "stage/C24C").exists())

    def test_ordinary_work_is_excluded_while_an_operation_holds_the_lock(self):
        locked, release = threading.Event(), threading.Event()
        def hold():
            with self.runtime.operation_lock:
                locked.set()
                release.wait(2)
        worker = threading.Thread(target=hold)
        worker.start()
        self.assertTrue(locked.wait(1))
        try:
            status, _ = self.request("/api/farm/create-content", {"device_id": "C24C"})
            self.assertEqual(400, status)
            self.assertFalse((self.root / "stage/C24C").exists())
            # The emergency path stays responsive while ordinary work holds the lock.
            status, _ = self.request("/api/farm/emergency-stop", {"device_id": "C24C"})
            self.assertEqual(200, status)
        finally:
            release.set()
            worker.join(2)

    def test_content_needs_a_known_profile_and_a_phone_free_request(self):
        self.assertEqual(400, self.request("/api/farm/create-content", {"device_id": "no-such-profile"})[0])
        self.assertEqual(400, self.request("/api/farm/create-content", {"device_id": ""})[0])
        self.assertFalse((self.root / "stage").exists() and any((self.root / "stage").iterdir()))
        status, body = self.request("/api/farm/create-content", {"device_id": engine.LIVE_TEST_DEVICE_ID})   # The console's ID for C24C.
        self.assertEqual(200, status, body)
        self.assertEqual(("ok", "/stage/C24C/manifest.json", "local_templates", True),
                         (body["status"], body["manifest"], body["contentSource"], body["reviewRequired"]))
        self.assertEqual(5, len(body["slates"])); self.assertNotIn("simulated", body)
        self.assertFalse((self.root / "stage/C24C/iMousePull.shortcut.plist").exists())

    def test_generated_slate_contains_readable_carousel_images_and_video(self):
        if not engine.PIL_AVAILABLE:
            self.skipTest("Pillow unavailable; JPEG decoding not established")
        self.runtime.factory.generate_daily_slate_for_device("C24C")
        folder = self.runtime.stage_root / "C24C"
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        files = [folder / Path(path).name for path in manifest["files"]]
        self.assertEqual(5, len(files))
        self.assertEqual(4, sum(path.suffix == ".jpg" for path in files))
        self.assertEqual(1, sum(path.suffix == ".mp4" for path in files))
        for path in files:
            self.assertTrue(path.is_file())
            if path.suffix == ".jpg":
                with engine.Image.open(path) as img:
                    self.assertEqual("JPEG", img.format)
                    self.assertEqual((540, 675), img.size)
                    img.load()
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            self.skipTest("ffprobe unavailable; staged video decoding not established")
        video = next(path for path in files if path.suffix == ".mp4")
        probe = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", str(video)], capture_output=True, text=True, timeout=20)
        self.assertEqual(0, probe.returncode, probe.stderr)
        stream = json.loads(probe.stdout)["streams"][0]
        self.assertEqual((360, 640), (stream["width"], stream["height"]))
        self.assertGreater(int(stream["nb_read_frames"]), 0)

    def test_manifest_video_checksum_matches_the_staged_file(self):
        self.runtime.factory.generate_daily_slate_for_device("C24C")
        folder = self.runtime.stage_root / "C24C"
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        video = folder / Path(manifest["files"][0]).name
        self.assertEqual(hashlib.sha256(video.read_bytes()).hexdigest(), manifest["sha256Hex"],
                         "Manifest sha256Hex is not the SHA-256 of its video")

    def test_video_has_decodable_frames_or_reports_missing_encoder(self):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            self.skipTest("ffprobe unavailable; actual decoding not established")
        path = self.root / "sample.mp4"
        animator = engine.LlmCodeAnimationEngine()
        animator.compile_code_spec_to_mp4({"fps": 15, "durationSec": 1.2}, path, "C24C")
        probe = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=width,height,nb_read_frames", "-of", "json", str(path)], capture_output=True, text=True, timeout=20)
        self.assertEqual(0, probe.returncode, probe.stderr)
        streams = json.loads(probe.stdout).get("streams", [])
        self.assertTrue(streams, "MP4 has no decodable video stream")
        self.assertGreater(int(streams[0]["nb_read_frames"]), 0)

    def test_missing_video_encoder_is_reported_or_fallback_is_playable(self):
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            self.skipTest("ffprobe unavailable; fallback decoding not established")
        path = self.root / "missing-encoder.mp4"
        with patch.object(engine, "CV2_AVAILABLE", False):
            try:
                engine.LlmCodeAnimationEngine().compile_code_spec_to_mp4({}, path, "C24C")
            except (RuntimeError, ValueError):
                return  # Explicitly unavailable is acceptable; false success is not.
        probe = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "json", str(path)], capture_output=True, text=True, timeout=20)
        self.assertEqual(0, probe.returncode, "Fallback was returned as success but cannot decode: " + probe.stderr)
        streams = json.loads(probe.stdout).get("streams", [])
        self.assertTrue(streams, "Fallback MP4 contains no video stream")
        self.assertGreater(int(streams[0]["nb_read_frames"]), 0)


if __name__ == "__main__":
    unittest.main()
