"""Real loopback HTTP with fake draft execution; no rack access."""
import threading
from unittest.mock import patch
import unittest
import uuid

import farm_draft_runs as runs
from test_farm_http_jobs import FarmHttpJobsTests
from test_farm_draft_runs import Drafts, FixtureRuns, CONFIG
from test_farm_creation import FixtureCreation


class DraftRunHttpTests(unittest.TestCase):
    setUp = FarmHttpJobsTests.setUp
    tearDown = FarmHttpJobsTests.tearDown
    request = FarmHttpJobsTests.request

    def prepare(self):
        drafts=Drafts(); digest=runs.source_content(drafts.export('fixture',3))[2]
        p=patch.object(runs,'CONTENT_SHA256',digest); p.start(); self.addCleanup(p.stop)
        self.service=FixtureRuns(self.root/'runs',drafts,self.runtime.jobs,CONFIG)
        self.runtime.draft_runs=self.service
        return dict(id=str(uuid.uuid4()),draft_id=str(uuid.uuid4()),revision=3,store_id=self.service.store_id)

    def finish(self,spec):
        self.assertTrue(self.runtime.jobs._jobs[spec['id']].done.wait(4))
        return self.request('/api/farm/draft-runs/'+spec['id'])[1]['run']

    def test_real_http_admission_history_duplicate_result_and_origins(self):
        spec=self.prepare(); route='/api/farm/draft-runs'
        with patch.object(self.runtime,'get_kernel',side_effect=AssertionError('Default rack must not be used')):
            status,body=self.request(route,spec); self.assertEqual(202,status,body)
            result=self.finish(spec); self.assertFalse(result['savedDraftVerified'])
            self.assertEqual(result,self.request(route,spec)[1]['run'])
            self.assertEqual(1,self.service.executions)
            self.assertEqual([dict(id=spec['id'],revision=3)],self.request(route+'?draft_id='+spec['draft_id'])[1]['runs'])
            self.assertEqual(self.service.store_id,self.request('/health')[1]['draftWorkflow']['storeId'])
            eligible=route+'/eligibility?draft_id='+spec['draft_id']+'&revision=3'
            self.assertTrue(self.request(eligible)[1]['eligibility']['eligible'])
            for path in (route+'?draft_id='+spec['draft_id'],route+'/'+spec['id'],eligible,route+'/'+spec['id']+'/frames/'+str(uuid.uuid4())):
                self.assertEqual(403,self.request(path,origin='https://untrusted.invalid')[0])
            self.assertEqual(403,self.request(route,spec,origin='https://untrusted.invalid')[0])
            self.assertEqual(409,self.request(route,{**spec,'revision':4})[0])
            self.assertEqual(400,self.request(route,{**spec,'device_id':'C241'})[0])

    def test_stop_during_active_worker_bypasses_operation_lock_and_is_store_bound(self):
        spec=self.prepare(); self.service.wait=True
        self.assertEqual(202,self.request('/api/farm/draft-runs',spec)[0])
        self.assertTrue(self.service.entered.wait(1))
        route='/api/farm/draft-runs/'+spec['id']+'/cancel'
        with self.runtime.operation_lock:
            self.assertEqual(400,self.request(route,dict(store_id=str(uuid.uuid4())))[0])
            self.assertEqual(200,self.request(route,dict(store_id=self.service.store_id))[0])
        result=self.finish(spec)
        self.assertEqual('cancelled',result['jobStatus']); self.assertEqual('confirmed',result['cleanup'])
        self.assertEqual(1,self.service.executions)

    def test_default_simulation_backend_cannot_send_a_phone_workflow(self):
        capability=self.request('/health')[1]['draftWorkflow']
        spec=dict(id=str(uuid.uuid4()),draft_id=str(uuid.uuid4()),revision=1,store_id=capability['storeId'])
        self.assertFalse(capability['enabled'])
        with patch.object(self.runtime,'get_kernel',side_effect=AssertionError('No kernel')):
            self.assertEqual(409,self.request('/api/farm/draft-runs',spec)[0])
        self.assertEqual(404,self.request('/api/farm/draft-runs/'+spec['id'])[0])

    def test_configured_draft_candidate_cannot_fall_back_to_installed_kernel(self):
        self.prepare()
        self.runtime.execution_mode='live'
        with patch.object(self.runtime.kernel_client,'kernel_status',side_effect=AssertionError('Must not contact the release')):
            status,response=self.request('/api/farm/state')
            self.assertEqual(200,status); self.assertIn('bounded draft workflow',response['kernelError'])
            status,response=self.request('/kernel-proxy/',dict(fun='/mouse/click',data={'id':'C24C','x':200,'y':300}))
            self.assertEqual(409,status); self.assertIn('bounded draft workflow',response['error'])

    def test_new_creation_route_is_draft_only_local_and_cannot_fall_back_to_release(self):
        service=FixtureCreation(self.root/'creations',Drafts(),self.runtime.jobs,CONFIG)
        service.supports=lambda package: True  # Admission fixture; media bounds have separate tests.
        self.runtime.draft_creations=service;self.runtime.execution_mode='live'
        spec=dict(id=str(uuid.uuid4()),draft_id=str(uuid.uuid4()),revision=3,store_id=service.store_id)
        route='/api/farm/draft-creations'
        self.assertTrue(self.request('/health')[1]['draftCreation']['enabled'])
        with patch.object(self.runtime.kernel_client,'kernel_status',side_effect=AssertionError('No release access')):
            self.assertIn('bounded draft workflow',self.request('/api/farm/state')[1]['kernelError'])
            self.assertEqual(409,self.request('/kernel-proxy/',dict(fun='/mouse/click',data={'id':'C24C','x':200,'y':300}))[0])
            self.assertEqual(202,self.request(route,spec)[0]);self.assertTrue(self.runtime.jobs._jobs[spec['id']].done.wait(4))
            self.assertFalse(self.request(route+'/'+spec['id'])[1]['run']['savedDraftVerified'])
            self.assertEqual(202,self.request(route,spec)[0]);self.assertEqual(1,service.executions)
            self.assertEqual(409,self.request(route,dict(spec,id=str(uuid.uuid4())))[0])
            for path in (route+'?draft_id='+spec['draft_id'],route+'/'+spec['id'],route+'/eligibility?draft_id='+spec['draft_id']+'&revision=3'):
                self.assertEqual(403,self.request(path,origin='https://untrusted.invalid')[0])
            self.assertEqual(403,self.request(route,spec,origin='https://untrusted.invalid')[0])
            self.assertEqual(400,self.request(route,dict(spec,device_id='C241'))[0])

    def test_new_creation_is_disabled_by_default_and_stop_is_store_bound(self):
        capability=self.request('/health')[1]['draftCreation'];self.assertFalse(capability['enabled'])
        spec=dict(id=str(uuid.uuid4()),draft_id=str(uuid.uuid4()),revision=1,store_id=capability['storeId'])
        self.assertEqual(409,self.request('/api/farm/draft-creations',spec)[0])
        route='/api/farm/draft-creations/'+spec['id']+'/cancel'
        self.assertEqual(400,self.request(route,dict(store_id=str(uuid.uuid4())))[0])
        self.assertEqual(200,self.request(route,dict(store_id=capability['storeId']))[0])


del FarmHttpJobsTests
