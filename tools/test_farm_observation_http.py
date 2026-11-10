"""New screen-review and preparation endpoints, with no actual rack connection."""
import json
from unittest.mock import patch
import uuid
import unittest

from test_farm_http_jobs import FarmHttpJobsTests
from test_farm_observations import ReadOnlyKernel, FixtureOcr


class ReviewHttpTests(unittest.TestCase):
    # Reuse only the ephemeral server fixture; do not duplicate its test bodies.
    setUp = FarmHttpJobsTests.setUp
    tearDown = FarmHttpJobsTests.tearDown
    request = FarmHttpJobsTests.request
    outside_connections = FarmHttpJobsTests.outside_connections

    def test_observation_capture_recovery_frames_and_origin_policy(self):
        kernel = ReadOnlyKernel(); self.runtime.observations.ocr = FixtureOcr()
        body = dict(id=str(uuid.uuid4()), device_id='C24C', platform='tiktok', account='test.account', caption='', source='phone', read_only=True)
        with patch('imouse_farm_server.engine.IMouseKernel', return_value=kernel):
            status, response = self.request('/api/farm/observations', body)
            self.assertEqual(200, status, response); self.assertNotIn('simulated', response)
            self.assertEqual(('observed', 'phone'), (response['observation']['state'], response['observation']['source']))
            count = len(kernel.reads)
            self.assertEqual(200, self.request('/api/farm/observations', body)[0]); self.assertEqual(count, len(kernel.reads))
        status, stored = self.request('/api/farm/observations/' + body['id']); self.assertEqual(200, status)
        self.assertEqual('exact_text_match', stored['observation']['result']['accountStatus'])
        self.assertIn('frame', self.request('/api/farm/observations/' + body['id'] + '/frame')[1])
        for path in ('/api/farm/observations', '/api/farm/observations/' + body['id'], '/api/farm/observations/' + body['id'] + '/frame'):
            self.assertEqual(403, self.request(path, origin='https://untrusted.invalid')[0])
        self.assertEqual(400, self.request('/api/farm/observations', {**body, 'read_only': False})[0])
        self.assertEqual([], self.outside_connections())

    def test_local_schedule_http_idempotence_pause_and_worker(self):
        calls = []
        self.runtime.preparation.prepare = lambda: calls.append('local') or [{}]
        body = dict(id=str(uuid.uuid4()), action='create-content', device_id='C24C', interval_minutes=60, max_runs=1)
        status, response = self.request('/api/farm/preparation-schedule', body)
        self.assertEqual(200, status, response); self.assertFalse(response['preparationSchedule']['phoneInput'])
        self.runtime.preparation.tick(); self.assertEqual(['local'], calls)
        self.assertEqual(200, self.request('/api/farm/preparation-schedule', body)[0])
        self.runtime.preparation.tick(); self.assertEqual(['local'], calls)
        status, response = self.request('/api/farm/preparation-schedule/pause', {'cancel_request_id': str(uuid.uuid4())})
        self.assertEqual(200, status); self.assertFalse(response['preparationSchedule']['config']['enabled'])
        self.assertEqual(403, self.request('/api/farm/preparation-schedule', origin='https://untrusted.invalid')[0])
        self.assertEqual([], self.outside_connections())

    def test_saved_http_observation_ages_out_without_recapture(self):
        now = [1000.0]
        store = self.runtime.observations
        store.clock = store.monotonic = lambda: now[0]
        store.ocr = FixtureOcr(); kernel = ReadOnlyKernel()
        body = dict(id=str(uuid.uuid4()), device_id='C24C', platform='tiktok', account='test.account', caption='', source='phone', read_only=True)
        with patch('imouse_farm_server.engine.IMouseKernel', return_value=kernel):
            status, response = self.request('/api/farm/observations', body)
            self.assertEqual(200, status)
            result = response['observation']
            self.assertEqual('recent', result['freshness'])
            self.assertEqual('ready_for_review', result['workflowReview']['status'])
            self.assertFalse(result['workflowReview']['automaticInputAllowed'])
            reads = list(kernel.reads)
            now[0] += 2
            status, response = self.request('/api/farm/observations/' + body['id'])
            self.assertEqual(200, status)
            result = response['observation']
            self.assertEqual('stale', result['freshness'])
            self.assertEqual('blocked', result['workflowReview']['status'])
            self.assertEqual(reads, kernel.reads)
        self.assertEqual([], self.outside_connections())

    def test_emergency_stop_reports_a_failed_schedule_pause_and_still_cancels_the_job(self):
        order = []
        cancel = self.runtime.jobs.cancel_active
        def unavailable():
            self.assertEqual(['cancel'], order, 'Local schedule storage must never delay cancelling the job')
            raise OSError('Schedule storage unavailable')
        with patch.object(self.runtime.jobs, 'cancel_active', side_effect=lambda: order.append('cancel') or cancel()), \
                patch.object(self.runtime.preparation, 'pause', side_effect=unavailable):
            status, response = self.request('/api/farm/emergency-stop', {'device_id': 'C24C'})
        self.assertEqual(500, status); self.assertEqual('partial', response['status'])
        self.assertFalse(response['preparationPaused']); self.assertIn('Schedule storage unavailable', response['preparationPauseError'])
        self.assertFalse(response['phoneStopped']); self.assertIsNone(response['stopped'])
        self.assertEqual([], self.outside_connections())


del FarmHttpJobsTests
