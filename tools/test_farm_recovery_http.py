"""Real loopback HTTP with fixture recovery workers; no phone/installed kernel."""
import threading
import unittest
import uuid
from unittest.mock import patch

from test_farm_http_jobs import FarmHttpJobsTests
import test_farm_recovery as fixtures


class RecoveryHttpTests(unittest.TestCase):
    setUp = FarmHttpJobsTests.setUp
    tearDown = FarmHttpJobsTests.tearDown
    request = FarmHttpJobsTests.request

    def prepare(self):
        f = fixtures.RecoveryTests(); f.setUp(); self.addCleanup(f.doCleanups)
        self.fixture = f
        self.runtime.draft_creations = f.creations
        self.runtime.draft_recoveries = f.service
        return f.spec

    def test_http_inspection_is_explicit_origin_checked_and_never_repeats_original(self):
        spec = self.prepare(); f = self.fixture; route = '/api/farm/draft-recoveries'
        before = f.origin_path.read_bytes()
        with patch.object(self.runtime, 'get_kernel', side_effect=AssertionError('No installed kernel')):
            self.assertTrue(self.request('/health')[1]['draftRecovery']['inspectionOnly'])
            self.assertTrue(self.request(route+'/eligibility?creation_id='+spec['creation_id'])[1]['eligibility']['eligible'])
            self.assertEqual(202, self.request(route, spec)[0]); f.finish()
            self.assertEqual(202, self.request(route, spec)[0]); self.assertEqual(1, f.service.executions)
            value = self.request(route+'/'+spec['id'])[1]['run']
            self.assertTrue(value['inspectionOnly']); self.assertFalse(value['savedDraftVerified'])
            self.assertEqual([dict(id=spec['id'], revision=spec['revision'])], self.request(route+'?draft_id='+spec['draft_id'])[1]['runs'])
            for path in (route+'/'+spec['id'], route+'?draft_id='+spec['draft_id'],
                         route+'/eligibility?creation_id='+spec['creation_id'], route+'/'+spec['id']+'/frames/'+str(uuid.uuid4())):
                self.assertEqual(403, self.request(path, origin='https://untrusted.invalid')[0])
            self.assertEqual(403, self.request(route, spec, origin='https://untrusted.invalid')[0])
            self.assertEqual(400, self.request(route, dict(spec, device='C241'))[0])
            self.assertEqual(409, self.request(route, dict(spec, id=str(uuid.uuid4()), creation_record_sha256='b'*64))[0])
        self.assertEqual(before, f.origin_path.read_bytes())

    def test_stop_is_store_bound_and_available_during_a_pending_http_operation(self):
        spec = self.prepare(); f = self.fixture
        f.service.wait = True; f.service.entered = threading.Event()
        self.assertEqual(202, self.request('/api/farm/draft-recoveries', spec)[0])
        self.assertTrue(f.service.entered.wait(2))
        path = '/api/farm/draft-recoveries/'+spec['id']+'/cancel'
        with self.runtime.operation_lock:
            self.assertEqual(400, self.request(path, dict(store_id=str(uuid.uuid4())))[0])
            self.assertEqual(200, self.request(path, dict(store_id=f.service.store_id))[0])
        value = f.finish()
        self.assertEqual('cancelled', value['jobStatus']); self.assertEqual(1, f.service.executions)

    def test_unconfigured_backend_cannot_start_inspection_or_contact_release(self):
        capability = self.request('/health')[1]['draftRecovery']
        self.assertFalse(capability['enabled'])
        spec = dict(id=str(uuid.uuid4()), draft_id=str(uuid.uuid4()), revision=1, store_id=capability['storeId'],
            creation_id=str(uuid.uuid4()), creation_store_id=str(uuid.uuid4()), creation_record_sha256='a'*64)
        with patch.object(self.runtime, 'get_kernel', side_effect=AssertionError('No installed kernel')):
            self.assertEqual(409, self.request('/api/farm/draft-recoveries', spec)[0])


del FarmHttpJobsTests
