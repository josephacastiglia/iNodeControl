"""Offline job, recovery and integration tests. No desktop or real transport."""
import json
from pathlib import Path
import tempfile
import threading
import time
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
        self.enterContext(patch.object(engine.MediaPullOrchestrator, "detect_host_lan_url", return_value="http://127.0.0.1:9915"))
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

    def test_cancel_interrupts_wait_and_releases_owned_mock_phone(self):
        started = threading.Event()
        kernel = self.runtime.kernel_client
        def run(cancel):
            with kernel.job_context(cancel):
                tokens = kernel.acquire(["C24C"])
                try:
                    started.set()
                    kernel.wait(30)
                    self.fail("Cancelled wait returned normally")
                finally:
                    kernel.release(tokens)
        request_id = str(uuid.uuid4())
        self.jobs.submit(request_id, "test", {}, run)
        self.assertTrue(started.wait(1))
        self.jobs.cancel(request_id)
        self.assertEqual("cancelled", self.finish(request_id)["status"])
        self.assertEqual({}, self.runtime.mock_kernel.leases)

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
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_warmup_job_accepts_console_id_and_releases(self):
        request_id = self.submit("warmup-wave", {"device_id": engine.LIVE_TEST_DEVICE_ID, "clips": 1, "time_scale": 0})
        job = self.finish(request_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(1, job["result"]["sessionsRun"])
        self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_create_and_deploy_job_runs_the_whole_simulated_c24c_flow(self):
        job = self.finish(self.submit("auto-create-and-deploy", {"device_id": engine.LIVE_TEST_DEVICE_ID}))
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(1, job["result"]["summary"]["uploadsExecuted"])
        self.assertEqual("simulated_upload_and_pin", job["result"]["devices"][0]["status"])
        self.assertTrue(job["result"]["simulated"])
        self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_unknown_observations_do_not_claim_dm_success(self):
        job = self.finish(self.submit("funnel-action", {"device_id": "C24C", "action": "comment_to_dm"}))
        self.assertEqual("failed", job["status"])
        self.assertIn("No text observation provider", job["error"])
        self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_unavailable_counts_do_not_clear_an_existing_pause(self):
        self.runtime.db.update_persona("C24C", paused_zero_view=True)
        guard = engine.ShadowbanGuardAndDiagnostics(self.runtime.kernel_client, self.runtime.db)
        result = guard.scan_device_profile_views("C24C")
        self.assertEqual("observation_unavailable", result["status"])
        self.assertTrue(self.runtime.db.get_persona("C24C")["paused_zero_view"])

    def test_live_automation_refuses_before_any_kernel_probe(self):
        self.runtime.execution_mode = "live"
        with patch.object(self.runtime, "get_kernel", side_effect=AssertionError("Must not connect")):
            with self.assertRaises(engine.KernelSafetyError):
                self.submit("single-upload", {"device_id": "C24C"})

    def test_every_upload_format_dispatches_and_releases_in_simulation(self):
        platforms = {"ig": "instagram", "tt": "tiktok", "x": "x", "yt": "youtube"}
        for fmt in engine.UploadFormat:
            with self.subTest(format=fmt.value):
                job = self.finish(self.submit("single-upload", {"device_id": "C24C", "platform": platforms[fmt.value.split('_')[0]], "format": fmt.value, "caption": "Sample"}))
                self.assertEqual("succeeded", job["status"], job)
                self.assertEqual({}, self.runtime.mock_kernel.leases)

    def test_cancelled_context_never_acquires_or_sends_but_allows_cleanup(self):
        cancel = threading.Event()
        tokens = self.runtime.kernel_client.acquire(["C24C"])
        cancel.set()
        with self.runtime.kernel_client.job_context(cancel):
            with self.assertRaises(JobCancelled):
                self.runtime.kernel_client.send("C24C", tokens["C24C"], "/mouse/click", x=1, y=1)
            self.runtime.kernel_client.release(tokens)
        self.assertEqual({}, self.runtime.mock_kernel.leases)


if __name__ == "__main__":
    unittest.main()
