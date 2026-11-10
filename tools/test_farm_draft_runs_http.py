"""Real loopback HTTP with fake draft execution; no rack access."""
import unittest
import uuid

from test_farm_http_jobs import FarmHttpJobsTests, no_kernel
from test_farm_draft_runs import Drafts, FixtureRuns, CONFIG
from test_farm_creation import FixtureCreation

# Every creation route and the runtime attribute that serves it. The route mechanics are the same for all.
ROUTES = {'draft-creations': 'draft_creations', 'reel-creations': 'reel_creations', 'tiktok-creations': 'tiktok_creations',
          'x-creations': 'x_creations', 'youtube-creations': 'youtube_creations', 'x-image-creations': 'x_image_creations',
          'tiktok-photo-creations': 'tiktok_photo_creations'}


class DraftRunHttpTests(unittest.TestCase):
    setUp = FarmHttpJobsTests.setUp
    tearDown = FarmHttpJobsTests.tearDown
    request = FarmHttpJobsTests.request

    def prepare(self, name):
        self.service=FixtureRuns(self.root/('runs-'+name),Drafts(),self.runtime.jobs,CONFIG)
        setattr(self.runtime,ROUTES[name],self.service)
        return dict(id=str(uuid.uuid4()),draft_id=str(uuid.uuid4()),revision=3,store_id=self.service.store_id)

    def finish(self,name,spec):
        self.assertTrue(self.runtime.jobs._jobs[spec['id']].done.wait(4))
        return self.request('/api/farm/'+name+'/'+spec['id'])[1]['run']

    def test_real_http_admission_history_duplicate_result_and_origins_on_every_creation_route(self):
        for name in ROUTES:
            with self.subTest(route=name):
                spec=self.prepare(name); route='/api/farm/'+name
                status,body=self.request(route,spec); self.assertEqual(202,status,body)
                result=self.finish(name,spec); self.assertFalse(result['savedDraftVerified'])
                self.assertEqual(result,self.request(route,spec)[1]['run'])
                self.assertEqual(1,self.service.executions)
                self.assertEqual([dict(id=spec['id'],revision=3)],self.request(route+'?draft_id='+spec['draft_id'])[1]['runs'])
                eligible=route+'/eligibility?draft_id='+spec['draft_id']+'&revision=3'
                self.assertTrue(self.request(eligible)[1]['eligibility']['eligible'])
                for path in (route+'?draft_id='+spec['draft_id'],route+'/'+spec['id'],eligible,route+'/'+spec['id']+'/frames/'+str(uuid.uuid4())):
                    self.assertEqual(403,self.request(path,origin='https://untrusted.invalid')[0])
                self.assertEqual(403,self.request(route,spec,origin='https://untrusted.invalid')[0])
                self.assertEqual(409,self.request(route,{**spec,'revision':4})[0])
                self.assertEqual(400,self.request(route,{**spec,'device_id':'C241'})[0])
                self.assertEqual(404,self.request(route+'/'+str(uuid.uuid4()))[0])
                self.assertEqual(404,self.request(route+'/'+spec['id']+'/frames/'+str(uuid.uuid4()))[0])
                self.assertEqual(404,self.request(route+'/'+spec['id']+'/unknown/extra/parts')[0])

    def test_stop_during_active_worker_bypasses_operation_lock_and_is_store_bound_on_every_creation_route(self):
        for name in ROUTES:
            with self.subTest(route=name):
                spec=self.prepare(name); self.service.wait=True
                self.assertEqual(202,self.request('/api/farm/'+name,spec)[0])
                self.assertTrue(self.service.entered.wait(1))
                route='/api/farm/'+name+'/'+spec['id']+'/cancel'
                with self.runtime.operation_lock:
                    self.assertEqual(400,self.request(route,dict(store_id=str(uuid.uuid4())))[0])
                    self.assertEqual(200,self.request(route,dict(store_id=self.service.store_id))[0])
                result=self.finish(name,spec)
                self.assertEqual('cancelled',result['jobStatus']); self.assertEqual('confirmed',result['cleanup'])
                self.assertEqual(1,self.service.executions)

    def test_new_creation_route_is_draft_only_local_and_cannot_fall_back_to_release(self):
        service=FixtureCreation(self.root/'creations',Drafts(),self.runtime.jobs,CONFIG)
        service.supports=lambda package: True  # Admission fixture; media bounds have separate tests.
        self.runtime.draft_creations=service;self.runtime.execution_mode='live'
        spec=dict(id=str(uuid.uuid4()),draft_id=str(uuid.uuid4()),revision=3,store_id=service.store_id)
        route='/api/farm/draft-creations'
        self.assertTrue(self.request('/health')[1]['draftCreation']['enabled'])
        with no_kernel():
            self.assertNotIn('kernelError',self.request('/api/farm/state')[1])
            self.assertEqual(404,self.request('/kernel-proxy/',dict(fun='/mouse/click',data={'id':'C24C','x':200,'y':300}))[0])
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
