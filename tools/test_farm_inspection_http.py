import concurrent.futures
import threading
import unittest
from unittest.mock import patch

from test_farm_http_jobs import FarmHttpJobsTests


class InspectionHttpTests(unittest.TestCase):
    setUp=FarmHttpJobsTests.setUp
    tearDown=FarmHttpJobsTests.tearDown
    request=FarmHttpJobsTests.request

    def fixture(self):
        from test_farm_carousel_inspection import InspectionTests
        f=InspectionTests(); f.setUp(); self.addCleanup(f.doCleanups)
        self.runtime.inspections=f.store; self.runtime.kernel_client=f.kernel
        return f

    def test_inspection_recovery_retained_frame_and_origin_guards(self):
        f=self.fixture()
        with patch('imouse_farm_server.engine.IMouseKernel',side_effect=AssertionError('No real kernel')):
            path='/api/farm/carousel-inspections'
            status,response=self.request(path,f.spec)
            self.assertEqual(200,status,response); self.assertTrue(response['simulated'])
            saved=response['inspection']; self.assertEqual('visual_match',saved['state'])
            calls=list(f.kernel.calls)
            self.assertEqual(saved,self.request(path,f.spec)[1]['inspection']); self.assertEqual(calls,f.kernel.calls)
            self.assertEqual(saved,self.request(path+'/'+f.spec['id'])[1]['inspection'])
            frame=path+'/'+f.spec['id']+'/frames/'+saved['slides'][0]['observationId']
            self.assertIn('frame',self.request(frame)[1])
            for route in (path+'/'+f.spec['id'],frame):
                self.assertEqual(403,self.request(route,origin='https://untrusted.invalid')[0])
            self.assertEqual(403,self.request(path,f.spec,origin='https://untrusted.invalid')[0])
            self.assertEqual(400,self.request(path,{**f.spec,'device_id':'C241'})[0])
            self.assertEqual(409,self.request(path,{**f.spec,'account':'other.account'})[0])
            self.assertFalse(self.request('/health')[1]['carouselInspectionLiveMovement'])

    def test_http_cancel_bypasses_operation_lock_and_releases_lease(self):
        f=self.fixture(); entered=threading.Event(); proceed=threading.Event()
        original=f.kernel.send
        def blocked(*args,**kwargs):
            entered.set()
            if not proceed.wait(3): raise AssertionError('Test failed to cancel promptly')
            return original(*args,**kwargs)
        with patch.object(f.kernel,'send',side_effect=blocked),concurrent.futures.ThreadPoolExecutor() as pool:
            future=pool.submit(self.request,'/api/farm/carousel-inspections',f.spec)
            try:
                self.assertTrue(entered.wait(3))
                status,body=self.request('/api/farm/carousel-inspections/'+f.spec['id']+'/cancel',{})
                self.assertEqual(200,status); self.assertTrue(body['cancellationRequested'])
            finally: proceed.set()
            result=future.result(timeout=4)[1]['inspection']
        self.assertEqual('review_required',result['state']); self.assertEqual('confirmed',result['cleanup'])
        self.assertEqual(1,f.kernel.calls.count('swipe'))


del FarmHttpJobsTests
