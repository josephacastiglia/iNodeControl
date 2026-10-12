"""Synthetic and saved-file analysis only. Never start the soak or contact hardware."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("endurance", Path(__file__).with_name("analyze_endurance.py"))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def sample(seconds=0, console=2, frames=10, receiver_pid=3, restarts=0, live=True):
    return {"kind": "sample", "at": f"2026-10-11T00:00:{seconds:02d}+00:00", "elapsed_s": seconds,
            "kernel_pid": 1, "console_pid": console, "fleet_match": True,
            "receivers": [{"name": "iMouse2-C24C", "deviceid": "fixture", "frames": frames,
                           "receiver_pid": receiver_pid, "receiver_restarts": restarts,
                           "receiver_state": "mirroring" if live else "offline", "live": live}],
            "processes": [{"pid": 1, "role": "kernel", "name": "kernel", "alive": True,
                           "working_set": 100, "private_bytes": 80}]}


class EnduranceTests(unittest.TestCase):
    def setUp(self):
        self.fixture_root = Path(__file__).resolve().parents[1] / ".tools/offline-test-fixtures"
        self.fixture_root.mkdir(parents=True, exist_ok=True)

    def test_explicit_false_stuck_flag_is_not_a_stuck_input(self):
        self.assertFalse(a.mentions_stuck({"stuck": False, "stuck_buttons": 0}))

    def test_restart_counter_and_pid_change_are_not_double_counted(self):
        phones = a.analyze_phones([sample(), sample(15, frames=20, receiver_pid=4, restarts=1)])
        self.assertEqual(phones[0]["restarts"], 1)

    def test_console_restart_splits_continuous_run(self):
        self.assertEqual(len(a.split_sessions([sample(), sample(15, console=4)])), 2)

    def test_requested_fleet_cannot_silently_fall_back(self):
        with self.assertRaises(ValueError):
            a.pick_live([[sample()]], {"expected": {"kernel_pid": 999}})

    def test_offline_interval_is_not_called_a_live_stream_freeze(self):
        phones = a.analyze_phones([sample(live=False), sample(15, live=False)])
        self.assertEqual(phones[0]["freezes"], 0)

    def test_failed_interactions_are_not_labelled_ok(self):
        result = a.analyze_interactions([{"kind": "interaction", "ok": False, "target": "C24C"}], [sample()])
        self.assertNotIn("ok", result["errors"])

    def test_nonobject_json_rows_are_counted_as_bad(self):
        with tempfile.TemporaryDirectory(dir=self.fixture_root) as folder:
            path = Path(folder) / "telemetry.jsonl"
            path.write_text('42\nnull\n{"kind":"sample"}\n', encoding="utf-8")
            rows, bad = a.load_rows(path)
        self.assertEqual(bad, 2)
        self.assertEqual(rows, [{"kind": "sample"}])

    def test_all_failed_interactions_produce_nonzero_analyzer_exit(self):
        with tempfile.TemporaryDirectory(dir=self.fixture_root) as folder:
            root = Path(folder)
            rows = [sample(), {"kind": "interaction", "ok": False, "target": "C24C",
                               "error": "fixture ownership conflict", "acquire_code": 409}, sample(15, frames=30)]
            (root / "telemetry.jsonl").write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            (root / "status.json").write_text('{"running": false, "duration_s":15}', encoding="utf-8")
            with patch("sys.argv", ["analyze_endurance.py", "--dir", str(root)]), contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(a.main(), 0)

    def test_true_stuck_state_is_detected_recursively(self):
        self.assertTrue(a.mentions_stuck({"input": {"stuck": True}}))
        self.assertTrue(a.mentions_stuck({"error": "mouse button stuck"}))
        self.assertFalse(a.mentions_stuck({"error": "no stuck inputs", "input": {"stuck": False}}))

    def test_repeated_pid_transition_is_counted_each_time(self):
        phones = a.analyze_phones([sample(), sample(15, receiver_pid=4), sample(30, receiver_pid=3)])
        self.assertEqual(phones[0]["restarts"], 2)

    def test_live_zero_frame_gap_is_flagged(self):
        samples = [sample(), sample(15)]
        phones = a.analyze_phones(samples)
        ix = a.analyze_interactions([], samples)
        health = a.evaluate_health(samples, phones, a.analyze_memory(samples), ix)
        self.assertEqual(phones[0]["freezes"], 1)
        self.assertEqual(health["status"], "failed")
        self.assertFalse(health["gate10_acceptance"])

    def test_no_interactions_is_incomplete_even_when_samples_look_clean(self):
        samples = [sample(), sample(15, frames=30)]
        health = a.evaluate_health(samples, a.analyze_phones(samples), a.analyze_memory(samples), a.analyze_interactions([], samples))
        self.assertEqual(health["status"], "incomplete")

    def test_unrecorded_release_does_not_count_as_clean(self):
        samples = [sample(), sample(15, frames=30)]
        ix = a.analyze_interactions([{"kind": "interaction", "ok": True, "target": "C24C"}], samples)
        health = a.evaluate_health(samples, a.analyze_phones(samples), a.analyze_memory(samples), ix)
        self.assertEqual(health["status"], "incomplete")
        self.assertEqual(ix["release_unverified"], 1)

    def test_transient_dead_process_remains_a_failure(self):
        samples = [sample(), sample(15, frames=20), sample(30, frames=30)]
        samples[1]["processes"][0]["alive"] = False
        health = a.evaluate_health(samples, a.analyze_phones(samples), a.analyze_memory(samples), a.analyze_interactions([], samples))
        self.assertEqual(health["status"], "failed")

    def test_separate_output_keeps_saved_evidence_and_old_dashboard_unchanged(self):
        with tempfile.TemporaryDirectory(dir=self.fixture_root) as folder:
            root = Path(folder)
            rows = [sample(), {"kind": "interaction", "ok": False, "target": "C24C", "error": "fixture"}, sample(15, frames=20)]
            telemetry = "\n".join(json.dumps(row) for row in rows)
            (root / "telemetry.jsonl").write_text(telemetry, encoding="utf-8")
            (root / "status.json").write_text("{}", encoding="utf-8")
            (root / "DASHBOARD.md").write_text("original dashboard", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(a.main(["--dir", str(root), "--out", str(root / "new-report")]), 1)
            self.assertEqual((root / "telemetry.jsonl").read_text(encoding="utf-8"), telemetry)
            self.assertEqual((root / "DASHBOARD.md").read_text(encoding="utf-8"), "original dashboard")
            result = json.loads((root / "new-report/analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(result["health"]["status"], "failed")
            self.assertFalse(result["health"]["gate10_acceptance"])


if __name__ == "__main__":
    unittest.main()
