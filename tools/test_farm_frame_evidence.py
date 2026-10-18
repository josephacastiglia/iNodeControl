import unittest
from farm_frame_evidence import delivery_evidence, workflow_review


class FrameEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(deviceid='C24C', receiver_pid=10, receiver_restarts=0, live=True, frames=5, frame_session='a' * 32)
        self.after = {**self.before, 'frames': 7}
        self.headers = {'X-iMouse-Frame-Session': 'a' * 32, 'X-iMouse-Frame-Sequence': '6',
                        'X-iMouse-Frame-Age-Ms': '25', 'X-iMouse-Frame-Delivery': 'flowing'}

    def test_matching_frame_metadata_uses_a_conservative_total_age(self):
        result = delivery_evidence(self.before, self.headers, self.after, 400)
        self.assertEqual('recent', result['freshness']); self.assertEqual(425, result['ageUpperBoundMs'])
        self.assertTrue(result['pairedMetadata']); self.assertTrue(result['deliveryAdvanced'])
        self.assertFalse(result['phoneCaptureTimeKnown'])

    def test_frame_counter_progress_alone_is_not_freshness(self):
        result = delivery_evidence(self.before, {}, self.after, 200)
        self.assertEqual('unavailable', result['freshness']); self.assertTrue(result['deliveryAdvanced'])
        self.assertFalse(result['pairedMetadata']); self.assertIsNone(result['ageUpperBoundMs'])

    def test_slow_transport_and_ocr_or_quiet_delivery_hold_the_frame(self):
        self.assertEqual('stale', delivery_evidence(self.before, self.headers, self.after, 1476)['freshness'])
        self.assertEqual('recent', delivery_evidence(self.before, self.headers, self.after, 1475)['freshness'])
        self.assertEqual('stale', delivery_evidence(self.before, {**self.headers, 'X-iMouse-Frame-Delivery': 'quiet'}, self.after, 0)['freshness'])

    def test_restarts_sessions_sequence_and_identity_must_agree(self):
        changes = [{'receiver_pid': 11}, {'receiver_restarts': 1}, {'frame_session': 'b' * 32},
                   {'deviceid': 'C241'}, {'live': False}, {'frames': 4}, {'frames': None}]
        for change in changes:
            with self.subTest(change=change):
                self.assertEqual('invalid', delivery_evidence(self.before, self.headers, {**self.after, **change}, 1)['freshness'])
        for sequence in ('4', '8', '-1', '0', '1.5', 'NaN'):
            self.assertEqual('invalid', delivery_evidence(self.before, {**self.headers, 'X-iMouse-Frame-Sequence': sequence}, self.after, 1)['freshness'])

    def test_bad_partial_metadata_and_nonfinite_timing_never_pass(self):
        for age in ('NaN', 'Infinity', '-1', 'x'):
            self.assertEqual('invalid', delivery_evidence(self.before, {**self.headers, 'X-iMouse-Frame-Age-Ms': age}, self.after, 0)['freshness'])
        for elapsed in (float('nan'), float('inf'), -1):
            self.assertEqual('invalid', delivery_evidence(self.before, self.headers, self.after, elapsed)['freshness'])
        for key in self.headers:
            self.assertEqual('invalid', delivery_evidence(self.before, {k: v for k, v in self.headers.items() if k != key}, self.after, 0)['freshness'])

    def test_review_never_grants_input_or_infers_draft_save(self):
        value = dict(state='observed', expired=False, freshness='recent', stable=True, inputIdle=True, expected={'caption': 'COPY'},
                     result=dict(screen='draft_details', expectedAppMatches=True, accountStatus='exact_text_match', captionStatus='exact_line_match'))
        self.assertEqual('ready_for_review', workflow_review(value)['status'])
        for change in ({'freshness': 'unavailable'}, {'stable': False}, {'expired': True}, {'inputIdle': False},
                       {'result': {**value['result'], 'screen': 'caption_editor'}},
                       {'result': {**value['result'], 'accountStatus': 'different_text'}}):
            review = workflow_review({**value, **change})
            self.assertEqual('blocked', review['status']); self.assertTrue(review['blockers'])
            self.assertFalse(review['automaticInputAllowed']); self.assertFalse(review['savedDraftVerified'])


if __name__ == '__main__': unittest.main()
