"""Offline evidence-integrity regressions. Never start UIA or contact the rack."""
import importlib.util
import contextlib
import copy
import hashlib
import io
import json
import os
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
        states = [ready_kernel(count) for count in (1, 2)]
        with tempfile.TemporaryDirectory() as folder, contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(gate6, "OUT", Path(folder)))
            stack.enter_context(patch.object(gate6, "status", side_effect=states))
            stack.enter_context(patch.object(gate6.time, "sleep"))
            stack.enter_context(patch.object(gate6, "input_status", return_value=ready_input()))
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


class RunLifecycleTests(unittest.TestCase):
    """Drive the runner with fake frames/leases; forbid transport and UI children."""

    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        transport = self.stack.enter_context(patch.object(gate6, "api", side_effect=AssertionError("network forbidden")))
        child = self.stack.enter_context(patch.object(gate6.subprocess, "Popen", side_effect=AssertionError("UI forbidden")))
        self.addCleanup(transport.assert_not_called)
        self.addCleanup(child.assert_not_called)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.folder = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.object(gate6, "OUT", Path(self.folder)))
        self.stack.enter_context(patch.object(gate6.time, "sleep"))
        states = [ready_kernel(count) for count in (1, 2, 3)]
        self.stack.enter_context(patch.object(gate6, "status", side_effect=states))
        self.stack.enter_context(patch.object(gate6, "input_status", return_value=ready_input()))
        gate6.HELD.clear()
        self.addCleanup(gate6.HELD.clear)
        self.addCleanup(setattr, gate6, "RUN", None)
        self.addCleanup(gate6.UIA_OWNS.update, {"on": False})

    def fake_acquire(self, ids):
        gate6.HELD[gate6.C24C] = "mock-token"

    def fake_release(self):
        gate6.HELD.clear()

    def record(self, name):
        return json.loads((gate6.RUN / name).read_text(encoding="utf-8"))

    @staticmethod
    def observation(miss=True):
        return {"miss": miss, "error": None, "frame": gate6.solid(0), "via": "api",
                "first_visible_ms": None if miss else 10, "first_correct_ms": None,
                "settled_ms": None, "dispatch_ms": 1, "visual": "other",
                "visual_ok": False, "poll_count": 1, "polls": [], "code": 0}

    def test_visual_miss_is_saved_and_stops_before_next_trial(self):
        self.stack.enter_context(patch.object(gate6, "hold_lease", side_effect=self.fake_acquire))
        self.stack.enter_context(patch.object(gate6, "post", return_value=(1, {"code": 0})))
        release = self.stack.enter_context(patch.object(gate6, "drop_lease", side_effect=self.fake_release))
        trial = self.stack.enter_context(patch.object(gate6, "run_cycle", return_value={
            **self.observation(), "frame": None, "phone": "C24C", "category": "home",
            "correctness_checked": True, "cycle": 1}))
        with self.assertRaisesRegex(SystemExit, "trial aborted"):
            gate6.live(2, ["home"], True)
        trial.assert_called_once()
        release.assert_called_once()
        self.assertEqual(len(self.record("rows.json")), 1)
        self.assertEqual(self.record("summary.json")["home"]["p95"], gate6.MISS_MS)
        self.assertEqual(self.record("run-state.json")["status"], "aborted")

    def test_missed_transition_never_sends_dismiss_api_or_uia(self):
        for api_only in (True, False):
            with self.subTest(api_only=api_only), contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(gate6, "need_token", return_value="mock-token"))
                stack.enter_context(patch.object(gate6, "home_pair"))
                home = stack.enter_context(patch.object(gate6, "home_via"))
                stack.enter_context(patch.object(gate6, "fetch_shot", return_value=gate6.solid(0)))
                stack.enter_context(patch.object(gate6, "observe", return_value=self.observation()))
                stack.enter_context(patch.object(gate6, "save_frame"))
                post = stack.enter_context(patch.object(gate6, "post"))
                row = gate6.run_cycle("C24C", gate6.C24C, "C241", gate6.C241,
                                      "appswitch", 1, api_only, Path(self.folder))
                self.assertTrue(row["miss"])
                post.assert_not_called()
                self.assertEqual(home.call_count, 0 if api_only else 1, "setup only; no dismissal")

    def test_missed_search_never_sends_dismiss(self):
        self.stack.enter_context(patch.object(gate6, "need_token", return_value="mock-token"))
        self.stack.enter_context(patch.object(gate6, "fetch_shot", return_value=gate6.solid(0)))

        def observe(fetch, before, act, **kwargs):
            if kwargs.get("expect") == "home":
                act([None])
                return {**self.observation(False), "visual_ok": True}
            return self.observation()

        self.stack.enter_context(patch.object(gate6, "observe", side_effect=observe))
        self.stack.enter_context(patch.object(gate6, "home_pair", return_value=(1, 1)))
        self.stack.enter_context(patch.object(gate6, "save_frame", return_value=0))
        post = self.stack.enter_context(patch.object(gate6, "post", return_value=(1, {})))
        row = gate6.run_cycle("C24C", gate6.C24C, "C241", gate6.C241,
                              "search", 1, True, Path(self.folder))
        self.assertTrue(row["miss"])
        post.assert_not_called()

    def test_renewal_failure_records_unsent_trial_and_releases(self):
        self.stack.enter_context(patch.object(gate6, "hold_lease", side_effect=self.fake_acquire))
        self.stack.enter_context(patch.object(gate6, "post", side_effect=RuntimeError("renew refused")))
        release = self.stack.enter_context(patch.object(gate6, "drop_lease", side_effect=self.fake_release))
        trial = self.stack.enter_context(patch.object(gate6, "run_cycle"))
        with self.assertRaisesRegex(SystemExit, "renew refused"):
            gate6.live(2, ["home"], True)
        trial.assert_not_called()
        release.assert_called_once()
        row = self.record("rows.json")[0]
        self.assertEqual(row["failure_stage"], "renew")
        self.assertFalse(row["action_attempted"])
        self.assertEqual(self.record("cleanup.json")["api_release"], "confirmed")

    def test_partial_acquire_failure_still_releases_known_token(self):
        def partial(ids):
            self.fake_acquire(ids)
            raise RuntimeError("incomplete acquire response")
        self.stack.enter_context(patch.object(gate6, "hold_lease", side_effect=partial))
        release = self.stack.enter_context(patch.object(gate6, "drop_lease", side_effect=self.fake_release))
        with self.assertRaisesRegex(RuntimeError, "incomplete acquire"):
            gate6.live(1, ["home"], True)
        release.assert_called_once()
        state = self.record("run-state.json")
        self.assertEqual((state["status"], state["phase"]), ("aborted", "acquire"))
        self.assertNotIn("mock-token", (gate6.RUN / "cleanup.json").read_text(encoding="utf-8"))

    def test_unknown_acquire_does_not_guess_token_or_claim_release(self):
        self.stack.enter_context(patch.object(gate6, "hold_lease", side_effect=TimeoutError("acquire outcome unknown")))
        release = self.stack.enter_context(patch.object(gate6, "drop_lease"))
        with self.assertRaises(TimeoutError):
            gate6.live(1, ["home"], True)
        release.assert_not_called()
        self.assertEqual(self.record("cleanup.json")["api_acquire"], "unconfirmed")
        self.assertEqual(self.record("cleanup.json")["api_release"], "no_known_tokens")

    def test_failed_release_is_recorded_alongside_original_failure(self):
        self.stack.enter_context(patch.object(gate6, "hold_lease", side_effect=self.fake_acquire))
        self.stack.enter_context(patch.object(gate6, "post", side_effect=RuntimeError("renew refused")))
        self.stack.enter_context(patch.object(gate6, "drop_lease", side_effect=RuntimeError("release unreachable")))
        with self.assertRaisesRegex(RuntimeError, "release.*unreachable"):
            gate6.live(1, ["home"], True)
        self.assertIn("renew refused", self.record("run-state.json")["error"])
        self.assertEqual(self.record("cleanup.json")["api_release"], "unconfirmed")
        self.assertEqual(self.record("cleanup.json")["remaining_known_phones"], [gate6.C24C])

    def test_existing_run_cannot_be_reused_or_overwritten(self):
        root = Path(self.folder)
        dest = gate6.open_run(root, "recorded")
        gate6.dump(root, dest, "rows.json", ["original"])
        with self.assertRaises(SystemExit):
            gate6.open_run(root, "recorded")
        self.assertEqual(json.loads((dest / "rows.json").read_text(encoding="utf-8")), ["original"])

    def test_output_escape_is_refused_before_creating_directory(self):
        root = Path(self.folder)
        with self.assertRaises(SystemExit):
            gate6.open_run(root, "../escaped")
        self.assertFalse((root / "escaped").exists())

    def test_artifact_cannot_escape_into_a_different_run(self):
        root = Path(self.folder)
        first = gate6.open_run(root, "first")
        second = gate6.open_run(root, "second")
        gate6.dump(root, second, "rows.json", ["original"])
        with self.assertRaises(SystemExit):
            gate6.dump(root, first, "../second/rows.json", ["replacement"])
        self.assertEqual(json.loads((second / "rows.json").read_text(encoding="utf-8")), ["original"])

    def test_successful_run_records_confirmed_api_release_without_tokens(self):
        post = self.stack.enter_context(patch.object(gate6, "post", side_effect=[
            (1, {"leases": [{"id": gate6.C24C, "token": "mock-token"}]}),
            (1, {"code": 0}), (1, {"code": 0}),
        ]))
        self.stack.enter_context(patch.object(gate6, "run_cycle", return_value={
            "phone": "C24C", "category": "home", "cycle": 1, "via": "api",
            "miss": False, "correctness_checked": True, "first_correct_ms": 100,
        }))
        gate6.live(1, ["home"], True)
        self.assertEqual([c.args[0] for c in post.call_args_list],
                         ["/input/acquire", "/input/renew", "/input/release"])
        self.assertEqual(self.record("run-state.json")["status"], "complete")
        self.assertEqual(self.record("cleanup.json")["api_release"], "confirmed")
        self.assertFalse(gate6.HELD)
        self.assertFalse(self.record("manifest.json")["gate6_acceptance"])
        self.assertNotIn("mock-token", (gate6.RUN / "cleanup.json").read_text(encoding="utf-8"))

    def test_malformed_acquire_reply_releases_token_parsed_before_error(self):
        post = self.stack.enter_context(patch.object(gate6, "post", side_effect=[
            (1, {"leases": [{"id": gate6.C24C, "token": "mock-token"}, {}]}),
            (1, {"code": 0}),
        ]))
        with self.assertRaises(KeyError):
            gate6.live(1, ["home"], True)
        self.assertEqual([c.args[0] for c in post.call_args_list], ["/input/acquire", "/input/release"])
        self.assertEqual(post.call_args_list[1].args[1]["tokens"], {gate6.C24C: "mock-token"})
        self.assertEqual(self.record("cleanup.json")["api_acquire"], "unconfirmed")
        self.assertEqual(self.record("cleanup.json")["api_release"], "confirmed")
        self.assertFalse(gate6.HELD)

    def test_interrupt_preserves_abort_and_releases_known_lease(self):
        self.stack.enter_context(patch.object(gate6, "hold_lease", side_effect=self.fake_acquire))
        self.stack.enter_context(patch.object(gate6, "post", return_value=(1, {"code": 0})))
        self.stack.enter_context(patch.object(gate6, "run_cycle", side_effect=KeyboardInterrupt("operator stop")))
        release = self.stack.enter_context(patch.object(gate6, "drop_lease", side_effect=self.fake_release))
        with self.assertRaises(KeyboardInterrupt):
            gate6.live(1, ["home"], True)
        release.assert_called_once()
        self.assertEqual(self.record("run-state.json")["status"], "aborted")
        self.assertIn("operator stop", self.record("run-state.json")["error"])
        self.assertEqual(self.record("cleanup.json")["api_release"], "confirmed")


class ConsoleRunCleanupTests(unittest.TestCase):
    setUp = RunLifecycleTests.setUp
    record = RunLifecycleTests.record

    def prepare(self, failure=None, cleanup_error=None):
        self.stack.enter_context(patch.object(gate6, "prepare_console", return_value={"test": True}))
        def trial(*args):
            gate6.UIA_OWNS["on"] = True
            if failure:
                raise failure
            return {"phone": "C24C", "category": "home", "cycle": 1, "via": "uia", "miss": False}
        self.stack.enter_context(patch.object(gate6, "run_cycle", side_effect=trial))
        return self.stack.enter_context(patch.object(gate6, "release_console", create=True,
            side_effect=cleanup_error, return_value={"console_disconnect": "confirmed", "target_free": True}))

    def test_console_success_releases_through_console(self):
        release = self.prepare()
        gate6.live(1, ["home"], False, console_pid=999999)
        release.assert_called_once_with([gate6.C24C])
        self.assertEqual(self.record("cleanup.json")["console_release"], "confirmed")

    def test_uncertain_helper_still_releases_without_replay(self):
        release = self.prepare(TimeoutError("helper outcome unknown"))
        with self.assertRaisesRegex(SystemExit, "outcome unknown"):
            gate6.live(2, ["home"], False, console_pid=999999)
        release.assert_called_once()
        self.assertEqual(len(self.record("rows.json")), 1)

    def test_console_release_failure_preserves_trial_failure(self):
        self.prepare(RuntimeError("original trial failed"), RuntimeError("disconnect unknown"))
        with self.assertRaisesRegex(RuntimeError, "disconnect unknown"):
            gate6.live(1, ["home"], False, console_pid=999999)
        self.assertIn("original trial failed", self.record("run-state.json")["error"])
        self.assertEqual(self.record("cleanup.json")["console_release"], "unconfirmed")

    def test_interrupt_still_disconnects(self):
        release = self.prepare(KeyboardInterrupt("operator interruption"))
        with self.assertRaises(KeyboardInterrupt):
            gate6.live(1, ["home"], False, console_pid=999999)
        release.assert_called_once()

    def test_fire_marks_possible_ownership_before_helper_returns(self):
        with self.assertRaises(TimeoutError):
            gate6.fire("home", gate6.C24C, None, [None], uia=Mock(side_effect=TimeoutError()))
        self.assertTrue(gate6.UIA_OWNS["on"])

    def test_setup_marks_possible_ownership_before_helper_returns(self):
        gate6.UIA_OWNS["on"] = False
        with self.assertRaises(TimeoutError):
            gate6.home_via(gate6.C24C, None, False, uia=Mock(side_effect=TimeoutError()))
        self.assertTrue(gate6.UIA_OWNS["on"])

    def test_no_uia_action_does_not_disconnect_a_console(self):
        self.stack.enter_context(patch.object(gate6, "prepare_console", return_value={"test": True}))
        self.stack.enter_context(patch.object(gate6, "run_cycle", side_effect=RuntimeError("preparation failed")))
        release = self.stack.enter_context(patch.object(gate6, "release_console"))
        gate6.UIA_OWNS["on"] = False
        with self.assertRaises(SystemExit):
            gate6.live(1, ["home"], False, console_pid=999999)
        release.assert_not_called()
        self.assertEqual(self.record("cleanup.json")["console_release"], "no_action_attempted")

    def test_free_status_does_not_override_failed_disconnect(self):
        release = self.prepare()
        release.return_value = {"console_disconnect": "unconfirmed", "target_free": True}
        with self.assertRaisesRegex(RuntimeError, "not confirmed"):
            gate6.live(1, ["home"], False, console_pid=999999)
        state = self.record("run-state.json")
        self.assertEqual(state["status"], "cleanup_failed")
        self.assertTrue(state["cleanup_failed"])
        self.assertTrue(gate6.UIA_OWNS["on"])

    def test_owned_status_does_not_override_successful_disconnect(self):
        release = self.prepare()
        release.return_value = {"console_disconnect": "confirmed", "target_free": False}
        with self.assertRaisesRegex(RuntimeError, "not confirmed"):
            gate6.live(1, ["home"], False, console_pid=999999)
        self.assertEqual(self.record("cleanup.json")["console_release"], "unconfirmed")

    def test_failed_cleanup_never_prints_successful_completion(self):
        self.prepare(cleanup_error=RuntimeError("disconnect unknown"))
        with contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(RuntimeError):
            gate6.live(1, ["home"], False, console_pid=999999)
        self.assertNotIn("done ", output.getvalue())


def ready_kernel(frames=1):
    return {"code": 0, "input_protocol": 1, "input_leases_required": True, "receivers": [
        {"name": "iMouse2-" + name, "deviceid": device, "frames": frames,
         "live": True, "receiver_pid": pid, "frame_session": name + "-session"}
        for name, device, pid in (("C24C", gate6.C24C, 101), ("C241", gate6.C241, 102))]}


def ready_input():
    return {"code": 0, "protocol": 1, "phones": [{"id": device, "owned": False, "active": False,
        "releasing": False, "release_failed": False, "stopped": False, "generation": 0}
        for device in (gate6.C24C, gate6.C241)]}


class UnsafePreflightTests(unittest.TestCase):
    setUp = RunLifecycleTests.setUp
    record = RunLifecycleTests.record

    def attempt(self, first, second, ownership):
        self.stack.enter_context(patch.object(gate6, "status", side_effect=[first, second, second]))
        self.stack.enter_context(patch.object(gate6, "input_status", return_value=ownership))
        acquire = self.stack.enter_context(patch.object(gate6, "hold_lease"))
        trial = self.stack.enter_context(patch.object(gate6, "run_cycle", return_value={"miss": False}))
        with self.assertRaises((SystemExit, ValueError)):
            gate6.live(1, ["home"], True)
        acquire.assert_not_called()
        trial.assert_not_called()

    def test_owned_phone_refuses_before_acquisition(self):
        state = ready_input(); state["phones"][0]["owned"] = True
        self.attempt(ready_kernel(1), ready_kernel(2), state)

    def test_stopped_phone_is_not_automatically_resumed(self):
        state = ready_input(); state["phones"][0]["stopped"] = True
        self.attempt(ready_kernel(1), ready_kernel(2), state)

    def test_wrong_device_under_right_receiver_name_is_refused(self):
        first, second = ready_kernel(1), ready_kernel(2)
        first["receivers"][0]["deviceid"] = second["receivers"][0]["deviceid"] = "wrong-phone"
        self.attempt(first, second, ready_input())

    def test_nonstreaming_second_phone_refuses_workload(self):
        first, second = ready_kernel(1), ready_kernel(2)
        second["receivers"][1]["frames"] = 1
        self.attempt(first, second, ready_input())

    def test_receiver_replacement_during_preflight_is_refused(self):
        first, second = ready_kernel(1), ready_kernel(2)
        second["receivers"][0]["receiver_pid"] += 10
        self.attempt(first, second, ready_input())

    def test_failed_preflight_is_saved_without_cleanup_or_input(self):
        state = ready_input(); state["phones"][1]["owned"] = True
        self.attempt(ready_kernel(1), ready_kernel(2), state)
        self.assertEqual(self.record("run-state.json")["phase"], "preflight")
        self.assertEqual(self.record("run-state.json")["status"], "aborted")
        self.assertEqual(self.record("cleanup.json")["api_acquire"], "not_attempted")
        self.assertEqual(self.record("cleanup.json")["api_release"], "no_known_tokens")
        self.assertTrue(self.record("preflight-frames.json")["input"]["phones"][1]["owned"])

    def test_missing_or_ambiguous_state_never_passes(self):
        cases = []
        for flag in ("owned", "active", "releasing", "release_failed", "stopped"):
            for value in (True, None, 0, "false"):
                state = ready_input(); state["phones"][0][flag] = value
                cases.append((ready_kernel(1), ready_kernel(2), state))
        state = ready_input(); state["phones"].append(state["phones"][0]); cases.append((ready_kernel(1), ready_kernel(2), state))
        for field,value in (("frame_session","changed"),("live",False),("frames",True),("deviceid",gate6.C24C)):
            state = ready_kernel(2); state["receivers"][1][field] = value
            cases.append((ready_kernel(1),state,ready_input()))
        for first,second,ownership in cases:
            with self.subTest(second=second,ownership=ownership), self.assertRaises(ValueError):
                gate6.validate_preflight(first,second,ownership)

    def test_valid_two_phone_preflight_does_not_claim_gate_acceptance(self):
        result = gate6.validate_preflight(ready_kernel(1), ready_kernel(2), ready_input())
        self.assertTrue(result["input_idle"])
        self.assertFalse(result["gate6_acceptance"])
        self.assertFalse(result["physical_identity_verified"])
        self.assertEqual([r["id"] for r in result["verified_receivers"]], [gate6.C24C,gate6.C241])

    def test_other_phone_becoming_owned_aborts_before_next_action(self):
        taken = ready_input();taken["phones"][1]["owned"] = True
        self.stack.enter_context(patch.object(gate6,"input_status",side_effect=[ready_input(),taken]))
        self.stack.enter_context(patch.object(gate6,"hold_lease",side_effect=lambda ids: gate6.HELD.update({gate6.C24C:"test-token"})))
        release=self.stack.enter_context(patch.object(gate6,"drop_lease",side_effect=gate6.HELD.clear))
        trial=self.stack.enter_context(patch.object(gate6,"run_cycle"))
        with self.assertRaisesRegex(SystemExit,"another phone"):
            gate6.live(1,["home"],True)
        trial.assert_not_called();release.assert_called_once()
        row=self.record("rows.json")[0]
        self.assertEqual(row["failure_stage"],"ownership-check")
        self.assertFalse(row["action_attempted"])

    def test_intervening_other_phone_release_is_detected_by_generation(self):
        pre=gate6.validate_preflight(ready_kernel(1),ready_kernel(2),ready_input())
        for generation in (1, None, False, "0"):
            changed=ready_input();changed["phones"][1]["generation"]=generation
            with self.subTest(generation=generation), self.assertRaisesRegex(ValueError,"generation changed"):
                gate6.require_idle_observers(changed,pre,[gate6.C24C])

    def test_target_ownership_does_not_look_like_other_phone_interference(self):
        pre=gate6.validate_preflight(ready_kernel(1),ready_kernel(2),ready_input())
        changed=ready_input();changed["phones"][0]["owned"]=True
        gate6.require_idle_observers(changed,pre,[gate6.C24C])

    def test_unknown_extra_receiver_is_not_a_declared_two_phone_load(self):
        extra=ready_kernel(2);extra["receivers"].append({"name":"unreviewed"})
        with self.assertRaisesRegex(ValueError,"exactly"):
            gate6.validate_preflight(ready_kernel(1),extra,ready_input())


class CandidateProfileTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.exe = self.root / "candidate with spaces" / "iMouse2.exe"
        self.exe.parent.mkdir(); self.exe.write_bytes(b"fake apphost")
        self.exe.with_suffix(".dll").write_bytes(b"fake managed binary")
        self.digest = hashlib.sha256(b"fake managed binary").hexdigest()
        self.folder = self.root / "isolated data"; self.folder.mkdir()
        self.settings = self.folder / "settings.json"
        self.settings.write_text(json.dumps({"address":gate6.BASE,"trackPointer":False}),encoding="utf-8")
        self.shared = self.root / "appdata"; self.shared.mkdir()
        self.stack.enter_context(patch.dict(os.environ,{"APPDATA":str(self.shared)}))
        for name in ("api","process_identity","read_console_command"):
            boundary=self.stack.enter_context(patch.object(gate6,name,side_effect=AssertionError("offline only")))
            self.addCleanup(boundary.assert_not_called)
        self.child=self.stack.enter_context(patch.object(gate6.subprocess,"Popen",side_effect=AssertionError("no process")))
        self.addCleanup(self.child.assert_not_called)
        self.args=[str(self.exe),"--data-dir="+str(self.folder),"--address="+gate6.BASE]

    def validate(self,args=None,folder=None,digest=None):
        return gate6.validate_candidate_profile(str(self.exe),self.args if args is None else args,
            str(self.folder) if folder is None else folder,self.digest if digest is None else digest)

    def test_explicit_profile_pins_directory_address_hover_and_binary(self):
        result=self.validate()
        self.assertEqual(result["data_directory"],str(self.folder.resolve()))
        self.assertEqual(result["assembly_sha256"],self.digest)
        self.assertEqual(result["address"],"http://127.0.0.1:9913")
        self.assertFalse(result["saved_track_pointer"])
        self.assertFalse(result["active_connection_verified"])
        self.assertNotIn("settings",result)

    @unittest.skipUnless(sys.platform=="win32","Windows command line")
    def test_windows_quoted_paths_round_trip_with_both_data_dir_forms(self):
        for args in (self.args,[str(self.exe),"--data-dir",str(self.folder)]):
            parsed=gate6.command_args(subprocess.list2cmdline(args))
            self.assertEqual(parsed,args)
            self.validate(args=parsed)

    def test_empty_duplicate_testmode_and_unknown_options_are_refused(self):
        cases=[[str(self.exe)],self.args+["--ui-test"],self.args+["--data-dir=x"],
               [str(self.exe),"--data-dir"],[str(self.exe),"--data-dir="],
               self.args+["--address=http://localhost:9999"],self.args+["--address","http://localhost:9999"]]
        for args in cases:
            with self.subTest(args=args),self.assertRaises(ValueError): self.validate(args=args)

    def test_shared_or_adjacent_data_folders_are_refused_before_read(self):
        for folder in (self.shared/"iMouse2",self.shared/"iMouse2"/"child",self.exe.parent/"data"):
            folder.mkdir(parents=True)
            # No settings file there: refusal must happen before reading one.
            with self.subTest(folder=folder),self.assertRaisesRegex(ValueError,"dedicated"):
                self.validate(args=[str(self.exe),"--data-dir="+str(folder)],folder=str(folder))

    def test_relative_or_different_profile_is_refused(self):
        for args,folder in (([str(self.exe),"--data-dir=data"],str(self.folder)),
                            (self.args,"relative"),(self.args,str(self.exe.parent))):
            with self.subTest(folder=folder),self.assertRaises(ValueError): self.validate(args=args,folder=folder)

    def test_hover_must_be_explicitly_boolean_false(self):
        for value in (None,True,0,"false"):
            self.settings.write_text(json.dumps({"address":gate6.BASE,"trackPointer":value}),encoding="utf-8")
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,"hover"): self.validate()

    def test_unknown_wrong_or_changed_binary_is_refused(self):
        for digest in ("", "not-a-hash", "0"*64):
            with self.subTest(digest=digest),self.assertRaises(ValueError): self.validate(digest=digest)
        self.exe.with_suffix(".dll").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"hash"): self.validate()

    def test_settings_and_command_line_must_both_match_runner_service(self):
        for address in ("http://127.0.0.1:9911","http://127.0.0.1:9988","http://127.0.0.1"):
            self.settings.write_text(json.dumps({"address":address,"trackPointer":False}),encoding="utf-8")
            with self.subTest(address=address),self.assertRaises(ValueError): self.validate()
        self.settings.write_text(json.dumps({"address":gate6.BASE,"trackPointer":False}),encoding="utf-8")
        with self.assertRaises(ValueError): self.validate(args=self.args[:-1]+["--address=http://localhost:9988"])

    def test_invalid_endpoint_shapes_are_refused(self):
        for value in (None,"file:///tmp","http://user:pass@localhost:9913","http://localhost:9913/other",
                      "http://localhost:9913/api?token=x","http://localhost:9913/#x","http://localhost:99999"):
            with self.subTest(value=value),self.assertRaises(ValueError): gate6.endpoint(value)
        self.assertEqual(gate6.endpoint("https://[::1]:9443/api/"),"https://[::1]:9443")

    def test_profile_change_prevents_any_uia_helper(self):
        profile=self.validate()
        with patch.dict(gate6.CONSOLE,{"exe":str(self.exe),"args":self.args,"profile":profile}):
            self.settings.write_text(json.dumps({"address":gate6.BASE,"trackPointer":True}),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"hover"): gate6.uia_invoke("HomeButton")

    def test_managed_process_replacement_during_command_query_is_refused(self):
        def bind(*args): gate6.CONSOLE.update(exe=str(self.exe),started=1); return str(self.exe)
        with patch.object(gate6,"bind_console",side_effect=bind), \
             patch.object(gate6,"read_console_command",return_value=self.args), \
             patch.object(gate6,"process_identity",return_value={"exe":str(self.exe),"started":2}):
            with self.assertRaisesRegex(ValueError,"process changed"):
                gate6.prepare_console(999999,str(self.exe),str(self.folder),self.digest)

    def test_profile_failure_stops_before_any_service_preflight(self):
        with patch.object(gate6,"prepare_console",side_effect=ValueError("profile refused")), \
             patch.object(gate6,"status") as status,patch.object(gate6,"OUT",self.root), \
             patch.object(gate6,"release_console") as release,contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError,"profile refused"):
                gate6.live(1,["home"],False,console_pid=999999)
        status.assert_not_called();release.assert_not_called()
        record=json.loads((gate6.RUN/"run-state.json").read_text(encoding="utf-8"))
        self.assertEqual(record["phase"],"preflight")


class ConsoleReleaseProtocolTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(gate6.CONSOLE, {"pid": 999999, "phone": "C24C",
            "exe": r"C:\scratch\candidate's folder\imouse-candidate-5\iMouse2.exe", "started": 123456789}))
        self.child = self.stack.enter_context(patch.object(gate6.subprocess, "Popen", side_effect=AssertionError("UI forbidden")))
        self.addCleanup(self.child.assert_not_called)
        self.network = self.stack.enter_context(patch.object(gate6, "api", side_effect=AssertionError("network forbidden")))

    @staticmethod
    def status():
        return {"code": 0, "protocol": 1, "phones": [{"id": gate6.C24C, "owned": False,
            "active": False, "releasing": False, "release_failed": False}]}

    def reply(self, status=None):
        self.network.side_effect = None
        self.network.return_value = (1, json.dumps({"data": self.status() if status is None else status}).encode())

    def test_release_checks_current_status_after_completed_disconnect(self):
        self.reply()
        with patch.object(gate6, "run_uia_helper") as helper:
            result = gate6.release_console([gate6.C24C])
        helper.assert_called_once()
        self.network.assert_called_once_with("GET", gate6.BASE + "/input/status", timeout=3)
        self.assertEqual(result, {"console_disconnect": "confirmed", "target_free": True})

    def test_failed_helper_only_reads_status_never_force_releases_or_retries(self):
        self.reply()
        with patch.object(gate6, "run_uia_helper", side_effect=TimeoutError("unknown")) as helper:
            result = gate6.release_console([gate6.C24C])
        self.assertEqual(result["console_disconnect"], "unconfirmed")
        self.assertTrue(result["target_free"])
        helper.assert_called_once()
        self.network.assert_called_once_with("GET", gate6.BASE + "/input/status", timeout=3)

    def test_unreachable_status_is_preserved_as_unknown(self):
        self.network.side_effect = TimeoutError("status timed out")
        with patch.object(gate6, "run_uia_helper"):
            result = gate6.release_console([gate6.C24C])
        self.assertEqual(result["console_disconnect"], "confirmed")
        self.assertFalse(result["target_free"])
        self.assertEqual(result["status_error"], "status timed out")

    def test_free_status_requires_exact_unambiguous_boolean_fields(self):
        variants = [None, {}, {"code": 1, "protocol": 1, "phones": []},
                    {"code": 0, "protocol": 1, "phones": []}]
        for flag in ("owned", "active", "releasing", "release_failed"):
            for value in (True, None, 0, "false"):
                snapshot = self.status(); snapshot["phones"][0][flag] = value; variants.append(snapshot)
            snapshot = self.status(); del snapshot["phones"][0][flag]; variants.append(snapshot)
        snapshot = self.status(); snapshot["phones"] *= 2; variants.append(snapshot)
        snapshot = self.status(); snapshot["phones"][0]["id"] = gate6.C241; variants.append(snapshot)
        for snapshot in variants:
            with self.subTest(snapshot=snapshot):
                self.assertFalse(gate6.released_targets(snapshot, [gate6.C24C]))
        self.assertFalse(gate6.released_targets(self.status(), []))
        self.assertTrue(gate6.released_targets(self.status(), [gate6.C24C]))

    def test_bound_identity_records_creation_time_and_exact_executable(self):
        exe = gate6.CONSOLE["exe"]
        identity = Mock(return_value={"exe": exe, "started": 987654321})
        self.assertEqual(gate6.bind_console(999999, exe, read_identity=identity), exe)
        identity.assert_called_once_with(999999)
        self.assertEqual(gate6.CONSOLE["started"], 987654321)
        self.network.assert_not_called()

    def test_explicit_path_mismatch_cannot_use_legacy_candidate_exception(self):
        with self.assertRaisesRegex(SystemExit, "does not match"):
            gate6.bind_console(999999, r"C:\different\iMouse2.exe", read_identity=lambda _: {
                "exe": gate6.CONSOLE["exe"], "started": 1})

    def test_unverified_creation_time_cannot_bind_or_create_helper(self):
        for started in (None, 0, -1, True, "123"):
            with self.subTest(started=started), self.assertRaises(SystemExit):
                gate6.bind_console(999999, read_identity=lambda _: {"exe": gate6.CONSOLE["exe"], "started": started})
        with patch.dict(gate6.CONSOLE, {"started": None}), self.assertRaises(SystemExit):
            gate6.console_root_ps()

    def test_installed_path_is_refused_even_if_explicit(self):
        exe = r"C:\project\release\iMouse2-two-phone-candidate\iMouse2.exe"
        with self.assertRaisesRegex(SystemExit, "installed"):
            gate6.bind_console(999999, exe, read_identity=lambda _: {"exe": exe, "started": 1})

    def test_script_limits_cleanup_to_disconnect_and_rechecks_process_lifetime(self):
        script = gate6.disconnect_script()
        self.assertIn("$p.StartTime.ToUniversalTime().ToFileTimeUtc() -ne 123456789", script)
        self.assertIn("candidate''s folder", script)
        self.assertIn("$p.Path -ine", script)
        self.assertIn("Current.ProcessId -ne 999999", script)
        self.assertIn("Input released", script)
        self.assertIn("-ceq 'Disconnected'", script)
        self.assertIn("AddSeconds(12)", script)
        self.assertEqual(script.count(".Invoke();"), 2)  # Settings, Disconnect only
        for forbidden in ("HomeButton", "StopInputButton", "ResumeInputButton", "Stop-Process", "/input/release"):
            self.assertNotIn(forbidden, script)
        self.assertIn("*C24C*", script)
        self.assertIn("*C241*", script)

    def test_action_helper_also_checks_process_lifetime(self):
        with patch.object(gate6, "run_uia_helper") as helper, patch.object(gate6, "verify_bound_profile"):
            gate6.uia_invoke("HomeButton")
        script = helper.call_args.args[0][-1]
        self.assertIn("ToFileTimeUtc() -ne 123456789", script)
        self.assertIn("button unavailable", script)
        self.network.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "Windows process metadata")
    def test_native_identity_reads_only_this_test_process(self):
        identity = gate6.process_identity(os.getpid())
        self.assertEqual(Path(identity["exe"]).resolve(), Path(sys.executable).resolve())
        unix_start = identity["started"] / 10_000_000 - 11644473600
        self.assertLessEqual(unix_start, time.time())
        self.assertGreater(unix_start, time.time() - 600)
        self.network.assert_not_called()


class ConsoleTimingReaderTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name in ("api", "bind_console", "live"):
            boundary = self.stack.enter_context(patch.object(gate6, name, side_effect=AssertionError("offline only")))
            self.addCleanup(boundary.assert_not_called)

    @staticmethod
    def fixture():
        def event(index, time, kind, **extra):
            return {"index":index, "timestamp":time, "kind":kind, "epoch":1, "targets":"TEST:A", **extra}
        action = {"action_id":1, "origin":"button_handler", "operation":"Home"}
        events = [event(1, 0, "action_requested", **action), event(2, 25, "command_started", **action),
                  event(3, 125, "bitmap_applied", frame_sequence=42, frame_session="test"),
                  event(4, 325, "action_finished", **action, outcome="command_completed")]
        return {"console":{"response_timing":{"schema_version":1, "recording_id":"test",
                "timestamp_frequency":1000, "captured_at":400, "capacity":4096, "dropped_events":0, "events":events}}}

    def test_command_completion_is_separate_from_bitmap_update_and_correctness(self):
        result = gate6.summarize_console_timing(self.fixture())
        row = result["actions"][0]
        self.assertEqual((row["queue_ms"], row["command_ms"], row["handler_to_finish_ms"]), (25, 300, 325))
        self.assertEqual(row["first_bitmap_after_handler_ms"], 125)
        self.assertEqual(row["frame_sequence"], 42)
        self.assertFalse(row["correctness_verified"])
        self.assertFalse(result["gate6_acceptance"])

    def test_uses_declared_clock_frequency(self):
        report = self.fixture()
        report["console"]["response_timing"]["timestamp_frequency"] = 1000000
        row = gate6.summarize_console_timing(report)["actions"][0]
        self.assertEqual(row["first_bitmap_after_handler_ms"], .125)

    def test_dropped_events_refuse_metrics(self):
        report = self.fixture()
        report["console"]["response_timing"]["dropped_events"] = 1
        with self.assertRaisesRegex(ValueError, "dropped"):
            gate6.summarize_console_timing(report)

    def test_wrong_phone_or_epoch_is_not_matched(self):
        for field, value in (("targets", "TEST:B"), ("epoch", 2)):
            with self.subTest(field=field):
                report = self.fixture()
                report["console"]["response_timing"]["events"][2][field] = value
                row = gate6.summarize_console_timing(report)["actions"][0]
                self.assertIsNone(row["first_bitmap_after_handler_ms"])

    def test_frames_before_handler_are_not_matched(self):
        report = self.fixture()
        events = report["console"]["response_timing"]["events"]
        events.insert(0, events.pop(2))
        for i, event in enumerate(events, 1):
            event["index"] = i
            event["timestamp"] = i * 10
        self.assertIsNone(gate6.summarize_console_timing(report)["actions"][0]["first_bitmap_after_handler_ms"])

    def test_group_target_has_no_selected_preview_metric(self):
        report = self.fixture()
        for e in report["console"]["response_timing"]["events"]:
            if e["kind"] != "bitmap_applied": e["targets"] = "TEST:A,TEST:B"
        self.assertIsNone(gate6.summarize_console_timing(report)["actions"][0]["first_bitmap_after_handler_ms"])

    def test_incomplete_action_is_retained(self):
        report = self.fixture()
        report["console"]["response_timing"]["events"].pop()
        row = gate6.summarize_console_timing(report)["actions"][0]
        self.assertEqual(row["outcome"], "incomplete")
        self.assertIsNone(row["handler_to_finish_ms"])

    def test_malformed_and_mismatched_events_are_refused(self):
        edits = [lambda t: t.update(timestamp_frequency=0),
                 lambda t: t["events"][2].update(timestamp=20),
                 lambda t: t["events"][2].update(index=1),
                 lambda t: t["events"][1].update(targets="TEST:B"),
                 lambda t: t["events"][1].update(action_id=2),
                 lambda t: t.update(capacity=2),
                 lambda t: t.update(captured_at=100)]
        for edit in edits:
            report = copy.deepcopy(self.fixture()); edit(report["console"]["response_timing"])
            with self.assertRaises(ValueError): gate6.summarize_console_timing(report)

    def test_cli_analysis_never_enters_live_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "diagnostics.json"
            path.write_text(json.dumps(self.fixture()), encoding="utf-8")
            with patch.object(sys, "argv", ["run_gate6.py", "--analyze-console-trace", str(path)]), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                gate6.main()
            self.assertFalse(json.loads(output.getvalue())["gate6_acceptance"])


class ConsoleHelperDeadlineTests(unittest.TestCase):
    """Fake child processes only; never launch PowerShell or touch a window."""

    def setUp(self):
        self.console = patch.dict(gate6.CONSOLE, {"pid": 999999, "phone": "C24C",
            "exe": r"C:\scratch\imouse-candidate-5\iMouse2.exe", "started": 1})
        self.console.start()
        self.addCleanup(self.console.stop)
        profile = patch.object(gate6, "verify_bound_profile")
        profile.start(); self.addCleanup(profile.stop)

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
