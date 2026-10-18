import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
import zipfile
from unittest.mock import patch

from PIL import Image, ImageDraw
from farm_drafts import CarouselDrafts, DraftConflict
from farm_draft_verification import DraftVerifications, assess, media_comparison, caption_comparison
from farm_observations import ObservationStore
from test_farm_observations import ocr_lines


def patterned(color, number):
    image = Image.new('RGB', (1080, 1350), color); draw = ImageDraw.Draw(image)
    draw.rectangle((80, 200, 550, 390), fill='white')
    draw.ellipse((number * 100, 650, 600 + number * 100, 1180), fill='orange')
    data = io.BytesIO(); image.save(data, 'PNG'); return data.getvalue()


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.drafts = CarouselDrafts(self.root / 'drafts.db', self.root / 'stage')
        self.draft = self.drafts.create(str(uuid.uuid4()))
        for n, color in enumerate(('navy', 'green'), 1):
            self.draft = self.drafts.import_image(self.draft['id'], self.draft['revision'], str(n), base64.b64encode(patterned(color, n)).decode())
        self.draft = self.drafts.save(self.draft['id'], self.draft['revision'], self.draft['title'], 'First line\nSecond line', self.draft['slideIds'])
        with zipfile.ZipFile(io.BytesIO(self.drafts.export(self.draft['id'], self.draft['revision']))) as files:
            self.assets = [files.read('01.jpg'), files.read('02.jpg')]
        self.observations = ObservationStore(self.root / 'observations.db')
        self.reviews = DraftVerifications(self.root / 'reviews.db', self.observations, self.drafts)
        self.spec = dict(id=str(uuid.uuid4()), draft_id=self.draft['id'], revision=self.draft['revision'],
                         device_id='C24C', platform='instagram', account='test.account', observations={})
        self.captures = {}; self.n = 0
        for role in ('account_before', 'prepared', 'library', 'reopened', 'account_after'):
            self.spec['observations'][role] = [self.add_capture(role, n) for n in (range(2) if role in ('prepared', 'reopened') else range(1))]

    def add_capture(self, role, index):
        self.n += 1; observation_id = str(uuid.uuid4())
        image = Image.new('RGB', (500, 1080), 'white')
        if role in ('prepared', 'reopened'):
            with Image.open(io.BytesIO(self.assets[index])) as asset: image.paste(asset.resize((240, 300)), (20, 126))
            text = ocr_lines(('New post', 78), ('Add audio', 641), ('Tag people', 754), ('Add location', 812),
                             ('Add AI Label', 865), ('Share', 991), ('First line', 454), ('Second line', 474))
        elif role == 'library':
            with Image.open(io.BytesIO(self.assets[0])) as asset: image.paste(asset.crop((0, 135, 1080, 1215)).resize((124, 124)), (0, 112))
            text = ocr_lines(('Drafts', 78), ('Select', 78))
        else:
            text = ocr_lines(('test.account', 90), ('Posts', 180), ('Following', 180), ('Edit profile', 300), ('Share profile', 300))
        output = io.BytesIO(); image.save(output, 'PNG'); frame = output.getvalue()
        value = dict(id=observation_id, state='observed', source='simulation', expected=dict(device_id='C24C', platform='instagram', account='test.account'),
                     text=text, requestedAt=1000 + self.n * 2, completedAt=1001 + self.n * 2, observerSession='test-session',
                     resolvedDeviceId='C24C', receiverPid=10, inputGeneration=4, reviewFrameSha256=hashlib.sha256(frame).hexdigest(),
                     stable=True, inputIdle=True, freshness='recent', frameEvidence=dict(pairedMetadata=True, session='a' * 32, sequence=self.n))
        with self.observations.connect() as db: db.execute('INSERT INTO observations VALUES (?,?,?,?)', (observation_id, '', json.dumps(value), frame))
        self.captures[observation_id] = (value, frame)
        return observation_id

    def evaluate(self): return assess(self.spec, self.draft, self.assets, self.captures)
    def row(self, role, index=0): return self.captures[self.spec['observations'][role][index]][0]

    def test_account_media_caption_and_reopen_match_only_visual_evidence(self):
        result = self.evaluate()
        self.assertEqual('consistent_visual_evidence', result['status'], result['blockers'])
        self.assertEqual('simulation_or_mixed', result['source'])
        self.assertEqual([1, 2], [r['media']['matchedIndex'] for r in result['stages']['reopened']])
        for key in ('savedDraftVerified', 'automaticInputAllowed', 'accountContinuityProven'): self.assertFalse(result[key])
        self.assertFalse(result['stages']['library'][0]['appIndependentlyIdentified'])

    def test_wrong_account_or_caption_mention_cannot_establish_identity(self):
        self.row('account_after')['text']['lines'][0]['text'] = 'wrong.account'
        self.assertTrue(any('account was not read exactly' in b for b in self.evaluate()['blockers']))
        self.row('account_after')['text'] = self.row('reopened')['text']
        self.assertEqual('incomplete', self.evaluate()['status'])

    def test_missing_reordered_duplicated_or_wrong_media_blocks(self):
        original = copy.deepcopy(self.spec)
        for replacement in ([self.spec['observations']['reopened'][0]], self.spec['observations']['reopened'][::-1],
                            [self.spec['observations']['reopened'][0]] * 2):
            self.spec['observations']['reopened'] = replacement
            self.assertEqual('incomplete', self.evaluate()['status'])
            self.spec = copy.deepcopy(original)
        key = self.spec['observations']['reopened'][1]
        self.captures[key] = (self.captures[key][0], self.captures[self.spec['observations']['reopened'][0]][1])
        self.assertEqual('incomplete', self.evaluate()['status'])

    def test_caption_requires_every_line_punctuation_and_spacing(self):
        text = self.row('reopened')['text']
        for caption in ('First line', 'First line\nSecondline', 'First line\nSecond line!', 'First line\nSecond line\nHidden'):
            self.assertEqual('needs_review', caption_comparison(text, caption)['status'])
        self.assertEqual('exact_visible_lines', caption_comparison(text, 'First line\r\nSecond line')['status'])

    def test_lookalike_or_flat_media_never_establishes_identity(self):
        frame = self.captures[self.spec['observations']['prepared'][0]][1]
        self.assertEqual('ambiguous_or_different', media_comparison(frame, [self.assets[0]] * 2, 'carousel_details')['status'])
        flat = io.BytesIO(); Image.new('RGB', (500, 1080), 'blue').save(flat, 'PNG')
        self.assertEqual('insufficient_detail', media_comparison(flat.getvalue(), self.assets, 'carousel_details')['status'])
        self.assertEqual('unsupported_layout', media_comparison(frame, self.assets, 'caption_editor')['status'])

    def test_stale_capture_changed_context_time_and_sequence_are_blocked(self):
        saved = copy.deepcopy(self.captures)
        for change in ({'freshness': 'unavailable'}, {'stable': False}, {'inputIdle': False}, {'inputGeneration': 5},
                       {'receiverPid': 11}, {'observerSession': 'restart'}, {'requestedAt': 0},
                       {'completedAt': float('nan')}, {'resolvedDeviceId': 'C241'}, {'frameEvidence': {}}):
            with self.subTest(change=change):
                self.row('reopened').update(change)
                self.assertEqual('incomplete', self.evaluate()['status'])
            self.captures = copy.deepcopy(saved)

    def test_permission_dialog_and_unrelated_library_thumbnail_block(self):
        self.row('reopened')['text']['lines'] += ocr_lines(("Don't Allow", 640), ('Allow', 690))['lines']
        self.assertEqual('incomplete', self.evaluate()['status'])
        self.row('library')['text'] = ocr_lines(('Reels drafts', 78), ('Uninstall the Instagram app', 190))
        self.assertTrue(any('Library' in b for b in self.evaluate()['blockers']))

    def test_request_refuses_foreign_targets_formats_paths_verdicts_and_duplicate_ids(self):
        for change in ({'device_id': 'C241'}, {'platform': 'tiktok'}, {'savedDraftVerified': True}, {'frame_path': 'C:/private'},
                       {'observations': {'account_before': self.spec['observations']['prepared']}}):
            with self.subTest(change=change), self.assertRaises(ValueError): self.reviews.create({**self.spec, **change})
        duplicate = copy.deepcopy(self.spec); duplicate['observations']['account_after'] = duplicate['observations']['account_before']
        with self.assertRaises(ValueError): self.reviews.create(duplicate)

    def test_durable_review_retains_images_package_and_never_repeats_capture(self):
        saved = self.reviews.create(self.spec)
        with self.observations.connect() as db: db.execute('DELETE FROM observations')
        reopened = DraftVerifications(self.root / 'reviews.db', self.observations, self.drafts)
        self.assertEqual(saved, reopened.create(self.spec))
        with self.reviews.connect() as db:
            evidence, package = db.execute('SELECT evidence,package FROM reviews').fetchone()
        self.assertEqual(saved['evidenceSha256'], hashlib.sha256(evidence).hexdigest())
        self.assertEqual(saved['packageSha256'], hashlib.sha256(package).hexdigest())
        with zipfile.ZipFile(io.BytesIO(evidence)) as archive: self.assertEqual(len(self.captures) * 2, len(archive.namelist()))
        observation_id = self.spec['observations']['reopened'][0]
        self.assertEqual(self.captures[observation_id][1], reopened.frame(self.spec['id'], observation_id))
        with self.assertRaises(KeyError): reopened.frame(self.spec['id'], str(uuid.uuid4()))
        with self.assertRaises(DraftConflict): reopened.create({**self.spec, 'account': 'other.account'})
        self.assertEqual(1, len(reopened.list(self.draft['id'])))

    def test_revision_changes_refused_and_saved_review_marked_historical(self):
        self.reviews.create(self.spec)
        self.drafts.save(self.draft['id'], self.draft['revision'], 'New title', 'Changed', self.draft['slideIds'])
        self.assertTrue(self.reviews.get(self.spec['id'])['draftChangedSinceReview'])
        with self.assertRaises(DraftConflict): self.reviews.create({**self.spec, 'id': str(uuid.uuid4())})

    def test_corrupted_or_pruned_observation_is_recorded_as_missing(self):
        with self.observations.connect() as db:
            db.execute('UPDATE observations SET frame=? WHERE id=?', (b'bad', self.spec['observations']['reopened'][0]))
        result = self.reviews.create(self.spec)
        self.assertEqual('incomplete', result['assessment']['status'])
        self.assertTrue(any('checksum' in b for b in result['assessment']['blockers']))

    def test_corrupted_saved_review_package_is_never_displayed_as_verified(self):
        self.reviews.create(self.spec)
        with self.reviews.connect() as db: db.execute('UPDATE reviews SET package=?', (b'corrupt',))
        with self.assertRaisesRegex(ValueError, 'damaged'): self.reviews.get(self.spec['id'])

    def test_real_capture_checksum_and_history_are_separate_from_current_freshness(self):
        from test_farm_observations import ReadOnlyKernel, FixtureOcr
        clock = [1000.0]; store = ObservationStore(self.root / 'capture.db', FixtureOcr(), clock=lambda: clock[0], monotonic=lambda: clock[0])
        kernel = ReadOnlyKernel(); request = dict(id=str(uuid.uuid4()), device_id='C24C', platform='tiktok', account='test.account')
        record = store.capture(request, kernel); reads = list(kernel.reads)
        clock[0] += 60
        self.assertEqual('stale', store.get(request['id'])['freshness'])
        saved, frame = store.evidence(request['id'])
        self.assertEqual('recent', saved['freshness']); self.assertEqual(hashlib.sha256(frame).hexdigest(), saved['reviewFrameSha256'])
        self.assertEqual(4, saved['inputGeneration']); self.assertEqual('C24C', saved['resolvedDeviceId'])
        self.assertEqual(reads, kernel.reads)

    def test_evidence_limit_counts_ocr_records_and_never_leaves_partial_success(self):
        package_size = len(self.drafts.export(self.draft['id'], self.draft['revision']))
        first = self.spec['observations']['account_before'][0]
        value, frame = self.captures[first]
        value['text']['extraFixtureData'] = 'x' * 10000
        with self.observations.connect() as db: db.execute('UPDATE observations SET document=? WHERE id=?', (json.dumps(value), first))
        with patch('farm_draft_verification.MAX_EVIDENCE_BYTES', package_size + len(frame) + 1000):
            with self.assertRaisesRegex(ValueError, 'no partial'): self.reviews.create(self.spec)
        with self.assertRaises(KeyError): self.reviews.get(self.spec['id'])


if __name__ == '__main__': unittest.main()
