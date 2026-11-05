"""Rack-wide run lock: one holder at a time, the holder named for whoever waits, released on exit."""
from pathlib import Path
import tempfile
import unittest

from farm_rack_lock import RackBusy, current_holder, rack_run_lock


class RackLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state' / 'rack-run.lock'

    def test_one_holder_at_a_time_and_released_after(self):
        with rack_run_lock('slot runner, phone 18', self.path):
            self.assertEqual('slot runner, phone 18', current_holder(self.path)['holder'])
            with self.assertRaises(RackBusy) as busy:
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
            with self.assertRaises(RackBusy):
                with rack_run_lock('second', self.path, wait=3, poll=1, sleep=sleep, clock=lambda: now[0]): pass
        self.assertEqual([1, 1, 1], slept)


if __name__ == '__main__':
    unittest.main()
