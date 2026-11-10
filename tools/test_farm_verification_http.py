import json
import uuid
from unittest.mock import patch
import unittest

from test_farm_http_jobs import FarmHttpJobsTests


class VerificationHttpTests(unittest.TestCase):
    setUp = FarmHttpJobsTests.setUp
    tearDown = FarmHttpJobsTests.tearDown
    request = FarmHttpJobsTests.request
    outside_connections = FarmHttpJobsTests.outside_connections

    def test_review_roundtrip_recovery_origin_policy_and_no_phone(self):
        from test_farm_draft_verification import VerificationTests
        fixture = VerificationTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        self.runtime.verifications = fixture.reviews
        with patch('imouse_farm_server.engine.IMouseKernel', side_effect=AssertionError('Review must never contact a phone')):
            status, response = self.request('/api/farm/draft-verifications', fixture.spec)
            self.assertEqual(200, status, response); self.assertNotIn('simulated', response)
            report = response['verification']
            self.assertNotEqual('phone', report['assessment']['source'])   # Fixture observations, and the report says so.
            self.assertEqual('consistent_visual_evidence', report['assessment']['status'])
            self.assertFalse(report['assessment']['savedDraftVerified'])
            self.assertEqual(report, self.request('/api/farm/draft-verifications', fixture.spec)[1]['verification'])
            self.assertEqual(report, self.request('/api/farm/draft-verifications/' + fixture.spec['id'])[1]['verification'])
            frame_path = '/api/farm/draft-verifications/' + fixture.spec['id'] + '/frames/' + fixture.spec['observations']['reopened'][0]
            self.assertIn('frame', self.request(frame_path)[1])
            self.assertEqual(403, self.request(frame_path, origin='https://untrusted.invalid')[0])
            self.assertEqual(404, self.request('/api/farm/draft-verifications/' + fixture.spec['id'] + '/frames/' + str(uuid.uuid4()))[0])
            listed = self.request('/api/farm/draft-verifications?draft_id=' + fixture.draft['id'])[1]['verifications']
            self.assertEqual(1, len(listed))
            for path in ('/api/farm/draft-verifications?draft_id=' + fixture.draft['id'], '/api/farm/draft-verifications/' + fixture.spec['id']):
                self.assertEqual(403, self.request(path, origin='https://untrusted.invalid')[0])
            self.assertEqual(403, self.request('/api/farm/draft-verifications', fixture.spec, origin='https://untrusted.invalid')[0])
            self.assertEqual(400, self.request('/api/farm/draft-verifications', {**fixture.spec, 'device_id': 'C241'})[0])
            self.assertEqual(409, self.request('/api/farm/draft-verifications', {**fixture.spec, 'account': 'another.account'})[0])
            self.assertEqual(404, self.request('/api/farm/draft-verifications/' + str(uuid.uuid4()))[0])
        self.assertEqual([], self.outside_connections())


del FarmHttpJobsTests
