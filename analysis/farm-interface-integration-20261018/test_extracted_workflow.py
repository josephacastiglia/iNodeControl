"""Extraction parity using retained C24C frames and protocol fixtures, offline."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'analysis/farm-live-final-20261018'))
import test_validate_workflow as retained
import farm_draft_workflow as product
import farm_test_network  # Deny every real socket; fixtures use no transport.
from farm_observations import ObservationStore
from farm_draft_runs import DraftRuns
from farm_jobs import FarmJobs


class ExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retained.WorkflowTests.setUpClass()
        cls.fixtures=retained.WorkflowTests

    def fixture(self, scenario='normal'):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        folder=Path(temp.name)
        kernel=retained.FixtureKernel(self.fixtures.templates,self.fixtures.texts,scenario)
        store=ObservationStore(folder/'observations.sqlite3',ocr=retained.FixtureOcr(kernel),clock=kernel.clock,monotonic=kernel.clock)
        workflow=product.Workflow(folder,kernel,store,self.fixtures.assets,self.fixtures.caption,product.references(),
            'a'*64,'fixture-uid',account='xs.halle.xo',package_hash='b'*64,monotonic=kernel.clock,pause=kernel.pause)
        kernel.cancelled=workflow.cancelled
        return workflow,kernel

    def test_extracted_sequence_keeps_all_19_actions_two_saves_and_full_slide_caption_checks(self):
        workflow,kernel=self.fixture(); result=workflow.run()
        self.assertEqual('validation_passed',result['state'],result.get('error'))
        self.assertEqual(19,len(result['actions'])); self.assertEqual(2,kernel.saves)
        self.assertEqual('profile',kernel.screen); self.assertEqual('confirmed',result['cleanup'])
        self.assertEqual('consistent_sampled_history',result['accountHistory']['status'])
        self.assertEqual('b'*64,result['packageSha256']); self.assertEqual('offline_protocol_fixture',result['source'])
        self.assertEqual(2,len([o for o in result['observations'] if o['role']=='details']))
        self.assertTrue(all(a['state']=='answered' for a in result['actions']))

    def test_lost_save_reply_stops_and_releases_without_parking_or_reopening(self):
        workflow,kernel=self.fixture('lost_save'); result=workflow.run()
        self.assertEqual('review_required',result['state']); self.assertFalse(result['savedDraftVerified'])
        self.assertEqual(1,kernel.saves); self.assertEqual('outcome_unknown',result['actions'][-1]['state'])
        self.assertEqual('release',kernel.calls[-1]); self.assertEqual('/mouse/click',kernel.calls[-2][0])

    def test_cancel_after_save_sends_no_followup_action(self):
        workflow,kernel=self.fixture('cancel_after_save'); result=workflow.run()
        self.assertEqual('review_required',result['state']); self.assertEqual(1,kernel.saves)
        self.assertEqual('release',kernel.calls[-1]); self.assertEqual('/mouse/click',kernel.calls[-2][0])

    def test_transients_settle_with_fresh_frames_without_repeating_actions(self):
        workflow,kernel=self.fixture('known_transients'); result=workflow.run()
        self.assertEqual('validation_passed',result['state'],result.get('error'))
        self.assertEqual(19,len(result['actions'])); self.assertEqual(2,kernel.saves)

    def test_stale_frames_or_wrong_account_never_click(self):
        for scenario in ('stale_frame','wrong_account','failed_ocr'):
            with self.subTest(scenario=scenario):
                workflow,kernel=self.fixture(scenario); result=workflow.run()
                self.assertEqual('review_required',result['state']); self.assertFalse(result['savedDraftVerified'])
                self.assertFalse(any(isinstance(c,tuple) and c[0]=='/mouse/click' for c in kernel.calls))

    def test_wrong_caption_never_saves(self):
        workflow,kernel=self.fixture('wrong_caption'); result=workflow.run()
        self.assertEqual('review_required',result['state']); self.assertEqual(0,kernel.saves)

    def test_cleanup_failure_revokes_verified_claim(self):
        workflow,kernel=self.fixture()
        with patch.object(kernel,'release',side_effect=RuntimeError('Cleanup reply lost')):
            result=workflow.run()
        self.assertEqual('review_required',result['state']); self.assertEqual('unconfirmed',result['cleanup'])
        self.assertFalse(result['savedDraftVerified'])

    def test_lost_reopen_answer_never_swipes_or_saves_again(self):
        workflow,kernel=self.fixture(); send=kernel.send
        def lose_reopen(phone,token,fun,**data):
            reopen=kernel.saves==1 and kernel.screen=='library' and fun=='/mouse/click'
            response=send(phone,token,fun,**data)
            if reopen: raise TimeoutError('Reopen happened but its answer was lost')
            return response
        with patch.object(kernel,'send',lose_reopen): result=workflow.run()
        self.assertEqual('review_required',result['state']); self.assertEqual(1,kernel.saves)
        self.assertEqual('outcome_unknown',result['actions'][-1]['state'])
        self.assertEqual('reopen-saved-test-draft',result['actions'][-1]['label'])
        self.assertEqual('release',kernel.calls[-1]); self.assertEqual('/mouse/click',kernel.calls[-2][0])

    def test_candidate_restart_after_save_stops_before_next_input(self):
        workflow,kernel=self.fixture(); status=kernel.kernel_status
        def restart():
            value=status()
            if kernel.saves: value['process']['pid']=999
            return value
        with patch.object(kernel,'kernel_status',restart): result=workflow.run()
        self.assertEqual('review_required',result['state']); self.assertEqual(1,kernel.saves)
        self.assertEqual('release',kernel.calls[-1]); self.assertEqual('/mouse/click',kernel.calls[-2][0])

    def test_cancel_at_last_journal_boundary_is_not_sent(self):
        workflow,kernel=self.fixture(); save=workflow.save
        def interrupt():
            save()
            if workflow.record['commands'] and workflow.record['commands'][-1].get('purpose')=='prepared-save-once' and workflow.record['commands'][-1]['state']=='outcome_unknown':
                workflow.cancelled.set()
        with patch.object(workflow,'save',interrupt): result=workflow.run()
        self.assertEqual('review_required',result['state']); self.assertEqual(0,kernel.saves)
        self.assertEqual('not_sent',result['actions'][-1]['state']); self.assertEqual('confirmed',result['cleanup'])

    def test_navigation_crops_match_the_exact_verified_pixels_and_reject_changed_icon(self):
        boxes={'profile':(15,69,57,108),'details':(12,67,55,106),'editor3':(17,76,62,122),'picker_saved':(19,66,58,105)}
        templates=product.references()
        for key,box in boxes.items():
            product.icon_matches(self.fixtures.templates[key],templates[key],box)
            with Image.open(io.BytesIO(templates[key])) as image:
                image.paste('red',box); output=io.BytesIO(); image.save(output,'PNG')
            with self.assertRaises(product.InspectionStopped): product.icon_matches(output.getvalue(),templates[key],box)

    def test_complete_extracted_sequence_through_durable_service_retains_and_checks_every_frame(self):
        package=(ROOT/'analysis/farm-phone-transfer-20261017/test-carousel.zip').read_bytes()
        class SourceDraft:
            def export(self,draft_id,revision): return package
            def get(self,draft_id): return dict(revision=5)
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root=Path(temp.name); jobs=FarmJobs(journal_path=root/'jobs.db')
        service=DraftRuns(root/'runs',SourceDraft(),jobs,dict(api='http://127.0.0.1:9916/api',kernelSha256='a'*64,expectedUid='fixture-uid'))
        def execute(folder,assets,caption,package_hash,cancelled):
            kernel=retained.FixtureKernel(self.fixtures.templates,self.fixtures.texts)
            store=ObservationStore(folder/'observations.sqlite3',ocr=retained.FixtureOcr(kernel),clock=kernel.clock,monotonic=kernel.clock)
            workflow=product.Workflow(folder,kernel,store,assets,caption,product.references(),'a'*64,'fixture-uid',account='xs.halle.xo',package_hash=package_hash,cancelled=cancelled,monotonic=kernel.clock,pause=kernel.pause)
            return workflow.run()
        request=dict(id=str(uuid.uuid4()),draft_id=str(uuid.uuid4()),revision=5,store_id=service.store_id)
        with patch.object(service,'execute',execute):
            service.start(request)
            self.assertTrue(jobs._jobs[request['id']].done.wait(30))
        value=service.get(request['id'])
        self.assertEqual('succeeded',value['jobStatus']); self.assertEqual('validation_passed',value['workflow']['state'],value['reason'])
        self.assertFalse(value['savedDraftVerified'],'An offline protocol fixture is never a live phone result.')
        self.assertGreaterEqual(len(value['workflow']['observations']),32)
        for entry in value['workflow']['observations']:
            frame=service.frame(request['id'],entry['observationId'])
            self.assertEqual(entry['observation']['reviewFrameSha256'],hashlib.sha256(frame).hexdigest())
        store=ObservationStore(root/'runs'/request['id']/'observations.sqlite3')
        with store.connect() as db:
            db.execute('UPDATE observations SET document=? WHERE id=?',(json.dumps(dict(reviewFrameSha256='bad')),value['workflow']['observations'][0]['observationId']))
        with self.assertRaises(ValueError): service.get(request['id'])


if __name__=='__main__': unittest.main(verbosity=2)
