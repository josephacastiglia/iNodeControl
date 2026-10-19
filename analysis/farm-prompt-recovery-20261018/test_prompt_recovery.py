"""Offline adversarial runs using retained frames, real observer and simulated HID."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('extracted', ROOT / 'analysis/farm-interface-integration-20261018/test_extracted_workflow.py')
extracted = importlib.util.module_from_spec(spec); spec.loader.exec_module(extracted)
import farm_draft_workflow as product
import farm_test_network  # Every socket denied; fixtures create no transport.


class PromptRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        extracted.ExtractionTests.setUpClass()
        cls.fixtures = extracted.ExtractionTests.fixtures

    fixture = extracted.ExtractionTests.fixture

    def age_save(self, workflow, kernel, *, count=1, boundary='before_transport', after_age=lambda:None):
        original = workflow.save
        aged = []
        def save():
            original()
            commands, actions = workflow.record['commands'], workflow.record['actions']
            if boundary == 'before_transport':
                target = commands[-1] if commands else None
                eligible = target and target['purpose'] == 'prepared-save-once' and target['state'] == 'outcome_unknown'
            else:
                target = actions[-1]['attempts'][-1] if actions and actions[-1]['attempts'] else None
                eligible = (actions and actions[-1]['label'] == 'prepared-save-once'
                            and actions[-1]['state'] == 'outcome_unknown'
                            and (not commands or commands[-1]['purpose'] != 'prepared-save-once'))
            if eligible and id(target) not in aged and len(aged) < count:
                aged.append(id(target)); kernel.pause(1.6); after_age()
        return patch.object(workflow, 'save', save)

    def assert_held_without_save(self, result, kernel):
        self.assertEqual('review_required', result['state'], result.get('error'))
        self.assertFalse(result['savedDraftVerified'])
        self.assertEqual(0, kernel.saves)
        self.assertEqual('confirmed', result['cleanup'])
        self.assertEqual('release', kernel.calls[-1])
        self.assertFalse(kernel.owned)

    def test_expired_at_last_commit_recaptures_same_prompt_and_sends_save_once(self):
        workflow, kernel = self.fixture()
        with self.age_save(workflow, kernel): result = workflow.run()
        self.assertEqual('validation_passed', result['state'], result.get('error'))
        self.assertEqual(2, kernel.saves)  # Once in prepared phase, once after verified reopening.
        self.assertEqual(19, len(result['actions']))
        action = next(a for a in result['actions'] if a['label'] == 'prepared-save-once')
        self.assertEqual(['not_sent','answered'], [a['state'] for a in action['attempts']])
        self.assertNotEqual(*[a['observationId'] for a in action['attempts']])
        commands = [c for c in result['commands'] if c['purpose'] == 'prepared-save-once']
        self.assertEqual(['not_sent','answered'], [c['state'] for c in commands])
        self.assertGreater(commands[0]['decisionChecks'][-1]['frameAgeMs'], 1500)
        self.assertLessEqual(commands[1]['decisionChecks'][-1]['frameAgeMs'], 1500)
        self.assertEqual(1, len(result['promptRecoveries']))
        self.assertFalse(result['promptRecoveries'][0]['phoneActionRetried'])
        self.assertEqual('profile', kernel.screen)

    def test_expiry_before_dispatch_journal_can_get_one_new_decision(self):
        workflow, kernel = self.fixture()
        with self.age_save(workflow, kernel, boundary='before_journal'): result = workflow.run()
        self.assertEqual('validation_passed', result['state'], result.get('error'))
        self.assertEqual(2, kernel.saves)
        command = next(c for c in result['commands'] if c['purpose'] == 'prepared-save-once')
        self.assertEqual('before_dispatch_journal', command['decisionChecks'][-1]['stage'])
        self.assertEqual('not_sent', command['state'])

    def test_persistent_delay_is_bounded_and_never_uses_stale_coordinates(self):
        workflow, kernel = self.fixture()
        with self.age_save(workflow, kernel, count=2): result = workflow.run()
        self.assert_held_without_save(result, kernel)
        self.assertEqual(1, len(result['promptRecoveries']))
        self.assertEqual(['not_sent','not_sent'], [a['state'] for a in result['actions'][-1]['attempts']])

    def test_cancel_during_refusal_prevents_refresh_input(self):
        workflow, kernel = self.fixture()
        with self.age_save(workflow, kernel, after_age=workflow.cancelled.set): result = workflow.run()
        self.assert_held_without_save(result, kernel)
        self.assertEqual('/mouse/move', kernel.calls[-2][0])  # Last capture challenge, not Save.
        self.assertEqual(1, len([o for o in result['observations'] if o['role'] == 'save_prompt']))

    def test_lost_reply_after_fresh_decision_stays_unknown_without_replay(self):
        workflow, kernel = self.fixture('lost_save')
        with self.age_save(workflow, kernel): result = workflow.run()
        self.assertEqual('review_required', result['state'])
        self.assertEqual(1, kernel.saves)
        self.assertEqual(['not_sent','outcome_unknown'], [a['state'] for a in result['actions'][-1]['attempts']])
        self.assertEqual('/mouse/click', kernel.calls[-2][0]); self.assertEqual('release', kernel.calls[-1])

    def test_changed_prompt_background_is_not_clicked_through(self):
        workflow, kernel = self.fixture()
        kernel.templates = dict(kernel.templates)
        def change():
            with Image.open(io.BytesIO(kernel.templates['save_prompt'])) as image:
                ImageDraw.Draw(image).rectangle((80,160,420,640), fill='white')
                output = io.BytesIO(); image.save(output,'PNG')
            kernel.templates['save_prompt'] = output.getvalue()
        with self.age_save(workflow, kernel, after_age=change): result = workflow.run()
        self.assert_held_without_save(result, kernel)
        self.assertIn('Protected prompt content changed', result['error'])

    def test_permission_dialog_over_save_labels_never_gets_save(self):
        workflow, kernel = self.fixture()
        kernel.texts = copy.deepcopy(kernel.texts)
        def interrupt():
            for label, y in (("Don't Allow",400),('Allow',450)):
                kernel.texts['save_prompt']['lines'].append(dict(text=label, words=[dict(text=label,x=180,y=y,width=140,height=20)]))
        with self.age_save(workflow, kernel, after_age=interrupt): result = workflow.run()
        self.assert_held_without_save(result, kernel)
        self.assertIn('Unsupported or interrupted workflow screen', result['error'])

    def test_unexpected_permission_dialog_is_blocked_even_without_age_failure(self):
        workflow, kernel = self.fixture(); kernel.texts = copy.deepcopy(kernel.texts)
        for label, y in (("Don't Allow",400),('Allow',450)):
            kernel.texts['save_prompt']['lines'].append(dict(text=label, words=[dict(text=label,x=180,y=y,width=140,height=20)]))
        result = workflow.run()
        self.assert_held_without_save(result,kernel)
        self.assertEqual([],result['promptRecoveries'])

    def test_stop_at_final_refreshed_dispatch_still_sends_nothing(self):
        workflow,kernel = self.fixture(); save = workflow.save
        def cancel_final():
            save()
            commands=[c for c in workflow.record['commands'] if c['purpose']=='prepared-save-once']
            if len(commands)==2 and commands[-1]['state']=='outcome_unknown': workflow.cancelled.set()
        with patch.object(workflow,'save',cancel_final), self.age_save(workflow,kernel): result=workflow.run()
        self.assert_held_without_save(result,kernel)
        self.assertEqual(['not_sent','not_sent'],[a['state'] for a in result['actions'][-1]['attempts']])

    def test_actual_failed_live_sheet_has_exact_safe_save_target(self):
        workflow,_=self.fixture()
        folder=ROOT/'analysis/farm-interface-live-20261018/live-response-loss/backend-evidence'
        record=json.loads((folder/'record.json').read_text(encoding='utf-8'))
        entry=next(o for o in record['observations'] if o['frame']=='19-save_prompt.png')
        frame=(folder/entry['frame']).read_bytes(); value=entry['observation']
        # Retained pixels prove recognition only, never current phone state.
        self.assertEqual({'sheet':'exact_save_draft'},workflow.verify_screen('save_prompt',value,frame))
        self.assertEqual((250,929),workflow.target('save_draft',value,frame))

    def test_refresh_cannot_reuse_sequence_or_change_caption_context(self):
        workflow,kernel=self.fixture(); original=workflow.observe
        for change in ('sequence','caption'):
            with self.subTest(change=change):
                workflow,kernel=self.fixture(); original=workflow.observe
                def tamper(*args,**kwargs):
                    value,frame=original(*args,**kwargs)
                    if workflow.record['promptRecoveries']:
                        value=copy.deepcopy(value)
                        if change=='sequence': value['frameEvidence']['sequence']=1
                        else: value['expected']['caption']='another caption'
                    return value,frame
                with self.age_save(workflow,kernel),patch.object(workflow,'observe',tamper): result=workflow.run()
                self.assert_held_without_save(result,kernel)

    def test_missing_or_ambiguous_save_label_never_gets_tapped(self):
        for ambiguous in (False, True):
            with self.subTest(ambiguous=ambiguous):
                workflow, kernel = self.fixture(); kernel.texts = copy.deepcopy(kernel.texts)
                def interrupt():
                    rows = kernel.texts['save_prompt']['lines']
                    row = next(r for r in rows if r['text'].casefold() == 'save draft')
                    if ambiguous: rows.append(copy.deepcopy(row))
                    else: rows.remove(row)
                with self.age_save(workflow,kernel,after_age=interrupt): result = workflow.run()
                self.assert_held_without_save(result,kernel)

    def test_changed_receiver_or_generation_during_refresh_prevents_any_save(self):
        for change in ('stream','generation'):
            with self.subTest(change=change):
                workflow,kernel = self.fixture()
                def interrupt():
                    if change == 'stream': kernel.session = 'f'*32
                    else: kernel.generation += 1
                with self.age_save(workflow,kernel,after_age=interrupt): result = workflow.run()
                self.assert_held_without_save(result,kernel)

    def test_expired_observer_session_is_not_treated_as_local_age(self):
        workflow,kernel = self.fixture()
        with self.age_save(workflow,kernel,after_age=lambda:setattr(workflow.store,'session','new-session')):
            result = workflow.run()
        self.assert_held_without_save(result,kernel)
        self.assertEqual([],result['promptRecoveries'])

    def test_changed_expected_account_during_refresh_prevents_save(self):
        workflow,kernel = self.fixture()
        with self.age_save(workflow,kernel,after_age=lambda:setattr(workflow,'account','another.account')):
            result = workflow.run()
        self.assert_held_without_save(result,kernel)
        self.assertEqual([],result['promptRecoveries'])

    def test_four_second_refresh_bound_and_original_deadline_remain_in_force(self):
        for bound in ('refresh','overall'):
            with self.subTest(bound=bound):
                workflow,kernel = self.fixture(); observe = workflow.observe
                def slow(*args,**kwargs):
                    value = observe(*args,**kwargs)
                    if workflow.record['promptRecoveries']:
                        kernel.pause(4.1 if bound == 'refresh' else 121)
                    return value
                with self.age_save(workflow,kernel), patch.object(workflow,'observe',slow): result = workflow.run()
                self.assert_held_without_save(result,kernel)
                self.assertEqual(1,len(result['promptRecoveries']))

    def test_changed_refused_evidence_cannot_be_laundered_by_new_capture(self):
        workflow,kernel = self.fixture(); original = workflow.refresh_save_prompt
        def corrupt(action,value,frame):
            with workflow.store.connect() as db:
                raw = db.execute('SELECT document FROM observations WHERE id=?',(value['id'],)).fetchone()[0]
                doc = json.loads(raw); doc['expected']['caption'] = 'changed'
                db.execute('UPDATE observations SET document=? WHERE id=?',(json.dumps(doc),value['id']))
            return original(action,value,frame)
        with self.age_save(workflow,kernel), patch.object(workflow,'refresh_save_prompt',corrupt): result = workflow.run()
        self.assert_held_without_save(result,kernel)
        self.assertIn('refused decision evidence changed',result['error'])

    def test_known_save_prompt_requires_completed_slide_caption_and_account_checks(self):
        for missing in ('profile','slide','caption'):
            with self.subTest(missing=missing):
                workflow,kernel = self.fixture(); original = workflow.refresh_save_prompt
                def remove_proof(action,value,frame):
                    if missing == 'profile':
                        entry = next(o for o in workflow.record['observations'] if o['role']=='profile')
                        entry['observation']['result']['accountStatus'] = 'not_visible'
                    else:
                        label = 'prepared-slide-2' if missing=='slide' else 'prepared-details'
                        workflow.record['actions'] = [a for a in workflow.record['actions'] if a['label']!=label]
                    return original(action,value,frame)
                with self.age_save(workflow,kernel), patch.object(workflow,'refresh_save_prompt',remove_proof): result = workflow.run()
                self.assert_held_without_save(result,kernel)
                self.assertEqual([],result['promptRecoveries'])


if __name__ == '__main__': unittest.main(verbosity=2)
