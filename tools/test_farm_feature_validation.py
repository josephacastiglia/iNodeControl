"""Acceptance probes for farm features, entirely offline.

Failing tests intentionally remain failures: this suite measures advertised behavior,
not just whether a mock returns code 0. It never opens a window or uses a real phone.
Run with --report <json> to preserve individual results and source hashes.
"""
from __future__ import annotations
from farm_phone_identity import LEGACY_C24C

import argparse
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import plistlib
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import imouse_farm_server as server
import imouse_social_automation as engine

C24C = engine.LIVE_TEST_DEVICE_ID
C241 = "FE:A9:BC:D7:A0:44"


class FarmFeatureValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="farm-feature-validation-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("Real network forbidden")))
        self.enterContext(patch.object(engine.MediaPullOrchestrator, "detect_host_lan_url", return_value="http://127.0.0.1:9914"))
        self.runtime = server.FarmBackendRuntime(self.root / "farm.db", self.root / "stage", execution_mode="simulate")
        self.runtime.rng.seed(71)
        self.enterContext(patch.object(server, "RUNTIME", self.runtime))
        self.kernel = self.runtime.kernel_client

    def handler(self, path, body=None, raw=None, origin=None):
        handler = object.__new__(server.FarmRequestHandler)
        handler.path = path
        handler.headers = Message()
        if origin:
            handler.headers["Origin"] = origin
        raw = raw if raw is not None else json.dumps(body or {}).encode()
        handler.headers["Content-Length"] = str(len(raw))
        handler.rfile = io.BytesIO(raw)
        handler._send_bytes = Mock()
        return handler

    def reply(self, handler, method="POST"):
        getattr(handler, "do_" + method)()
        self.assertTrue(handler._send_bytes.called, "Handler returned no response")
        status, content_type, data = handler._send_bytes.call_args.args
        return status, json.loads(data) if "json" in content_type else data

    def input_commands(self):
        return [(fun, data) for fun, data in self.runtime.mock_kernel.commands_dispatched
                if fun.startswith(("/mouse/", "/key/"))]

    def type_text(self, text, strategy=engine.TextEntryStrategy.CHUNKED_SENDKEY):
        tokens = self.kernel.acquire(["C24C"])
        try:
            engine.type_text_on_ios(self.kernel, self.runtime.jitter, self.runtime.vision,
                                   "C24C", tokens["C24C"], text, strategy, [])
        finally:
            self.kernel.release(tokens)

    def test_state_reports_simulation_and_nineteen_personas(self):
        status, body = self.reply(self.handler("/api/farm/state"), "GET")
        self.assertEqual(200, status)
        self.assertEqual(19, len(body["personas"]))
        self.assertEqual("simulate", body["executionMode"])
        self.assertTrue(body["simulated"])
        self.assertFalse(body["liveKernelConnected"])
        self.assertEqual([], self.input_commands())

    def test_scheduler_status_does_not_dispatch_input(self):
        status, body = self.reply(self.handler("/api/farm/scheduler-status"), "GET")
        self.assertEqual(200, status)
        self.assertEqual(19, len(body["devices"]))
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_scheduler_dry_run_never_acquires_or_sends(self):
        status, body = self.reply(self.handler("/api/farm/scheduler-tick", {"cohort": 1, "execute_actions": False}))
        self.assertEqual(200, status)
        self.assertEqual(4, len(body["wave"]["actions"]))
        self.assertTrue(all(not a["executed"] for a in body["wave"]["actions"]))
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_alias_warmup_runs_one_mock_session_and_releases(self):
        status, body = self.reply(self.handler("/api/farm/warmup-wave", {"device_id": "C24C", "clips": 1, "time_scale": 0}))
        self.assertEqual(200, status)
        self.assertEqual(1, body["sessionsRun"])
        self.assertTrue(self.input_commands())
        self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_console_hardware_id_runs_requested_warmup(self):
        status, body = self.reply(self.handler("/api/farm/warmup-wave", {"device_id": C24C, "clips": 1, "time_scale": 0}))
        self.assertEqual(200, status)
        self.assertEqual(1, body["sessionsRun"], f"Console target silently did no work: {body}")

    def test_console_hardware_id_upload_finds_its_persona(self):
        status, body = self.reply(self.handler("/api/farm/single-upload", {"device_id": C24C, "platform": "instagram", "format": "ig_reel"}))
        self.assertEqual(200, status, str(body))
        self.assertGreater(body["result"]["totalClicks"], 0)

    def test_alias_upload_runs_mock_sequence_and_releases(self):
        status, body = self.reply(self.handler("/api/farm/single-upload", {"device_id": "C24C", "platform": "instagram", "format": "ig_reel"}))
        self.assertEqual(200, status, str(body))
        self.assertGreater(body["result"]["totalClicks"], 0)
        self.assertTrue(body["simulated"])
        self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_console_funnel_payload_runs_advertised_dm_workflow(self):
        # Exact fields sent by MainWindow.FarmTab.cs; fake leaf operations record routing only.
        with patch.object(engine.ConversionFunnelEngine, "run_comment_to_dm_responder", return_value={}) as dm, \
             patch.object(engine.ConversionFunnelEngine, "post_and_pin_cta_comment", return_value={}) as pin:
            status, body = self.reply(self.handler("/api/farm/funnel-suite", {"device_id": C24C, "keyword": "TESTWORD"}))
        self.assertEqual(200, status, str(body))
        self.assertTrue(dm.called, f"UI advertises Comment-to-DM, but DM calls={dm.call_count}, pin calls={pin.call_count}")

    def test_owned_phone_refuses_upload_without_taking_over(self):
        tokens = self.kernel.acquire(["C24C"])
        status, body = self.reply(self.handler("/api/farm/single-upload", {"device_id": "C24C"}))
        self.assertEqual(409, status, str(body))
        self.assertEqual(tokens, self.runtime.mock_kernel.leases)
        self.assertEqual([], self.input_commands())
        self.kernel.release(tokens)

    def test_upload_failure_releases_lease_and_stops_sequence(self):
        with patch.object(engine.SocialUploadOrchestrator, "_trigger_imouse_pull_shortcut", side_effect=RuntimeError("Injected failure")), \
             patch.object(engine.SocialUploadOrchestrator, "_launch_app_spotlight") as later:
            status, body = self.reply(self.handler("/api/farm/single-upload", {"device_id": "C24C"}))
        self.assertEqual(500, status)
        self.assertIn("Injected failure", body["error"])
        later.assert_not_called()
        self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_stop_targets_only_requested_mock_phone(self):
        self.kernel.acquire(["C24C", "C241"])
        status, body = self.reply(self.handler("/api/farm/emergency-stop", {"device_id": "C24C"}))
        self.assertEqual(200, status, str(body))
        self.assertNotIn("C24C", self.runtime.mock_kernel.leases)
        self.assertIn("C241", self.runtime.mock_kernel.leases)

    def test_mock_stop_remains_latched_until_explicit_resume(self):
        self.kernel.post("/input/stop", {"id": "C24C"})
        with self.assertRaises(engine.KernelSafetyError, msg="Mock permits work immediately after Stop; cannot validate a persistent Stop"):
            self.kernel.preflight_phone("C24C")

    def test_stop_during_warmup_causes_failure_and_releases(self):
        def stopped_during_wait(_):
            self.kernel.post("/input/stop", {"id": "C24C"})
        with patch.object(engine.time, "sleep", side_effect=stopped_during_wait):
            status, body = self.reply(self.handler("/api/farm/warmup-wave", {"device_id": "C24C", "clips": 2, "time_scale": 1}))
        self.assertEqual(409, status, str(body))
        self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_stop_requires_explicit_success_reply(self):
        with patch.object(self.kernel, "post", return_value={}):
            status, body = self.reply(self.handler("/api/farm/emergency-stop", {"device_id": "C24C"}))
        self.assertNotEqual(200, status, f"Unconfirmed stop claimed success: {body}")

    def test_mixed_live_wave_refuses_before_any_input(self):
        # Live-mode validation with an IN-MEMORY transport; no socket is possible.
        mock = engine.MockApiServer(device_ids=[C24C, C241])
        def transport(method, url, body, timeout):
            raw, headers = mock.handle(method, url, body, timeout)
            if method == "GET" and url.endswith("/kernel/status"):
                data = json.loads(raw)
                data["data"]["receivers"][0]["name"] = "iMouse2-C24C"
                raw = json.dumps(data).encode()
            return raw, headers
        client = engine.IMouseKernel(transport=transport)
        client._is_live_http = True
        personas = [self.runtime.db.get_persona("C24C"), self.runtime.db.get_persona("C241")]
        for persona in personas:
            persona["account_day"] = 1
        with patch.object(self.runtime, "get_kernel", return_value=client), \
             patch.object(self.runtime.db, "list_personas", return_value=personas):
            status, body = self.reply(self.handler("/api/farm/warmup-wave", {"clips": 1, "time_scale": 0}))
        self.assertEqual(409, status, str(body))
        inputs = [fun for fun, _ in mock.commands_dispatched if fun.startswith(("/mouse/", "/key/"))]
        self.assertEqual([], inputs, "Mixed wave already acted on C24C before refusing C241")

    def test_100_character_text_preserves_bytes_in_twelve_character_chunks(self):
        text = "Hi there! " * 10
        self.type_text(text)
        chunks = [data["key"] for fun, data in self.input_commands() if fun == "/key/sendkey"]
        self.assertEqual(text, "".join(chunks))
        self.assertEqual(9, len(chunks))
        self.assertLessEqual(max(map(len, chunks)), 12)

    def test_chunk_timeout_is_never_retried(self):
        original = self.kernel.send
        calls = []
        def send(pid, token, fun, **data):
            calls.append(data["key"])
            if len(calls) == 2:
                raise TimeoutError("Injected lost response")
            return original(pid, token, fun, **data)
        with patch.object(self.kernel, "send", side_effect=send):
            with self.assertRaises(TimeoutError):
                self.type_text("a" * 40)
        self.assertEqual(["a" * 12, "a" * 12], calls)
        self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_chunk_strategy_refuses_non_ascii_before_input(self):
        with self.assertRaises(engine.KernelSafetyError):
            self.type_text("snowman \u2603")
        self.assertEqual([], self.input_commands())

    def test_oversize_text_is_refused_not_silently_truncated(self):
        with self.assertRaises((ValueError, engine.KernelSafetyError), msg="201 characters were silently shortened"):
            self.type_text("x" * 201)
        self.assertEqual([], self.input_commands())

    def test_unsupported_screen_keyboard_character_is_not_silently_dropped(self):
        with self.assertRaises((ValueError, engine.KernelSafetyError), msg="Unsupported emoji was silently dropped"):
            self.type_text("\U0001f642", engine.TextEntryStrategy.ON_SCREEN_KEYBOARD_JITTER)

    def test_blank_image_does_not_match_a_comment_keyword(self):
        result = self.runtime.vision.inspect_comment_notification(self.runtime.mock_kernel._make_bmp(255), "TESTWORD")
        self.assertFalse(result.get("matched"), f"No text in image, yet reported keyword match: {result}")

    def test_blank_image_does_not_fabricate_profile_view_counts(self):
        result = self.runtime.vision.extract_profile_grid_views(self.runtime.mock_kernel._make_bmp(90))
        self.assertEqual([], result, "A blank image has no readable view counters; report unavailable, not invented numbers")

    def test_explicit_observation_provider_result_is_used(self):
        provider = Mock(return_value={"matched": False})
        vision = engine.VlmComputerUseAdapter(external_vlm_fn=provider)
        self.assertFalse(vision.inspect_comment_notification(b"image", "TESTWORD")["matched"])
        provider.assert_called_once_with(b"image", "notif_keyword:TESTWORD")

    def test_existing_staged_media_serves_exact_bytes(self):
        folder = self.runtime.stage_root / "C24C"
        folder.mkdir()
        (folder / "sample.jpg").write_bytes(b"test-media")
        status, body = self.reply(self.handler("/stage/C24C/sample.jpg"), "GET")
        self.assertEqual((200, b"test-media"), (status, body))

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

    def test_shortcut_export_is_parseable_and_targets_simulation_manifest(self):
        shortcut = plistlib.loads((self.runtime.stage_root / "iMousePull.shortcut.plist").read_bytes())
        first = shortcut["WFWorkflowActions"][0]["WFWorkflowActionParameters"]
        self.assertEqual("http://127.0.0.1:9914/stage/C24C/manifest.json", first["WFURLActionURL"])
        self.assertEqual("C24C", first["WFDeviceId"])

    def test_stage_cannot_read_outside_stage_root(self):
        # A harmless marker in our temporary directory, never any real private file.
        (self.root / "outside.txt").write_text("test-marker-outside-stage", encoding="utf-8")
        status, body = self.reply(self.handler("/stage/../outside.txt"), "GET")
        self.assertNotEqual(200, status, f"Stage traversal exposed marker: {body!r}")

    def test_malformed_json_returns_client_error_instead_of_aborting_handler(self):
        handler = self.handler("/api/farm/warmup-wave", raw=b"{bad-json")
        try:
            status, _ = self.reply(handler)
        except Exception as exc:
            self.fail(f"Uncaught {type(exc).__name__} instead of a 4xx response: {exc}")
        self.assertGreaterEqual(status, 400)
        self.assertLess(status, 500)

    def test_cross_origin_post_is_refused_without_input(self):
        status, _ = self.reply(self.handler("/api/farm/warmup-wave", origin="https://example.invalid"))
        self.assertEqual(403, status)
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

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


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({"test": test.id(), "status": "passed"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append({"test": test.id(), "status": "failed", "detail": self._exc_info_to_string(err, test)})

    def addError(self, test, err):
        super().addError(test, err)
        self.records.append({"test": test.id(), "status": "error", "detail": self._exc_info_to_string(err, test)})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records.append({"test": test.id(), "status": "skipped", "detail": reason})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    # Defense in depth: even an accidental direct socket cannot reach a service.
    def offline_only(event, event_args):
        if event in ("socket.connect", "socket.sendto"):
            raise AssertionError("All network access forbidden in feature validation")
    sys.addaudithook(offline_only)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FarmFeatureValidation)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    root = Path(__file__).resolve().parents[1]
    sources = ["tools/imouse_farm_server.py", "tools/imouse_social_automation.py",
               "src/iMouse.Console/MainWindow.FarmTab.cs", "src/iMouse.Console/MainWindow.xaml",
               "tools/test_farm_feature_validation.py"]
    report = {"offlineOnly": True, "desktopControl": False, "phoneInput": False,
              "testedAtUtc": engine.utc_now(), "testsRun": result.testsRun,
              "passed": sum(r["status"] == "passed" for r in result.records),
              "failed": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "results": result.records,
              "dependencies": {"python": sys.version.split()[0], "pillowAvailable": engine.PIL_AVAILABLE,
                               "opencvAvailable": engine.CV2_AVAILABLE, "ffprobe": shutil.which("ffprobe")},
              "sourceSha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sources}}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
