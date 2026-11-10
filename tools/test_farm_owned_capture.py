"""OwnedCaptureRun: one phone's lease for one bounded run, authenticated around every frame. No phone."""
import json
import threading
import unittest

from farm_owned_capture import InspectionStopped, OwnedCaptureRun
from farm_phone_identity import LEGACY_C24C

BOARD, TOKEN = LEGACY_C24C.board, 'private-test-token'


class Kernel:
    """The few kernel calls the guard makes. `calls` records every one that could change the phone's lease."""
    phone = LEGACY_C24C

    def __init__(self):
        self.calls, self.owned, self.token, self.generation = [], False, None, 4
        self.active = self.paused = self.live_off = self.renew_refused = False
        self.session, self.receiver_pid, self.restarts = 'a' * 32, 10, 0

    def receiver(self):
        return dict(deviceid='resolved', live=not self.live_off, receiver_pid=self.receiver_pid, receiver_restarts=self.restarts,
                    frame_session=self.session)

    def kernel_status(self): return dict(receivers=[self.receiver()])

    def input_status(self):
        return {'resolved': dict(generation=self.generation, owned=self.owned, active=self.active, stopped=self.paused,
                                 releasing=False, release_failed=False)}

    def preflight_phone(self, board):
        assert board == BOARD
        if self.owned: raise RuntimeError('Another controller owns this phone')
        return dict(resolved_id='resolved', receiver=self.receiver())

    def acquire(self, ids, lease_ms):
        assert ids == [BOARD] and lease_ms == 30000
        self.calls.append('acquire'); self.owned, self.token = True, TOKEN
        return {BOARD: TOKEN}

    def renew_if_needed(self, tokens, min_remaining_ms):
        assert min_remaining_ms > 120000   # Always renews: the token itself is authenticated, not a status field.
        self.calls.append('renew')
        if self.renew_refused or not self.owned or tokens != {BOARD: self.token}: raise RuntimeError('Refused token')
        return True

    def release(self, tokens):
        self.calls.append('release')
        if tokens != {BOARD: self.token}: raise RuntimeError('A new owner cannot be released')
        self.owned, self.token = False, None


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now


class OwnedCaptureRunTests(unittest.TestCase):
    def setUp(self):
        self.kernel, self.clock, self.cancelled = Kernel(), Clock(), threading.Event()
        self.run = OwnedCaptureRun(self.kernel, 'run-1', self.cancelled, self.clock, budget_seconds=90)

    def test_budget_must_be_a_whole_number_of_seconds_up_to_two_minutes(self):
        for budget in (0, 121, 1.5, '90', True):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                OwnedCaptureRun(self.kernel, 'run', self.cancelled, self.clock, budget_seconds=budget)
        OwnedCaptureRun(self.kernel, 'run', self.cancelled, self.clock, budget_seconds=120)

    def test_acquire_takes_one_lease_and_authenticates_it(self):
        self.run.acquire()
        self.assertEqual(['acquire', 'renew'], self.kernel.calls)
        self.assertEqual(({BOARD: TOKEN}, 4, 'resolved'), (self.run.tokens, self.run.generation, self.run.resolved))
        self.run.check(self.kernel); self.assertEqual(['acquire', 'renew', 'renew'], self.kernel.calls)

    def test_a_foreign_owner_is_never_acquired_or_released(self):
        self.kernel.owned, self.kernel.token = True, 'other-controller'
        with self.assertRaises(RuntimeError): self.run.acquire()
        self.run.release()
        self.assertEqual([], self.kernel.calls); self.assertTrue(self.kernel.owned)

    def test_an_unsettled_phone_after_acquire_stops(self):
        for flag in ('active', 'paused'):
            kernel = Kernel(); setattr(kernel, flag, True)
            run = OwnedCaptureRun(kernel, 'run', self.cancelled, self.clock)
            with self.subTest(flag=flag), self.assertRaisesRegex(InspectionStopped, 'not settled'): run.acquire()
            run.release(); self.assertEqual(['acquire', 'release'], kernel.calls)   # Its own lease is still given back.

    def test_check_stops_on_cancel_and_on_an_expired_budget_but_release_still_runs(self):
        self.run.acquire()
        self.clock.now += 90
        with self.assertRaisesRegex(InspectionStopped, '90-second budget'): self.run.check(self.kernel)
        self.clock.now -= 90; self.cancelled.set()
        with self.assertRaisesRegex(InspectionStopped, 'cancelled'): self.run.check(self.kernel)
        sent = list(self.kernel.calls)
        self.run.release()
        self.assertEqual(sent + ['release'], self.kernel.calls); self.assertFalse(self.kernel.owned); self.assertEqual({}, self.run.tokens)
        self.run.release(); self.assertEqual(sent + ['release'], self.kernel.calls)   # Nothing left to release.

    def test_check_needs_this_run_and_its_own_kernel(self):
        with self.assertRaisesRegex(InspectionStopped, 'no matching owned run'): self.run.check(self.kernel)   # Nothing acquired yet.
        self.run.acquire()
        with self.assertRaisesRegex(InspectionStopped, 'no matching owned run'): self.run.check(Kernel())

    def test_a_refused_token_or_a_replaced_lease_stops(self):
        self.run.acquire(); self.kernel.renew_refused = True
        with self.assertRaisesRegex(InspectionStopped, 'could not be authenticated'): self.run.check(self.kernel)
        self.kernel.renew_refused = False; self.kernel.generation += 1   # Another controller took and returned the phone.
        with self.assertRaisesRegex(InspectionStopped, 'ownership changed'): self.run.check(self.kernel)

    def test_a_paused_phone_or_a_changed_stream_stops(self):
        for change in (dict(paused=True), dict(active=True), dict(live_off=True), dict(session='b' * 32), dict(receiver_pid=11),
                       dict(restarts=1)):
            kernel = Kernel(); run = OwnedCaptureRun(kernel, 'run', self.cancelled, self.clock); run.acquire()
            for name, value in change.items(): setattr(kernel, name, value)
            with self.subTest(change=change), self.assertRaises(InspectionStopped): run.check(kernel)

    def test_accepts_only_settled_states_of_its_own_generation(self):
        self.run.acquire()
        mine = self.kernel.input_status()['resolved']
        self.assertTrue(self.run.accepts(mine, dict(mine)))
        self.assertFalse(self.run.accepts()); self.assertFalse(self.run.accepts(mine, None))
        self.assertFalse(self.run.accepts(mine, dict(mine, generation=5)))
        self.assertFalse(self.run.accepts(dict(mine, owned=False)))
        for flag in ('active', 'stopped', 'releasing', 'release_failed'):
            self.assertFalse(self.run.accepts(dict(mine, **{flag: True})), flag)

    def test_evidence_names_the_run_and_never_the_token(self):
        self.run.acquire()
        evidence = self.run.evidence()
        self.assertEqual(dict(runId='run-1', generation=4, authenticatedBeforeAndAfter=True, source='owned_capture_guard',
                              continuousPhoneActivityKnown=False), evidence)
        self.assertNotIn(TOKEN, json.dumps(evidence))


if __name__ == '__main__':
    unittest.main()
