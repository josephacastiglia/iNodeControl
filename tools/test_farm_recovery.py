"""Offline recovery admission, immutable evidence, process restart and guards."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import uuid
from unittest.mock import patch

from farm_draft_creation import CreationWorkflow
from farm_draft_recovery import RecoveryRuns, RecoveryWorkflow
from farm_drafts import DraftConflict
from farm_draft_workflow import atomic_json
from farm_jobs import FarmJobs
from farm_carousel_inspection import InspectionStopped
from imouse_social_automation import KernelSafetyError
import test_farm_creation as fixtures


class FixtureRecovery(RecoveryRuns):
    executions = 0
    wait = False
    entered = None
    def execute(self, folder, assets, caption, package_hash, cancelled):
        self.executions += 1
        spec, _, _ = self.row(folder.name)
        self.package_for_request(spec)
        _, _, proof = self.source(spec['creation_id'])
        result = dict(packageSha256=package_hash, mode='inspect_saved_draft', inspectionOnly=True,
            source='offline_protocol_fixture', state='review_required', savedDraftVerified=False,
            cleanup='confirmed', evidenceExport='confirmed', observations=[], sourceCreation=proof,
            actions=[dict(label='inspect-open-draft', state='outcome_unknown')])
        atomic_json(folder/'record.json', result)
        if self.entered: self.entered.set()
        if self.wait:
            if not cancelled.wait(4): raise TimeoutError('Fixture was not cancelled.')
        return result


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CreationTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.root, self.jobs, self.creations = f.root, f.jobs, f.service
        self.origin = f.spec
        self.origin_path = self.creations.folder/self.origin['id']/'record.json'
        def source(folder, assets, caption, package_hash, cancelled):
            result = dict(packageSha256=package_hash, mode='create_new_draft', source='candidate_phone_workflow',
                account='xs.halle.xo', state='review_required', cleanup='confirmed', evidenceExport='confirmed',
                savedDraftVerified=False, observations=[], error='Fixture: Save answer lost.',
                commands=[dict(purpose='prepared-save-once', state='outcome_unknown')],
                actions=[dict(label='prepared-save-once', state='outcome_unknown')])
            atomic_json(folder/'record.json', result); return result
        self.creations.execute = source
        self.creations.start(self.origin)
        self.assertTrue(self.jobs._jobs[self.origin['id']].done.wait(4))
        self.service = FixtureRecovery(self.root/'recoveries', f.drafts, self.jobs, self.creations)
        proof = self.service.eligibility(self.origin['id'])['sourceProof']
        self.spec = dict(id=str(uuid.uuid4()), draft_id=self.origin['draft_id'], revision=self.origin['revision'],
            store_id=self.service.store_id, creation_id=self.origin['id'],
            creation_store_id=proof['creationStoreId'], creation_record_sha256=proof['creationRecordSha256'])

    def finish(self, spec=None):
        spec = spec or self.spec
        self.assertTrue(self.jobs._jobs[spec['id']].done.wait(4))
        return self.service.get(spec['id'])

    def test_unknown_save_can_be_inspected_but_original_is_never_relabelled_or_replayed(self):
        before = self.origin_path.read_bytes()
        self.service.start(self.spec); result = self.finish()
        self.assertFalse(result['savedDraftVerified']); self.assertTrue(result['inspectionOnly'])
        self.assertFalse(result['automaticResume']); self.assertFalse(result['appRestartVerified'])
        self.assertFalse(result['originalOutcomeChanged'])
        self.assertEqual(before, self.origin_path.read_bytes())
        self.assertEqual('outcome_unknown', self.creations.get(self.origin['id'])['workflow']['commands'][0]['state'])
        with self.assertRaises(DraftConflict): self.creations.start(dict(self.origin, id=str(uuid.uuid4())))

    def test_duplicate_and_restarted_inspection_retrieve_same_request_without_input(self):
        self.service.start(self.spec); result = self.finish()
        self.assertEqual(result, self.service.start(self.spec)); self.assertEqual(1, self.service.executions)
        other = FixtureRecovery(self.service.folder, self.fixture.drafts, self.jobs, self.creations)
        self.assertEqual(result, other.start(self.spec)); self.assertEqual(0, other.executions)

    def test_original_package_survives_local_editor_changes_and_deletion(self):
        expected = self.creations.row(self.origin['id'])[1]
        self.fixture.drafts.save(self.origin['draft_id'], self.origin['revision'], 'Edited locally', 'Other text', self.fixture.draft['slideIds'])
        self.assertEqual(expected, self.service.package_for_request(self.spec))
        self.service.start(self.spec); result = self.finish()
        self.assertTrue(result['draftChangedSinceRun']); self.assertEqual(hashlib.sha256(expected).hexdigest(), result['packageSha256'])

    def test_disabled_recovery_never_starts_or_constructs_a_transport(self):
        self.creations.config = None
        service = RecoveryRuns(self.root/'disabled-recovery', self.fixture.drafts, self.jobs, self.creations)
        self.assertFalse(service.eligibility(self.origin['id'])['eligible'])
        with patch('farm_draft_recovery.StepKernel', side_effect=AssertionError('No network')):
            with self.assertRaises(KernelSafetyError): service.start(dict(self.spec, store_id=service.store_id))

    def test_other_source_store_hash_revision_or_device_is_refused_before_worker(self):
        for changes in ({'creation_store_id': str(uuid.uuid4())}, {'creation_record_sha256': 'b'*64},
                        {'revision': self.origin['revision']+1}, {'draft_id': str(uuid.uuid4())},
                        {'device': 'C241'}, {'actions': ['save']}, {'api': 'http://127.0.0.1:9913/api'}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, DraftConflict)):
                self.service.start(dict(self.spec, **changes))
        self.assertEqual(0, self.service.executions)

    def test_active_source_or_no_started_instagram_save_cannot_be_inspected(self):
        source = self.creations.get(self.origin['id'])
        changes = [dict(terminal=False), dict(workflow=dict(source['workflow'], commands=[])),
            dict(workflow=dict(source['workflow'], commands=[dict(purpose='save-photo-1', state='outcome_unknown')])),
            dict(workflow=dict(source['workflow'], commands=[dict(purpose='prepared-save-once', state='not_sent')])),
            dict(workflow=dict(source['workflow'], source='offline_protocol_fixture')),
            dict(workflow=dict(source['workflow'], account='different.account'))]
        for change in changes:
            with self.subTest(change=change), patch.object(self.creations, 'get', return_value=dict(source, **change)):
                self.assertFalse(self.service.eligibility(self.origin['id'])['eligible'])
                with self.assertRaises(DraftConflict): self.service.start(self.spec)

    def test_modified_original_record_and_saved_inspection_package_fail_closed(self):
        before = self.origin_path.read_bytes(); value = json.loads(before); value['error'] = 'changed'
        atomic_json(self.origin_path, value)
        with self.assertRaisesRegex(ValueError, 'journal'): self.service.start(self.spec)
        self.origin_path.write_bytes(before)
        self.service.start(self.spec); self.finish()
        with self.service.connect() as db: db.execute('UPDATE runs SET package=?', (b'broken',))
        with self.assertRaisesRegex(ValueError, 'package'): self.service.get(self.spec['id'])

    def test_stop_and_lost_status_never_repeat_inspection_or_original_save(self):
        self.service.wait = True; self.service.entered = threading.Event()
        before = self.origin_path.read_bytes()
        self.service.start(self.spec); self.assertTrue(self.service.entered.wait(2))
        self.service.cancel(self.spec['id']); result = self.finish()
        self.assertEqual('cancelled', result['jobStatus']); self.assertFalse(result['savedDraftVerified'])
        self.service.start(self.spec); self.assertEqual(1, self.service.executions)
        self.assertEqual(before, self.origin_path.read_bytes())

    def test_cancel_before_admission_does_not_start_an_inspector(self):
        self.service.cancel(self.spec['id']); value = self.service.start(self.spec)
        self.assertTrue(value['terminal']); self.assertEqual('cancelled', value['jobStatus'])
        self.assertEqual(0, self.service.executions)

    def test_inspection_action_surface_cannot_save_type_or_click_through_prompts(self):
        workflow = object.__new__(RecoveryWorkflow)
        with patch('farm_draft_recovery.Workflow.action') as action:
            for label, kind in [('save', 'save_draft'), ('inspect-details', 'save_draft'),
                                ('paste', 'paste'), ('inspect-open-draft', 'leave_picker')]:
                with self.subTest(label=label), self.assertRaises(InspectionStopped):
                    workflow.action(label, kind, 'save_prompt')
            action.assert_not_called()
            workflow.action('inspect-open-draft', 'open_test_draft', 'library')
            action.assert_called_once()

    def test_hard_process_exit_is_latched_even_while_a_different_job_runs(self):
        code = '''
import os,sys,threading
from pathlib import Path
from farm_jobs import FarmJobs
jobs=FarmJobs(journal_path=Path(sys.argv[1]))
def die(cancel):os._exit(23)
jobs.submit(sys.argv[2], 'crash-fixture', {}, die)
threading.Event().wait(3)
'''
        key = str(uuid.uuid4()); path = self.root/'crash-jobs.db'
        child = subprocess.run([sys.executable, '-c', code, str(path), key], cwd=Path(__file__).parent,
            capture_output=True, timeout=8, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(23, child.returncode, child.stderr)
        registry = FarmJobs(journal_path=path); self.addCleanup(registry.close)
        self.assertEqual('interrupted', registry.get(key)['status'])
        entered = threading.Event(); next_id = str(uuid.uuid4())
        def wait(cancel): entered.set(); cancel.wait(3); return {}
        registry.submit(next_id, 'other-job', {}, wait); self.assertTrue(entered.wait(1))
        result = registry.get(key)
        self.assertTrue(result['terminal']); self.assertEqual('interrupted', result['status'])
        calls = []
        registry.submit(key, 'crash-fixture', {}, lambda cancel: calls.append('replayed'))
        self.assertEqual([], calls)
        registry.cancel(next_id)

    def test_creation_save_refresh_needs_complete_caption_history_and_later_exact_details(self):
        workflow = object.__new__(CreationWorkflow)
        labels = ['prepared-slide-2', 'prepared-slide-3', 'prepared-details',
            'focus-empty-caption', 'open-paste-menu', 'paste-exact-caption', 'close-caption-editor',
            'prepared-back', 'prepared-exit-sheet']
        prior = [dict(label=label, state='answered', observationId=label) for label in labels]
        workflow.record = dict(observations=[dict(observationId='close-caption-editor'),
            dict(state='observed', role='details', screenCheck=dict(status='exact_visible_lines'))])
        self.assertTrue(workflow.save_history_ready('prepared', prior))
        for missing in range(len(labels)):
            changed = copy.deepcopy(prior); changed.pop(missing)
            with self.subTest(missing=missing): self.assertFalse(workflow.save_history_ready('prepared', changed))
        self.assertFalse(workflow.save_history_ready('reopened', prior))
        workflow.record['observations'].reverse()
        self.assertFalse(workflow.save_history_ready('prepared', prior))


if __name__ == '__main__': unittest.main()
