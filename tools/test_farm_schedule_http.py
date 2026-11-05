"""Review queue endpoints: view, approve and reject. Local-only; nothing here runs a slot or touches a phone."""
from pathlib import Path
import tempfile
import unittest

from farm_schedule_queue import ReviewQueue
import test_farm_http_jobs as http_jobs


class ScheduleQueueHttpTests(unittest.TestCase):
    setUp_server = http_jobs.FarmHttpJobsTests.setUp
    tearDown = http_jobs.FarmHttpJobsTests.tearDown
    request = http_jobs.FarmHttpJobsTests.request

    def setUp(self):
        self.setUp_server()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.runtime.schedule_queue_path = Path(self.temp.name) / 'queue.json'
        q = ReviewQueue(self.runtime.schedule_queue_path)
        q.set_settings(window=[0, 24])
        q.submit('reel18-aaaaaa', 'instagram', 'ig_reel', 'acct-a18', 'Fresh reel acceptance', {'slot': 18, 'manifestSha256': 'a' * 64})
        q.submit(7, 'tiktok', 'tt_photo', None, 'Prepared copy', {'stagedFiles': ['s1.jpg']})

    def test_view_lists_pending_and_a_dry_run_plan(self):
        status, body = self.request('/api/farm/schedule-queue')
        self.assertEqual(200, status, body)
        view = body['scheduleQueue']
        self.assertEqual(['reel18-aaaaaa', 7], view['schedule']['pending'])
        self.assertEqual(['reel18-aaaaaa', 7], [p['id'] for p in view['pending']])
        self.assertTrue(view['plan']['dryRun'])
        self.assertFalse(body['startsRuns'] or body['phoneInput'] or body['publishing'])

    def test_approve_and_reject(self):
        status, body = self.request('/api/farm/schedule-queue/approve', {'id': 'reel18-aaaaaa'})
        self.assertEqual((200, 'approved'), (status, body['package']['state']), body)
        status, body = self.request('/api/farm/schedule-queue/approve', {'id': '7', 'account': 'acct-2'})
        self.assertEqual(('approved', 'acct-2'), (body['package']['state'], body['package']['account']), body)
        status, body = self.request('/api/farm/schedule-queue/reject', {'id': 7, 'reason': 'caption off'})
        self.assertEqual((200, 'rejected'), (status, body['package']['state']))
        q = ReviewQueue(self.runtime.schedule_queue_path)
        self.assertEqual((['reel18-aaaaaa'], [7], []), (q.schedule()['approved'], q.schedule()['rejected'], q.schedule()['slots']))
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_refusals(self):
        self.assertEqual(400, self.request('/api/farm/schedule-queue/approve', {'id': 7})[0])            # No account yet.
        self.assertEqual(400, self.request('/api/farm/schedule-queue/approve', {'id': 99})[0])           # Unknown package.
        self.assertEqual(400, self.request('/api/farm/schedule-queue/approve', {'id': 7, 'account': 'some.handle'})[0])
        self.assertEqual(400, self.request('/api/farm/schedule-queue/approve', {'id': 'reel18-aaaaaa', 'slot': 1})[0])
        self.assertEqual(400, self.request('/api/farm/schedule-queue/reject', {'id': 7, 'run': True})[0])
        self.assertEqual(['reel18-aaaaaa', 7], ReviewQueue(self.runtime.schedule_queue_path).schedule()['pending'])

    def test_local_only(self):
        self.assertEqual(403, self.request('/api/farm/schedule-queue', origin='https://untrusted.invalid')[0])
        self.assertEqual(403, self.request('/api/farm/schedule-queue/approve', {'id': 'reel18-aaaaaa'}, origin='https://untrusted.invalid')[0])
        self.assertEqual(['reel18-aaaaaa', 7], ReviewQueue(self.runtime.schedule_queue_path).schedule()['pending'])


if __name__ == '__main__':
    unittest.main()
