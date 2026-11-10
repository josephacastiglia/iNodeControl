"""Read-only screen verification and restart holds; fixtures contain no private accounts."""
from farm_phone_identity import LEGACY_C24C
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
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
    phone = LEGACY_C24C   # Fixtures model the single-phone C24C window.
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
    def read(self, raw): return {**PROFILE, 'frameSha256': hashlib.sha256(raw).hexdigest()}


class ObservationTests(unittest.TestCase):
    def test_creation_retention_preserves_early_frames_and_rejects_unbounded_limits(self):
        with self.assertRaises(ValueError): ObservationStore(self.path,retained_limit=161)
        store=ObservationStore(self.path.with_name('creation.db'),FixtureOcr(),retained_limit=160)
        first=None
        for number in range(51):
            request=dict(self.request,id=str(uuid.uuid4()))
            result=store.capture(request,self.kernel)
            self.assertEqual('observed',result['state'])
            if first is None:first=request['id']
        self.assertTrue(store.frame(first))

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

    def test_tiktok_profile_likes_dropped_by_full_frame_ocr_is_reread_enlarged_in_place(self):
        # A20, 4 Nov: full-frame OCR drops 'Likes'; only the counter band is read again, enlarged.
        dropped = ocr_lines(*[(l['text'], l['words'][0]['y']) for l in PROFILE['lines'] if l['text'] != 'Likes'])
        self.assertEqual('unknown', classify(dropped, expectations(self.request))['screen'])   # No frame: no reread.
        frame = b'frame'
        for words, screen in (([('Following', 20, 235, 90, 250), ('Likes', 205, 235, 245, 250)], 'profile'),
                              ([('Likes', 120, 235, 160, 250)], 'unknown'),                         # Not in its own place.
                              ([('Likes', 205, 235, 245, 250), ('Likes', 210, 236, 250, 251)], 'unknown'),
                              ([], 'unknown')):
            with self.subTest(words=words), patch('farm_reel_layout.band_words', return_value=words) as band:
                result = classify(dropped, expectations(self.request), frame)
                self.assertEqual(screen, result['screen'])
                band.assert_called_once_with(frame, (10, 205, 300, 262), 3)
                if screen == 'profile':
                    self.assertEqual(('tiktok', 'exact_text_match'), (result['appPattern'], result['accountStatus']))
        with patch('farm_reel_layout.band_words', side_effect=ValueError('OCR failed')):
            self.assertEqual('unknown', classify(dropped, expectations(self.request), frame)['screen'])
        with patch('farm_reel_layout.band_words') as band:   # Full-frame 'Likes' read: no extra OCR.
            self.assertEqual('profile', classify(PROFILE, expectations(self.request), frame)['screen'])
            band.assert_not_called()

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

    def test_interval_audits_the_boundary_phone_not_only_c24c(self):
        # Until 4 Nov the interval kept only C24C records, so verifiers on 724E/C214 audited 0 observations.
        with self.store.connect(): pass   # Creates the table.
        frame = b'frame-bytes'; digest = hashlib.sha256(frame).hexdigest(); ids = {}
        def put(name, board):
            ids[name] = str(uuid.uuid4())
            value = dict(id=ids[name], expected=dict(device_id=board), reviewFrameSha256=digest)
            db = sqlite3.connect(self.path)
            try:
                with db: db.execute('INSERT INTO observations VALUES (?,?,?,?)', (ids[name], 'f', json.dumps(value), frame))
            finally: db.close()   # Windows cannot remove the temporary folder over an open handle.
        for name, board in (('first', 'C214'), ('other', '724E'), ('middle', 'C214'), ('last', 'C214'), ('foreign', '724E')):
            put(name, board)
        timeline = self.store.interval(ids['first'], ids['last'])
        self.assertEqual([ids['first'], ids['middle'], ids['last']], [v['id'] for v, _ in timeline])
        self.assertTrue(all(f == frame for _, f in timeline))
        with self.assertRaises(ValueError): self.store.interval(ids['first'], ids['foreign'])   # Boundaries on two phones.
        with self.assertRaises(ValueError): self.store.interval(ids['last'], ids['first'])      # Out of order.

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
        def slow(raw): self.mono[0] += 2; return FixtureOcr().read(raw)
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

    def test_capture_rejects_missing_or_wrong_ocr_frame_digest(self):
        for digest in (None, 'f' * 64):
            with self.subTest(digest=digest), patch.object(self.store.ocr, 'read', return_value={**PROFILE, 'frameSha256': digest}):
                result = self.store.capture({**self.request, 'id': str(uuid.uuid4())}, self.kernel)
            self.assertEqual('failed', result['state']); self.assertIn('exact captured frame', result['reason'])
            self.assertFalse(result['automaticInputAllowed']); self.assertNotIn('text', result)


class OcrBridgeTests(unittest.TestCase):
    """WindowsOcr against a stand-in for its PowerShell process: what it submits and what it refuses."""
    def setUp(self):
        stream = io.BytesIO(); Image.new('RGB', (500, 1080), 'black').save(stream, format='BMP')
        self.raw = stream.getvalue()

    def test_real_ocr_bridge_checks_the_image_digest_returned_by_its_process(self):
        def reply(arguments, **kwargs):
            image_path = Path(arguments[arguments.index('-ImagePath')+1])
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            control_path = Path(arguments[arguments.index('-ControlImagePath')+1])
            value = dict(width=500, height=1080, lines=[], imageSha256=digest,
                         control=dict(width=129, height=117, lines=[], imageSha256=hashlib.sha256(control_path.read_bytes()).hexdigest()))
            return subprocess.CompletedProcess(arguments, 0, json.dumps(value).encode(), b'')
        with patch('farm_observations.subprocess.run', side_effect=reply) as process: value = WindowsOcr(next_control=True).read(self.raw)
        self.assertEqual(1, process.call_count)
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), value['frameSha256'])
        wrong = dict(width=500, height=1080, lines=[], imageSha256='f'*64)
        with patch('farm_observations.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(wrong).encode(), b'')):
            with self.assertRaisesRegex(ValueError, 'exact submitted image'): WindowsOcr(next_control=True).read(self.raw)

    def test_ocr_batch_rejects_missing_swapped_or_mis_sized_control(self):
        def reply(arguments, **kwargs):
            image = Path(arguments[arguments.index('-ImagePath')+1]).read_bytes()
            control = Path(arguments[arguments.index('-ControlImagePath')+1]).read_bytes()
            detail = dict(width=129, height=117, lines=[], imageSha256=hashlib.sha256(control).hexdigest())
            if problem == 'swapped': detail['imageSha256'] = hashlib.sha256(image).hexdigest()
            elif problem == 'dimensions': detail['width'] = 128
            elif problem == 'missing': detail = None
            value = dict(width=500, height=1080, lines=[], imageSha256=hashlib.sha256(image).hexdigest(), control=detail)
            return subprocess.CompletedProcess(arguments, 0, json.dumps(value).encode(), b'')
        for problem in ('missing', 'swapped', 'dimensions'):
            with self.subTest(problem=problem), patch('farm_observations.subprocess.run', side_effect=reply):
                with self.assertRaises(ValueError): WindowsOcr(next_control=True).read(self.raw)

    def test_only_a_reader_that_asks_has_the_next_label_crop_read(self):
        seen = []
        def reply(arguments, **kwargs):
            seen.append(list(arguments))
            image = Path(arguments[arguments.index('-ImagePath')+1]).read_bytes()
            value = dict(width=500, height=1080, lines=[], imageSha256=hashlib.sha256(image).hexdigest())
            if '-ControlImagePath' in arguments:
                control = Path(arguments[arguments.index('-ControlImagePath')+1]).read_bytes()
                value['control'] = dict(width=129, height=117, lines=[], imageSha256=hashlib.sha256(control).hexdigest())
            return subprocess.CompletedProcess(arguments, 0, json.dumps(value).encode(), b'')
        with patch('farm_observations.subprocess.run', side_effect=reply):
            plain = WindowsOcr().read(self.raw)
            asked = WindowsOcr(next_control=True).read(self.raw)
        self.assertNotIn('-ControlImagePath', seen[0]); self.assertIn('-ControlImagePath', seen[1])
        self.assertEqual(seen[0][:seen[0].index('-ImagePath')], seen[1][:seen[1].index('-ImagePath')])   # The same reader otherwise.
        self.assertEqual(plain, asked); self.assertNotIn('control', plain); self.assertNotIn('controlOcr', plain)
        self.assertFalse(WindowsOcr().next_control)

    def test_the_carousel_readers_ask_and_the_lanes_do_not(self):
        import inspect
        import farm_creation_runs
        import farm_reel_runs
        import imouse_farm_server as server
        with tempfile.TemporaryDirectory() as directory:
            runtime = server.FarmBackendRuntime(Path(directory) / 'farm.db', Path(directory) / 'stage')
            self.addCleanup(runtime.transfers.close)
            self.assertTrue(runtime.observations.ocr.next_control)
            self.assertIs(runtime.observations, runtime.verifications.observations)
        self.assertIn("WindowsOcr(next_control=True)", inspect.getsource(farm_creation_runs.CreationRuns.execute))
        self.assertNotIn('WindowsOcr', inspect.getsource(farm_reel_runs.ReelCreationRuns.execute))   # The six lanes read once.
        self.assertFalse(ObservationStore(Path(self.enterContext(tempfile.TemporaryDirectory())) / 'o.db').ocr.next_control)


if __name__ == '__main__': unittest.main()


import farm_paths as _paths  # noqa: E402
from farm_observations import instagram_new_account_profile  # noqa: E402

A14 = _paths.ARCHIVE/'20261105-fleet-a14'


def _line(text, x, y, w, h=20):
    return dict(text=text, words=[dict(text=text, x=x, y=y, width=w, height=h)])


def _profile(*lines):
    return dict(width=500, height=1080, lines=[_line(*l) for l in lines])


# A14's new-account profile geometry (5 Nov): header handle, name, Add banners, Edit profile | Share profile.
NEW_PROFILE = (('demo.account v', 172, 78, 156), ('Demo', 150, 143, 40), ('+ Add banners', 31, 271, 107),
               ('Edit profile', 90, 318, 87), ('Share profile', 315, 318, 103))


class InstagramNewAccountProfileTests(unittest.TestCase):
    def test_new_account_profile_and_chevron(self):
        text = _profile(*NEW_PROFILE)
        result = classify(text, dict(platform='instagram', account='demo.account', caption=''))
        self.assertEqual(('profile', 'new_account_profile', 'exact_text_match'),
                         (result['screen'], result['layout'], result['accountStatus']))
        other = classify(text, dict(platform='instagram', account='other.account', caption=''))
        self.assertEqual('different_text', other['accountStatus'])

    def test_near_misses_are_not_profiles(self):
        cases = {
            'stacked buttons': (NEW_PROFILE[0], ('Edit profile', 90, 318, 87), ('Share profile', 90, 380, 103)),
            'no header': NEW_PROFILE[1:],
            'buttons low': (NEW_PROFILE[0], ('Edit profile', 90, 700, 87), ('Share profile', 315, 700, 103)),
            'edit only (X)': (NEW_PROFILE[0], ('Edit profile', 350, 318, 90)),
            'tiktok Edit': (NEW_PROFILE[0], ('Edit', 230, 318, 40), ('Share profile', 315, 318, 103)),
            'swapped': (NEW_PROFILE[0], ('Share profile', 90, 318, 103), ('Edit profile', 315, 318, 87)),
        }
        for name, lines in cases.items():
            with self.subTest(name):
                self.assertFalse(instagram_new_account_profile(_profile(*lines)))
                self.assertNotEqual('profile', classify(_profile(*lines), dict(platform='instagram', account='demo.account', caption=''))['screen'])

    def test_the_note_bubble_is_not_a_handle(self):
        text = _profile(('Note...', 35, 130, 43), *NEW_PROFILE)
        result = classify(text, dict(platform='instagram', account='demo.account', caption=''))
        self.assertEqual(('exact_text_match', ['demo.account']), (result['accountStatus'], result['observedHandles']))

    def test_chevron_only_dropped_on_a_profile(self):
        text = _profile(('demo.account v', 172, 78, 156), ('Search', 30, 500, 80))
        self.assertEqual('not_visible', classify(text, dict(platform='instagram', account='demo.account', caption=''))['accountStatus'])

    @unittest.skipUnless((A14/'ig-profile.bmp').exists(), 'A14 frames of 5 Nov are not available in this checkout.')
    def test_a14_frame(self):
        text = json.loads((A14/'ig-profile.json').read_text(encoding='utf-8'))
        account = (A14/'ig-account.txt').read_text(encoding='utf-8').strip()
        result = classify(text, dict(platform='instagram', account=account, caption=''), (A14/'ig-profile.bmp').read_bytes())
        self.assertEqual(('profile', 'new_account_profile', 'exact_text_match'),
                         (result['screen'], result['layout'], result['accountStatus']))
