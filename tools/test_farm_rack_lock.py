"""Rack-wide run lock: one holder at a time, the holder named for whoever waits, released on exit."""
from contextlib import contextmanager, redirect_stderr
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import farm_rack_lock as lock
from farm_rack_lock import RackBusy, current_holder, hold_rack, rack_run_lock


@contextmanager
def stranger():
    """As another process would be: without the holder's token in its environment."""
    token = os.environ.pop(lock.TOKEN_ENV, None)
    try: yield
    finally:
        if token: os.environ[lock.TOKEN_ENV] = token


class RackLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state' / 'rack-run.lock'

    def test_one_holder_at_a_time_and_released_after(self):
        with rack_run_lock('slot runner, phone 18', self.path):
            self.assertEqual('slot runner, phone 18', current_holder(self.path)['holder'])
            with stranger(), self.assertRaises(RackBusy) as busy:
                with rack_run_lock('a lane run', self.path): self.fail('Two holders.')
            self.assertEqual('slot runner, phone 18', busy.exception.holder)
        self.assertIsNone(current_holder(self.path))
        with rack_run_lock('a lane run', self.path): pass

    def test_released_when_the_run_fails(self):
        with self.assertRaises(RuntimeError):
            with rack_run_lock('first', self.path): raise RuntimeError('run stopped')
        with rack_run_lock('second', self.path): self.assertEqual('second', current_holder(self.path)['holder'])

    def test_waits_up_to_its_budget(self):
        now, slept = [0.0], []
        def sleep(seconds): slept.append(seconds); now[0] += seconds
        with rack_run_lock('first', self.path):
            with stranger(), self.assertRaises(RackBusy):
                with rack_run_lock('second', self.path, wait=3, poll=1, sleep=sleep, clock=lambda: now[0]): pass
        self.assertEqual([1, 1, 1], slept)


CHILD = """
import sys
sys.path.insert(0, {tools!r})
from farm_rack_lock import RackBusy, rack_run_lock
try:
    with rack_run_lock('child', {path!r}): print('ran')
except RackBusy as busy: print('busy', busy.holder)
"""


class AcrossProcessesTests(unittest.TestCase):
    """The holder's child tools join its hold; any other process waits or is refused; a stale token counts for nothing."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'rack-run.lock'

    def child(self, env=None):
        script = CHILD.format(tools=str(Path(__file__).resolve().parent), path=str(self.path))
        environ = {k: v for k, v in os.environ.items() if k != lock.TOKEN_ENV}
        environ.update(env or {})
        return subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, env=environ, timeout=30).stdout.strip()

    def test_a_child_of_the_holder_joins_and_a_stranger_is_refused(self):
        with rack_run_lock('slot runner', self.path):
            self.assertEqual('ran', self.child({lock.TOKEN_ENV: os.environ[lock.TOKEN_ENV]}))
            self.assertEqual('busy slot runner', self.child())
            self.assertEqual('busy slot runner', self.child({lock.TOKEN_ENV: 'some-old-token'}))
            self.assertEqual('slot runner', current_holder(self.path)['holder'])   # The joining child left the hold alone.
        self.assertNotIn(lock.TOKEN_ENV, os.environ)

    def test_a_token_from_a_finished_holder_counts_for_nothing(self):
        with rack_run_lock('first', self.path): token = os.environ[lock.TOKEN_ENV]
        self.assertEqual('ran', self.child({lock.TOKEN_ENV: token}))    # It takes the free lock normally.
        with rack_run_lock('second', self.path):
            self.assertEqual('busy second', self.child({lock.TOKEN_ENV: token}))

    def test_a_dead_holder_releases_the_rack(self):
        script = (f'import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n'
                  f'import os\nfrom farm_rack_lock import rack_run_lock\n'
                  f'lock = rack_run_lock("dying", {str(self.path)!r}); lock.__enter__(); os._exit(0)\n')
        subprocess.run([sys.executable, '-c', script], timeout=30)
        self.assertEqual('ran', self.child())


class HoldRackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'rack-run.lock'

    def test_runs_the_body_and_releases(self):
        ran = []
        with hold_rack('run_window', self.path): ran.append(current_holder(self.path)['holder'])
        self.assertEqual(['run_window'], ran); self.assertIsNone(current_holder(self.path))

    def test_a_failing_body_keeps_its_own_error_and_releases(self):
        with self.assertRaises(ValueError):
            with hold_rack('run_window', self.path): raise ValueError('the run stopped')
        with self.assertRaises(SystemExit) as stop:
            with hold_rack('run_window', self.path): raise SystemExit('Not eligible')
        self.assertEqual('Not eligible', stop.exception.code)
        self.assertIsNone(current_holder(self.path))

    def test_a_busy_rack_waits_says_so_once_then_exits_before_the_body(self):
        now, slept = [0.0], []
        def sleep(seconds): slept.append(seconds); now[0] += seconds
        err = io.StringIO()
        with rack_run_lock('fleet run', self.path), redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            with stranger():
                with hold_rack('run_window', self.path, wait=6, poll=2, sleep=sleep, clock=lambda: now[0]): self.fail('Ran while the rack was held.')
        self.assertEqual([2, 2, 2], slept)
        self.assertEqual(1, err.getvalue().count('Waiting for the rack: fleet run'))
        self.assertIn('fleet run', stop.exception.code); self.assertIn('Nothing was sent', stop.exception.code)

    def test_every_hand_run_tool_holds_the_rack_from_the_shared_path(self):
        import farm_paths
        self.assertEqual(farm_paths.MAIN / 'output' / 'farm-state' / 'rack-run.lock', farm_paths.RUN_LOCK)   # Main folder: every lane shares it.
        root = Path(__file__).resolve().parents[1]; folder = root / 'rack'
        for path in (folder / 'run_window.py', folder / 'verify_window.py', folder / 'relaunch_check.py', root / 'tools/farm_start_screen.py',
                     root / 'tools/farm_fleet_survey.py', root / 'tools/farm_photos_cleanup.py'):
            with self.subTest(path.name): self.assertIn('with hold_rack(', path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
