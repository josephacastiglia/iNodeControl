"""Read-only screen verification and restart holds; fixtures contain no private accounts."""
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from unittest.mock import patch

from PIL import Image
from farm_observations import ObservationStore, WindowsOcr, classify, expectations


def ocr_lines(*rows):
    return {'provider': 'fixture', 'width': 500, 'height': 1080, 'lines': [
        {'text': text, 'words': [{'text': text, 'x': 20, 'y': y, 'width': 200, 'height': 20}]} for text, y in rows]}


PROFILE = ocr_lines(('@test.account', 130), ('Following', 250), ('Followers', 250), ('Likes', 250), ('Profile', 1000))


class ReadOnlyKernel:
    _is_live_http = True
    def __init__(self):
        stream = io.BytesIO(); Image.new('RGB', (500, 1080), 'white').save(stream, format='BMP')
        self.raw = stream.getvalue(); self.reads = []; self.offline = False; self.changing = False; self.calls = 0
        self.headers = {'X-iMouse-Frame-Age-Ms': '15', 'X-iMouse-Frame-Session': 'a' * 32,
                        'X-iMouse-Frame-Sequence': '1', 'X-iMouse-Frame-Delivery': 'flowing'}
    def resolve_device_id(self, phone):
        if phone != 'C24C': raise AssertionError('Other phone requested')
        return 'C24C'
    def kernel_status(self):
        self.reads.append('status')
        return {'receivers': [{'deviceid': 'C24C', 'live': not self.offline, 'receiver_pid': 10,
                               'receiver_restarts': 0, 'frames': 1, 'frame_session': 'a' * 32}]}
    def input_status(self):
        self.calls += 1; self.reads.append('input-status')
        return {'C24C': {'generation': self.calls if self.changing else 4, 'owned': False,
                         'active': False, 'stopped': False, 'releasing': False, 'release_failed': False}}
    def shot(self, phone):
        self.resolve_device_id(phone); self.reads.append('frame')
        return self.raw, self.headers
    def __getattr__(self, name): raise AssertionError('No input method may be called: ' + name)


class FixtureOcr:
    def read(self, raw): return PROFILE


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'observations.db'; self.now = [1000.0]
        self.mono = [1000.0]
        self.store = ObservationStore(self.path, FixtureOcr(), clock=lambda: self.now[0], monotonic=lambda: self.mono[0])
        self.kernel = ReadOnlyKernel()
        self.request = {'id': str(uuid.uuid4()), 'device_id': 'C24C', 'platform': 'tiktok', 'account': '@test.account', 'caption': 'DRAFT ONLY'}

    def test_profile_account_exact_match_never_authorizes_input_or_invents_metrics(self):
        result = classify(PROFILE, expectations(self.request))
        self.assertEqual(('profile', 'tiktok', 'exact_text_match'), (result['screen'], result['appPattern'], result['accountStatus']))
        self.assertFalse(result['automaticInputAllowed']); self.assertFalse(result['savedDraftVerified']); self.assertIsNone(result['metrics'])

    def test_wrong_handle_homoglyph_and_wrong_platform_do_not_pass(self):
        for changes in ({'account': 'test.acc0unt'}, {'account': 'test.account1'}, {'platform': 'x'}):
            with self.subTest(changes=changes):
                self.assertNotEqual('exact_text_match', classify(PROFILE, expectations({**self.request, **changes}))['accountStatus'])
        mixed = ocr_lines(('@test.account', 130), ('@other.account', 155), ('Following', 250), ('Followers', 250), ('Likes', 250), ('Profile', 1000))
        self.assertNotEqual('exact_text_match', classify(mixed, expectations(self.request))['accountStatus'])

    def test_caption_account_mentions_do_not_establish_identity(self):
        screen = ocr_lines(('Cancel', 70), ('Post', 70), ('@test.account', 150), ('Everyone can reply', 800))
        result = classify(screen, expectations({**self.request, 'platform': 'x'}))
        self.assertEqual('draft_details', result['screen']); self.assertEqual('not_visible', result['accountStatus'])

    def test_permission_and_sharing_interruptions_override_background_app(self):
        for dialog, state in (([("Don't Allow", 700), ('Allow', 700)], 'permission_prompt'),
                              ([('New Shared Album', 100), ('Participants', 700)], 'sharing_dialog')):
            screen = ocr_lines(*[(l['text'], l['words'][0]['y']) for l in PROFILE['lines']], *dialog)
            result = classify(screen, expectations(self.request))
            self.assertEqual(state, result['screen']); self.assertIsNone(result['appPattern']); self.assertFalse(result['automaticInputAllowed'])

    def test_caption_requires_exact_text_and_draft_context(self):
        screen = ocr_lines(('New reel', 70), ('DRAFT ONLY', 200), ('Save draft', 1000), ('Share', 1000))
        expect = expectations({**self.request, 'platform': 'instagram'})
        self.assertEqual('exact_line_match', classify(screen, expect)['captionStatus'])
        self.assertEqual('needs_review', classify(screen, {**expect, 'platform': 'x'})['captionStatus'])
        screen['lines'][1]['text'] = 'DRAFTONLY'
        self.assertEqual('needs_review', classify(screen, expect)['captionStatus'])
        self.assertEqual('needs_review', classify(ocr_lines(('DRAFT ONLY', 200)), expect)['captionStatus'])

    def test_capture_persists_frame_and_duplicate_reads_never_replay(self):
        result = self.store.capture(self.request, self.kernel); count = len(self.kernel.reads)
        self.assertEqual('observed', result['state']); self.assertTrue(result['stable']); self.assertEqual('recent', result['freshness'])
        self.assertEqual(hashlib.sha256(self.kernel.raw).hexdigest(), result['frameSha256'])
        with Image.open(io.BytesIO(self.store.frame(self.request['id']))) as image: self.assertEqual((500, 1080), image.size)
        self.assertEqual(result, self.store.capture(self.request, self.kernel)); self.assertEqual(count, len(self.kernel.reads))
        with self.assertRaises(ValueError): self.store.capture({**self.request, 'account': 'different'}, self.kernel)

    def test_restart_with_uncertain_capture_keeps_review_hold_without_retry(self):
        desired = expectations(self.request); fingerprint = hashlib.sha256(json.dumps(desired, sort_keys=True).encode()).hexdigest()
        pending = {'id': self.request['id'], 'requestedAt': 1000, 'state': 'review_required', 'automaticInputAllowed': False}
        with self.store.connect() as db:
            db.execute('INSERT INTO observations VALUES (?,?,?,NULL)', (self.request['id'], fingerprint, json.dumps(pending)))
        restarted = ObservationStore(self.path, FixtureOcr(), clock=lambda: self.now[0])
        self.assertEqual('review_required', restarted.capture(self.request, self.kernel)['state']); self.assertEqual([], self.kernel.reads)

    def test_stale_missing_freshness_and_changed_receiver_are_not_hidden(self):
        good_headers = dict(self.kernel.headers)
        for age, expected in (('9999', 'stale'), (None, 'unavailable'), ('NaN', 'invalid')):
            self.kernel.headers = {} if age is None else {**good_headers, 'X-iMouse-Frame-Age-Ms': age}
            result = self.store.capture({**self.request, 'id': str(uuid.uuid4())}, self.kernel)
            self.assertEqual(expected, result['freshness']); self.assertFalse(result['automaticInputAllowed'])
        self.kernel.changing = True
        result = self.store.capture({**self.request, 'id': str(uuid.uuid4())}, self.kernel)
        self.assertFalse(result['stable']); self.assertIn('changed', result['reason'])
        self.now[0] += 16; self.assertTrue(self.store.get(result['id'])['expired'])
        self.now[0] = 999; self.assertTrue(self.store.get(result['id'])['expired'])

    def test_ocr_delay_counts_in_frame_age_and_saved_records_age_without_recapture(self):
        def slow(_): self.mono[0] += 2; return PROFILE
        with patch.object(self.store.ocr, 'read', side_effect=slow):
            result = self.store.capture(self.request, self.kernel)
        self.assertEqual('stale', result['freshness']); self.assertGreaterEqual(result['frameEvidence']['ageUpperBoundMs'], 2015)
        self.assertEqual('blocked', result['workflowReview']['status'])
        request = {**self.request, 'id': str(uuid.uuid4()), 'caption': ''}
        fresh = self.store.capture(request, self.kernel); self.assertEqual('recent', fresh['freshness'])
        self.assertEqual('ready_for_review', fresh['workflowReview']['status']); self.assertFalse(fresh['workflowReview']['automaticInputAllowed'])
        count = len(self.kernel.reads); self.mono[0] += 2
        aged = self.store.get(request['id'])
        self.assertEqual('stale', aged['freshness']); self.assertEqual(count, len(self.kernel.reads))

    def test_backend_restart_never_treats_a_saved_frame_as_current(self):
        self.store.capture(self.request, self.kernel)
        restarted = ObservationStore(self.path, FixtureOcr(), clock=lambda: self.now[0])
        count = len(self.kernel.reads); result = restarted.capture(self.request, self.kernel)
        self.assertTrue(result['expired']); self.assertEqual('unavailable', result['freshness'])
        self.assertEqual(count, len(self.kernel.reads)); self.assertEqual('blocked', result['workflowReview']['status'])

    def test_offline_and_ocr_failures_persist_and_do_not_retry(self):
        self.kernel.offline = True
        result = self.store.capture(self.request, self.kernel)
        self.assertEqual('failed', result['state']); self.assertNotIn('frame', self.kernel.reads)
        self.kernel.offline = False
        with patch.object(self.store.ocr, 'read', side_effect=ValueError('OCR unavailable')):
            second = self.store.capture({**self.request, 'id': str(uuid.uuid4())}, self.kernel)
        self.assertEqual('failed', second['state']); self.assertIn('OCR unavailable', second['reason'])
        count = len(self.kernel.reads); self.store.capture(self.request, self.kernel); self.assertEqual(count, len(self.kernel.reads))

    def test_other_targets_and_bad_expectations_refused_before_capture(self):
        for changes in ({'device_id': 'C241'}, {'platform': 'unknown'}, {'account': ''}, {'account': 'a/b'}, {'caption': '\0'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.store.capture({**self.request, **changes}, self.kernel)
        self.assertEqual([], self.kernel.reads)

    def test_older_frames_pruned_but_request_ids_still_cannot_replay(self):
        self.store.capture(self.request, self.kernel)
        for _ in range(50): self.store.capture({**self.request, 'id': str(uuid.uuid4())}, self.kernel)
        with self.assertRaises(KeyError): self.store.frame(self.request['id'])
        count = len(self.kernel.reads); self.store.capture(self.request, self.kernel)
        self.assertEqual(count, len(self.kernel.reads)); self.assertEqual(50, len(self.store.list()))


if __name__ == '__main__': unittest.main()
