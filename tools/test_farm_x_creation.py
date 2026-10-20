"""X creation/verification against retained C24C screens and a simulated HID kernel.

No socket, desktop or phone access. X screens are retained 17 Oct frames (image
route 28-45, video route 114-130) with their OCR; Safari/Files screens are the
retained 17 Oct video-transfer frames and 19 Oct Home/Safari frames. Synthetic
parts are labelled: the transfer page, the Paste callout and a later playback
frame of the reopened card. The signed-in handle is read from the retained menu
frame at run time and is never written into this file. This tests the protocol
and recognizers on known layouts. It is not fresh-phone acceptance.
"""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from PIL import Image, ImageDraw

import farm_test_network  # noqa: F401  Refuse every real socket in this process.
import farm_tiktok_layout as tt
from farm_draft_workflow import references
from farm_observations import ObservationStore
from farm_x_creation import XCreationWorkflow, XVerification, COMMITTING, PENDING, guard
from farm_carousel_inspection import InspectionStopped
from imouse_social_automation import LIVE_TEST_DEVICE_ID

ROOT = Path(__file__).resolve().parents[1]
R17 = ROOT/'analysis/farm-platform-drafts-20261017'
OCR_SAFARI = ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-reel-offline/ocr-20261017'
OCR_X = ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-x-offline/ocr-20261017'
P1 = ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-new-draft/backend/draft-creations/b8c155e2-1670-4f60-a090-aeff921e162e'
PRIVATE = all(p.exists() for p in (R17/'normalized-test.mp4', OCR_SAFARI, OCR_X, P1/'record.json'))
CAPTION = 'IMOUSE-VlDEO-DRAFT-TEST-20261017'   # The retained frames' exact OCR form (32 characters).
URL = 'http://192.168.50.2:9917/t/fixture-token/'
VIDEO_BYTES = 78953
DOWNLOAD = 'imouse-x-acdefh'


def png(image):
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


def line(text, x, y, width=None, height=18):
    words, cursor = [], x
    for part in text.split(' '):
        w = max(8, round((width or len(text)*9) * len(part)/max(1, len(text))))
        words.append(dict(text=part, x=cursor, y=y, width=w, height=height)); cursor += w + 6
    return dict(text=text, words=words)


class Screens:
    def __init__(self):
        self.frames, self.texts = {}, {}
        p1 = json.loads((P1/'record.json').read_text(encoding='utf-8'))
        by_frame = {e['frame']: e['observation']['text'] for e in p1['observations'] if e.get('state') == 'observed'}
        def p1_state(key, name):
            self.frames[key] = (P1/name).read_bytes(); self.texts[key] = copy.deepcopy(by_frame[name])
        def r17(key, step, which='after', ocr=OCR_X):
            self.frames[key] = (R17/step/(which+'.png')).read_bytes()
            text = json.loads((ocr/f'{step}__{which}.json').read_text(encoding='utf-8')); text.pop('source', None)
            for row in text['lines']:
                row['text'] = row['text'].replace('imouse-draft', DOWNLOAD)
                for word in row['words']: word['text'] = word['text'].replace('imouse-draft', DOWNLOAD)
            self.texts[key] = text
        p1_state('home_out', '02-home.png'); p1_state('search_out', '04-app_search_entry.png')
        p1_state('safari', '07-safari.png'); p1_state('address', '08-address_selected.png')
        p1_state('home_back', '25-home.png'); p1_state('search_back', '27-app_search_entry.png')
        for key, step, which in (('link_menu', '77-download-test-video', 'before'), ('download_ready', '78-downloads-menu', 'before'),
                                 ('page_menu', '79-downloads-list', 'before'), ('downloads', '80-downloaded-video-preview', 'before'),
                                 ('quicklook_hidden', '81-file-preview-controls', 'before'), ('quicklook', '89-video-test-home', 'before'),
                                 ('share', '87-save-options-settled', 'after')):
            r17(key, step, which, OCR_SAFARI)
        r17('x_feed', '30-x-loaded'); r17('x_menu', '31-x-account'); r17('x_feed_closed', '32-x-close-menu')
        r17('x_query', '28-x-query'); r17('x_composer_empty', '115-x-video-composer'); r17('x_composer_text', '116-x-video-caption')
        r17('x_picker_loading', '117-x-video-picker'); r17('x_picker', '118-x-picker-loaded'); r17('x_picker_selected', '119-x-select-test-video')
        r17('x_composer_media', '120-x-attach-video'); r17('x_save_sheet', '121-x-video-save-dialog'); r17('x_feed_saved', '122-x-save-video-draft')
        r17('x_composer_drafts', '123-x-open-drafts-route'); r17('x_drafts', '124-x-video-drafts-list')
        r17('x_reopened', '125-x-video-draft-reopen'); r17('x_playing', '127-x-reopened-video-play')
        r17('x_keep_sheet', '128-x-close-verified-video'); r17('x_feed_final', '129-x-resave-verified-video')
        self.synthetic()

    def synthetic(self):
        page = Image.new('RGB', (500, 1080), '#f4f7fc'); draw = ImageDraw.Draw(page)
        rows = [('X draft', 30, 120), ('File ' + DOWNLOAD, 30, 190), ('Download video', 170, 262), ('Copy caption', 180, 400)]
        for label, x, y in rows: draw.text((x, y), label, fill='black')
        self.frames['x_page'] = png(page)
        self.texts['x_page'] = dict(width=500, height=1080, lines=[line(t, x, y) for t, x, y in rows])
        def centre(label):
            words = next(r['words'] for r in self.texts['x_page']['lines'] if r['text'] == label)
            return (round((min(w['x'] for w in words)+max(w['x']+w['width'] for w in words))/2),
                    round((min(w['y'] for w in words)+max(w['y']+w['height'] for w in words))/2))
        self.targets = dict(copy=centre('Copy caption'), download=centre('Download video'))
        copied = page.copy(); ImageDraw.Draw(copied).text((30, 450), 'Caption copied.', fill='black')
        self.frames['x_copied'] = png(copied)
        self.texts['x_copied'] = dict(width=500, height=1080, lines=[line(t, x, y) for t, x, y in rows]
                                      + [line('Caption copied. Verify the pasted text in X.', 30, 450)])
        # Paste callout above the press point (shape observed on the Instagram caption sheet).
        with Image.open(io.BytesIO(self.frames['x_composer_empty'])) as base:
            image = base.convert('RGB'); draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((60, 84, 230, 118), 8, fill='white', outline='#cccccc')
            draw.text((75, 94), 'Paste', fill='black'); draw.text((140, 94), 'AutoFill', fill='black')
            self.frames['x_paste_menu'] = png(image)
        text = copy.deepcopy(self.texts['x_composer_empty'])
        text['lines'] += [line('Paste', 75, 94, 45), line('AutoFill', 140, 94, 70)]
        self.texts['x_paste_menu'] = text
        self.reference = tt.TikTokReference((R17/'normalized-test.mp4').read_bytes())


class FixtureOcr:
    def __init__(self, kernel): self.kernel = kernel
    def read(self, raw):
        k = self.kernel
        text = copy.deepcopy(k.screens.texts[k.frame_key]); text['frameSha256'] = hashlib.sha256(raw).hexdigest()
        if k.scenario == 'other_account' and k.screen == 'x_menu' and k.menu_opens > 1:
            for row in text['lines']:
                row['text'] = row['text'].replace('@', '@other')
                for word in row['words']: word['text'] = word['text'].replace('@', '@other')
        if k.scenario == 'wrong_text' and k.screen == 'x_drafts':
            for row in text['lines']:
                if row['text'] == CAPTION: row['text'] = 'A different draft text'
        if k.scenario == 'prompt' and k.screen == k.fault_screen:
            text['lines'] += [line('Allow', 120, 600, 60), line("Don't Allow", 260, 600, 110)]
        return text


class FixtureKernel:
    _is_live_http = False

    def __init__(self, screens, scenario='normal', fault_screen=None, saved=False):
        self.screens, self.scenario, self.fault_screen = screens, scenario, fault_screen
        self.screen = 'x_feed_saved' if saved else 'x_feed'; self.leg = 'out'
        self.saves = 1 if saved else 0; self.owned = False
        self.generation, self.sequence, self.now = 4, 100, 1000.
        self.session = uuid.uuid4().hex; self.calls = []; self.typed = ''; self.searched = ''
        self.unexpected = []; self.cancelled = None; self.photos = 0; self.captures = {}; self.frame_key = None
        self.menu_opens = 0; self.played = 0
        self.pointer = None   # Last pointer position the phone received.

    def clock(self): self.now += .001; return self.now
    def pause(self, seconds): self.now += seconds
    def resolve_device_id(self, phone):
        if phone != 'C24C': raise AssertionError('Other phone addressed')
        return LIVE_TEST_DEVICE_ID
    def receiver(self):
        return dict(deviceid=LIVE_TEST_DEVICE_ID, name='iMouse2-C24C', receiver_pid=321, receiver_restarts=0,
                    live=True, frames=self.sequence, frame_session=self.session)
    def kernel_status(self):
        return dict(code=0, build_identity=dict(sha256='a'*64), input_leases_required=True, allowed=['C24C'],
                    process=dict(pid=123, started_utc='fixture'), receivers=[self.receiver()])
    def devices(self): return [dict(deviceid=LIVE_TEST_DEVICE_ID, pid='C24C', uid='fixture-uid')]
    def input_status(self):
        return {LIVE_TEST_DEVICE_ID: dict(id=LIVE_TEST_DEVICE_ID, generation=self.generation, owned=self.owned, active=False,
                stopped=False, releasing=False, release_failed=False, lease_remaining_ms=30000)}
    def preflight_phone(self, phone):
        if self.owned: raise AssertionError('Takeover')
        return dict(resolved_id=self.resolve_device_id(phone), receiver=self.receiver())
    def acquire(self, phones, lease_ms):
        assert phones == ['C24C'] and not self.owned
        self.owned = True; return {'C24C': 'fixture-token'}
    def renew_if_needed(self, tokens, min_remaining_ms): assert tokens == {'C24C': 'fixture-token'} and self.owned
    def release(self, tokens):
        assert tokens == {'C24C': 'fixture-token'}; self.owned = False; self.generation += 1; self.calls.append('release')

    def key(self):
        s, n = self.screen, self.captures.get(self.screen, 0)
        if s in ('home', 'search'): return s + '_' + self.leg
        if s == 'x_picker' and n < 2: return 'x_picker_loading'
        return s

    def shot(self, phone):
        self.resolve_device_id(phone)   # The latest delivered frame; only a change on the phone delivers another.
        self.frame_key = self.key(); self.captures[self.screen] = self.captures.get(self.screen, 0) + 1
        raw = self.screens.frames[self.frame_key]
        if self.screen == 'x_playing' and self.captures['x_playing'] % 2 == 0 and self.scenario != 'frozen_video':
            raw = self.later(raw)
        if self.screen == 'x_picker' and self.frame_key == 'x_picker' and self.scenario == 'ambiguous_tile':
            with Image.open(io.BytesIO(raw)) as base:
                image = base.convert('RGB'); image.paste(image.crop((0, 201, 166, 367)), (167, 368)); raw = png(image)
        age = '2000' if self.scenario == 'stale_frame' and self.owned and self.screen == self.fault_screen else '0'
        return raw, {'X-iMouse-Frame-Session': self.session, 'X-iMouse-Frame-Sequence': str(self.sequence),
                     'X-iMouse-Frame-Age-Ms': age, 'X-iMouse-Frame-Delivery': 'flowing'}

    def later(self, raw):
        with Image.open(io.BytesIO(raw)) as base:
            image = base.convert('RGB'); image.paste(self.screens.later_frame.resize((288, 518)), (70, 172)); return png(image)

    def send(self, phone, token, fun, **data):
        assert phone == 'C24C' and token == 'fixture-token' and self.owned
        self.calls.append((fun, dict(data)))
        if fun == '/mouse/reset':
            self.pointer = None; self.sequence += 1; return dict(code=0)
        if fun == '/mouse/move':
            # A new frame arrives only when something changes on the phone. A move onto the
            # pointer's current spot changes nothing (the 20 Oct C24C Reel window stopped on that).
            if self.pointer != (data['x'], data['y']): self.pointer = (data['x'], data['y']); self.sequence += 1
            return dict(code=0)
        if fun == '/mouse/down': return dict(code=0)
        if fun == '/mouse/up': self.transition('hold', *self.position); return dict(code=0)
        if fun == '/mouse/click': self.pointer = (data['x'], data['y']); self.transition('click', data['x'], data['y']); return dict(code=0)
        if fun == '/key/sendkey':
            if 'key' in data:
                if self.screen == 'address': self.typed += data['key']; return dict(code=0)
                assert self.screen == 'search' and self.leg == 'back' and data['key'] == 'X', (self.screen, data)
                self.searched += data['key']; self.screen = 'x_query'; return dict(code=0)
            self.transition('key:' + data['fn_key']); return dict(code=0)
        raise AssertionError('Unapproved function ' + fun)

    @property
    def position(self):
        moves = [c[1] for c in self.calls if isinstance(c, tuple) and c[0] in ('/mouse/move', '/mouse/click')]
        return (moves[-1]['x'], moves[-1]['y']) if moves else (0, 0)

    def transition(self, kind, x=None, y=None):
        near = lambda tx, ty, r=14: x is not None and abs(x-tx) <= r and abs(y-ty) <= r
        s = self.screen
        table = [
            ('x_feed', 'click', (45, 85), 'x_menu'), ('x_feed_closed', 'click', (45, 85), 'x_menu'),
            ('x_feed_saved', 'click', (45, 85), 'x_menu'),
            ('x_menu', 'click', (447, 83), 'x_feed_closed'),
            ('x_feed_closed', 'key:Home', None, 'home'),
            ('home', 'click', (250, 900), 'search'),
            ('search', 'click', None, 'safari'),
            ('safari', 'click', (245, 953), 'address'),
            ('x_page', 'click', self.screens.targets['copy'], 'x_copied'),
            ('x_copied', 'hold', self.screens.targets['download'], 'link_menu'),
            ('link_menu', 'click', (161, 940), 'download_ready'),
            ('download_ready', 'click', (91, 955), 'page_menu'),
            ('page_menu', 'click', (100, 928), 'downloads'),
            ('downloads', 'click', (152, 594), 'quicklook_hidden'),
            ('quicklook_hidden', 'click', (250, 300), 'quicklook'),
            ('quicklook', 'click', (40, 1012), 'share'),
            ('share', 'click', (100, 846), 'quicklook'),
            ('quicklook', 'key:Home', None, 'home'),
            ('x_query', 'click', (88, 218), 'x_feed'),
            ('x_feed_closed', 'click', (454, 935), 'x_composer_drafts' if self.saves else 'x_composer_empty'),
            ('x_composer_empty', 'click', (160, 140), 'x_composer_empty'),
            ('x_composer_empty', 'hold', (160, 140), 'x_paste_menu'),
            ('x_paste_menu', 'click', None, 'x_composer_text'),
            ('x_composer_text', 'click', (26, 1009), 'x_picker'),
            ('x_picker', 'click', (83, 284), 'x_picker_selected'),
            ('x_picker_selected', 'click', (456, 103), 'x_composer_media'),
            ('x_composer_media', 'click', (57, 85), 'x_save_sheet'),
            ('x_save_sheet', 'click', (250, 472), 'x_feed_saved'),
            ('x_composer_drafts', 'click', (344, 85), 'x_drafts'),
            ('x_drafts', 'click', (182, 225), 'x_reopened'),
            ('x_reopened', 'click', (214, 432), 'x_playing'),
            ('x_playing', 'click', (57, 85), 'x_keep_sheet'),
            ('x_keep_sheet', 'click', (250, 472), 'x_feed_final'),
        ]
        if s == 'address' and kind == 'key:Enter':
            assert self.typed == URL, self.typed
            self.screen = 'x_page'; return
        for state, k, target, after in table:
            if state == s and k == kind and (target is None or near(*target, r=40 if state == 'search' else 14)):
                if state == 'home' and self.leg == 'back': after = 'search'
                if state == 'search' and self.leg == 'back': continue
                if s == 'share': self.photos += 1
                if after == 'x_menu': self.menu_opens += 1
                if s in ('x_save_sheet', 'x_keep_sheet'):
                    self.saves += 1; self.screen = after
                    if self.scenario == 'lost_save' and s == 'x_save_sheet': raise TimeoutError('Fixture Save happened; answer lost.')
                    return
                if s == 'quicklook' and kind == 'key:Home': self.leg = 'back'
                self.screen = after; return
        self.unexpected.append((s, kind, x, y))
        raise AssertionError(f'Unexpected {kind} at {(x, y)} on {s}')


class XGuardTests(unittest.TestCase):
    def test_post_discard_and_remove_are_never_targets(self):
        empty = dict(width=500, height=1080, lines=[])
        for role, point in (('x_composer_text', (430, 84)), ('x_composer_media', (334, 196)), ('x_save_sheet', (250, 538))):
            with self.assertRaises(InspectionStopped): guard(empty, *point, role)
        guard(empty, 57, 85, 'x_composer_media'); guard(empty, 250, 472, 'x_save_sheet')


@unittest.skipUnless(PRIVATE, 'Retained private C24C frames/OCR are not available in this checkout.')
class XProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shutil, subprocess
        cls.screens = Screens()
        ffmpeg = shutil.which('ffmpeg')
        data = subprocess.run([ffmpeg, '-v', 'error', '-ss', '2.4', '-i', str(R17/'normalized-test.mp4'), '-frames:v', '1',
                               '-vf', 'scale=288:518', '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True, check=True).stdout
        cls.screens.later_frame = Image.open(io.BytesIO(data)).convert('RGB')
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory)/'other.mp4'
            subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=720x1280:rate=15:duration=3',
                            '-pix_fmt', 'yuv420p', '-c:v', 'libx264', str(other)], check=True)
            cls.other = tt.TikTokReference(other.read_bytes())

    def fixture(self, scenario='normal', fault_screen=None, saved=False, verifier=False, account=None):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        kernel = FixtureKernel(self.screens, scenario, fault_screen, saved)
        store = ObservationStore(folder/'observations.sqlite3', ocr=FixtureOcr(kernel), clock=kernel.clock, monotonic=kernel.clock,
                                 retained_limit=160)
        options = dict(package_hash='b'*64, monotonic=kernel.clock, pause=kernel.pause)
        if verifier:
            flow = XVerification(folder, kernel, store, self.screens.reference, CAPTION, references(), 'a'*64, 'fixture-uid',
                                 account=account, **options)
        else:
            flow = XCreationWorkflow(folder, kernel, store, self.screens.reference, CAPTION, references(), 'a'*64, 'fixture-uid',
                                     transfer_url=URL, download=DOWNLOAD, video_bytes=VIDEO_BYTES, **options)
        kernel.cancelled = flow.cancelled
        return flow, kernel

    @staticmethod
    def semantic(kernel):
        return [c for c in kernel.calls if isinstance(c, tuple) and (c[0] in ('/mouse/click', '/mouse/up') or
                (c[0] == '/key/sendkey' and 'fn_key' in c[1] and c[1]['fn_key'] != 'Enter'))]

    def create(self):
        flow, kernel = self.fixture(); result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error'))
        return result, kernel

    def test_creation_binds_the_signed_in_account_then_verification_passes(self):
        result, kernel = self.create()
        self.assertEqual([], kernel.unexpected); self.assertEqual(1, kernel.saves); self.assertEqual(1, kernel.photos)
        self.assertEqual('x_feed_saved', kernel.screen); self.assertEqual('X', kernel.searched)
        self.assertNotEqual(PENDING, result['account']); self.assertRegex(result['account'], r'^[A-Za-z0-9_]{1,15}$')
        self.assertEqual('side_menu_handle', result['accountBinding']['method'])
        self.assertEqual([0, 201, 166, 367], result['pickerTile']); self.assertEqual('confirmed', result['cleanup'])
        self.assertTrue(all(a['state'] == 'answered' for a in result['actions']))
        flow, kernel2 = self.fixture(saved=True, verifier=True, account=result['account'])
        verified = flow.run()
        self.assertEqual('validation_passed', verified['state'], verified.get('error'))
        self.assertEqual(2, kernel2.saves); self.assertEqual('x_feed_final', kernel2.screen)
        self.assertNotEqual(*verified['playback']['sampledFrameIndices'])
        self.assertEqual(CAPTION, verified['draftRow']['text'])
        self.assertEqual('consistent_sampled_history', verified['accountHistory']['status'])

    def test_a_different_account_stops_creation_and_verification(self):
        flow, kernel = self.fixture('other_account'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(0, kernel.saves)
        self.assertIn('different X account', result['error'])
        account = self.create()[0]['account']
        flow, kernel = self.fixture('other_account', saved=True, verifier=True, account=account)
        kernel.menu_opens = 1   # The verifier's first menu read is already "later".
        result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertFalse(result['savedDraftVerified']); self.assertEqual(1, kernel.saves)
        self.assertIn('different X account', result['error'])

    def test_lost_answer_at_every_creation_action_stops_without_replay(self):
        flow, kernel = self.fixture(); flow.run(); total = len(self.semantic(kernel))
        self.assertGreater(total, 25)
        for boundary in range(1, total+1):
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
                self.assertEqual('release', kernel.calls[-1]); self.assertLessEqual(kernel.saves, 1); self.assertLessEqual(kernel.photos, 1)

    def test_lost_save_answer_is_never_repeated(self):
        flow, kernel = self.fixture('lost_save'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(1, kernel.saves)
        self.assertEqual('save-x-draft-once', result['actions'][-1]['label']); self.assertEqual('outcome_unknown', result['actions'][-1]['state'])

    def test_faults_stop_before_the_draft(self):
        for scenario, screen in (('ambiguous_tile', None), ('prompt', 'x_composer_media'), ('stale_frame', 'x_picker_selected')):
            with self.subTest(scenario=scenario):
                flow, kernel = self.fixture(scenario, screen); result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertEqual(0, kernel.saves)
                self.assertEqual('confirmed', result['cleanup']); self.assertEqual([], kernel.unexpected)
        flow, kernel = self.fixture(); flow.video = self.other; result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(0, kernel.photos); self.assertIn('package video', result['error'])

    def test_verifier_refuses_wrong_text_and_a_frozen_video(self):
        account = self.create()[0]['account']
        for scenario in ('wrong_text', 'frozen_video'):
            with self.subTest(scenario=scenario):
                flow, kernel = self.fixture(scenario, saved=True, verifier=True, account=account); result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertFalse(result['savedDraftVerified'])
                self.assertEqual(1, kernel.saves); self.assertEqual('confirmed', result['cleanup'])

    def test_committing_purposes_name_real_creation_actions(self):
        flow, kernel = self.fixture(); flow.run()
        labels = {a['label'] for a in flow.record['actions']}
        self.assertTrue(set(COMMITTING) <= labels, set(COMMITTING) - labels)


if __name__ == '__main__':
    unittest.main()
