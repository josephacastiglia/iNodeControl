"""Offline evidence-integrity regressions. Never start UIA or contact the rack."""
import importlib.util
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("gate6", Path(__file__).with_name("run_gate6.py"))
gate6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate6)


class EvidenceIntegrityTests(unittest.TestCase):
    def setUp(self):
        gate6.HELD.clear()
        gate6.UIA_OWNS["on"] = False
        self.network = patch.object(gate6, "api", side_effect=AssertionError("network forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.addCleanup(gate6.HELD.clear)
        self.addCleanup(setattr, gate6, "RUN", None)

    @staticmethod
    def act(box):
        box[0] = time.perf_counter()
        return {"via": "api", "dispatch_ms": 1.0, "code": 0}

    def test_rejected_console_action_never_falls_back_to_api(self):
        transport = Mock(return_value=(1, {"code": 0}))
        with self.assertRaisesRegex(RuntimeError, "wrong selected phone"):
            gate6.fire("home", gate6.C24C, None, [None],
                       uia=Mock(side_effect=RuntimeError("wrong selected phone")), api=transport)
        transport.assert_not_called()

    def test_search_requires_explicit_api_mode_before_any_live_preflight(self):
        with patch.object(gate6, "open_run") as output, patch.object(gate6, "bind_console") as bind, patch.object(gate6, "status") as status:
            with self.assertRaisesRegex(SystemExit, "api-only"):
                gate6.live(1, ["search"], False, console_pid=1)
            bind.assert_not_called()
            status.assert_not_called()
            output.assert_not_called()

    def test_unchanged_expected_screen_does_not_prove_response(self):
        frame = gate6.solid(0)
        with patch.object(gate6, "classify", return_value="home"):
            row = gate6.observe(lambda: frame, frame, self.act, expect="home", budget=.03)
        self.assertTrue(row["miss"])

    def test_failed_action_cannot_be_rescued_by_screen_change(self):
        def fail(box):
            box[0] = time.perf_counter()
            raise RuntimeError("request outcome unknown")
        with patch.object(gate6, "classify", return_value="home"):
            row = gate6.observe(lambda: gate6.solid(80), gate6.solid(0), fail,
                                expect="home", budget=.05)
        self.assertTrue(row["miss"])
        self.assertIn("outcome unknown", row.get("error", ""))

    def test_waits_past_wrong_stable_screen_and_times_correct_result(self):
        frames = iter([gate6.solid(40)] * 3 + [gate6.solid(90)] * 3)
        def fetch():
            time.sleep(.005)
            return next(frames, gate6.solid(90))
        def classify(frame, baseline=None):
            return "search" if frame[54] == 90 else "other"
        with patch.object(gate6, "classify", side_effect=classify):
            row = gate6.observe(fetch, gate6.solid(0), self.act, expect="search", budget=.2)
        self.assertFalse(row["miss"])
        self.assertGreater(row["first_correct_ms"], row["first_visible_ms"])
        self.assertGreaterEqual(row["settled_ms"], row["first_correct_ms"])

    def test_frame_returned_after_deadline_is_not_a_hit(self):
        def fetch():
            time.sleep(.06)
            return gate6.solid(90)
        with patch.object(gate6, "classify", return_value="search"):
            row = gate6.observe(fetch, gate6.solid(0), self.act, expect="search", budget=.02)
        self.assertTrue(row["miss"])
        self.assertIsNone(row.get("first_correct_ms"))

    def test_summary_uses_correct_time_and_keeps_measurement_types_separate(self):
        rows = [
            {"category": "search", "phone": "C24C", "via": "api", "miss": False,
             "first_visible_ms": 10, "first_correct_ms": 120, "correctness_checked": True},
            {"category": "search", "phone": "C24C", "via": "uia", "miss": False,
             "first_visible_ms": 20, "first_correct_ms": 240, "correctness_checked": True},
            {"category": "search", "phone": "C241", "via": "api", "miss": False,
             "first_visible_ms": 30, "first_correct_ms": 360, "correctness_checked": True},
        ]
        result = gate6.summarize(rows)["search"]
        self.assertIsNone(result["p95"])
        self.assertEqual(result["measurements"]["C24C/api"]["p95"], 120)
        self.assertEqual(result["measurements"]["C24C/uia"]["p95"], 240)
        self.assertEqual(result["measurements"]["C241/api"]["p95"], 360)

    def test_failed_live_trial_is_saved_and_aborts_remaining_trials(self):
        states = [{"receivers": [{"name": "iMouse2-C24C", "frames": count,
                                  "live": True, "receiver_pid": 1}]} for count in (1, 2)]
        with tempfile.TemporaryDirectory() as folder, contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(gate6, "OUT", Path(folder)))
            stack.enter_context(patch.object(gate6, "status", side_effect=states))
            stack.enter_context(patch.object(gate6.time, "sleep"))
            stack.enter_context(patch.object(gate6, "hold_lease"))
            trial = stack.enter_context(patch.object(gate6, "run_cycle", side_effect=RuntimeError("refused")))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            with self.assertRaisesRegex(SystemExit, "trial aborted"):
                gate6.live(2, ["home"], True)
            trial.assert_called_once()
            rows = json.loads((gate6.RUN / "rows.json").read_text(encoding="utf-8"))
            manifest = json.loads((gate6.RUN / "manifest.json").read_text(encoding="utf-8"))
            summary = json.loads((gate6.RUN / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]["miss"])
            self.assertEqual(rows[0]["error"], "refused")
            self.assertEqual(summary["home"]["p95"], gate6.MISS_MS)
            self.assertFalse(manifest["gate6_acceptance"])

    def test_action_failure_does_not_send_a_dismiss_command(self):
        def failed_action(*args, **kwargs):
            raise RuntimeError("timeout: outcome unknown")
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(gate6, "need_token", return_value="test-token"))
            stack.enter_context(patch.object(gate6, "home_pair"))
            stack.enter_context(patch.object(gate6, "fetch_shot", return_value=gate6.solid(0)))
            stack.enter_context(patch.object(gate6, "api_action", side_effect=failed_action))
            stack.enter_context(patch.object(gate6, "save_frame"))
            post = stack.enter_context(patch.object(gate6, "post"))
            row = gate6.run_cycle("C24C", gate6.C24C, "C241", gate6.C241,
                                  "appswitch", 1, True, Path("unused"))
            post.assert_not_called()
            self.assertTrue(row["miss"])
            self.assertIn("outcome unknown", row["error"])
            self.assertEqual(row["via"], "api")
            self.assertIn("polls", row)

    def test_console_home_requires_prepared_screen_without_api_input(self):
        with patch.object(gate6, "fetch_shot", return_value=gate6.solid(0)), \
             patch.object(gate6, "classify", return_value="home"), \
             patch.object(gate6, "need_token") as lease, patch.object(gate6, "fire") as fire:
            with self.assertRaisesRegex(RuntimeError, "prepared Search"):
                gate6.run_cycle("C24C", gate6.C24C, "C241", gate6.C241,
                               "home", 1, False, Path("unused"))
            lease.assert_not_called()
            fire.assert_not_called()

    def test_uia_duration_is_not_reported_as_kernel_dispatch(self):
        def invoke(button, box):
            box[0] = time.perf_counter()
            return 123
        row = gate6.fire("home", gate6.C24C, None, [None], uia=invoke)
        self.assertIsNone(row["dispatch_ms"])
        self.assertIsNotNone(row["ui_invoke_elapsed_ms"])

    def test_refused_api_result_is_a_miss(self):
        def refused(box):
            box[0] = time.perf_counter()
            return {"via": "api", "code": 409}
        with patch.object(gate6, "classify", return_value="home"):
            row = gate6.observe(lambda: gate6.solid(80), gate6.solid(0), refused,
                                expect="home", budget=.05)
        self.assertTrue(row["miss"])
        self.assertIn("409", row["error"])


class ConsoleHelperDeadlineTests(unittest.TestCase):
    """Fake child processes only; never launch PowerShell or touch a window."""

    def setUp(self):
        self.console = patch.dict(gate6.CONSOLE, {"pid": 999999, "phone": "C24C"})
        self.console.start()
        self.addCleanup(self.console.stop)

    def test_stdout_that_never_closes_has_a_deadline_and_is_reaped(self):
        unblocked = threading.Event()
        killed = threading.Event()

        class Stream:
            def __iter__(self):
                yield str(int(time.time() * 1000)) + "\n"
                unblocked.wait(2)

            def close(self):
                pass

        proc = Mock(stdout=Stream())
        proc.poll.side_effect = lambda: -9 if killed.is_set() else None
        proc.kill.side_effect = lambda: (killed.set(), unblocked.set())
        proc.wait.side_effect = lambda timeout: -9 if killed.is_set() else 0
        failures = []

        def invoke():
            try:
                gate6.uia_invoke("HomeButton", [None])
            except BaseException as exc:
                failures.append(exc)

        with patch.object(gate6, "UIA_HELPER_TIMEOUT", .05, create=True), \
             patch.object(gate6.subprocess, "Popen", return_value=proc), \
             contextlib.redirect_stdout(io.StringIO()):
            worker = threading.Thread(target=invoke, daemon=True)
            worker.start()
            worker.join(.5)
            returned_in_time = not worker.is_alive()
            # A broken reader must not leave the offline test itself hanging.
            unblocked.set()
            worker.join(1)
        self.assertTrue(returned_in_time, "stdout phase has no deadline")
        self.assertTrue(failures)
        self.assertIn("outcome unknown", str(failures[0]))
        proc.kill.assert_called_once()
        self.assertTrue(proc.wait.called, "terminated helper must be reaped")

    def test_ok_substring_does_not_count_as_completion(self):
        proc = Mock(stdout=io.StringIO("123\nnot ok: handler never completed\n"))
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        with patch.object(gate6.subprocess, "Popen", return_value=proc), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                gate6.uia_invoke("HomeButton", [None])
        proc.kill.assert_not_called()

    def test_closed_stdout_does_not_hide_a_hung_process(self):
        proc = Mock(stdout=io.StringIO("123\nok\n"))
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired("fake", .05), -9]
        with patch.object(gate6.subprocess, "Popen", return_value=proc), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "timed out.*outcome unknown"):
                gate6.run_uia_helper(["fake"], timeout=.05)
        proc.kill.assert_called_once()
        self.assertEqual(proc.wait.call_count, 2)
        self.assertLessEqual(proc.wait.call_args_list[0].kwargs["timeout"], .05 + 1e-6)

    def test_nonzero_exit_cannot_be_rescued_by_ok(self):
        proc = Mock(stdout=io.StringIO("123\nok\n"))
        proc.wait.return_value = 7
        proc.poll.return_value = 7
        with patch.object(gate6.subprocess, "Popen", return_value=proc), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "exit 7"):
                gate6.run_uia_helper(["fake"])
        proc.kill.assert_not_called()

    def test_completion_without_invocation_timestamp_is_not_success(self):
        proc = Mock(stdout=io.StringIO("ok\n"))
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        with patch.object(gate6.subprocess, "Popen", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "outcome unknown"):
                gate6.run_uia_helper(["fake"])

    def test_output_limit_stops_and_reaps_helper(self):
        proc = Mock(stdout=io.StringIO("x" * 100 + "\n"))
        proc.poll.return_value = None
        proc.wait.return_value = -9
        with patch.object(gate6, "UIA_HELPER_MAX_OUTPUT", 64), \
             patch.object(gate6.subprocess, "Popen", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "output limit"):
                gate6.run_uia_helper(["fake"])
        proc.kill.assert_called_once()
        proc.wait.assert_called_once()

    def test_bad_timeout_does_not_start_helper(self):
        with patch.object(gate6.subprocess, "Popen") as spawn:
            with self.assertRaises(ValueError):
                gate6.run_uia_helper(["fake"], timeout=0)
        spawn.assert_not_called()

    def test_cleanup_failure_reports_unknown_outcome_and_child_pid(self):
        proc = Mock(stdout=io.StringIO("not completed\n"), pid=999999)
        proc.poll.return_value = None
        proc.wait.side_effect = [7, subprocess.TimeoutExpired("fake", 2)]
        with patch.object(gate6.subprocess, "Popen", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "PID 999999 cleanup failed.*outcome unknown"):
                gate6.run_uia_helper(["fake"])


class ConsoleHelperChildTests(unittest.TestCase):
    """Real Python children exercise pipes and cleanup; no GUI or rack calls."""

    def test_timestamp_arrives_before_child_exit(self):
        clock = [None]
        done = threading.Event()
        result = []
        failure = []
        command = [sys.executable, "-c",
                   "import time; print(int(time.time()*1000), flush=True); "
                   "time.sleep(.3); print('ok', flush=True)"]

        def invoke():
            try:
                result.append(gate6.run_uia_helper(command, clock, timeout=3))
            except BaseException as exc:
                failure.append(exc)
            finally:
                done.set()

        timestamp_seen = threading.Event()
        original = gate6.note_invoked

        def record(*args):
            stamp = original(*args)
            timestamp_seen.set()
            return stamp

        with patch.object(gate6, "note_invoked", side_effect=record), \
             contextlib.redirect_stdout(io.StringIO()):
            worker = threading.Thread(target=invoke, daemon=True)
            worker.start()
            saw_timestamp = timestamp_seen.wait(2)
            completed_at_timestamp = done.is_set()
            worker.join(4)
        self.assertTrue(saw_timestamp)
        self.assertFalse(completed_at_timestamp, "timestamp buffered until helper exit")
        self.assertFalse(worker.is_alive())
        self.assertFalse(failure)
        self.assertEqual(len(result), 1)
        self.assertIsNotNone(clock[0])

    def test_silent_real_child_is_killed_and_reaped(self):
        original = subprocess.Popen
        children = []

        def spawn(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child

        started = time.monotonic()
        with patch.object(gate6.subprocess, "Popen", side_effect=spawn):
            with self.assertRaisesRegex(RuntimeError, "timed out.*outcome unknown"):
                gate6.run_uia_helper([sys.executable, "-c", "import time; time.sleep(60)"], timeout=.2)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(children[0].stdout.closed)


if __name__ == "__main__":
    unittest.main()
