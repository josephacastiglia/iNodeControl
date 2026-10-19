"""Offline diagnostics tests. All host/UI/network boundaries are replaced."""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("diagnostics", Path(__file__).with_name("export_diagnostics.py"))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "kernel data"
        self.console_data = self.root / "candidate data"
        for folder in (self.data, self.console_data, self.root / "console", self.root / "kernel"):
            folder.mkdir()
        self.receivers = self.data / "receivers.json"
        self.receivers.write_text("[]", encoding="utf-8")
        (self.data / "pointer-calibration.json").write_text("[]", encoding="utf-8")
        (self.data / "kernel-stdout.log").write_text("high-resolution 7 ms\n", encoding="utf-8")
        (self.console_data / "settings.json").write_text(json.dumps({"address": "http://127.0.0.1:9913", "theme": "Dark", "password": "fixture-secret"}), encoding="utf-8")
        for path in (self.root / "kernel/iMouse2.Kernel.dll", self.root / "console/iMouse2.exe", self.root / "console/iMouse2.dll", self.root / "uxplay.exe"):
            path.write_bytes(path.name.encode())
        command = subprocess.list2cmdline([str(self.root / "kernel/iMouse2.Kernel.exe"), "http://127.0.0.1:9913/api/", "--data-dir", str(self.data), "--receivers", str(self.receivers), "--receiver", str(self.root / "uxplay.exe")])
        self.procs = [
            {"pid": 1, "name": "iMouse2.Kernel.exe", "path": str(self.root / "kernel/iMouse2.Kernel.exe"), "command": command, "started": None},
            {"pid": 2, "name": "iMouse2.exe", "path": str(self.root / "console/iMouse2.exe"), "command": subprocess.list2cmdline(["iMouse2.exe", "--data-dir=" + str(self.console_data)]), "started": None},
        ]
        self.boundaries = contextlib.ExitStack()
        self.addCleanup(self.boundaries.close)
        self.boundaries.enter_context(patch.object(d, "ROOT", self.root))
        self.boundaries.enter_context(patch.object(d, "SOAK_STATUS", self.root / "no-soak.json"))
        self.boundaries.enter_context(patch.object(d, "processes", return_value=self.procs))
        self.boundaries.enter_context(patch.object(d, "window_titles", side_effect=AssertionError("UI forbidden")))
        self.boundaries.enter_context(patch.object(d, "mirror_state", side_effect=AssertionError("UI forbidden")))
        self.boundaries.enter_context(patch.object(d, "windows_version", return_value={"name": "fixture"}))
        self.boundaries.enter_context(patch.object(d, "memory", return_value={"total_bytes": 100}))
        self.network = self.boundaries.enter_context(patch.object(d, "get_json", side_effect=self.response))

    @staticmethod
    def response(url):
        if url.endswith("/kernel/status"):
            return {"data": {"receivers": [], "allowed": ["TEST"]}}
        if url.endswith("/input/status"):
            return {"data": {"phones": []}}
        return {"data": {"list": []}}

    def receiver_report(self, fields):
        receiver = {"name": "simulated", "deviceid": "fake", "receiver_pid": 3,
                    "receiver_state": "mirroring", "live": True, "frames": 5, **fields}
        self.procs.append({"pid": 3, "parent": 1, "name": "uxplay.exe", "command": "uxplay.exe -p 7110"})
        self.network.side_effect = lambda url: ({"data": {"receivers": [receiver]}}
            if url.endswith("/kernel/status") else self.response(url))
        return d.collect("http://127.0.0.1:9913")

    def test_frame_delivery_metadata_survives_export_without_false_freeze(self):
        report = self.receiver_report({"frame_age_ms": 2500, "frame_delivery": "quiet",
            "frame_session": "fixture-session", "frame_pipe_connected": True,
            "frame_message": "No new frame", "receiver_message": ""})
        row = report["receivers"][0]
        self.assertEqual(row["frame_age_ms"], 2500)
        self.assertEqual(row["frame_delivery"], "quiet")
        self.assertEqual(row["frame_session"], "fixture-session")
        self.assertTrue(row["frame_pipe_connected"])
        self.assertEqual(row["frame_message"], "No new frame")
        self.assertFalse(any("quiet" in err or "freeze" in err for err in report["errors"]))

    def test_legacy_receiver_freshness_stays_unknown(self):
        row = self.receiver_report({})["receivers"][0]
        self.assertIsNone(row["frame_age_ms"])
        self.assertIsNone(row["frame_delivery"])
        self.assertIsNone(row["frame_session"])
        self.assertIsNone(row["frame_pipe_connected"])

    def test_offline_kernel_still_produces_partial_report(self):
        self.network.side_effect = OSError("offline fixture")
        with patch.object(d, "processes", return_value=[]):
            report = d.collect("http://127.0.0.1:9913")
        self.assertEqual(report["collection_status"], "partial")
        self.assertTrue(report["errors"])
        self.assertIsNone(report["kernel"]["pid"])

    def test_default_export_never_reads_windows(self):
        d.collect("http://127.0.0.1:9913")
        d.window_titles.assert_not_called()
        d.mirror_state.assert_not_called()

    def test_candidate_settings_are_read_from_explicit_folder(self):
        report = d.collect("http://127.0.0.1:9913")
        self.assertEqual(report["console"]["address"], "http://127.0.0.1:9913")
        self.assertEqual(report["console"]["settings_path"], str(self.console_data / "settings.json"))
        self.assertNotIn("fixture-secret", json.dumps(report))

    def test_build_identity_includes_managed_console_dll(self):
        report = d.collect("http://127.0.0.1:9913")
        dll = next(row for row in report["binaries"] if row["name"] == "iMouse2.dll")
        self.assertEqual(dll["sha256"], d.sha256(self.root / "console/iMouse2.dll"))

    def test_missing_pacing_evidence_is_unknown(self):
        self.assertIsNone(d.pacing_ms("kernel.exe", ""))

    def test_equals_flag_with_spaces_and_quoted_token(self):
        command = subprocess.list2cmdline(["iMouse2.exe", "--data-dir=" + str(self.console_data)])
        self.assertEqual(d.arg_value(command, "--data-dir"), str(self.console_data))

    def test_empty_process_query_is_an_empty_fleet(self):
        done = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(d.subprocess, "run", return_value=done):
            # Restore the actual function despite the per-test collector boundary.
            self.assertEqual(self.real_processes(), [])

    def test_multiple_exports_never_overwrite_same_second(self):
        destination = self.root / "out"
        with patch.object(d, "collect", return_value={"exported_at": "fixture"}), contextlib.redirect_stdout(io.StringIO()):
            d.main(["--out", str(destination)])
            d.main(["--out", str(destination)])
        self.assertEqual(len(list(destination.glob("diagnostics-*.json"))), 2)

    def test_operator_settings_take_precedence_over_adjacent_mirror(self):
        appdata = self.root / "appdata"
        (appdata / "iMouse2").mkdir(parents=True)
        (appdata / "iMouse2/settings.json").write_text('{"address":"http://127.0.0.1:9913","theme":"Dark"}', encoding="utf-8")
        (self.root / "console/data").mkdir()
        (self.root / "console/data/settings.json").write_text('{"address":"http://127.0.0.1:9911"}', encoding="utf-8")
        self.procs[1]["command"] = "iMouse2.exe"
        with patch.dict(os.environ, {"APPDATA": str(appdata)}):
            report = d.collect("http://127.0.0.1:9913")
        self.assertEqual(report["console"]["address"], "http://127.0.0.1:9913")
        self.assertIn("appdata", report["console"]["settings_path"])

    def test_multiple_consoles_are_not_guessed(self):
        self.procs.append(dict(self.procs[1], pid=3))
        report = d.collect("http://127.0.0.1:9913")
        self.assertIsNone(report["console"]["pid"])
        self.assertIsNone(report["console"]["settings_path"])
        selected = d.collect("http://127.0.0.1:9913", console_pid=3)
        self.assertEqual(selected["console"]["pid"], 3)

    def test_kernel_on_other_port_is_not_used_as_fallback(self):
        self.procs[0]["command"] = self.procs[0]["command"].replace("9913", "99130")
        report = d.collect("http://127.0.0.1:9913")
        self.assertIsNone(report["kernel"]["pid"])
        self.assertIsNone(report["settings"]["data_dir"])

    def test_unknown_test_directory_never_uses_operator_settings(self):
        for args in (["iMouse2.exe", "--ui-test"], ["iMouse2.exe", "--data-dir="],
                     ["iMouse2.exe", "--data-dir", "--ui-test"], ["iMouse2.exe", "--data-dir=relative"]):
            with self.subTest(args=args):
                self.assertIsNone(d.console_settings_path({"command": subprocess.list2cmdline(args)}))

    def test_malformed_local_config_retains_other_components(self):
        self.receivers.write_text("{broken", encoding="utf-8")
        report = d.collect("http://127.0.0.1:9913")
        self.assertEqual(report["collection_status"], "partial")
        self.assertTrue(any("receiver map" in message for message in report["errors"]))
        self.assertTrue(all(binary["sha256"] for binary in report["binaries"]))

    def test_failed_host_metrics_do_not_prevent_export(self):
        with patch.object(d, "memory", side_effect=OSError("fixture denied")):
            report = d.collect("http://127.0.0.1:9913")
        self.assertIsNone(report["system"]["memory"])
        self.assertEqual(report["kernel"]["pid"], 1)

    def test_api_error_code_is_not_complete_status(self):
        self.network.side_effect = lambda url: {"data": {"code": 409, "list": []}}
        report = d.collect("http://127.0.0.1:9913")
        self.assertEqual(report["collection_status"], "partial")
        self.assertIsNone(report["kernel"]["input"])

    def test_invalid_endpoint_is_rejected_before_collection(self):
        for url in ("file:///etc/example", "http://user:password@localhost:9913", "http://localhost:9913?token=secret", "http://localhost:bad"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                d.collect(url)
        self.network.assert_not_called()

    def test_export_redacts_known_credentials_but_keeps_build_and_board_identity(self):
        report = {"tokens": {"phone": "secret-value"}, "command": '--token "cli-secret"',
                  "error": 'password=error-secret Bearer bearer-secret https://user:url-secret@host/api',
                  "sha256": "build-hash", "uid": "board-id", "serial_number": "personal-serial"}
        path = d.write_report(report, self.root / "out")
        text = path.read_text(encoding="utf-8")
        for secret in ("secret-value", "cli-secret", "error-secret", "bearer-secret", "url-secret", "personal-serial"):
            self.assertNotIn(secret, text)
        self.assertIn("build-hash", text)
        self.assertIn("board-id", text)

    def test_invalid_report_leaves_no_partial_export(self):
        destination = self.root / "out"
        with self.assertRaises(ValueError):
            d.write_report({"invalid": float("nan")}, destination)
        self.assertFalse(destination.exists())


DiagnosticTests.real_processes = staticmethod(d.processes)

if __name__ == "__main__":
    unittest.main()
