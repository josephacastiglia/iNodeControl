"""Offline safeguards: every HTTP/UI/process boundary is replaced."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("soak", Path(__file__).with_name("endurance_soak.py"))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

ID = "02:00:00:00:00:01"
RECEIVERS = [{"name": "iMouse2-C24C", "deviceid": ID}]


class SoakSafetyTests(unittest.TestCase):
    def setUp(self):
        fixture_root = Path(__file__).resolve().parents[1] / ".tools/offline-test-fixtures"
        fixture_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=fixture_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.boundaries = contextlib.ExitStack()
        self.addCleanup(self.boundaries.close)
        self.boundaries.enter_context(patch.object(s, "http", side_effect=AssertionError("rack forbidden")))
        self.boundaries.enter_context(patch.object(s, "sample", side_effect=AssertionError("host/UI sampling forbidden")))
        self.boundaries.enter_context(patch.object(s, "bind_fleet", side_effect=AssertionError("host/UI fleet binding forbidden")))
        self.boundaries.enter_context(patch.object(s, "ROOT", self.root))

    def status(self, **flags):
        return (1, 200, json.dumps({"data": {"code": 0, "phones": [{"id": ID, "owned": False, "active": False, "stopped": False, "releasing": False, "release_failed": False, **flags}]}}).encode())

    def blocked_trial(self, response):
        with patch.object(s, "http", return_value=response), patch.object(s, "post", return_value={"code": 409, "rtt_ms": 1}) as mutate:
            row = s.interact("fixture", RECEIVERS, "C24C", Path("unused"), 0)
        return row, mutate

    def test_owned_phone_is_refused_before_any_post(self):
        row, mutate = self.blocked_trial(self.status(owned=True))
        mutate.assert_not_called()
        self.assertFalse(row["ok"])

    def test_stopped_phone_is_not_automatically_resumed(self):
        row, mutate = self.blocked_trial(self.status(stopped=True))
        mutate.assert_not_called()
        self.assertFalse(row["ok"])

    def test_missing_status_does_not_mean_free(self):
        row, mutate = self.blocked_trial((1, 200, b'{"data":{"code":0,"phones":[]}}'))
        mutate.assert_not_called()
        self.assertFalse(row["ok"])

    def test_plain_start_is_not_authorization_for_live_input(self):
        with patch.object(s, "bind_fleet", side_effect=AssertionError("live preflight reached")) as bind, contextlib.redirect_stderr(io.StringIO()), patch("sys.argv", ["endurance_soak.py"]):
            with self.assertRaises(SystemExit):
                s.main()
        bind.assert_not_called()

    def test_existing_telemetry_cannot_be_appended_to_new_run(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "telemetry.jsonl").write_text("preserved", encoding="utf-8")
            with patch.object(s, "bind_fleet") as bind, contextlib.redirect_stderr(io.StringIO()), patch("sys.argv", ["endurance_soak.py", "--live", "--phone", "C24C", "--out", folder]):
                with self.assertRaises(SystemExit):
                    s.main()
            bind.assert_not_called()
            self.assertEqual((path / "telemetry.jsonl").read_text(encoding="utf-8"), "preserved")

    def test_active_releasing_or_cleanup_failure_blocks_input(self):
        for flag in ("active", "releasing", "release_failed"):
            with self.subTest(flag=flag):
                row, mutate = self.blocked_trial(self.status(**{flag: True}))
                mutate.assert_not_called()
                self.assertFalse(row["ok"])

    def test_unsuccessful_status_never_acquires(self):
        row, mutate = self.blocked_trial((1, 200, b'{"data":{"code":409,"phones":[]}}'))
        mutate.assert_not_called()
        self.assertFalse(row["ok"])

    def test_only_explicit_named_receivers_are_selected(self):
        other = {"name": "iMouse2-C241", "deviceid": "02:00:00:00:00:02"}
        self.assertEqual(s.selected_receivers(RECEIVERS + [other], ["C24C"]), RECEIVERS)

    def test_ambiguous_placeholder_or_duplicate_binding_is_refused(self):
        fixtures = [(RECEIVERS + RECEIVERS, ["C24C"]),
                    ([dict(RECEIVERS[0], deviceid="*")], ["C24C"]),
                    ([dict(RECEIVERS[0], deviceid="unbound-C24C")], ["C24C"]),
                    (RECEIVERS + [dict(RECEIVERS[0], name="iMouse2-C241")], ["C24C", "C241"])]
        for receivers, labels in fixtures:
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                s.selected_receivers(receivers, labels)

    def test_failed_send_is_not_retried(self):
        with patch.object(s, "post", return_value={"code": 409}) as mutate:
            with self.assertRaisesRegex(RuntimeError, "no retry"):
                s.send("fixture", "/mouse/click", {}, ID, {ID: "fake-token"})
        mutate.assert_called_once()

    def test_aggregate_success_cannot_hide_failed_member(self):
        self.assertFalse(s.call_succeeded({"code": 0, "results": [{"id": ID, "code": 409}]}))
        self.assertFalse(s.call_succeeded({"code": 0, "http": 500}))
        self.assertTrue(s.call_succeeded({"code": 0, "http": 200, "results": [{"id": ID, "code": 0}]}))

    def test_unexpected_lease_does_not_trigger_input_or_release_on_another_phone(self):
        acquired = {"code": 0, "rtt_ms": 1, "leases": [{"id": ID, "token": "fake-token"}, {"id": "outsider", "token": "fake-other"}]}
        with patch.object(s, "http", return_value=self.status()), patch.object(s, "post", side_effect=[acquired, {"code": 0}]) as mutate, patch.object(s, "send") as send:
            row = s.interact("fixture", RECEIVERS, "C24C", self.root, 0)
        send.assert_not_called()
        self.assertFalse(row["ok"])
        self.assertEqual(mutate.call_args.args[1], "/input/release")
        self.assertEqual(mutate.call_args.args[2], {"id": ID, "tokens": {ID: "fake-token"}})

    def test_first_failed_interaction_stops_and_preserves_failure(self):
        sampled = {"kind": "sample", "fleet_match": True, "kernel_pid": 1, "console_pid": 2, "receivers": RECEIVERS}
        failed = {"kind": "interaction", "target": "C24C", "ok": False, "error": "fixture failure", "release": {"code": 0}}
        with patch.object(s, "bind_fleet", return_value={"kernel_pid": 1, "console_pid": 2}), \
             patch.object(s, "kernel_status", return_value={"receivers": RECEIVERS}), \
             patch.object(s, "http", return_value=self.status()), \
             patch.object(s, "sample", return_value=sampled), \
             patch.object(s, "interact", return_value=failed) as interact, \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "interaction failed"):
                s.main(["--live", "--phone", "C24C", "--out", str(self.root / "run")])
        interact.assert_called_once()
        status = json.loads((self.root / "run/status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["stop_reason"], "failure")
        self.assertFalse(status["running"])
        self.assertFalse((self.root / "run/soak.pid").exists())
        rows = [json.loads(line) for line in (self.root / "run/telemetry.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(row["kind"] == "interaction" for row in rows), 1)

    def test_invalid_duration_is_refused_before_preflight(self):
        with patch.object(s, "bind_fleet") as bind, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                s.main(["--live", "--phone", "C24C", "--duration-hours", "nan", "--out", str(self.root / "run")])
        bind.assert_not_called()
        self.assertFalse((self.root / "run").exists())

    def test_status_write_failure_still_removes_own_pid_marker(self):
        sampled = {"kind": "sample", "fleet_match": True, "kernel_pid": 1, "console_pid": 2, "receivers": RECEIVERS}
        with patch.object(s, "bind_fleet", return_value={"kernel_pid": 1, "console_pid": 2}), \
             patch.object(s, "kernel_status", return_value={"receivers": RECEIVERS}), \
             patch.object(s, "http", return_value=self.status()), \
             patch.object(s, "sample", return_value=sampled), \
             patch.object(s, "write_json", side_effect=OSError("fixture disk failure")), \
             patch.object(s, "interact") as interact, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                s.main(["--live", "--phone", "C24C", "--out", str(self.root / "run")])
        interact.assert_not_called()
        self.assertFalse((self.root / "run/soak.pid").exists())

    def test_cleanup_does_not_remove_someone_elses_pid_marker(self):
        marker = self.root / "soak.pid"
        marker.write_text("999999", encoding="utf-8")
        s.release_pid_marker(marker)
        self.assertEqual(marker.read_text(encoding="utf-8"), "999999")


if __name__ == "__main__":
    unittest.main()
