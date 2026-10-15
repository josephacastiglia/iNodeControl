"""Offline failure-path tests. No listener, device, shell or desktop use."""
import contextlib
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "analysis/gate5-everyday-controls-20260916/run_controls.py"
spec = importlib.util.spec_from_file_location("gate5_navigation", SOURCE)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

PLAN = {"url": "http://127.0.0.1:9913/api", "kernel_sha256": "expected-hash"}


def bmp():
    data = bytearray(54 + 16 * 3 * 128)
    data[:2] = b"BM"
    struct.pack_into("<I", data, 10, 54)
    struct.pack_into("<ii", data, 18, 16, 128)
    struct.pack_into("<H", data, 28, 24)
    return bytes(data)


class FakeKernel(runner.CaptureKernel):
    def __init__(self):
        super().__init__(PLAN["url"])
        self.current = {"code": 0, "input_leases_required": True, "allowed": ["C24C"],
            "process": {"pid": 123, "started_utc": "fixed-start"}, "build_identity": {"sha256": "expected-hash"},
            "input_configuration": {"hid_reply_boards": ["C24C"], "absolute_probe_board": None},
            "control_compatibility": {"home_sequence": "command-h", "home_sends_tab": False,
                                      "navigation_sequence": "direct-fn", "navigation_sends_tab": False},
            "receivers": [{"deviceid": runner.PHONE, "name": "iMouse2-C24C", "live": True,
                           "frame_pipe_connected": True, "frame_age_ms": 50, "frame_session": 2}]}
        self.device_rows = [{**runner.BINDING, "state": 1}]
        self.lease = {"id": runner.PHONE, "owned": False, "active": False, "stopped": False,
                      "releasing": False, "release_failed": False, "lease_remaining_ms": 120000, "generation": 3}
        self.calls = []
        self.photos = 0
        self.on_send = lambda: None
        self.on_acquire = lambda: None
        self.on_photo = lambda: None
        self.acquire_error = False
        self.release_error = False

    def _req(self, method, url, body=None, timeout=25):
        fun = body["fun"] if body else url.rsplit("/", 1)[1]
        self.calls.append((method, fun, deepcopy(body)))
        if body:
            data = body["data"]
            if fun == "/input/status":
                result = {"code": 0, "phones": [deepcopy(self.lease)]}
            elif fun == "/input/acquire":
                assert data["id"] == runner.PHONE
                assert data["lease_ms"] == 120000
                if self.acquire_error:
                    raise TimeoutError("MUST-NOT-LOG-TOKEN")
                if self.lease["owned"]:
                    result = {"code": 409, "message": "busy"}
                else:
                    self.lease["owned"] = True
                    result = {"code": 0, "leases": [{"id": runner.PHONE, "token": "PRIVATE-LEASE"}]}
                    self.on_acquire()
            elif fun == "/key/sendkey":
                assert data["id"] == runner.PHONE and data["token"] == "PRIVATE-LEASE"
                assert self.lease["owned"]
                self.on_send()
                result = {"code": 0}
            elif fun == "/input/release":
                assert data["id"] == runner.PHONE and data["tokens"] == {runner.PHONE: "PRIVATE-LEASE"}
                if self.release_error:
                    raise TimeoutError("MUST-NOT-LOG-TOKEN")
                self.lease["owned"] = False
                self.lease["generation"] += 1
                result = {"code": 0}
            else:
                raise AssertionError("Unexpected write " + fun)
        elif url.endswith("/kernel/status"):
            result = deepcopy(self.current)
        elif url.endswith("/device/get"):
            result = {"code": 0, "list": deepcopy(self.device_rows)}
        elif "/pic/screenshot?" in url:
            self.photos += 1
            self.on_photo()
            return bmp()
        else:
            raise AssertionError("Unexpected read " + url)
        return json.dumps({"status": 200, "data": result}).encode()

    def count(self, fun):
        return sum(c[1] == fun for c in self.calls)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(runner, "LIVE_ROOT", self.root / "live")
        self.root_patch.start()
        self.kernel = FakeKernel()
        self.n = 0

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def run_case(self, **kwargs):
        self.n += 1
        out = runner.LIVE_ROOT / str(self.n)
        result = runner.run_action(PLAN, kwargs.pop("case", "home-field"), 123, "on", out,
                                   live=True, kernel=self.kernel, sleep=lambda _: None, **kwargs)
        self.assertEqual(result, runner.load(out / "result.json"))
        self.assertNotIn("PRIVATE-LEASE", (out / "result.json").read_text())
        self.assertNotIn("MUST-NOT-LOG-TOKEN", (out / "result.json").read_text())
        return result

    def test_each_action_is_single_and_never_automatically_scored(self):
        for case, (key, _) in runner.CASES.items():
            with self.subTest(case=case):
                self.kernel = FakeKernel()
                result = self.run_case(case=case)
                self.assertEqual(result["errors"], [])
                self.assertTrue(result["api_success"])
                self.assertEqual(result["visible_acceptance"], "not_scored_requires_review")
                self.assertEqual(result["cleanup"], "release_confirmed")
                self.assertEqual(len(result["frames"]), 4)
                self.assertEqual(self.kernel.count("/key/sendkey"), 1)
                call = next(c for c in self.kernel.calls if c[1] == "/key/sendkey")
                self.assertEqual(call[2]["data"]["fn_key"], key)
                writes = [c[1] for c in self.kernel.calls if c[0] == "POST" and c[1] != "/input/status"]
                self.assertEqual(writes, ["/input/acquire", "/key/sendkey", "/input/release"])

    def test_explicit_live_flag_required_before_any_call(self):
        with self.assertRaises(ValueError):
            runner.run_action(PLAN, "home-field", 123, "on", runner.LIVE_ROOT / "no", kernel=self.kernel)
        self.assertEqual(self.kernel.calls, [])

    def test_historical_or_existing_output_is_refused(self):
        for out in (self.root, runner.LIVE_ROOT):
            with self.assertRaises(ValueError):
                runner.run_action(PLAN, "home-field", 123, "on", out, live=True, kernel=self.kernel)
        out = runner.LIVE_ROOT / "existing"
        out.mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            runner.run_action(PLAN, "home-field", 123, "on", out, live=True, kernel=self.kernel)
        self.assertEqual(self.kernel.calls, [])

    def test_bad_candidate_or_scope_refused_before_acquire(self):
        modifications = [
            ("build_identity", "sha256", "old-release"), ("process", "pid", 999),
            ("control_compatibility", "home_sends_tab", True),
            ("control_compatibility", "navigation_sequence", "vendor"),
            ("input_configuration", "absolute_probe_board", "C24C"),
            ("input_configuration", "hid_reply_boards", ["C241"]),
        ]
        for group, key, value in modifications:
            with self.subTest(key=key):
                self.kernel = FakeKernel()
                self.kernel.current[group][key] = value
                self.assertFalse(self.run_case()["command_attempted"])
                self.assertEqual(self.kernel.count("/input/acquire"), 0)
        for key, value in (("allowed", ["C24C", "C241"]), ("input_leases_required", False)):
            self.kernel = FakeKernel()
            self.kernel.current[key] = value
            self.assertFalse(self.run_case()["command_attempted"])
            self.assertEqual(self.kernel.count("/input/acquire"), 0)

    def test_busy_or_failed_phone_is_never_taken(self):
        for flag in ("owned", *runner.FLAGS):
            with self.subTest(flag=flag):
                self.kernel = FakeKernel()
                self.kernel.lease[flag] = True
                self.assertFalse(self.run_case()["command_attempted"])
                self.assertEqual(self.kernel.count("/input/acquire"), 0)

    def test_wrong_binding_or_stale_video_prevents_action(self):
        for mutate in (lambda k: k.device_rows[0].update(uid="OTHER"),
                       lambda k: k.current["receivers"][0].update(frame_age_ms=5001),
                       lambda k: k.current["receivers"][0].update(live=False),
                       lambda k: k.current["receivers"].append({"deviceid": "C241"})):
            self.kernel = FakeKernel()
            mutate(self.kernel)
            self.assertFalse(self.run_case()["command_attempted"])
            self.assertEqual(self.kernel.count("/input/acquire"), 0)

    def test_lost_acquire_answer_never_guesses_or_stops(self):
        self.kernel.acquire_error = True
        result = self.run_case()
        self.assertFalse(result["command_attempted"])
        self.assertIn("acquisition_unconfirmed", result["cleanup"])
        self.assertEqual(self.kernel.count("/input/acquire"), 1)
        self.assertEqual(self.kernel.count("/input/release"), 0)

    def test_baseline_failure_releases_without_sending(self):
        self.kernel.on_photo = lambda: (_ for _ in ()).throw(TimeoutError("no frame"))
        result = self.run_case()
        self.assertFalse(result["command_attempted"])
        self.assertEqual(result["cleanup"], "release_confirmed")

    def test_change_during_baseline_cancels_dispatch_without_touching_new_owner(self):
        self.kernel.on_photo = lambda: self.kernel.lease.update(generation=4)
        result = self.run_case()
        self.assertFalse(result["command_attempted"])
        self.assertEqual(result["cleanup"], "unconfirmed_requires_operator_review")
        self.assertEqual(self.kernel.count("/input/release"), 0)

    def test_timed_out_command_is_not_retried(self):
        def timeout():
            self.kernel.lease.update(owned=False, stopped=True)
            raise TimeoutError("MUST-NOT-LOG-TOKEN")
        self.kernel.on_send = timeout
        result = self.run_case()
        self.assertTrue(result["command_attempted"])
        self.assertFalse(result["api_success"])
        self.assertEqual(self.kernel.count("/key/sendkey"), 1)
        self.assertEqual(self.kernel.count("/input/release"), 0)
        self.assertIn("already_unowned", result["cleanup"])

    def test_failed_after_frame_keeps_record_and_releases(self):
        def photo():
            if self.kernel.photos > 1:
                raise TimeoutError("no frame")
        self.kernel.on_photo = photo
        result = self.run_case()
        self.assertTrue(result["api_success"])
        self.assertEqual(len(result["frames"]), 1)
        self.assertEqual(result["cleanup"], "release_confirmed")
        self.assertEqual(result["errors"][0]["stage"], "after_capture")

    def test_restart_after_command_blocks_cleanup_to_replacement_service(self):
        self.kernel.on_send = lambda: self.kernel.current["process"].update(started_utc="new-start")
        result = self.run_case()
        self.assertTrue(result["api_success"])
        self.assertEqual(result["cleanup"], "unconfirmed_requires_operator_review")
        self.assertEqual(self.kernel.count("/input/release"), 0)

    def test_release_timeout_preserves_partial_evidence(self):
        self.kernel.release_error = True
        result = self.run_case()
        self.assertEqual(result["cleanup"], "unconfirmed_requires_operator_review")
        self.assertEqual(self.kernel.count("/input/release"), 1)
        self.assertEqual(result["errors"][0]["stage"], "release")

    def test_insufficient_lease_time_refuses_command_and_releases(self):
        self.kernel.on_acquire = lambda: self.kernel.lease.update(lease_remaining_ms=15000)
        result = self.run_case()
        self.assertFalse(result["command_attempted"])
        self.assertEqual(result["cleanup"], "release_confirmed")

    def test_new_frame_session_during_preparation_refuses_command(self):
        self.kernel.on_photo = lambda: self.kernel.current["receivers"][0].update(frame_session=3)
        result = self.run_case()
        self.assertFalse(result["command_attempted"])
        self.assertEqual(result["cleanup"], "release_confirmed")

    def test_new_owner_after_command_is_left_alone(self):
        self.kernel.on_send = lambda: self.kernel.lease.update(generation=4)
        result = self.run_case()
        self.assertTrue(result["api_success"])
        self.assertEqual(self.kernel.count("/input/release"), 0)
        self.assertEqual(result["cleanup"], "unconfirmed_requires_operator_review")

    def test_command_and_capture_outcomes_remain_distinct(self):
        self.kernel.on_send = lambda: (_ for _ in ()).throw(TimeoutError("lost response"))
        result = self.run_case()
        self.assertEqual(result["command_outcome"], "unconfirmed_do_not_retry")
        self.assertEqual(result["cleanup"], "release_confirmed")
        self.assertEqual(self.kernel.count("/key/sendkey"), 1)

    def test_malformed_baseline_is_rejected_and_released(self):
        with patch.object(self.kernel, "shot", return_value=b"BM"):
            result = self.run_case()
        self.assertFalse(result["command_attempted"])
        self.assertEqual(result["cleanup"], "release_confirmed")

    def test_http_redirect_is_not_followed(self):
        redirect = runner.CaptureKernel.NoRedirect()
        self.assertIsNone(redirect.redirect_request(None, None, 302, "redirect", {}, "http://elsewhere/"))

    def test_idle_wait_is_before_lease_and_rechecks_busy_state(self):
        waits = []
        def sleep(seconds):
            waits.append(seconds)
            self.assertEqual(self.kernel.count("/input/acquire"), 0)
            self.kernel.lease["owned"] = True
        result = runner.run_action(PLAN, "home-idle", 123, "on", runner.LIVE_ROOT / "idle",
                                   live=True, kernel=self.kernel, sleep=sleep)
        self.assertEqual(waits, [60])
        self.assertFalse(result["command_attempted"])
        self.assertEqual(self.kernel.count("/input/acquire"), 0)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.record = self.root / "record"
        self.record.mkdir()
        self.run = self.root / "run"
        files = {"kernel/bin/iMouse2.Kernel.dll": b"fake-dll", "kernel/bin/iMouse2.Kernel.pdb": b"fake-pdb",
                 "kernel/data/devices.json": json.dumps([{k: v for k, v in runner.BINDING.items() if k != "receiver_name"}]).encode(),
                 "kernel/data/receivers.json": b"[]", "kernel/data/pointer-calibration.json": b"[]",
                 "console/data/settings.json": b'{"trackPointer":false,"address":"http://127.0.0.1:9913"}'}
        self.inventory = {}
        for relative, content in files.items():
            path = self.run / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            self.inventory[relative] = {"bytes": len(content), "sha256": runner.sha(path)}
        self.prep = {"run_directory": str(self.run), "kernel_validation": {
            "allowed": ["C24C"], "hid_reply_boards": ["C24C"], "absolute_probe_board": None,
            "home_sequence": "command-h", "navigation_sequence": "direct-fn", "address": PLAN["url"],
            "build": {"sha256": runner.sha(self.run / "kernel/bin/iMouse2.Kernel.dll")}}}
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        (self.record / "preparation.json").write_text(json.dumps(self.prep), encoding="utf-8")
        (self.record / "run-inventory.json").write_text(json.dumps(self.inventory), encoding="utf-8")

    def test_saved_fixture_verifies_without_network(self):
        with patch.object(runner.CaptureKernel, "_req", side_effect=AssertionError("No network")):
            self.assertEqual(runner.verify_preparation(self.record)["url"], PLAN["url"])

    def test_changed_candidate_file_is_refused(self):
        (self.run / "kernel/bin/iMouse2.Kernel.dll").write_bytes(b"changed!")
        with self.assertRaisesRegex(ValueError, "changed"):
            runner.verify_preparation(self.record)

    def test_inventory_escape_and_missing_critical_files_are_refused(self):
        self.inventory["../outside"] = {"bytes": 0, "sha256": ""}
        self.save()
        with self.assertRaisesRegex(ValueError, "escapes"):
            runner.verify_preparation(self.record)
        del self.inventory["../outside"]
        del self.inventory["kernel/bin/iMouse2.Kernel.pdb"]
        self.save()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            runner.verify_preparation(self.record)

    def test_remote_vendor_port_and_credential_urls_are_refused(self):
        for url in ("http://192.168.4.1:9913/api", "http://127.0.0.1:9911/api", "http://user@127.0.0.1:9913/api"):
            self.prep["kernel_validation"]["address"] = url
            self.save()
            with self.assertRaisesRegex(ValueError, "endpoint"):
                runner.verify_preparation(self.record)

    def test_default_cli_is_offline_even_with_case_selected(self):
        with patch.object(runner, "verify_preparation", return_value=PLAN), \
             patch.object(runner, "CaptureKernel", side_effect=AssertionError("No kernel")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(["--case", "home-field"]), 0)
        self.assertFalse(json.loads(output.getvalue())["rack_contacted"])

    def test_live_cli_requires_complete_explicit_arguments(self):
        with patch.object(runner, "verify_preparation", return_value=PLAN), \
             patch.object(runner, "CaptureKernel", side_effect=AssertionError("No kernel")), \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                runner.main(["--live"])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
