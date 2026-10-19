"""Real observer/guards with retained C24C frames and a simulated HID kernel.

No socket, desktop or phone access. This replays known layouts, not fresh-phone
or app-restart acceptance. Every input boundary is adversarially interrupted.
"""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(ROOT/'analysis/farm-live-final-20261018'))
import test_validate_workflow as retained
import farm_test_network  # Refuse every real socket in this test process.
from farm_draft_creation import CreationWorkflow
from farm_draft_recovery import RecoveryWorkflow
from farm_draft_workflow import Workflow, references
from farm_observations import ObservationStore


class RetainedRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retained.WorkflowTests.setUpClass()
        cls.f = retained.WorkflowTests

    def fixture(self, scenario='normal', creation=False):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        kernel = retained.FixtureKernel(self.f.templates, self.f.texts, scenario)
        store = ObservationStore(folder/'observations.sqlite3', ocr=retained.FixtureOcr(kernel),
            clock=kernel.clock, monotonic=kernel.clock)
        kind = CreationWorkflow if creation else RecoveryWorkflow
        options = dict(transfer_url='http://192.168.50.2:9917/fixture', transfer_title='Carousel draft') if creation else {}
        flow = kind(folder, kernel, store, self.f.assets, self.f.caption, references(), 'a'*64, 'fixture-uid',
            account='xs.halle.xo', package_hash='b'*64, monotonic=kernel.clock, pause=kernel.pause, **options)
        kernel.cancelled = flow.cancelled
        return flow, kernel

    def semantic(self, kernel):
        return [row for row in kernel.calls if isinstance(row, tuple) and row[0] in ('/mouse/click', '/mouse/swipe')]

    def test_repeated_inspections_check_all_slides_caption_and_never_save_or_type(self):
        for repeat in range(3):
            with self.subTest(repeat=repeat):
                flow, kernel = self.fixture(); result = flow.run()
                self.assertEqual('validation_passed', result['state'], result.get('error'))
                self.assertEqual(7, len(result['actions'])); self.assertEqual(7, len(self.semantic(kernel)))
                self.assertEqual(0, kernel.saves); self.assertEqual('details', kernel.screen)
                self.assertEqual('confirmed', result['cleanup']); self.assertFalse(kernel.owned)
                self.assertTrue(result['inspectionOnly']); self.assertFalse(result['appRestartVerified'])
                self.assertEqual('offline_protocol_fixture', result['source'])
                self.assertTrue(any(e['role'] == 'details' and e['screenCheck']['status'] == 'exact_visible_lines'
                                    for e in result['observations']))
                self.assertTrue(all(c['fun'] in ('/mouse/reset', '/mouse/move', '/mouse/swipe', '/mouse/click') for c in result['commands']))

    def test_lost_answer_at_each_of_seven_actions_stops_without_replay(self):
        for boundary in range(1, 8):
            with self.subTest(boundary=boundary):
                flow, kernel = self.fixture(); original = kernel.send
                def send(phone, token, fun, **data):
                    value = original(phone, token, fun, **data)
                    if len(self.semantic(kernel)) == boundary and fun in ('/mouse/click', '/mouse/swipe'):
                        raise TimeoutError('Fixture action happened; answer lost.')
                    return value
                with patch.object(kernel, 'send', send): result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertFalse(result['savedDraftVerified'])
                self.assertEqual(boundary, len(self.semantic(kernel)))
                self.assertEqual('outcome_unknown', result['actions'][-1]['state'])
                self.assertEqual('release', kernel.calls[-1]); self.assertEqual(0, kernel.saves)

    def test_stop_at_each_last_dispatch_journal_sends_no_target_action(self):
        for boundary, label in enumerate(RecoveryWorkflow.ACTIONS, 1):
            with self.subTest(label=label):
                flow, kernel = self.fixture(); original = flow.save
                def save():
                    original()
                    if flow.record['commands'] and flow.record['commands'][-1]['purpose'] == label and flow.record['commands'][-1]['state'] == 'outcome_unknown':
                        flow.cancelled.set()
                with patch.object(flow, 'save', save): result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertEqual(boundary-1, len(self.semantic(kernel)))
                self.assertEqual('not_sent', result['actions'][-1]['state'])
                self.assertEqual('confirmed', result['cleanup']); self.assertEqual(0, kernel.saves)

    def test_disconnect_and_receiver_restart_at_every_action_stop_before_further_input(self):
        for failure in ('disconnect', 'receiver_restart'):
            for boundary in range(1, 8):
                with self.subTest(failure=failure, boundary=boundary):
                    flow, kernel = self.fixture(); original = kernel.send; receiver = kernel.receiver
                    changed = [False]
                    def send(phone, token, fun, **data):
                        value = original(phone, token, fun, **data)
                        if len(self.semantic(kernel)) == boundary and fun in ('/mouse/click', '/mouse/swipe'):
                            changed[0] = True
                            if failure == 'receiver_restart': kernel.session = 'different-stream'
                        return value
                    def current_receiver():
                        value = receiver()
                        if changed[0] and failure == 'disconnect': value['live'] = False
                        return value
                    with patch.object(kernel, 'send', send), patch.object(kernel, 'receiver', current_receiver): result = flow.run()
                    self.assertEqual('review_required', result['state'], result.get('error'))
                    self.assertEqual(boundary, len(self.semantic(kernel))); self.assertEqual(0, kernel.saves)
                    self.assertEqual('release', kernel.calls[-1]); self.assertFalse(result['savedDraftVerified'])

    def test_wrong_account_caption_or_stale_delivery_never_pass_or_save(self):
        for scenario in ('wrong_account', 'wrong_caption', 'stale_frame', 'failed_ocr'):
            with self.subTest(scenario=scenario):
                flow, kernel = self.fixture(scenario); result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertFalse(result['savedDraftVerified'])
                self.assertEqual(0, kernel.saves)

    def test_app_returning_to_profile_mid_inspection_is_not_treated_as_restart_success(self):
        flow, kernel = self.fixture(); original = kernel.send
        def close_app(phone, token, fun, **data):
            value = original(phone, token, fun, **data)
            if len(self.semantic(kernel)) == 4: kernel.screen = 'profile'
            return value
        with patch.object(kernel, 'send', close_app): result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(4, len(self.semantic(kernel)))
        self.assertFalse(result['appRestartVerified']); self.assertEqual(0, kernel.saves)

    def prepare_creation_prompt(self, scenario='normal'):
        flow, kernel = self.fixture(scenario, creation=True)
        flow.identity = flow.runtime(); flow.record['cleanup'] = 'unconfirmed'; flow.owned.acquire()
        flow.observe('profile')
        kernel.screen = 'details'; kernel.index = 3
        close, _ = flow.observe('details')
        flow.observe('details')  # Independent exact Details after the close basis.
        labels = ['prepared-slide-2', 'prepared-slide-3', 'prepared-details', 'focus-empty-caption',
            'open-paste-menu', 'paste-exact-caption', 'close-caption-editor', 'prepared-back', 'prepared-exit-sheet']
        flow.record['actions'] = [dict(label=label, state='answered', observationId=close['id']) for label in labels]
        kernel.screen = 'save_prompt'
        return flow, kernel

    def expire_save(self, flow, kernel, count=1):
        original = flow.save; aged = set()
        def save():
            original()
            if flow.record['commands']:
                item = flow.record['commands'][-1]
                if item['purpose'] == 'prepared-save-once' and item['state'] == 'outcome_unknown' and id(item) not in aged and len(aged) < count:
                    aged.add(id(item)); kernel.pause(1.6)
        return patch.object(flow, 'save', save)

    def test_creation_save_local_expiry_uses_new_exact_prompt_and_sends_save_only_once(self):
        flow, kernel = self.prepare_creation_prompt()
        try:
            with self.expire_save(flow, kernel): flow.action('prepared-save-once', 'save_draft', 'save_prompt')
            self.assertEqual(1, kernel.saves)
            self.assertEqual(['not_sent', 'answered'], [c['state'] for c in flow.record['commands'] if c['purpose'] == 'prepared-save-once'])
            self.assertEqual(1, len(flow.record['promptRecoveries']))
            self.assertFalse(flow.record['promptRecoveries'][0]['phoneActionRetried'])
        finally: flow.finish()

    def test_creation_prompt_refresh_is_bounded_and_lost_save_answer_stays_unknown(self):
        for scenario, repeats in (('normal', 2), ('lost_save', 1)):
            with self.subTest(scenario=scenario):
                flow, kernel = self.prepare_creation_prompt(scenario)
                try:
                    with self.expire_save(flow, kernel, repeats), self.assertRaises(Exception):
                        flow.action('prepared-save-once', 'save_draft', 'save_prompt')
                    self.assertEqual(0 if repeats == 2 else 1, kernel.saves)
                    self.assertEqual('not_sent' if repeats == 2 else 'outcome_unknown', flow.record['actions'][-1]['state'])
                    self.assertEqual(1, len(flow.record['promptRecoveries']))
                finally: flow.finish()


if __name__ == '__main__': unittest.main(verbosity=2)
