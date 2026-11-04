import datetime as dt
from pathlib import Path
import tempfile
import unittest

from farm_schedule_queue import ReviewQueue

MIDNIGHT = dt.datetime(2026, 11, 4, 0, 0, tzinfo=dt.timezone.utc).timestamp()


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'queue.json'; self.now = [MIDNIGHT]
        self.q = self.make()

    def make(self):
        return ReviewQueue(self.path, clock=lambda: self.now[0])

    def add(self, i, platform='tiktok', account='acct-1'):
        return self.q.submit(i, platform, 'photo', account, 'cap')

    def test_pending_is_never_planned(self):
        self.add(1); self.assertEqual([], self.q.plan())
        self.assertEqual([1], self.q.schedule()['pending'])

    def test_approved_gets_slot_in_window_and_reject_cancels_it(self):
        self.add(1); self.q.approve(1); planned = self.q.plan()
        self.assertEqual([1], [p['id'] for p in planned])
        hour = dt.datetime.fromtimestamp(planned[0]['slot'], dt.timezone.utc).hour
        self.assertTrue(9 <= hour < 21)
        self.q.reject(1); self.assertEqual([], self.q.schedule()['slots'])
        with self.assertRaises(ValueError): self.q.approve(1)

    def test_daily_budget_pushes_extras_to_next_day(self):
        self.q.set_budget('acct-1', 'tiktok', 2)
        for i in (1, 2, 3): self.add(i); self.q.approve(i)
        self.q.plan(); days = [s['day'] for s in self.q.schedule()['slots']]
        self.assertEqual(['2026-11-04', '2026-11-04', '2026-11-05'], days)

    def test_budgets_are_per_account_and_platform(self):
        self.add(1); self.add(2, account='acct-2'); self.add(3, platform='x')
        for i in (1, 2, 3): self.q.approve(i)
        self.q.plan(); self.assertEqual({'2026-11-04'}, {s['day'] for s in self.q.schedule()['slots']})

    def test_slots_keep_the_minimum_gap(self):
        self.q.set_budget('acct-1', 'tiktok', 5); self.q.set_budget('acct-2', 'tiktok', 5)
        for i, acct in ((1, 'acct-1'), (2, 'acct-2'), (3, 'acct-1')): self.add(i, account=acct); self.q.approve(i)
        self.q.plan(); times = sorted(s['at'] for s in self.q.schedule()['slots'])
        self.assertTrue(all(b - a >= 45 * 60 for a, b in zip(times, times[1:])))

    def test_zero_budget_plans_nothing(self):
        self.q.set_budget('acct-1', 'tiktok', 0); self.add(1); self.q.approve(1)
        self.assertEqual([], self.q.plan()); self.assertEqual([1], self.q.schedule()['approved'])

    def test_replanning_is_stable(self):
        self.add(1); self.q.approve(1); self.q.plan(); before = self.q.schedule()
        self.q.plan(); self.assertEqual(before, self.q.schedule())

    def test_restart_keeps_state_and_lapsed_slots_are_not_run_late(self):
        self.add(1); self.q.approve(1); self.q.plan(); slot = self.q.schedule()['slots'][0]['at']
        self.now[0] = slot + 3 * 3600; restarted = self.make()
        self.assertEqual([1], restarted.lapse_stale()); self.assertEqual([], restarted.schedule()['slots'])
        self.assertEqual([1], restarted.schedule()['approved'])
        restarted.plan(); self.assertGreater(restarted.schedule()['slots'][0]['at'], self.now[0])

    def test_no_handles_or_device_ids_and_budget_bounds(self):
        for bad in ('@someone', 'C24C', 'Acct', '1abc'):
            with self.assertRaises(ValueError): self.q.submit(9, 'tiktok', 'photo', bad)
        for bad in (-1, 11, True, 1.5):
            with self.assertRaises(ValueError): self.q.set_budget('acct-1', 'tiktok', bad)

    def test_nothing_in_the_view_can_run_or_publish(self):
        view = self.q.schedule()
        self.assertFalse(any(view[k] for k in ('startsRuns', 'phoneInput', 'publishing', 'messaging')))
        self.assertFalse([n for n in dir(self.q) if any(w in n for w in ('run', 'post', 'publish', 'send', 'start'))])


if __name__ == '__main__': unittest.main()
