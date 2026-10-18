import concurrent.futures
import threading
import unittest
import uuid
from unittest.mock import patch

from farm_draft_rehearsal import DraftAppModel
from test_farm_http_jobs import FarmHttpJobsTests


class RehearsalHttpTests(unittest.TestCase):
    setUp=FarmHttpJobsTests.setUp
    tearDown=FarmHttpJobsTests.tearDown
    request=FarmHttpJobsTests.request

    def spec(self):
        from test_farm_draft_rehearsal import RehearsalTests
        f=RehearsalTests(); f.setUp(); self.addCleanup(f.doCleanups)
        self.runtime.rehearsals=f.store
        return dict(f.spec)

    def test_real_http_run_recover_history_frame_and_origin_without_kernel_access(self):
        spec=self.spec(); route='/api/farm/draft-rehearsals'
        with patch.object(self.runtime,'get_kernel',side_effect=AssertionError('Must not request any kernel')):
            status,response=self.request(route,spec)
            self.assertEqual(200,status,response); result=response['rehearsal']
            self.assertEqual('simulation_passed',result['state']); self.assertTrue(response['simulated'])
            self.assertEqual(result,self.request(route+'/'+spec['id'])[1]['rehearsal'])
            self.assertEqual(result,self.request(route,spec)[1]['rehearsal'])
            self.assertEqual(1,len(self.request(route+'?draft_id='+spec['draft_id'])[1]['rehearsals']))
            frame=route+'/'+spec['id']+'/frames/'+result['observationIds'][0]
            self.assertIn('frame',self.request(frame)[1])
            for path in (route+'?draft_id='+spec['draft_id'],route+'/'+spec['id'],frame):
                self.assertEqual(403,self.request(path,origin='https://untrusted.invalid')[0])
            self.assertEqual(403,self.request(route,spec,origin='https://untrusted.invalid')[0])
            self.assertEqual(409,self.request(route,{**spec,'scenario':'save_reply_lost'})[0])
            self.assertEqual(400,self.request(route,{**spec,'device_id':'C241'})[0])
            self.assertFalse(self.request('/health')[1]['draftRehearsalLiveEnabled'])

    def test_live_backend_cannot_run_rehearsal_or_route_to_phone(self):
        spec=self.spec(); self.runtime.execution_mode='live'
        with patch.object(self.runtime,'get_kernel',side_effect=AssertionError('No kernel')):
            self.assertEqual(400,self.request('/api/farm/draft-rehearsals',spec)[0])
        self.assertEqual([],self.runtime.rehearsals.list(spec['draft_id']))

    def test_cancel_bypasses_operation_lock_even_during_lost_save_reply(self):
        spec=self.spec(); entered=threading.Event(); proceed=threading.Event()
        original=DraftAppModel.perform
        def perform(model,action,token):
            if action['kind']=='save_draft':
                entered.set()
                if not proceed.wait(3): raise AssertionError('Cancel did not reach the server.')
            return original(model,action,token)
        with patch.object(DraftAppModel,'perform',perform), concurrent.futures.ThreadPoolExecutor() as pool:
            future=pool.submit(self.request,'/api/farm/draft-rehearsals',spec)
            try:
                self.assertTrue(entered.wait(4))
                status,body=self.request('/api/farm/draft-rehearsals/'+spec['id']+'/cancel',{})
                self.assertEqual(200,status); self.assertTrue(body['cancellationRequested'])
                snapshot=self.request('/api/farm/draft-rehearsals/'+spec['id'])[1]['rehearsal']
                self.assertEqual('running',snapshot['state']); self.assertEqual('outcome_unknown',snapshot['actions'][-1]['state'])
            finally: proceed.set()
            result=future.result(timeout=5)[1]['rehearsal']
        self.assertEqual('review_required',result['state']); self.assertEqual('confirmed',result['cleanup'])
        self.assertEqual(1,sum(a['kind']=='save_draft' for a in result['actions']))
        self.assertFalse(any(a['kind']=='reopen' for a in result['actions']))


del FarmHttpJobsTests
