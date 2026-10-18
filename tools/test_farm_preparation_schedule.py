import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid

from farm_preparation_schedule import PreparationSchedule


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'schedule.db'; self.now = [1000.0]; self.calls = []
        self.profile = {'account_day': 5, 'paused_zero_view': False}
        self.operation = threading.Lock()
        self.item = {'id': 1, 'platform': 'instagram', 'format': 'ig_carousel', 'caption': 'Review', 'stagedFiles': ['a.jpg', 'b.jpg']}
        def prepare(): self.calls.append('prepare'); return [self.item]
        self.schedule = PreparationSchedule(self.path, prepare, lambda: self.profile, self.operation, clock=lambda: self.now[0])
        self.addCleanup(self.schedule.close)
        self.request = {'id': str(uuid.uuid4()), 'device_id': 'C24C', 'action': 'create-content', 'interval_minutes': 60, 'max_runs': 2}

    def test_default_no_work_then_runs_at_due_time_and_stops_at_limit(self):
        self.schedule.tick(); self.assertEqual([], self.calls)
        self.schedule.configure(self.request); self.schedule.tick(); self.assertEqual(1, len(self.calls))
        self.now[0] += 3599; self.schedule.tick(); self.assertEqual(1, len(self.calls))
        self.now[0] += 1; self.schedule.tick(); self.assertEqual(2, len(self.calls))
        self.now[0] += 3600; self.schedule.tick(); self.assertEqual(2, len(self.calls))
        status = self.schedule.status(); self.assertEqual('complete', status['config']['state'])
        self.assertFalse(status['publishing']); self.assertFalse(status['phoneInput']); self.assertFalse(status['messaging'])

    def test_duplicate_configuration_does_not_reenable_paused_work(self):
        self.schedule.configure(self.request); self.schedule.pause(); self.schedule.configure(self.request); self.schedule.tick()
        self.assertEqual([], self.calls); self.assertFalse(self.schedule.status()['config']['enabled'])
        with self.assertRaises(ValueError): self.schedule.configure({**self.request, 'max_runs': 3})

    def test_pause_cancels_an_inflight_configuration_before_it_arrives(self):
        self.schedule.pause(self.request['id'])
        self.schedule.configure(self.request); self.schedule.tick()
        self.assertEqual([], self.calls); self.assertFalse(self.schedule.status()['config']['enabled'])

    def test_missed_runs_skip_instead_of_catchup_burst(self):
        self.schedule.configure(self.request); self.now[0] += 86400; self.schedule.tick()
        self.assertEqual([], self.calls); self.assertEqual('missed', self.schedule.status()['runs'][0]['state'])
        self.assertEqual(self.now[0] + 3600, self.schedule.status()['config']['nextDue'])
        self.schedule.tick(); self.assertEqual([], self.calls)

    def test_clock_rollback_does_not_create_duplicate(self):
        self.schedule.configure(self.request); self.schedule.tick(); self.now[0] -= 86400; self.schedule.tick()
        self.assertEqual(1, len(self.calls))

    def test_completed_run_keeps_its_content_references_after_the_next_slate(self):
        items = [{'id': 12, 'platform': 'instagram', 'format': 'ig_carousel', 'caption': 'Review this',
                  'stagedFiles': ['slide_a.jpg', 'slide_b.jpg']}]
        self.schedule.prepare = lambda: items
        self.schedule.configure(self.request); self.schedule.tick()
        items[0] = {**items[0], 'id': 13, 'caption': 'Later slate', 'stagedFiles': ['slide_c.jpg']}
        self.now[0] += 3600; self.schedule.tick()
        runs = self.schedule.status()['runs']
        self.assertEqual('Review this', runs[1]['contentItems'][0]['caption'])
        self.assertEqual(['slide_a.jpg', 'slide_b.jpg'], runs[1]['contentItems'][0]['stagedFiles'])
        self.assertEqual(13, runs[0]['contentItems'][0]['id'])

    def test_busy_manual_operation_defers_preparation(self):
        self.schedule.configure(self.request)
        with self.operation: self.schedule.tick()
        self.assertEqual([], self.calls); self.schedule.tick(); self.assertEqual(1, len(self.calls))

    def test_second_backend_cannot_recover_or_execute_current_render(self):
        self.schedule.configure(self.request)
        started, finish = threading.Event(), threading.Event()
        def blocked(): started.set(); finish.wait(5); return [self.item]
        self.schedule.prepare = blocked
        worker = threading.Thread(target=self.schedule.tick); worker.start(); self.assertTrue(started.wait(2))
        try:
            other = PreparationSchedule(self.path, lambda: self.fail('Competing render'), lambda: self.profile, threading.Lock(), clock=lambda: self.now[0])
            self.assertEqual('running', other.status()['runs'][0]['state']); other.tick()
            self.assertEqual('running', other.status()['runs'][0]['state'])
            with self.assertRaises(ValueError): other.configure({**self.request, 'id': str(uuid.uuid4())})
            self.schedule.pause()
        finally: finish.set(); worker.join(3)
        self.assertEqual('succeeded', self.schedule.status()['runs'][0]['state']); self.assertFalse(self.schedule.status()['config']['enabled'])

    def test_restart_with_running_record_holds_and_never_replays(self):
        self.schedule.configure(self.request)
        with self.schedule.connect() as db:
            db.execute('INSERT INTO preparation_runs VALUES (?,?)', ('interrupted', json.dumps({'state': 'running', 'id': 'interrupted'})))
        restarted = PreparationSchedule(self.path, lambda: self.fail('No replay'), lambda: self.profile, threading.Lock(), clock=lambda: self.now[0])
        restarted.tick(); self.assertEqual('needs_review', restarted.status()['config']['state'])
        self.assertEqual('interrupted', restarted.status()['runs'][0]['state'])

    def test_failed_or_empty_render_is_held_without_retry(self):
        self.schedule.configure(self.request); self.schedule.prepare = lambda: []
        self.schedule.tick(); self.schedule.tick()
        self.assertEqual('failed', self.schedule.status()['runs'][0]['state']); self.assertFalse(self.schedule.status()['config']['enabled'])

    def test_profile_pause_and_early_phase_hold_without_rendering(self):
        for changes in ({'account_day': 1}, {'account_day': 5, 'paused_zero_view': True}):
            self.profile.update(changes); self.schedule.configure({**self.request, 'id': str(uuid.uuid4())}); self.schedule.tick()
            self.assertEqual('held', self.schedule.status()['config']['state']); self.assertEqual([], self.calls)

    def test_live_actions_and_other_targets_cannot_be_scheduled(self):
        for changes in ({'device_id': 'C241'}, {'action': 'publish'}, {'action': 'warmup'}, {'interval_minutes': 1}, {'max_runs': 100}, {'max_runs': True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.schedule.configure({**self.request, **changes})

    def test_worker_executes_without_ui_heartbeat_and_closes(self):
        self.schedule.configure({**self.request, 'max_runs': 1}); self.schedule.start()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and not self.calls: time.sleep(.02)
        self.schedule.close(); self.assertEqual(1, len(self.calls)); self.assertFalse(self.schedule.thread.is_alive())


if __name__ == '__main__': unittest.main()
