import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import farm_schedule_cli as cli
import farm_schedule_runner as runner
from farm_schedule_queue import GRACE_SECONDS, ReviewQueue

NOON = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc).timestamp()
SHA = 'a' * 64
PREP = {'platform': 'reel', 'slot': 18, 'packageSha256': SHA, 'kernelSha256': 'k' * 64,
        'phone': {'deviceId': 'dev-18', 'receiver': 'iMouse2-18', 'board': 'B18', 'slot': 18}}


def run(state='verified', verified=True, saved=False, **extra):
    workflow = {'creationState': 'created_unverified', 'cleanup': 'confirmed', 'verification': {}} if saved else {}
    return {'id': 'run-1', 'terminal': True, 'state': state, 'savedDraftVerified': verified, 'cleanup': 'confirmed',
            'reason': 'Reel draft verified' if verified else 'stopped', 'workflow': workflow, **extra}


class FakeSteps:
    """Records the order of window steps; each step's answer is set per test."""
    def __init__(self):
        self.calls, self.prep = [], dict(PREP)
        self.ready = [None]; self.start_problem = None; self.screen_problem = None; self.stop_problem = None
        self.created = (run(), None); self.rechecked = ({'state': 'validation_passed', 'savedDraftVerified': True}, None)
        self.backend = False; self.in_place = False

    def read_staged(self, pid): self.calls.append('read'); return self.prep
    def phone_ready(self, prep):
        self.calls.append('ready'); return self.ready.pop(0) if len(self.ready) > 1 else self.ready[0]
    def restore(self, pid, name):
        if self.in_place: raise runner.PhoneNotReady(f'another window {name} is in place')
        self.calls.append('restore')
    def unstage_back(self, pid, name): self.calls.append('unstage')
    def start(self, pid, name): self.calls.append('start'); return self.start_problem
    def backend_running(self, name): return self.backend
    def start_screen(self, pid, name, prep): self.calls.append('screen'); return self.screen_problem
    def create(self, pid, name): self.calls.append('create'); return self.created
    def recheck(self, pid, name, check): self.calls.append(f'recheck-{check}'); return self.rechecked
    def stop(self, pid, name): self.calls.append('stop'); return self.stop_problem
    def archive(self, pid, name): self.calls.append('archive'); return Path(f'{name}-sched-{pid}-1')


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.now = [NOON]
        self.q = ReviewQueue(Path(self.temp.name) / 'queue.json', clock=lambda: self.now[0])
        self.q.set_settings(window=[0, 24], utc_offset_hours=0, rack_gap_minutes=10)
        self.q.set_account('acct-a18', daily_cap=4, gap_minutes=20)
        self.steps = FakeSteps()

    def package(self, pid='reel18-aaaaaa', slot=18, sha=SHA):
        source = {'kind': 'window', 'window': f'reel-slot{slot}', 'slot': slot, 'manifestSha256': sha, 'stagedFiles': ['v.mp4']}
        self.q.submit(pid, 'instagram', 'ig_reel', 'acct-a18', 'Fresh reel acceptance', source)
        self.q.approve(pid)
        return pid

    def planned(self, *pids):
        for pid in pids or ('reel18-aaaaaa',): self.package(pid)
        return [p['slot'] for p in self.q.plan(commit=True)['proposed']]

    def runner(self, **kw): return runner.SlotRunner(self.q, self.steps, 18, clock=lambda: self.now[0], **kw)

    def at(self, ts): self.now[0] = ts

    # --- the happy path ---
    def test_due_slot_runs_the_window_steps_in_order_and_records_verified(self):
        slot, = self.planned(); self.at(slot + 5)
        record = self.runner().run_due()
        self.assertEqual(['read', 'ready', 'restore', 'start', 'ready', 'screen', 'create', 'stop', 'archive'], self.steps.calls)
        self.assertEqual(('verified', 'run-1', 'reel-slot18-sched-reel18-aaaaaa-1'), (record['outcome'], record['runId'], record['archive']))
        self.assertEqual(['reel18-aaaaaa'], self.q.schedule()['done'])
        self.assertEqual(slot, self.q.history()[0]['slot'])

    def test_nothing_runs_early_and_a_passed_slot_lapses_instead_of_running_late(self):
        slot, = self.planned()
        self.at(slot - 1); self.assertIsNone(self.runner().run_due())
        self.at(slot + GRACE_SECONDS + 1); self.assertIsNone(self.runner().run_due())
        self.assertEqual([], self.steps.calls)
        self.assertEqual(['reel18-aaaaaa'], self.q.schedule()['approved'])

    def test_only_this_phones_slots(self):
        self.package('reel20-bbbbbb', slot=20); slot, = [p['slot'] for p in self.q.plan(commit=True)['proposed']]
        self.at(slot + 1); self.assertIsNone(self.runner().run_due()); self.assertEqual([], self.steps.calls)

    # --- not ready: nothing sent, back to approved without a slot ---
    def test_phone_not_mirroring_is_not_ready_and_nothing_starts(self):
        slot, = self.planned(); self.at(slot); self.steps.ready = ['mirror stalled (newest frame 9000 ms old)']
        record = self.runner().run_due()
        self.assertEqual(('not_ready', 'mirror stalled (newest frame 9000 ms old)'), (record['outcome'], record['reason']))
        self.assertEqual(['read', 'ready'], self.steps.calls)
        self.assertEqual(['reel18-aaaaaa'], self.q.schedule()['approved']); self.assertEqual([], self.q.schedule()['slots'])

    def test_changed_staged_content_is_not_run(self):
        slot, = self.planned(); self.at(slot); self.steps.prep = dict(PREP, packageSha256='b' * 64)
        self.assertEqual('not_ready', self.runner().run_due()['outcome']); self.assertEqual(['read'], self.steps.calls)

    def test_another_window_in_place_is_not_ready(self):
        slot, = self.planned(); self.at(slot); self.steps.in_place = True
        record = self.runner().run_due()
        self.assertEqual('not_ready', record['outcome']); self.assertIn('in place', record['reason'])

    def test_backend_refusing_to_start_is_stopped_and_restaged(self):
        slot, = self.planned(); self.at(slot); self.steps.start_problem = 'Start-Window: Backend identity differs'; self.steps.backend = True
        record = self.runner().run_due()
        self.assertEqual('not_ready', record['outcome'])
        self.assertEqual(['read', 'ready', 'restore', 'start', 'stop', 'unstage'], self.steps.calls)

    def test_phone_busy_after_backend_start_stops_backend_before_any_input(self):
        slot, = self.planned(); self.at(slot); self.steps.ready = [None, 'the phone is not idle (owned)']
        record = self.runner().run_due()
        self.assertEqual('not_ready', record['outcome'])
        self.assertEqual(['read', 'ready', 'restore', 'start', 'ready', 'stop', 'unstage'], self.steps.calls)
        self.assertNotIn('screen', self.steps.calls)

    # --- stopped: phone input was sent; never retried ---
    def test_start_screen_refusal_is_stopped_and_archived(self):
        slot, = self.planned(); self.at(slot); self.steps.screen_problem = 'start screen: unrecognized screen'
        record = self.runner().run_due()
        self.assertEqual(('stopped', 'start screen: unrecognized screen'), (record['outcome'], record['reason']))
        self.assertEqual(['stop', 'archive'], self.steps.calls[-2:]); self.assertNotIn('create', self.steps.calls)
        self.assertEqual(['reel18-aaaaaa'], self.q.schedule()['stopped'])

    def test_stopped_run_is_not_retried_by_later_runner_passes(self):
        slot, = self.planned(); self.at(slot); self.steps.created = (run('review_required', False, error='OCR missed Next'), None)
        self.assertEqual('stopped', self.runner().run_due()['outcome'])
        calls = len(self.steps.calls); self.at(slot + 60)
        self.assertIsNone(self.runner().run_due()); self.assertEqual(calls, len(self.steps.calls))
        self.assertEqual({'pending': [], 'approved': []}, {k: self.q.schedule()[k] for k in ('pending', 'approved')})
        self.assertEqual([], self.q.plan(commit=True)['proposed'])   # A stopped package never gets a new slot.

    def test_saved_but_unverified_reports_the_recheck_without_running_it(self):
        slot, = self.planned(); self.at(slot); self.steps.created = (run('review_required', False, saved=True), None)
        record = self.runner().run_due()
        self.assertEqual('stopped', record['outcome']); self.assertTrue(record['savedUnverified'])
        self.assertIn('--check 2', record['reason']); self.assertNotIn('recheck-2', self.steps.calls)

    def test_explicit_recheck_runs_the_read_only_verifier_once(self):
        slot, = self.planned(); self.at(slot); self.steps.created = (run('review_required', False, saved=True), None)
        record = self.runner(recheck=True).run_due()
        self.assertEqual('verified', record['outcome']); self.assertEqual(1, self.steps.calls.count('recheck-2'))
        self.assertEqual({'check': 2, 'state': 'validation_passed', 'savedDraftVerified': True, 'problem': None}, record['recheck'])

    def test_failed_recheck_stays_stopped(self):
        slot, = self.planned(); self.at(slot); self.steps.created = (run('review_required', False, saved=True), None)
        self.steps.rechecked = ({'state': 'review_required', 'savedDraftVerified': False, 'error': 'Drafts unreadable'}, None)
        record = self.runner(recheck=True).run_due()
        self.assertEqual('stopped', record['outcome']); self.assertIn('Drafts unreadable', record['reason'])

    def test_create_timeout_leaves_the_window_running_for_review(self):
        slot, = self.planned(); self.at(slot); self.steps.created = (None, 'run-window did not end within 2400 s')
        record = self.runner().run_due()
        self.assertEqual('stopped', record['outcome']); self.assertNotIn('stop', self.steps.calls)

    def test_stop_window_refusal_keeps_window_in_place_and_says_so(self):
        slot, = self.planned(); self.at(slot); self.steps.stop_problem = 'Stop-Window: A run still holds this phone'
        record = self.runner().run_due()
        self.assertEqual('verified', record['outcome']); self.assertIn('window left in place', record['reason'])
        self.assertNotIn('archive', self.steps.calls)

    def test_runner_error_after_claim_is_recorded_as_stopped(self):
        slot, = self.planned(); self.at(slot)
        with mock.patch.object(self.steps, 'create', side_effect=RuntimeError('boom')):
            record = self.runner().run_due()
        self.assertEqual('stopped', record['outcome']); self.assertIn('boom', record['reason'])

    # --- one at a time per phone ---
    def test_a_run_without_recorded_end_blocks_the_phone_until_abandoned(self):
        first, second = self.planned('reel18-aaaaaa', 'reel18-bbbbbb')
        self.at(first); self.q.claim('reel18-aaaaaa', 18)     # The runner died here.
        self.at(second)
        with self.assertRaises(ValueError): self.runner().run_due()
        with self.assertRaises(ValueError): self.q.claim('reel18-bbbbbb', 18)
        self.q.abandon('reel18-aaaaaa', 'backend log reviewed; no draft saved')
        self.assertEqual('verified', self.runner().run_due()['outcome'])
        self.assertEqual(['stopped', 'verified'], [r['outcome'] for r in self.q.history()])

    def test_two_slots_in_a_row_with_waiting(self):
        first, second = self.planned('reel18-aaaaaa', 'reel18-bbbbbb')
        self.assertEqual(20 * 60, second - first)
        self.at(first - 30)
        sleeps = []
        def sleep(seconds): sleeps.append(seconds); self.now[0] += seconds
        records = runner.SlotRunner(self.q, self.steps, 18, clock=lambda: self.now[0], sleep=sleep).run(max_slots=2, wait_seconds=3600)
        self.assertEqual(['verified', 'verified'], [r['outcome'] for r in records])
        self.assertEqual(2, self.steps.calls.count('create'))
        self.assertTrue(all(s <= 30 for s in sleeps))

    def test_used_slots_keep_counting_toward_the_daily_cap(self):
        self.q.set_account('acct-a18', daily_cap=1)
        slot, = self.planned(); self.at(slot); self.runner().run_due()
        self.package('reel18-cccccc'); proposal = self.q.plan(commit=True)['proposed']
        self.assertEqual('2026-11-05', dt.datetime.fromtimestamp(proposal[0]['slot'], dt.timezone.utc).date().isoformat())

    def test_finished_packages_cannot_be_rejected_or_rerun(self):
        slot, = self.planned(); self.at(slot); self.runner().run_due()
        with self.assertRaises(ValueError): self.q.reject('reel18-aaaaaa')
        with self.assertRaises(ValueError): self.q.claim('reel18-aaaaaa', 18)


class RackLockRunnerTests(RunnerTests):
    """The runner holds the rack-wide lock for a whole slot run and never claims while another run holds it."""
    def busy_lock(self, holders):
        from farm_rack_lock import RackBusy
        taken = []
        from contextlib import contextmanager
        @contextmanager
        def lock(holder):
            if holders and holders.pop(0): raise RackBusy('a lane run on A20')
            taken.append(holder); yield
        return lock, taken

    def test_a_held_rack_leaves_the_slot_unclaimed_then_it_runs(self):
        slot, = self.planned(); self.at(slot + 5)
        lock, taken = self.busy_lock([True, False]); lines = []
        r = self.runner(rack_lock=lock, log=lines.append)
        self.assertIsNone(r.run_due()); self.assertEqual([], self.steps.calls)
        self.assertEqual(['reel18-aaaaaa'], [s['id'] for s in self.q.schedule()['slots']])   # Still planned.
        self.assertIn('waiting', lines[0])
        self.assertEqual('verified', r.run_due()['outcome'])
        self.assertEqual(['slot runner, phone 18, pkg reel18-aaaaaa'], taken)

    def test_a_rack_held_past_the_grace_lapses_the_slot(self):
        slot, = self.planned(); self.at(slot)
        lock, _ = self.busy_lock([True] * 10000)
        sleeps = []
        def sleep(seconds): sleeps.append(seconds); self.now[0] += seconds
        records = runner.SlotRunner(self.q, self.steps, 18, clock=lambda: self.now[0], sleep=sleep, rack_lock=lock).run(1, 3600)
        self.assertEqual([], records); self.assertEqual([], self.steps.calls)
        self.assertEqual(['reel18-aaaaaa'], self.q.schedule()['approved'])   # Lapsed, never run late.
        self.assertTrue(all(s >= 5 for s in sleeps))

    def test_the_lock_is_released_when_the_run_stops(self):
        from contextlib import contextmanager
        events = []
        @contextmanager
        def lock(holder):
            events.append('take')
            try: yield
            finally: events.append('release')
        slot, = self.planned(); self.at(slot); self.steps.screen_problem = 'start screen: stopped'
        self.assertEqual('stopped', self.runner(rack_lock=lock).run_due()['outcome'])
        self.assertEqual(['take', 'release'], events)


class PhoneReadyTests(unittest.TestCase):
    def status(self, **receiver):
        r = {'deviceid': 'dev-18', 'name': 'iMouse2-18', 'live': True, 'receiver_state': 'mirroring',
             'frame_delivery': 'flowing', 'frame_pipe_connected': True, 'frame_age_ms': 62.0, **receiver}
        return {'build_identity': {'sha256': 'k' * 64}, 'receivers': [r]}

    def phones(self, **flags): return {'phones': [{'id': 'dev-18', 'owned': False, 'active': False, 'stopped': False,
                                                   'releasing': False, 'release_failed': False, **flags}]}

    def test_ready_when_mirroring_fresh_and_idle(self):
        self.assertIsNone(runner.phone_ready(self.status(), self.phones(), PREP))

    def test_a_still_screen_is_ready(self):
        """No frames while nothing changes on screen (4 Nov, A18 on Home: 'quiet', 55 s old)."""
        self.assertIsNone(runner.phone_ready(self.status(frame_delivery='quiet', frame_age_ms=55000.0), self.phones(), PREP))

    def test_reasons(self):
        cases = [(self.status(frame_age_ms=4000), self.phones(), 'stalled'),
                 (self.status(receiver_state='waiting', live=False), self.phones(), 'not mirroring'),
                 (self.status(frame_delivery='stalled'), self.phones(), 'not arriving'),
                 (self.status(frame_delivery='quiet', frame_pipe_connected=False), self.phones(), 'not arriving'),
                 (self.status(), self.phones(owned=True), 'not idle (owned)'),
                 (self.status(), {'phones': []}, 'no input board'),
                 ({**self.status(), 'build_identity': {'sha256': 'z'}}, self.phones(), 'kernel is not'),
                 (self.status(name='iMouse2-20'), self.phones(), 'does not map')]
        for status, phones, expected in cases:
            with self.subTest(expected): self.assertIn(expected, runner.phone_ready(status, phones, PREP))

    def test_start_screen_summary_decides_not_its_exit_code(self):
        ok = '{"state": "at_start", "error": null}'
        self.assertIsNone(runner.start_screen_problem(0, ok))
        self.assertIsNone(runner.start_screen_problem(0, '{"state": "already_at_start", "error": null}'))
        stopped = '{"state": "stopped", "error": "InspectionStopped: No fresh frame matching the recognized reel_editor screen"}'
        self.assertIn('reel_editor', runner.start_screen_problem(0, stopped))
        self.assertIn('no summary', runner.start_screen_problem(0, 'Traceback'))
        self.assertIn('start screen', runner.start_screen_problem(1, ok))

    def test_outcome_of(self):
        self.assertEqual('verified', runner.outcome_of(run())[0])
        self.assertEqual(('stopped', 'review_required: OCR'), runner.outcome_of(run('review_required', False, error='OCR')))


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name); self.folder = root / 'farm'; self.queue = root / 'state/queue.json'
        self.window = self.folder / 'windows/reel-slot18'; self.window.mkdir(parents=True)
        prep = dict(PREP, config=str(self.window / 'creation-config.json'), testToken='abc123def456', downloadName='imouse-reel-x',
                    backendSourceHash='h' * 64, caption='Fresh reel acceptance')
        (self.window / 'preparation.json').write_text(json.dumps(prep), encoding='utf-8')
        (self.window / 'creation-config.json').write_text('{}', encoding='utf-8')
        self.steps = runner.WindowSteps(root / 'state/windows', folder=self.folder)

    def test_stage_moves_the_fresh_window_and_queues_its_exact_package(self):
        q = ReviewQueue(self.queue)
        pkg = runner.stage_window(self.steps, q, 'reel-slot18', 'acct-a18')
        self.assertEqual(('reel18-abc123', 'pending', 'instagram', 'ig_reel'), (pkg['id'], pkg['state'], pkg['platform'], pkg['format']))
        self.assertEqual((SHA, 18, True), (pkg['source']['manifestSha256'], pkg['source']['slot'], pkg['source']['testPackage']))
        self.assertFalse(self.window.exists()); self.assertTrue((self.steps.staged('reel18-abc123') / 'preparation.json').exists())
        # Restore puts it back at the exact path its config names; archive moves it aside.
        self.steps.restore('reel18-abc123', 'reel-slot18'); self.assertTrue((self.window / 'creation-config.json').exists())
        self.assertEqual('reel-slot18-sched-reel18-abc123-1', self.steps.archive('reel18-abc123', 'reel-slot18').name)

    def test_a_started_window_is_refused_and_left_alone(self):
        (self.window / 'processes.json').write_text('{}', encoding='utf-8')
        with self.assertRaises(ValueError): runner.stage_window(self.steps, ReviewQueue(self.queue), 'reel-slot18', 'acct-a18')
        self.assertTrue(self.window.exists())

    def test_handle_shaped_account_is_refused_before_anything_moves(self):
        with self.assertRaises(ValueError): runner.stage_window(self.steps, ReviewQueue(self.queue), 'reel-slot18', 'some.handle')
        self.assertTrue(self.window.exists())

    def test_cli_stage_then_review(self):
        out = io.StringIO()
        with mock.patch.object(runner, 'FOLDER', self.folder), \
             mock.patch.object(runner.WindowSteps.__init__, '__defaults__', (self.folder, runner.KERNEL, 'python', None)):
            code = cli.main(['--queue', str(self.queue), 'stage-window', 'reel-slot18', '--account', 'acct-a18'], out=out)
        self.assertEqual(0, code); self.assertIn('pkg reel18-abc123: pending', out.getvalue())
        out = io.StringIO(); cli.main(['--queue', str(self.queue), 'review'], out=out)
        self.assertIn('Fresh reel acceptance', out.getvalue())


class ToolProcessTests(unittest.TestCase):
    def test_a_child_left_running_with_the_tools_handles_does_not_hang_the_step(self):
        """Start-Window starts a backend that outlives it (4 Nov: the runner waited on its pipe for 25 min)."""
        import subprocess, sys, time
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            steps = runner.WindowSteps(Path(temp) / 'staging', folder=Path(temp), log_dir=Path(temp) / 'runs')
            script = ('import subprocess,sys; c=subprocess.Popen([sys.executable,"-c","import time; time.sleep(20)"]); '
                      'print("started", c.pid); print("ready line")')
            began = time.monotonic()
            code, tail = steps._run('pkg', 'start-window', [sys.executable, '-c', script], 15)
            self.assertLess(time.monotonic() - began, 10)
            self.assertEqual((0, 'ready line'), (code, tail))
            started = (Path(temp) / 'runs/pkg-start-window.txt').read_text().split()
            subprocess.run(['taskkill', '/F', '/PID', started[started.index('started') + 1]], capture_output=True)
            time.sleep(0.5)

    def test_a_long_summary_line_comes_back_whole(self):
        """The start screen's JSON summary runs past 300 characters (22:48 slot, A18: cut, then unreadable)."""
        import sys
        summary = json.dumps({'state': 'at_start', 'error': None, 'commands': [['open-app-search', 'answered']] * 40})
        with tempfile.TemporaryDirectory() as temp:
            steps = runner.WindowSteps(Path(temp) / 'staging', folder=Path(temp), log_dir=Path(temp) / 'runs')
            code, tail = steps._run('pkg', 'start-screen', [sys.executable, '-c', f'print({summary!r})'], 15)
        self.assertGreater(len(tail), 300)
        self.assertIsNone(runner.start_screen_problem(code, tail))

    def test_timeout_is_reported_not_waited_out(self):
        import sys, time
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            steps = runner.WindowSteps(Path(temp) / 'staging', folder=Path(temp), log_dir=Path(temp) / 'runs')
            code, tail = steps._run('pkg', 'run-window', [sys.executable, '-c', 'import time; time.sleep(3)'], 1)
            time.sleep(2.5)    # Let the left-running tool end before the folder is removed.
            self.assertEqual((None, 'run-window did not end within 1 s'), (code, tail))


class CliRunTests(unittest.TestCase):
    def test_run_with_nothing_due_says_so_and_holds_the_phone_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            queue = Path(temp) / 'queue.json'; out = io.StringIO()
            with runner.phone_lock(Path(temp) / 'phone-18.lock'):
                code = cli.main(['--queue', str(queue), 'run', '--phone', '18'], out=io.StringIO())
                self.assertEqual(2, code)    # A second runner for the same phone is refused.
            self.assertEqual(0, cli.main(['--queue', str(queue), 'run', '--phone', '18'], out=out))
            self.assertIn('No slot was due on phone 18', out.getvalue())


if __name__ == '__main__':
    unittest.main()
