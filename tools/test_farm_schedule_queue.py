import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from farm_schedule_queue import ReviewQueue

MIDNIGHT = dt.datetime(2026, 11, 4, 0, 0, tzinfo=dt.timezone.utc).timestamp()
HOUR = 3600


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'queue.json'; self.now = [MIDNIGHT]
        self.q = self.make(); self.q.set_settings(utc_offset_hours=0, rack_gap_minutes=45)

    def make(self):
        return ReviewQueue(self.path, clock=lambda: self.now[0])

    def add(self, i, platform='tiktok', account='acct-1', caption='cap'):
        return self.q.submit(i, platform, 'photo', account, caption)

    def approved(self, *ids, **kw):
        for i in ids: self.add(i, **kw); self.q.approve(i)

    def slots(self): return self.q.schedule()['slots']

    def test_pending_is_never_planned(self):
        self.add(1); self.assertEqual([], self.q.plan(commit=True)['proposed'])
        self.assertEqual([1], self.q.schedule()['pending'])

    def test_approved_gets_slot_in_window_and_reject_cancels_it(self):
        self.approved(1); planned = self.q.plan(commit=True)['proposed']
        self.assertEqual([1], [p['id'] for p in planned])
        self.assertTrue(9 <= dt.datetime.fromtimestamp(planned[0]['slot'], dt.timezone.utc).hour < 21)
        self.q.reject(1); self.assertEqual([], self.slots())
        with self.assertRaises(ValueError): self.q.approve(1)

    def test_dry_run_writes_nothing(self):
        self.approved(1); before = self.path.read_bytes()
        dry = self.q.plan()
        self.assertTrue(dry['dryRun']); self.assertEqual([1], [p['id'] for p in dry['proposed']])
        self.assertEqual(before, self.path.read_bytes()); self.assertEqual([], self.slots())
        self.assertEqual([1], self.q.schedule()['approved'])

    def test_commit_records_exactly_the_dry_run(self):
        self.q.set_account('acct-1', daily_cap=3, gap_minutes=60); self.approved(1, 2, 3)
        dry = self.q.plan(); committed = self.q.plan(commit=True)
        self.assertEqual(dry['proposed'], committed['proposed'])
        self.assertEqual([p['slot'] for p in dry['proposed']], [s['at'] for s in self.slots()])

    def test_account_daily_cap_pushes_extras_to_next_day(self):
        self.q.set_account('acct-1', daily_cap=2, gap_minutes=60); self.approved(1, 2, 3)
        self.q.plan(commit=True)
        self.assertEqual(['2026-11-04', '2026-11-04', '2026-11-05'], [s['day'] for s in self.slots()])

    def test_account_cap_spans_platforms_and_platform_cap_narrows_it(self):
        self.q.set_account('acct-1', daily_cap=2, gap_minutes=60, platform_caps={'x': 1})
        self.approved(1, 2, platform='x'); self.approved(3, platform='tiktok'); self.approved(4, platform='tiktok')
        self.q.plan(commit=True); by_id = {s['id']: s['day'] for s in self.slots()}
        self.assertEqual({1: '2026-11-04', 2: '2026-11-05', 3: '2026-11-04', 4: '2026-11-05'}, by_id)

    def test_set_budget_is_a_platform_cap(self):
        self.q.set_account('acct-1', daily_cap=5, gap_minutes=30); self.q.set_budget('acct-1', 'tiktok', 2)
        self.approved(1, 2, 3); self.q.plan(commit=True)
        self.assertEqual(['2026-11-04', '2026-11-04', '2026-11-05'], [s['day'] for s in self.slots()])

    def test_budgets_are_per_account(self):
        self.approved(1); self.approved(2, account='acct-2'); self.q.plan(commit=True)
        self.assertEqual({'2026-11-04'}, {s['day'] for s in self.slots()})

    def test_account_spacing_and_rack_gap(self):
        self.q.set_account('acct-1', daily_cap=5, gap_minutes=180); self.q.set_account('acct-2', daily_cap=5, gap_minutes=180)
        self.approved(1, 3, account='acct-1'); self.approved(2, account='acct-2'); self.q.plan(commit=True)
        at = {s['id']: s['at'] for s in self.slots()}
        self.assertGreaterEqual(at[3] - at[1], 180 * 60)
        times = sorted(at.values()); self.assertTrue(all(b - a >= 45 * 60 for a, b in zip(times, times[1:])))
        self.assertLess(at[2] - at[1], 180 * 60)  # other accounts need only the rack gap

    def test_rack_gap_zero_lets_accounts_share_a_time(self):
        self.q.set_settings(rack_gap_minutes=0); self.approved(1); self.approved(2, account='acct-2')
        self.q.plan(commit=True); self.assertEqual(1, len({s['at'] for s in self.slots()}))

    def test_no_slot_before_lead_time_or_outside_window(self):
        self.now[0] = MIDNIGHT + 20 * HOUR + 58 * 60  # 20:58, two minutes before the window closes
        self.approved(1); self.q.plan(commit=True); slot = self.slots()[0]
        self.assertEqual('2026-11-05', slot['day']); self.assertEqual(MIDNIGHT + 33 * HOUR, slot['at'])

    def test_window_and_utc_offset(self):
        self.q.set_settings(window=[10, 12], utc_offset_hours=-5); self.approved(1)
        self.q.plan(commit=True); local = dt.datetime.fromtimestamp(self.slots()[0]['at'], dt.timezone(dt.timedelta(hours=-5)))
        self.assertEqual((10, 0), (local.hour, local.minute)); self.assertEqual('2026-11-04', local.date().isoformat())  # 19:00 on the 3rd locally: today's window is past

    def test_warmup_ramp_holds_early_days(self):
        self.q.set_account('acct-1', daily_cap=3, gap_minutes=60, first_day='2026-11-03', ramp=[0, 0, 0, 1, 2])
        self.approved(1, 2, 3, 4); result = self.q.plan(commit=True)
        days = [s['day'] for s in self.slots()]
        self.assertEqual(['2026-11-06', '2026-11-07', '2026-11-07', '2026-11-08'], days)
        self.assertEqual([], result['unplaced'])
        with self.assertRaises(ValueError): self.q.set_account('acct-9', ramp=[1])

    def test_zero_cap_plans_nothing_and_says_why(self):
        self.q.set_account('acct-1', daily_cap=0); self.approved(1)
        result = self.q.plan(commit=True)
        self.assertEqual([], result['proposed']); self.assertIn('daily cap', result['unplaced'][0]['reason'])
        self.assertEqual([1], self.q.schedule()['approved'])

    def test_replanning_is_stable(self):
        self.approved(1); self.q.plan(commit=True); before = self.q.schedule()
        self.q.plan(commit=True); self.assertEqual(before, self.q.schedule())

    def test_restart_keeps_state_and_lapsed_slots_are_not_run_late(self):
        self.approved(1); self.q.plan(commit=True); slot = self.slots()[0]['at']
        self.now[0] = slot + 3 * HOUR; restarted = self.make()
        self.assertEqual([1], restarted.plan()['lapsing'])
        self.assertEqual([1], restarted.lapse_stale()); self.assertEqual([], restarted.schedule()['slots'])
        self.assertEqual([1], restarted.schedule()['approved'])
        restarted.plan(commit=True); self.assertGreater(restarted.schedule()['slots'][0]['at'], self.now[0])

    def test_two_writers_never_lose_each_others_work(self):
        other = self.make(); self.add(1); other.submit(2, 'tiktok', 'photo', 'acct-1')
        self.q.approve(1); other.approve(2)
        self.assertEqual([1, 2], self.make().schedule()['approved'])

    def test_same_id_with_changed_content_is_refused(self):
        self.add(1); self.q.approve(1); self.add(1)  # same content: no-op
        with self.assertRaises(ValueError): self.add(1, caption='different copy')
        self.assertEqual('approved', self.q._get(self.q.reload().state, '1')['state'])

    def test_account_from_platform_map_or_at_approve(self):
        self.q.set_settings(platform_accounts={'tiktok': 'acct-7'})
        self.assertEqual('acct-7', self.q.submit(1, 'tiktok', 'photo')['account'])
        self.q.submit(2, 'x', 'video')
        with self.assertRaises(ValueError): self.q.approve(2)
        self.assertEqual('acct-3', self.q.approve(2, account='acct-3')['account'])
        with self.assertRaises(ValueError): self.q.approve(2, account='acct-4')

    def test_intake_from_preparation_items(self):
        items = [{'id': 12, 'platform': 'instagram', 'format': 'ig_carousel', 'caption': 'c', 'stagedFiles': ['a.jpg'],
                  'manifestSha256': 'ab', 'runId': 'r1'},
                 {'id': 12, 'platform': 'instagram', 'format': 'ig_carousel', 'caption': 'c', 'stagedFiles': ['a.jpg'],
                  'manifestSha256': 'ab', 'runId': 'r2'},
                 {'id': 12, 'platform': 'instagram', 'format': 'ig_carousel', 'caption': 'changed', 'stagedFiles': ['b.jpg'], 'runId': 'r3'},
                 {'id': 13, 'platform': 'Bad Platform', 'format': 'x'}]
        report = self.q.intake(items)
        self.assertEqual([12], report['added']); self.assertEqual([12], report['known'])
        self.assertEqual([12, 13], [r['id'] for r in report['refused']])
        pkg = self.q.pending()[0]
        self.assertEqual({'runId': 'r1', 'stagedFiles': ['a.jpg'], 'manifestSha256': 'ab'}, pkg['source'])
        self.assertIsNone(pkg['account'])

    def test_first_commit_queue_file_is_read(self):
        self.path.write_text(json.dumps({'budgets': {'acct-1': {'tiktok': 3}}, 'packages': {}}), encoding='utf-8')
        self.assertEqual({'tiktok': 3}, self.make().account('acct-1')['platformCaps'])

    def test_no_handles_or_device_ids_and_bounds(self):
        for bad in ('@someone', 'C24C', 'c24c', 'Acct', '1abc', '00008030'):
            with self.assertRaises(ValueError): self.q.submit(9, 'tiktok', 'photo', bad)
        for bad in (-1, 11, True, 1.5):
            with self.assertRaises(ValueError): self.q.set_account('acct-1', daily_cap=bad)
        for bad in ({'window': [21, 9]}, {'window': [9, 25]}, {'rack_gap_minutes': -1}, {'utc_offset_hours': 20}):
            with self.assertRaises(ValueError): self.q.set_settings(**bad)
        for bad in (0, True, 31):
            with self.assertRaises(ValueError): self.q.plan(bad)

    def test_render_lists_slots_new_and_waiting_and_says_dry_run(self):
        self.q.set_account('acct-1', daily_cap=2, gap_minutes=60)
        self.approved(1); self.q.plan(commit=True); self.approved(2); self.add(3, caption='waiting copy')
        self.q.submit(4, 'x', 'video'); self.approved(5, account='acct-9'); self.q.set_account('acct-9', daily_cap=0)
        text = self.q.render(); before = self.path.read_bytes()
        self.assertIn('DRY RUN: nothing runs on a phone, nothing posts', text)
        self.assertRegex(text, r'Wed 2026-11-04 09:00  acct-1 .* pkg 1 ')
        self.assertRegex(text, r'Wed 2026-11-04 10:00  acct-1 .* pkg 2 +NEW')
        self.assertIn('waiting copy', text); self.assertIn('(set at approve)', text)
        self.assertRegex(text, r'pkg 5 +acct-9 tiktok: account daily cap')
        self.assertEqual(before, self.q.render() and self.path.read_bytes())

    def test_nothing_in_the_queue_can_run_or_publish(self):
        view = self.q.schedule(); plan = self.q.plan()
        for result in (view, plan):
            self.assertFalse(any(result[k] for k in ('startsRuns', 'phoneInput', 'publishing', 'messaging')))
        self.assertFalse([n for n in dir(self.q) if any(w in n for w in ('run', 'post', 'publish', 'send', 'start', 'kernel', 'tap'))])


if __name__ == '__main__': unittest.main()
