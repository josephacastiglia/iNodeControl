import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

import farm_schedule_cli as cli
from farm_preparation_schedule import PreparationSchedule
from farm_schedule_queue import ReviewQueue


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.queue = self.root / 'queue.json'

    def run_cli(self, *argv):
        out = io.StringIO(); code = cli.main(['--queue', str(self.queue), *argv], out=out)
        return code, out.getvalue()

    def prepared_db(self):
        item = {'id': 21, 'platform': 'instagram', 'format': 'ig_carousel', 'caption': 'Prepared copy', 'stagedFiles': ['s1.jpg', 's2.jpg']}
        now = [1000.0]
        schedule = PreparationSchedule(self.root / 'prep.db', lambda: [item], lambda: {'account_day': 5}, threading.Lock(), clock=lambda: now[0])
        self.addCleanup(schedule.close)
        schedule.configure({'id': str(uuid.uuid4()), 'device_id': 'C24C', 'action': 'create-content', 'interval_minutes': 60, 'max_runs': 1})
        schedule.tick()
        return schedule.path

    def test_operator_flow_intake_review_approve_plan_commit(self):
        db = self.prepared_db()
        self.assertEqual(0, self.run_cli('settings', '--utc-offset', '0', '--window', '9-21')[0])
        code, text = self.run_cli('intake', '--preparation-db', str(db)); self.assertEqual(0, code)
        self.assertIn('1 added', text)
        self.assertIn('1 already queued', self.run_cli('intake', '--preparation-db', str(db))[1])
        code, text = self.run_cli('review'); self.assertIn('pkg 21', text); self.assertIn('file: s2.jpg', text)
        self.assertEqual(2, self.run_cli('approve', '21')[0])  # no account yet: refused
        self.assertIn('pkg 21: approved', self.run_cli('approve', '21', '--account', 'acct-1')[1])
        code, text = self.run_cli(); self.assertIn('no window yet', text)      # Real content runs only from its window.
        self.assertIn('Recorded 0 new slot', self.run_cli('plan', '--commit')[1])
        ReviewQueue(self.queue).bind_window(21, 'reel-slot18', 18, 'c' * 64)
        code, text = self.run_cli(); self.assertIn('DRY RUN', text); self.assertRegex(text, r'pkg 21 +NEW')
        self.assertEqual([], json.loads(self.queue.read_text())['packages']['21'].get('slot', []))
        code, text = self.run_cli('plan', '--commit'); self.assertIn('Recorded 1 new slot', text)
        self.assertNotRegex(self.run_cli('plan')[1], r'pkg 21 +NEW')
        self.assertEqual('planned', json.loads(self.queue.read_text())['packages']['21']['state'])

    def test_account_settings_and_reject(self):
        code, text = self.run_cli('account', 'acct-1', '--daily', '2', '--gap', '90', '--cap', 'tiktok=1',
                                  '--first-day', '2026-11-03', '--ramp', '0,0,1')
        self.assertEqual(0, code); account = json.loads(text)['acct-1']
        self.assertEqual((2, 90, {'tiktok': 1}, [0, 0, 1]), (account['dailyCap'], account['gapMinutes'], account['platformCaps'], account['ramp']))
        self.assertEqual(2, self.run_cli('account', 'C24C', '--daily', '1')[0])
        self.assertEqual(2, self.run_cli('reject', '5')[0])

    def test_json_plan_says_nothing_runs(self):
        code, text = self.run_cli('--json', 'plan'); plan = json.loads(text)
        self.assertTrue(plan['plan']['dryRun'])
        self.assertFalse(any(plan['schedule'][k] for k in ('startsRuns', 'phoneInput', 'publishing', 'messaging')))

    def test_missing_preparation_db_is_empty(self):
        self.assertIn('0 added', self.run_cli('intake', '--preparation-db', str(self.root / 'none.db'))[1])
        self.assertFalse((self.root / 'none.db').exists())


if __name__ == '__main__': unittest.main()
