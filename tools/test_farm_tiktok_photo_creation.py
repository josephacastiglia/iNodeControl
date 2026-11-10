"""TikTok photo creation/verification against A20 calibration frames and a simulated HID kernel.

No socket, desktop or phone access. Screens are the 4 Nov A20 (C214) calibration frames with their
OCR, kept in the private evidence archive (they show the signed-in account); the tests skip without
it. Synthetic parts are labelled: the Drafts count rows read in OCR before and after the save, and a
Drafts grid whose first tile is replaced by the package's first slide (the calibration post was
discarded, not saved). This tests the protocol and recognizers on known layouts, not phone acceptance.
"""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import uuid
import zipfile
from unittest.mock import patch

from PIL import Image, ImageOps

import farm_test_network  # noqa: F401  Refuse every real socket in this process.
import farm_paths
from farm_owned_capture import InspectionStopped
from farm_draft_workflow import references
from farm_image import ImageReference
from farm_observations import ObservationStore
from farm_phone_identity import PhoneIdentity
import farm_tiktok_photo_layout as ph
from farm_tiktok_photo_creation import TikTokPhotoCreationWorkflow, TikTokPhotoVerification, COMMITTING

CAL = farm_paths.ARCHIVE/'20261104-tiktok-photo-calibration'
PRIVATE = (CAL/'frames'/'s29-sel3.png').exists() and (CAL/'account.txt').exists()
CAPTION = 'Calib tiktok photo'
DOWNLOAD = 'imouse-tp-cpmvey'
URL = 'http://192.168.4.26:9927/t/fixture-token/'
DEVICE = '02:00:00:00:00:20'
PHONE = PhoneIdentity(board='C214', device_id=DEVICE, receiver='iMouse2-20', slot=20)


def png(image):
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


def line(text, x, y, width=None, height=14):
    words, cursor = [], x
    for part in text.split(' '):
        w = max(8, round((width or len(text)*8) * len(part)/max(1, len(text))))
        words.append(dict(text=part, x=cursor, y=y, width=w, height=height)); cursor += w + 6
    return dict(text=text, words=words)


class Screens:
    """Calibration frames/OCR keyed by fixture state. Built once per test class."""
    def __init__(self):
        self.frames, self.texts = {}, {}
        def load(key, name):
            self.frames[key] = (CAL/'frames'/f'{name}.png').read_bytes()
            self.texts[key] = json.loads((CAL/'frames'/f'{name}.json').read_text(encoding='utf-8'))
        for key, name in (('home', 's18-home'), ('search', 's19-search'), ('query', 's20-query'), ('splash', 's21-tiktok'),
                          ('feed', 's22-tiktok'), ('safari', 's01-safari'), ('address', 's02-address'), ('index', 's04-index'),
                          ('copied', 's05-copied'), ('slide1', 's06-slide1'), ('slide2', 's11-slide2'), ('slide3', 's15-slide3'),
                          ('menu1', 's09-menu1b'), ('menu2', 's13-menu2b'), ('menu3', 's16-menu3'), ('camera', 's25-camera2'),
                          ('picker0', 's26-picker'), ('picker1', 's27-sel1'), ('picker2', 's28-sel2'), ('picker3', 's29-sel3'),
                          ('editor_a', 's30-editor'), ('editor_b', 's30b-editor'), ('details', 's31-details'),
                          ('description', 's32-focus'), ('paste_menu', 's33-pastemenu'), ('pasted', 's34-pasted'),
                          ('details_filled', 's35-back'), ('profile', 's42-profile'), ('drafts_video', 's41-drafts')):
            load(key, name)
        self.account = (CAL/'account.txt').read_text(encoding='utf-8').strip()
        with zipfile.ZipFile(CAL/'package.zip') as archive:
            self.slides = [archive.read(f'{n:02}.jpg') for n in (1, 2, 3)]
        self.reference = ImageReference(self.slides)
        # Synthetic: the Drafts count read in OCR (4 before, 5 after; full-frame OCR missed it on A20).
        plain = self.texts['profile']
        for key, count in (('profile', 4), ('profile_after', 5)):
            self.frames[key] = self.frames['profile']
            text = copy.deepcopy(plain); text['lines'].append(line(f'Drafts: {count}', 9, 378, 70))
            self.texts[key] = text
        # Synthetic: Drafts grid whose first tile is the package's first slide (a 3:4 cover).
        with Image.open(io.BytesIO(self.frames['drafts_video'])) as base, Image.open(io.BytesIO(self.slides[0])) as slide:
            grid = base.convert('RGB'); left, top, right, bottom = 0, 238, 163, 453
            grid.paste(ImageOps.fit(slide.convert('RGB'), (right-left-4, bottom-top-4)), (left+2, top+2))
            self.frames['drafts'] = png(grid)
        self.texts['drafts'] = copy.deepcopy(self.texts['drafts_video'])
        self.texts['drafts']['lines'].append(line('Talking Body', 20, 420, 90))
        # The Top Hit label 'TikTok' that full-frame OCR missed on s20 is found by the enlarged read (4 Nov).


class FixtureOcr:
    def __init__(self, kernel): self.kernel = kernel
    def read(self, raw):
        k = self.kernel
        text = copy.deepcopy(k.screens.texts[k.frame_key]); text['frameSha256'] = hashlib.sha256(raw).hexdigest()
        if k.scenario == 'wrong_caption' and k.frame_key == 'details_filled':
            for row in text['lines']:
                if row['text'] == CAPTION: row['text'] = 'Calib tiktok phot'
        if k.scenario == 'wrong_account' and k.frame_key.startswith('profile'):
            for row in text['lines']:
                for word in row['words']: word['text'] = word['text'].replace(k.screens.account, 'other.account')
                row['text'] = row['text'].replace(k.screens.account, 'other.account')
        return text


class FixtureKernel:
    _is_live_http = False
    phone = PHONE

    def __init__(self, screens, scenario='normal', saved=False):
        self.screens, self.scenario = screens, scenario
        self.screen = 'profile_after' if saved else 'profile'; self.leg = 'out'
        self.saves = 1 if saved else 0; self.photos = []; self.owned = False; self.selected = 0; self.slide = 1
        self.generation, self.sequence, self.now = 4, 100, 1000.
        self.session = uuid.uuid4().hex; self.calls = []; self.typed = ''; self.unexpected = []
        self.pointer = None; self.frame_key = None; self.captures = {}; self.resets = 0; self.last_reset = False
        self.clicked = []   # (screen, x, y) of every click.
        self.holds = {}

    def clock(self): self.now += .001; return self.now
    def pause(self, seconds): self.now += seconds
    def resolve_device_id(self, phone):
        if phone != 'C214': raise AssertionError('Other phone addressed')
        return DEVICE
    def receiver(self):
        return dict(deviceid=DEVICE, name='iMouse2-20', receiver_pid=321, receiver_restarts=0, live=True, frames=self.sequence,
                    frame_session=self.session)
    def kernel_status(self):
        return dict(code=0, build_identity=dict(sha256='a'*64), input_leases_required=True, allowed=['C214'],
                    process=dict(pid=123, started_utc='fixture'), receivers=[self.receiver()])
    def devices(self): return [dict(deviceid=DEVICE, pid='C214', uid='fixture-uid')]
    def input_status(self):
        return {DEVICE: dict(id=DEVICE, generation=self.generation, owned=self.owned, active=False, stopped=False,
                             releasing=False, release_failed=False, lease_remaining_ms=30000)}
    def preflight_phone(self, phone):
        if self.owned: raise AssertionError('Takeover')
        return dict(resolved_id=self.resolve_device_id(phone), receiver=self.receiver())
    def acquire(self, phones, lease_ms):
        assert phones == ['C214'] and not self.owned
        self.owned = True; return {'C214': 'fixture-token'}
    def renew_if_needed(self, tokens, min_remaining_ms): assert tokens == {'C214': 'fixture-token'} and self.owned
    def release(self, tokens):
        assert tokens == {'C214': 'fixture-token'}; self.owned = False; self.generation += 1; self.calls.append('release')

    def key(self):
        s = self.screen
        n = self.captures.get(s, 0)
        if s == 'tiktok': return 'splash' if n < 1 else 'feed'
        if s == 'editor': return 'editor_a' if n % 2 == 0 else 'editor_b'
        if s.startswith('slide') and self.scenario == 'wrong_slide' and s == 'slide2': return 'slide1'
        return s

    def shot(self, phone):
        self.resolve_device_id(phone)
        self.frame_key = self.key(); self.captures[self.screen] = self.captures.get(self.screen, 0) + 1
        return self.screens.frames[self.frame_key], {'X-iMouse-Frame-Session': self.session, 'X-iMouse-Frame-Sequence': str(self.sequence),
                                                     'X-iMouse-Frame-Age-Ms': '0', 'X-iMouse-Frame-Delivery': 'flowing'}

    def send(self, phone, token, fun, **data):
        assert phone == 'C214' and token == 'fixture-token' and self.owned
        self.calls.append((fun, dict(data)))
        if fun == '/mouse/reset':
            self.pointer = None; self.sequence += 1; self.resets += 1; self.last_reset = True; return dict(code=0)
        if fun == '/mouse/move':
            if self.pointer != (data['x'], data['y']): self.pointer = (data['x'], data['y']); self.sequence += 1
            return dict(code=0)
        if fun == '/mouse/down': return dict(code=0)
        if fun == '/mouse/up':
            # A hold works only after a reset with no tap in between (A20, 4 Nov).
            held = self.screen
            self.holds[held] = self.holds.get(held, 0) + 1
            if self.scenario in ('hold_ignored', 'hold_ignored_twice') and held.startswith('slide') and (
                    self.holds[held] == 1 or self.scenario == 'hold_ignored_twice'):
                return dict(code=0)   # The press opened nothing (A20, 4 Nov); the page is unchanged.
            if self.last_reset: self.transition('hold', *self.pointer)
            return dict(code=0)
        if fun == '/mouse/click':
            self.pointer = (data['x'], data['y']); self.last_reset = False; self.clicked.append((self.screen, data['x'], data['y']))
            self.transition('click', data['x'], data['y']); return dict(code=0)
        if fun == '/key/sendkey':
            if 'key' in data:
                if self.screen == 'address': self.typed += data['key']
                elif self.screen == 'search': self.screen = 'query'
                else: raise AssertionError('Typing outside a field')
                return dict(code=0)
            self.transition('key:' + data['fn_key']); return dict(code=0)
        raise AssertionError('Unapproved function ' + fun)

    def transition(self, kind, x=None, y=None):
        near = lambda tx, ty, r=14: x is not None and abs(x-tx) <= r and abs(y-ty) <= r
        s = self.screen
        table = [
            ('profile', 'key:Home', None, 'home'),
            ('home', 'click', (422, 508), 'safari'),
            ('safari', 'click', (245, 953), 'address'),
            ('index', 'click', (102, 846), 'copied'),
            ('copied', 'click', (250, 124), 'slide1'),
            ('slide1', 'hold', (250, 536), 'menu1'), ('slide2', 'hold', (250, 536), 'menu2'), ('slide3', 'hold', (250, 536), 'menu3'),
            ('menu1', 'click', (188, 898), 'slide1'), ('menu2', 'click', (188, 898), 'slide2'), ('menu3', 'click', (188, 898), 'slide3'),
            ('slide1', 'click', (238, 878), 'slide2'), ('slide2', 'click', (238, 878), 'slide3'),
            ('slide3', 'key:Home', None, 'home'),
            ('home', 'click', (250, 899), 'search'),
            ('search', 'click', (88, 169), 'tiktok'),   # TikTok among the Siri suggestions (enlarged read).
            ('query', 'click', (87, 217), 'tiktok'),
            ('tiktok', 'click', (450, 1005), 'profile'),
            ('profile', 'click', (250, 1009), 'camera'),
            ('camera', 'click', (40, 1000), 'picker0'),
            ('picker0', 'click', (144, 825), 'picker1'), ('picker1', 'click', (310, 678), 'picker2'),
            ('picker2', 'click', (477, 678), 'picker3'), ('picker3', 'click', (370, 1007), 'editor'),
            ('editor', 'click', (367, 1006), 'details'),
            ('details', 'click', (200, 345), 'description'),
            ('description', 'hold', (80, 266), 'paste_menu'),
            ('paste_menu', 'click', (68, 209), 'pasted'),
            ('pasted', 'click', (27, 84), 'details_filled'),
            ('details_filled', 'click', (130, 1005), 'profile_after'),
            ('profile_after', 'click', (79, 478), 'drafts'),
            ('drafts', 'click', (30, 85), 'profile_after'),
        ]
        if s == 'address' and kind == 'key:Enter':
            assert self.typed == URL, self.typed
            self.screen = 'index'; return
        for state, k, target, after in table:
            if state == s and k == kind and (target is None or near(*target)):
                if s == 'home' and self.leg == 'out' and after == 'search': continue
                if s == 'home' and self.leg == 'back' and after == 'safari': continue
                if s.startswith('menu'): self.photos.append(s)
                if s == 'slide3' and kind == 'key:Home': self.leg = 'back'
                if s == 'details_filled':
                    self.saves += 1
                    if self.scenario == 'lost_save': self.screen = after; raise TimeoutError('Fixture Drafts happened; answer lost.')
                self.screen = after; return
        self.unexpected.append((s, kind, x, y))
        raise AssertionError(f'Unexpected {kind} at {(x, y)} on {s}')


@unittest.skipUnless(PRIVATE, 'The private A20 calibration frames are not in the evidence archive.')
class TikTokPhotoProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.screens = Screens()

    def fixture(self, scenario='normal', saved=False, verifier=False):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        kernel = FixtureKernel(self.screens, scenario, saved)
        store = ObservationStore(folder/'observations.sqlite3', ocr=FixtureOcr(kernel), clock=kernel.clock, monotonic=kernel.clock,
                                 retained_limit=160)
        options = dict(account=self.screens.account, package_hash='b'*64, monotonic=kernel.clock, pause=kernel.pause, allowed=['C214'])
        reference = self.screens.reference
        if verifier:
            flow = TikTokPhotoVerification(folder, kernel, store, reference, CAPTION, references(), 'a'*64, 'fixture-uid', **options)
        else:
            flow = TikTokPhotoCreationWorkflow(folder, kernel, store, reference, CAPTION, references(), 'a'*64, 'fixture-uid',
                transfer_url=URL, transfer_title='TikTok photo draft', package_name=DOWNLOAD, slides=['01.jpg', '02.jpg', '03.jpg'],
                **options)
        return flow, kernel

    @staticmethod
    def semantic(kernel):
        return [c for c in kernel.calls if isinstance(c, tuple) and (c[0] in ('/mouse/click', '/mouse/up') or
                (c[0] == '/key/sendkey' and 'fn_key' in c[1] and c[1]['fn_key'] != 'Enter'))]

    def test_creation_then_read_only_verification_pass_on_a20_layouts(self):
        flow, kernel = self.fixture(); result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error'))
        self.assertEqual([], kernel.unexpected); self.assertEqual(1, kernel.saves)
        self.assertEqual(['menu1', 'menu2', 'menu3'], kernel.photos); self.assertEqual('profile_after', kernel.screen)
        self.assertEqual('confirmed', result['cleanup']); self.assertFalse(kernel.owned)
        self.assertEqual(dict(before=4, after=5), result['draftsCount'])
        self.assertEqual([1, 2, 3], [t['slide'] for t in result['pickerTiles']])
        self.assertEqual(dict(observed='attached', label='Talking Body', kept=True, removed=False), result['sound'])
        self.assertTrue(all(a['state'] == 'answered' for a in result['actions']))
        # The sound pill is never touched; every hold follows a pointer reset.
        self.assertEqual([('editor', 367, 1006)], [c for c in kernel.clicked if c[0] == 'editor'])   # Next only; never the pill.
        self.assertFalse(any(s.startswith('details') and 255 <= x <= 485 and y >= 977 for s, x, y in kernel.clicked))   # Never Post.
        self.assertEqual(5, kernel.resets)   # The initial reset and one before each of the four holds.
        flow2, kernel2 = self.fixture(saved=True, verifier=True)
        verified = flow2.run()
        self.assertEqual('validation_passed', verified['state'], verified.get('error'))
        self.assertTrue(verified['savedDraftVerified']); self.assertFalse(verified['reopened']); self.assertEqual(1, kernel2.saves)
        self.assertEqual([0, 238, 163, 453], verified['draftTile']['tile']); self.assertEqual(4, verified['draftTile']['tiles'])
        self.assertEqual('consistent_sampled_history', verified['accountHistory']['status'])

    def test_lost_answer_at_every_creation_action_stops_without_replay(self):
        flow, kernel = self.fixture(); flow.run(); total = len(self.semantic(kernel))
        self.assertGreater(total, 25)
        # Every committing action and a spread of the others (each run reads frames with real OCR bands).
        labels = [c for c in self.semantic(kernel)]
        boundaries = sorted(set(range(1, total+1, 5)) | {total} | {i+1 for i, c in enumerate(labels) if c[0] == '/mouse/up'})
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                flow, kernel = self.fixture(); original = kernel.send
                def send(phone, token, fun, **data):
                    value = original(phone, token, fun, **data)
                    if len(self.semantic(kernel)) == boundary and fun in ('/mouse/click', '/mouse/up', '/key/sendkey') and (
                            fun != '/key/sendkey' or data.get('fn_key') not in (None, 'Enter')):
                        raise TimeoutError('Fixture action happened; answer lost.')
                    return value
                with patch.object(kernel, 'send', send): result = flow.run()
                self.assertEqual('review_required', result['state'])
                self.assertEqual(boundary, len(self.semantic(kernel)))
                self.assertEqual('outcome_unknown', result['actions'][-1]['state'])
                self.assertEqual('release', kernel.calls[-1]); self.assertLessEqual(kernel.saves, 1)
                self.assertEqual(len(kernel.photos), len(set(kernel.photos)))

    def test_an_ignored_hold_is_pressed_once_more_and_never_a_third_time(self):
        flow, kernel = self.fixture('hold_ignored'); result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error'))
        self.assertEqual([1, 2, 3], result['holdRetries']); self.assertEqual(['menu1', 'menu2', 'menu3'], kernel.photos)
        flow, kernel = self.fixture('hold_ignored_twice'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual([], kernel.photos)
        self.assertEqual(2, kernel.holds['slide1']); self.assertEqual(0, kernel.saves)

    def test_lost_drafts_answer_is_never_repeated(self):
        flow, kernel = self.fixture('lost_save'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(1, kernel.saves)
        self.assertEqual('save-tiktok-photo-draft-once', result['actions'][-1]['label'])
        self.assertEqual('outcome_unknown', result['actions'][-1]['state'])

    def test_faults_stop_before_the_draft(self):
        for scenario in ('wrong_slide', 'wrong_caption', 'wrong_account'):
            with self.subTest(scenario=scenario):
                flow, kernel = self.fixture(scenario); result = flow.run()
                self.assertEqual('review_required', result['state'])
                self.assertIn(result['cleanup'], ('confirmed', 'not_needed')); self.assertFalse(kernel.owned)
                self.assertEqual(0, kernel.saves); self.assertEqual([], kernel.unexpected)
        flow, kernel = self.fixture('wrong_slide'); result = flow.run()
        self.assertEqual(['menu1'], kernel.photos)   # Slide 2's page showed slide 1: nothing more was saved.
        flow, kernel = self.fixture('wrong_account'); result = flow.run()
        self.assertEqual([], [c for c in kernel.calls if isinstance(c, tuple)])   # Refused before the lease.

    def test_verifier_refuses_the_wrong_account(self):
        flow, kernel = self.fixture('wrong_account', saved=True, verifier=True); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertFalse(result['savedDraftVerified'])

    def test_committing_purposes_name_real_creation_actions(self):
        flow, kernel = self.fixture(); flow.run()
        labels = [a['label'] for a in flow.record['actions']]
        for prefix in COMMITTING: self.assertTrue(any(l.startswith(prefix) for l in labels), prefix)


class TikTokPhotoUnitTests(unittest.TestCase):
    def test_caption_and_slide_arguments_are_checked_before_any_transport(self):
        class Kernel: phone = PHONE; _is_live_http = False
        with tempfile.TemporaryDirectory() as directory:
            jpegs = []
            for colour in ((10, 20, 30), (200, 10, 10)):
                out = io.BytesIO(); Image.new('RGB', (1080, 1920), colour).save(out, 'JPEG'); jpegs.append(out.getvalue())
            reference = ImageReference(jpegs)
            base = dict(transfer_url=URL, transfer_title='TikTok photo draft', package_name=DOWNLOAD, account='a', package_hash='b'*64)
            for caption, slides, title in (('x'*25, ['01.jpg', '02.jpg'], 'TikTok photo draft'), ('ok', ['01.jpg'], 'TikTok photo draft'),
                                           ('ok', ['02.jpg', '01.jpg'], 'TikTok photo draft'), ('ok', ['01.jpg', '02.jpg'], 'X image draft')):
                with self.assertRaises(InspectionStopped):
                    TikTokPhotoCreationWorkflow(directory, Kernel(), None, reference, caption, {}, 'a'*64, 'u',
                                                **dict(base, slides=slides, transfer_title=title))

    def test_placeholder_reads(self):
        self.assertTrue(ph._placeholder(['riting a long description can help get 3x more', 'Views on average.']))
        self.assertTrue(ph._placeholder(['Writing a long description can help get 3x more', 'views on average.']))
        self.assertFalse(ph._placeholder(['Calib tiktok photo']))


if __name__ == '__main__':
    unittest.main()
