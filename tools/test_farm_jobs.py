"""Offline job, recovery and integration tests. No desktop or real transport."""
import json
from pathlib import Path
import tempfile
import threading
import time
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
import uuid

from farm_jobs import FarmJobs, JobCancelled
import imouse_farm_server as server
import imouse_social_automation as engine


class FarmJobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="farm-jobs-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.enterContext(patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")))
        self.enterContext(patch.object(engine.IMouseKernel, "__init__", side_effect=AssertionError("No kernel client may be built")))
        self.runtime = server.FarmBackendRuntime(self.root / "farm.db", self.root / "stage", port=9915)
        self.enterContext(patch.object(server, "RUNTIME", self.runtime))
        self.jobs = self.runtime.jobs

    def finish(self, request_id, jobs=None):
        jobs = jobs or self.jobs
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = jobs.get(request_id)
            if job["terminal"]:
                return job
            time.sleep(.005)
        self.fail("Job did not terminate")

    def submit(self, action, payload):
        return self.runtime.submit_job(str(uuid.uuid4()), action, payload)["id"]

    def test_duplicate_completed_submission_never_replays(self):
        request_id = str(uuid.uuid4())
        run = Mock(return_value={"value": 1})
        self.jobs.submit(request_id, "test", {}, run)
        self.assertEqual("succeeded", self.finish(request_id)["status"])
        self.jobs.submit(request_id, "test", {}, run)
        self.assertEqual(1, run.call_count)

    def test_cancel_before_admission_survives_restart_and_delayed_submission(self):
        request_id = str(uuid.uuid4())
        cancelled = self.jobs.cancel(request_id)
        self.assertEqual('cancelled', cancelled['status']); self.assertTrue(cancelled['terminal'])
        restarted = FarmJobs(journal_path=self.root / 'jobs.db')
        run = Mock(side_effect=AssertionError('A cancelled request cannot start later'))
        self.assertEqual(cancelled, restarted.submit(request_id, 'test', {}, run))
        self.assertEqual(cancelled, restarted.get(request_id)); run.assert_not_called()

    def test_another_registry_cannot_run_work_or_report_active_work_as_interrupted(self):
        started, finish = threading.Event(), threading.Event(); request_id = str(uuid.uuid4())
        def run(cancel): started.set(); finish.wait(3); return {}
        self.jobs.submit(request_id, 'test', {}, run)
        try:
            self.assertTrue(started.wait(1)); other = FarmJobs(journal_path=self.root / 'jobs.db')
            status = other.get(request_id)
            self.assertEqual('running_elsewhere', status['status']); self.assertFalse(status['terminal'])
            with self.assertRaisesRegex(ValueError, 'Another backend'):
                other.submit(str(uuid.uuid4()), 'other', {}, lambda cancel: self.fail('Competing work'))
            self.assertEqual(status, other.submit(request_id, 'test', {}, lambda cancel: self.fail('Replay')))
        finally: finish.set(); self.finish(request_id)
        self.assertEqual('succeeded', other.get(request_id)['status'])

    def test_cancel_from_another_registry_reaches_active_worker(self):
        started = threading.Event(); request_id = str(uuid.uuid4())
        def run(cancel):
            started.set()
            if not cancel.wait(3): self.fail('Durable cancellation was not observed')
            raise JobCancelled('Stopped from another client')
        self.jobs.submit(request_id, 'test', {}, run); self.assertTrue(started.wait(1))
        other = FarmJobs(journal_path=self.root / 'jobs.db'); other.cancel(request_id)
        self.assertEqual('cancelled', self.finish(request_id)['status'])

    def test_worker_start_failure_releases_registry_and_cannot_replay(self):
        request_id = str(uuid.uuid4()); run = Mock()
        with patch('threading.Thread.start', side_effect=RuntimeError('Thread unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'Thread unavailable'):
                self.jobs.submit(request_id, 'test', {}, run)
        run.assert_not_called(); self.assertIsNone(self.jobs.current())
        self.assertEqual('failed', self.jobs.get(request_id)['status'])
        other = FarmJobs(journal_path=self.root / 'jobs.db')
        self.assertEqual('failed', other.submit(request_id, 'test', {}, run)['status'])
        next_id = str(uuid.uuid4()); other.submit(next_id, 'next', {}, lambda cancel: {})
        self.assertEqual('succeeded', self.finish(next_id, other)['status'])

    def test_cancellation_at_atomic_admission_boundary_prevents_work(self):
        request_id = str(uuid.uuid4()); original = self.jobs._admit; other = FarmJobs(journal_path=self.root / 'jobs.db')
        def delayed(job): other.cancel(job.id); return original(job)
        run = Mock()
        with patch.object(self.jobs, '_admit', side_effect=delayed):
            result = self.jobs.submit(request_id, 'test', {}, run)
        self.assertEqual('cancelled', result['status']); run.assert_not_called(); self.assertIsNone(self.jobs.current())

    def test_external_cancellation_after_admission_is_checked_before_callback(self):
        request_id = str(uuid.uuid4()); original = self.jobs._admit; other = FarmJobs(journal_path=self.root / 'jobs.db')
        def delayed(job):
            accepted = original(job); other.cancel(job.id); return accepted
        run = Mock()
        with patch.object(self.jobs, '_admit', side_effect=delayed): self.jobs.submit(request_id, 'test', {}, run)
        self.assertEqual('cancelled', self.finish(request_id)['status']); run.assert_not_called()

    def test_cancel_preserves_completed_result_and_rejects_invalid_ids(self):
        request_id = str(uuid.uuid4()); self.jobs.submit(request_id, 'test', {}, lambda cancel: {'answer': 7})
        result = self.finish(request_id)
        self.assertEqual(result, self.jobs.cancel(request_id))
        self.assertEqual(result, FarmJobs(journal_path=self.root / 'jobs.db').cancel(request_id))
        with self.assertRaises(ValueError): self.jobs.cancel('not-an-id')

    def test_late_heartbeat_monitor_cannot_overwrite_a_terminal_result(self):
        from farm_jobs import Job
        waiting, proceed = threading.Event(), threading.Event()
        class PausedWait(threading.Event):
            def wait(self, timeout=None):
                waiting.set(); proceed.wait(3)
                return False  # Completion arrived just after the wait expired.
        job = Job(str(uuid.uuid4()), 'test', 'test', heartbeat=0)
        job.done = PausedWait(); watcher = threading.Thread(target=self.jobs._watch, args=(job,))
        watcher.start(); self.assertTrue(waiting.wait(1))
        with self.jobs._lock:
            job.status = 'succeeded'; job.done.set()
        proceed.set(); watcher.join(2)
        self.assertFalse(watcher.is_alive()); self.assertEqual('succeeded', job.public()['status']); self.assertFalse(job.cancel.is_set())

    def test_completion_between_status_read_and_owner_probe_is_not_reported_interrupted(self):
        from farm_jobs import Job, _ListenerOwner
        job = Job(str(uuid.uuid4()), 'fingerprint', 'test'); self.jobs._persist(job)
        acquire = _ListenerOwner.acquire
        def finish_before_probe(owner):
            job.status = 'succeeded'; job.result = {'answer': 9}; job.done.set(); self.jobs._persist(job)
            return acquire(owner)
        with patch.object(_ListenerOwner, 'acquire', finish_before_probe): recovered = self.jobs.get(job.id)
        self.assertEqual('succeeded', recovered['status']); self.assertEqual({'answer': 9}, recovered['result'])

    def test_real_process_crash_releases_worker_lock_but_never_replays_accepted_work(self):
        request_id = str(uuid.uuid4())
        child = '''import os,sys,time
from farm_jobs import FarmJobs
jobs=FarmJobs(journal_path=sys.argv[1])
jobs.submit(sys.argv[2], 'test', {}, lambda cancel: os._exit(73))
time.sleep(8)
'''
        result = subprocess.run([sys.executable, '-c', child, str(self.root / 'jobs.db'), request_id],
                                cwd=Path(__file__).parent, capture_output=True, timeout=12,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(73, result.returncode, result.stderr.decode(errors='replace'))
        restarted = FarmJobs(journal_path=self.root / 'jobs.db')
        run = Mock(side_effect=AssertionError('Crashed work must not replay'))
        recovered = restarted.submit(request_id, 'test', {}, run)
        self.assertEqual('interrupted', recovered['status']); self.assertTrue(recovered['terminal']); run.assert_not_called()
        next_id = str(uuid.uuid4()); restarted.submit(next_id, 'next', {}, lambda cancel: {})
        self.assertEqual('succeeded', self.finish(next_id, restarted)['status'])

    def test_a_separate_process_respects_ownership_and_durable_cancellation(self):
        request_id = str(uuid.uuid4()); marker = self.root / 'worker-started'
        child = '''import sys,time
from pathlib import Path
from farm_jobs import FarmJobs,JobCancelled
jobs=FarmJobs(journal_path=sys.argv[1])
def run(cancel):
    Path(sys.argv[3]).write_text('started')
    if not cancel.wait(8): raise RuntimeError('Cancellation missing')
    raise JobCancelled('External cancellation observed')
jobs.submit(sys.argv[2], 'test', {}, run)
assert jobs._jobs[sys.argv[2]].done.wait(10)
with jobs._lock: pass
'''
        process = subprocess.Popen([sys.executable, '-c', child, str(self.root / 'jobs.db'), request_id, str(marker)],
                                   cwd=Path(__file__).parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline: time.sleep(.01)
            self.assertTrue(marker.exists())
            self.assertEqual('running_elsewhere', self.jobs.get(request_id)['status'])
            with self.assertRaisesRegex(ValueError, 'Another backend'):
                self.jobs.submit(str(uuid.uuid4()), 'other', {}, lambda cancel: self.fail('Competing process'))
            self.jobs.cancel(request_id)
            _, stderr = process.communicate(timeout=6)
            self.assertEqual(0, process.returncode, stderr.decode(errors='replace'))
            self.assertEqual('cancelled', self.jobs.get(request_id)['status'])
        finally:
            if process.poll() is None: process.kill()
            process.communicate(timeout=3)

    def test_duplicate_id_with_different_payload_is_refused(self):
        request_id = str(uuid.uuid4())
        self.jobs.submit(request_id, "test", {}, lambda event: {})
        self.finish(request_id)
        with self.assertRaises(ValueError):
            self.jobs.submit(request_id, "test", {"different": True}, lambda event: {})

    def test_failure_is_not_success_or_automatically_retried(self):
        run = Mock(side_effect=RuntimeError("Injected failure"))
        request_id = str(uuid.uuid4())
        self.jobs.submit(request_id, "test", {}, run)
        job = self.finish(request_id)
        self.assertEqual("failed", job["status"])
        self.assertIn("Injected failure", job["error"])
        self.assertEqual(1, run.call_count)

    def test_second_concurrent_job_is_refused(self):
        started, release = threading.Event(), threading.Event()
        request_id = str(uuid.uuid4())
        def run(cancel):
            started.set()
            release.wait(3)
            return {}
        self.jobs.submit(request_id, "test", {}, run)
        try:
            self.assertTrue(started.wait(1))
            with self.assertRaises(ValueError):
                self.jobs.submit(str(uuid.uuid4()), "other", {}, lambda event: {})
        finally:
            release.set()
            self.finish(request_id)

    def test_cleanup_failure_during_cancellation_is_reported(self):
        started = threading.Event()
        def run(cancel):
            started.set()
            cancel.wait(2)
            raise RuntimeError("Release unconfirmed")
        request_id = str(uuid.uuid4())
        self.jobs.submit(request_id, "test", {}, run)
        self.assertTrue(started.wait(1))
        self.jobs.cancel(request_id)
        job = self.finish(request_id)
        self.assertEqual("failed", job["status"])
        self.assertEqual("Release unconfirmed", job["error"])

    def test_lost_client_heartbeat_cancels_job(self):
        jobs = FarmJobs(heartbeat_seconds=.04)
        request_id = str(uuid.uuid4())
        def run(cancel):
            if cancel.wait(2):
                raise JobCancelled("Client gone")
            raise RuntimeError("Heartbeat failed to cancel")
        jobs.submit(request_id, "test", {}, run)
        time.sleep(.10)  # Deliberately do not renew this heartbeat.
        self.assertEqual("cancelled", self.finish(request_id, jobs)["status"])

    def test_new_instance_recovers_completed_result_without_replaying(self):
        request_id = str(uuid.uuid4())
        self.jobs.submit(request_id, "test", {}, lambda cancel: {"answer": 42})
        self.finish(request_id)
        restarted = FarmJobs(journal_path=self.root / "jobs.db")
        run = Mock(side_effect=AssertionError("Must not replay"))
        recovered = restarted.submit(request_id, "test", {}, run)
        self.assertEqual(42, recovered["result"]["answer"])
        run.assert_not_called()

    def test_interrupted_record_is_unknown_not_rerun(self):
        from farm_jobs import Job
        import hashlib
        request_id = str(uuid.uuid4())
        fingerprint = hashlib.sha256(json.dumps(["test", {}], sort_keys=True, allow_nan=False).encode()).hexdigest()
        self.jobs._persist(Job(request_id, fingerprint, "test"))
        restarted = FarmJobs(journal_path=self.root / "jobs.db")
        run = Mock()
        recovered = restarted.submit(request_id, "test", {}, run)
        self.assertEqual("interrupted", recovered["status"])
        self.assertTrue(recovered["terminal"])
        run.assert_not_called()

    def test_invalid_job_ids_and_actions_are_refused(self):
        for request_id in (None, "", "not-a-uuid"):
            with self.subTest(request_id=request_id), self.assertRaises(ValueError):
                self.jobs.submit(request_id, "test", {}, lambda cancel: {})
        with self.assertRaises(ValueError):
            self.submit("unknown-action", {})

    def test_content_job_generates_media_without_kernel_input(self):
        request_id = self.submit("create-content", {"device_id": engine.LIVE_TEST_DEVICE_ID})
        job = self.finish(request_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertTrue((self.root / "stage/C24C/manifest.json").is_file())
        self.assertEqual("simulate", job["result"]["executionMode"]); self.assertNotIn("simulated", job["result"])

    def test_removed_automation_actions_are_not_jobs(self):
        for action in ("warmup-wave", "auto-create-and-deploy", "single-upload", "funnel-action", "scan-profile-views", "scheduler-tick"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.submit(action, {"device_id": "C24C"})
        self.assertFalse((self.root / "stage/C24C").exists())


if __name__ == "__main__":
    unittest.main()
