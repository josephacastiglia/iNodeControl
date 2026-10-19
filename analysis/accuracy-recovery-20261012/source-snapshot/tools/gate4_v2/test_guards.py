"""Run/evidence safeguards. All service and image boundaries are mocked."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import ExitStack
from argparse import Namespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gate4_1000_tap_suite as g


class Guards(unittest.TestCase):
    def test_unknown_ownership_refuses_preflight(self):
        k = Mock()
        k.status.return_value = {"input_leases_required": True, "mock": True,
                                 "receivers": [{"deviceid": "one", "live": True}]}
        k.input_status.return_value = {"one": {}}
        with self.assertRaises(SystemExit):
            g.preflight(k, {"_enabled": [{"id": "one", "tag": "One"}]})

    def test_pending_release_refuses_preflight(self):
        k = Mock()
        k.status.return_value = {"input_leases_required": True, "mock": True,
                                 "receivers": [{"deviceid": "one", "live": True}]}
        k.input_status.return_value = {"one": dict(owned=False, active=False, stopped=False,
                                                   releasing=True, release_failed=False)}
        with self.assertRaises(SystemExit):
            g.preflight(k, {"_enabled": [{"id": "one", "tag": "One"}]})

    def test_existing_run_refused_before_service_access(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); run = out / "runs/old"; run.mkdir(parents=True)
            manifest = run / "manifest.json"; manifest.write_text("original", encoding="utf-8")
            args = Namespace(out=str(out), url="mock://only", total=1, seed=1, run_id="old")
            with patch.object(g, "Kernel", side_effect=AssertionError("service must not be constructed")):
                with self.assertRaises(SystemExit): g.run(args, {"_enabled": []})
            self.assertEqual(manifest.read_text(), "original")

    def test_path_escape_run_id_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            args = Namespace(out=directory, url="mock://only", total=1, seed=1, run_id="../escape")
            with patch.object(g, "Kernel", side_effect=AssertionError("service must not be constructed")):
                with self.assertRaises(SystemExit): g.run(args, {"_enabled": []})
            self.assertFalse((Path(directory)/"escape").exists())

    def test_small_synthetic_run_cannot_pass_1000_trial_gate(self):
        rows = [{"target_hit": True, "pass": True, "setup_ok": True, "effect_ms": 1} for _ in range(60)]
        self.assertIsNone(g.summarize(rows, 60, "complete", None)["criterion_995_of_1000"])

    def test_error_blocks_following_inputs(self):
        self.assertIsNotNone(g.blocking_reason({"error": "request outcome unknown"}))

    def test_missing_release_confirmation_raises(self):
        k = g.Kernel("mock://only")
        with patch.object(k, "post", return_value={"code": 17}):
            with self.assertRaises(RuntimeError): k.release({"one": "token"})

    def test_failed_release_member_is_not_confirmation(self):
        k = g.Kernel("mock://only")
        with patch.object(k, "post", return_value={"code": 0, "results": [{"id": "one", "code": 33}]}):
            with self.assertRaises(RuntimeError): k.release({"one": "token"})

    def test_partial_acquire_releases_only_returned_approved_token(self):
        k = g.Kernel("mock://only")
        got = {"code": 409, "leases": [{"id": "one", "token": "a"}, {"id": "outsider", "token": "b"}]}
        with patch.object(k, "post", side_effect=[got, {"code": 0}]) as post:
            with self.assertRaises(RuntimeError): k.acquire(["one", "two"])
            self.assertEqual(post.call_args_list[-1].args, ("/input/release", {"id": "one", "tokens": {"one": "a"}}))

    def fake_run(self, directory, failure=None, release_failure=None):
        cfg = {"_enabled": [{"id": "one", "tag": "One"}], "phones": [], "_sha256": "config"}
        args = Namespace(out=directory, url="mock://only", total=2, seed=1, run_id="fresh")
        specs = [{"n": i, "phone": "One", "id": "one", "category": "after_home", "target": "A"} for i in range(2)]
        k = Mock(); k.acquire.return_value = {"one": "token"}
        k.input_status.return_value = {"one": {"lease_remaining_ms": 100000}}
        k.release.side_effect = release_failure
        def trial(*args):
            if failure: raise failure
            return {**args[1], "pass": True, "target_hit": True, "setup_ok": True, "effect_ms": 1}
        with ExitStack() as stack:
            for name, value in (("plan", specs), ("load_calibration", {"reviewed_by": "test"}),
                                ("preflight", {}), ("sha256_file", "hash"), ("Kernel", k)):
                stack.enter_context(patch.object(g, name, return_value=value))
            called = stack.enter_context(patch.object(g, "trial", side_effect=trial))
            code = g.run(args, cfg)
        status = json.loads((Path(directory)/"runs/fresh/status.json").read_text())
        return code, status, k, called.call_count

    def test_release_failure_prevents_complete_status(self):
        with tempfile.TemporaryDirectory() as directory:
            code, status, k, count = self.fake_run(directory, release_failure=RuntimeError("unknown release"))
        self.assertEqual(code, 2)
        self.assertEqual(status["state"], "stopped")
        self.assertFalse(status["release"]["confirmed"])
        k.release.assert_called_once_with({"one": "token"})

    def test_failed_trial_stops_and_is_recorded_before_release(self):
        with tempfile.TemporaryDirectory() as directory:
            code, status, k, count = self.fake_run(directory, failure=TimeoutError("tap answer lost"))
            rows = (Path(directory)/"runs/fresh/results.jsonl").read_text().splitlines()
        self.assertEqual((code, count, len(rows)), (2, 1, 1))
        self.assertIn("tap answer lost", json.loads(rows[0])["error"])
        self.assertTrue(status["release"]["confirmed"])

    def test_keyboard_interrupt_is_not_recorded_as_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KeyboardInterrupt): self.fake_run(directory, failure=KeyboardInterrupt())
            status = json.loads((Path(directory)/"runs/fresh/status.json").read_text())
        self.assertEqual(status["state"], "stopped")
        self.assertIn("interrupted", status["stopped_because"])
        self.assertTrue(status["release"]["confirmed"])

    def test_failed_setup_cannot_meet_accuracy_gate(self):
        rows = [{"target_hit": True, "pass": False, "setup_ok": False, "effect_ms": 1} for _ in range(1000)]
        self.assertFalse(g.summarize(rows, 1000, "complete", None)["criterion_995_of_1000"])

    def test_target_path_is_not_accepted_as_filename(self):
        phone = {"targets": [{"name": "../escape", "x": 70, "y": 150}]}
        self.assertIn("target names must be simple names, not paths", g.check_targets(phone))

    def test_cli_without_live_makes_no_service_call(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"config.json"; path.write_text("{}")
            with patch.object(sys, "argv", ["suite", "--config", str(path)]), \
                 patch.object(g, "load_config", return_value={}), \
                 patch.object(g, "Kernel", side_effect=AssertionError("unexpected service")):
                with self.assertRaisesRegex(SystemExit, "without --live"): g.main()

    def test_old_entry_point_is_the_same_implementation(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import gate4_suite
        self.assertIs(gate4_suite, g)

    def test_calibration_cannot_overwrite_previous_references(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory); (out/"refs").mkdir()
            with patch.object(g, "preflight", side_effect=AssertionError("no service before refusal")):
                with self.assertRaises(SystemExit): g.calibrate(Mock(), {"_enabled": []}, out)


if __name__ == "__main__": unittest.main(verbosity=2)
