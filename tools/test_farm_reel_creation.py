"""Reel creation/verification against retained C24C screens and a simulated HID kernel.

No socket, desktop or phone access. Instagram and Safari screens are retained
17 Oct (Reel route) and 19 Oct (Home/Safari/profile) frames with their OCR;
the new transfer page, Paste menu, settled selection and a later Preview frame
are synthetic composites, labelled as such. This tests the protocol and
recognizers on known layouts. It is not fresh-phone acceptance.
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

import numpy as np
from PIL import Image, ImageDraw

import farm_test_network  # noqa: F401  Refuse every real socket in this process.
import farm_reel_layout as reel
from farm_draft_workflow import references
from farm_observations import ObservationStore
from farm_reel_creation import ReelCreationWorkflow, ReelVerification, COMMITTING
from imouse_social_automation import LIVE_TEST_DEVICE_ID

ROOT = Path(__file__).resolve().parents[1]
R17 = ROOT/'analysis/farm-platform-drafts-20261017'
OCR17 = ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-reel-offline/ocr-20261017'
P1 = ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-new-draft/backend/draft-creations/b8c155e2-1670-4f60-a090-aeff921e162e'
PRIVATE = all(p.exists() for p in (R17/'normalized-test.mp4', OCR17, P1/'record.json'))
ACCOUNT = 'xs.halle.xo'
CAPTION = 'IMOUSE-VlDEO-DRAFT-TEST-20261017'   # The retained frames' exact OCR form.
URL = 'http://192.168.50.2:9917/t/fixture-token/'
VIDEO_BYTES = 78953


def png(image):
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


def line(text, x, y, width=None, height=18):
    words, cursor = [], x
    for part in text.split(' '):
        w = max(8, round((width or len(text)*9) * len(part)/max(1, len(text))))
        words.append(dict(text=part, x=cursor, y=y, width=w, height=height)); cursor += w + 6
    return dict(text=text, words=words)


class Screens:
    """Retained frames/OCR keyed by fixture state. Built once per test class."""
    def __init__(self, download):
        self.frames, self.texts = {}, {}
        p1 = json.loads((P1/'record.json').read_text(encoding='utf-8'))
        by_frame = {e['frame']: e['observation']['text'] for e in p1['observations'] if e.get('state') == 'observed'}
        def p1_state(key, name):
            self.frames[key] = (P1/name).read_bytes(); self.texts[key] = copy.deepcopy(by_frame[name])
        def r17(key, step, which='after'):
            self.frames[key] = (R17/step/(which+'.png')).read_bytes()
            text = json.loads((OCR17/f'{step}__{which}.json').read_text(encoding='utf-8'))
            text.pop('source', None)
            for row in text['lines']:  # Synthetic substitution: the new package name, same pixels.
                row['text'] = row['text'].replace('imouse-draft', download)
                for word in row['words']: word['text'] = word['text'].replace('imouse-draft', download)
            self.texts[key] = text
        p1_state('profile', '31-profile.png'); p1_state('home_out', '02-home.png'); p1_state('search_out', '04-app_search_entry.png')
        p1_state('safari', '07-safari.png'); p1_state('address', '08-address_selected.png')
        p1_state('home_back', '25-home.png'); p1_state('search_back', '27-app_search_entry.png'); p1_state('feed', '29-account_entry.png')
        r17('link_menu', '77-download-test-video', 'before'); r17('download_ready', '78-downloads-menu', 'before')
        r17('page_menu', '79-downloads-list', 'before'); r17('downloads', '80-downloaded-video-preview', 'before')
        r17('quicklook_hidden', '81-file-preview-controls', 'before'); r17('quicklook', '89-video-test-home', 'before')
        r17('share', '87-save-options-settled')
        r17('create', '155-instagram-create-menu'); r17('picker', '156-instagram-reel-picker')
        r17('editor', '158-instagram-reel-edit'); r17('details_blank', '159-instagram-reel-details')
        r17('caption_blank', '160-instagram-reel-caption-focus'); r17('caption_pasted', '161-instagram-reel-caption')
        r17('details', '162-instagram-reel-caption-ok'); r17('saved_picker', '163-instagram-save-reel-draft')
        r17('drafts', '164-instagram-reel-drafts-library'); r17('reopened', '165-instagram-reel-reopen')
        r17('preview', '166-instagram-reel-playback'); r17('drafts_kept', '167-instagram-keep-verified-reel')
        r17('selected_text', '157-instagram-select-test-mp4')
        self.synthetic(download)

    def synthetic(self, download):
        page = Image.new('RGB', (500, 1080), '#f4f7fc'); draw = ImageDraw.Draw(page)
        rows = [('Reel draft', 30, 120), ('File ' + download, 30, 190), ('Download video', 170, 262), ('Copy caption', 180, 400)]
        for label, x, y in rows: draw.text((x, y), label, fill='black')
        self.frames['reel_page'] = png(page)
        self.texts['reel_page'] = dict(width=500, height=1080, lines=[line(t, x, y) for t, x, y in rows])
        def centre(label):
            words = next(r['words'] for r in self.texts['reel_page']['lines'] if r['text'] == label)
            return (round((min(w['x'] for w in words)+max(w['x']+w['width'] for w in words))/2),
                    round((min(w['y'] for w in words)+max(w['y']+w['height'] for w in words))/2))
        self.targets = dict(copy=centre('Copy caption'), download=centre('Download video'))
        copied = page.copy(); ImageDraw.Draw(copied).text((30, 450), 'Caption copied.', fill='black')
        self.frames['reel_copied'] = png(copied)
        self.texts['reel_copied'] = dict(width=500, height=1080, lines=[line(t, x, y) for t, x, y in rows]
                                         + [line('Caption copied. Verify the pasted text in', 30, 450), line('Instagram.', 30, 478)])   # Wrapped as on C24C.
        # Paste callout over the blank caption sheet (shape observed on the carousel sheet).
        with Image.open(io.BytesIO(self.frames['caption_blank'])) as base:
            image = base.convert('RGB'); draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((30, 84, 200, 120), 8, fill='white', outline='#cccccc')
            draw.text((45, 96), 'Paste', fill='black'); draw.text((110, 96), 'AutoFill', fill='black')
            self.frames['paste_menu'] = png(image)
        text = copy.deepcopy(self.texts['caption_blank'])
        text['lines'] += [line('Paste', 45, 96, 45), line('AutoFill', 110, 96, 70)]
        self.texts['paste_menu'] = text
        # Settled selection without a Drafts chip: badge and tray from the
        # settled post-save frame composited onto the unselected picker.
        with Image.open(io.BytesIO(self.frames['picker'])) as base, Image.open(io.BytesIO(self.frames['saved_picker'])) as saved:
            image = base.convert('RGB'); saved = saved.convert('RGB')
            image.paste(saved.crop((290, 260, 332, 302)), (290, 260))
            image.paste(saved.crop((0, 940, 500, 1080)), (0, 940))
            self.frames['selected'] = png(image)
        self.texts['selected'] = copy.deepcopy(self.texts['selected_text'])
        # A later Preview frame: a sampled frame of the package video in the
        # central media area; header, account, caption and buttons unchanged.
        reference = reel.VideoReference((R17/'normalized-test.mp4').read_bytes())
        self.reference = reference


class FixtureOcr:
    def __init__(self, kernel): self.kernel = kernel
    def read(self, raw):
        k = self.kernel
        if k.scenario == 'failed_ocr' and k.owned and k.screen == k.fault_screen: raise RuntimeError('Fixture OCR failure')
        text = copy.deepcopy(k.screens.texts[k.frame_key()]); text['frameSha256'] = hashlib.sha256(raw).hexdigest()
        if k.scenario == 'wrong_account' and k.screen == 'preview':
            for row in text['lines']:
                row['text'] = row['text'].replace(ACCOUNT, 'wrong.account')
                for word in row['words']: word['text'] = word['text'].replace(ACCOUNT, 'wrong.account')
        if k.scenario == 'wrong_caption' and k.screen in ('details', 'reopened'):
            for row in text['lines']:
                if row['text'] == CAPTION: row['text'] = 'A different caption'
        if k.scenario == 'prompt' and k.screen == k.fault_screen:
            text['lines'] += [line('Allow', 120, 600, 60), line("Don't Allow", 260, 600, 110)]
        return text


class FixtureKernel:
    _is_live_http = False

    def __init__(self, screens, scenario='normal', fault_screen=None, saved=False):
        self.screens, self.scenario, self.fault_screen = screens, scenario, fault_screen
        self.screen = 'profile'; self.leg = 'out'; self.saves = 1 if saved else 0; self.owned = False
        self.generation, self.sequence, self.now = 4, 100, 1000.
        self.session = uuid.uuid4().hex; self.calls = []; self.typed = ''; self.down = None
        self.preview_captures = 0; self.unexpected = []; self.cancelled = None; self.photos = 0
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

    def frame_key(self):
        if self.screen == 'home': return 'home_' + self.leg
        if self.screen == 'search': return 'search_' + self.leg
        if self.screen == 'saved_picker' and self.scenario == 'no_drafts_chip': return 'picker'
        return self.screen

    def shot(self, phone):
        self.resolve_device_id(phone)   # The latest delivered frame; only a change on the phone delivers another.
        raw = self.screens.frames[self.frame_key()]
        if self.screen == 'preview':
            self.preview_captures += 1
            if self.preview_captures % 2 == 0 and self.scenario != 'frozen_preview':
                raw = self.later_preview(raw)
        if self.screen == 'picker' and self.scenario == 'ambiguous_tile':
            with Image.open(io.BytesIO(raw)) as base:
                image = base.convert('RGB'); image.paste(image.crop((167, 259, 333, 553)), (167, 554)); raw = png(image)
        age = '2000' if self.scenario == 'stale_frame' and self.owned and self.screen == self.fault_screen else '0'
        return raw, {'X-iMouse-Frame-Session': self.session, 'X-iMouse-Frame-Sequence': str(self.sequence),
                     'X-iMouse-Frame-Age-Ms': age, 'X-iMouse-Frame-Delivery': 'flowing'}

    def later_preview(self, raw):
        frames = self.screens.later_frames
        with Image.open(io.BytesIO(raw)) as base:
            image = base.convert('RGB'); image.paste(frames.crop((0, 76, 420, 776)), (0, 120)); return png(image)

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
        if fun == '/mouse/down': self.down = (data.get('x'), data.get('y'), self.position); return dict(code=0)
        if fun == '/mouse/up':
            self.transition('hold', *self.position); self.down = None; return dict(code=0)
        if fun == '/mouse/click': self.pointer = (data['x'], data['y']); self.transition('click', data['x'], data['y']); return dict(code=0)
        if fun == '/key/sendkey':
            if 'key' in data:
                assert self.screen == 'address'; self.typed += data['key']; return dict(code=0)
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
            ('profile', 'key:Home', None, 'home'),
            ('home', 'click', (250, 900), 'search'),
            ('search', 'click', None, 'safari' if self.leg == 'out' else 'feed'),
            ('safari', 'click', (245, 953), 'address'),
            ('reel_page', 'click', self.screens.targets['copy'], 'reel_copied'),
            ('reel_copied', 'hold', self.screens.targets['download'], 'link_menu'),
            ('link_menu', 'click', (161, 940), 'download_ready'),
            ('download_ready', 'click', (91, 955), 'page_menu'),
            ('page_menu', 'click', (100, 928), 'downloads'),
            ('downloads', 'click', (152, 594), 'quicklook_hidden'),
            ('quicklook_hidden', 'click', (250, 300), 'quicklook'),
            ('quicklook', 'click', (40, 1012), 'share'),
            ('share', 'click', (100, 846), 'quicklook'),
            ('quicklook', 'key:Home', None, 'home'),
            ('feed', 'click', (447, 1008), 'profile'),
            ('profile', 'click', (35, 88), 'create'),
            ('create', 'click', (105, 576), 'saved_picker' if self.saves else 'picker'),
            ('picker', 'click', (311, 280), 'selected'),
            ('selected', 'click', (444, 993), 'editor'),
            ('editor', 'click', (444, 993), 'details_blank'),
            ('details_blank', 'click', (80, 505), 'caption_blank'),
            ('caption_blank', 'hold', (80, 142), 'paste_menu'),
            ('paste_menu', 'click', None, 'caption_pasted'),
            ('caption_pasted', 'click', (461, 84), 'details'),
            ('details', 'click', (130, 996), 'saved_picker'),
            ('saved_picker', 'click', (42, 98), 'profile'),
            ('saved_picker', 'click', (70, 160), 'drafts'),
            ('drafts', 'click', (66, 169), 'reopened'),
            ('reopened', 'click', (225, 172), 'preview'),
            ('preview', 'click', (130, 996), 'drafts_kept'),
        ]
        if s == 'address' and kind == 'key:Enter':
            assert self.typed == URL, self.typed
            self.screen = 'reel_page'; return
        for state, k, target, after in table:
            if state == s and k == kind and (target is None or near(*target, r=40 if state == 'search' else 14)):
                if s == 'share': self.photos += 1
                if s in ('details', 'preview'):
                    self.saves += 1
                    self.screen = after
                    if self.scenario == 'lost_save' and s == 'details': raise TimeoutError('Fixture Save happened; answer lost.')
                    return
                if s == 'quicklook' and kind == 'key:Home': self.leg = 'back'
                self.screen = after; return
        self.unexpected.append((s, kind, x, y))
        raise AssertionError(f'Unexpected {kind} at {(x, y)} on {s}')


@unittest.skipUnless(PRIVATE, 'Retained private C24C frames/OCR are not available in this checkout.')
class ReelProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shutil, subprocess
        cls.download = 'imouse-reel-acdefh'
        cls.screens = Screens(cls.download)
        ffmpeg = shutil.which('ffmpeg')
        data = subprocess.run([ffmpeg, '-v', 'error', '-ss', '2.4', '-i', str(R17/'normalized-test.mp4'), '-frames:v', '1',
                               '-vf', 'scale=500:889', '-f', 'image2pipe', '-vcodec', 'png', '-'], capture_output=True, check=True).stdout
        cls.screens.later_frames = Image.open(io.BytesIO(data)).convert('RGB')
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory)/'other.mp4'
            subprocess.run([ffmpeg, '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=720x1280:rate=15:duration=3',
                            '-pix_fmt', 'yuv420p', '-c:v', 'libx264', str(other)], check=True)
            cls.other = reel.VideoReference(other.read_bytes())

    def fixture(self, scenario='normal', fault_screen=None, saved=False, verifier=False):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        kernel = FixtureKernel(self.screens, scenario, fault_screen, saved)
        store = ObservationStore(folder/'observations.sqlite3', ocr=FixtureOcr(kernel), clock=kernel.clock, monotonic=kernel.clock,
                                 retained_limit=160)
        options = dict(account=ACCOUNT, package_hash='b'*64, monotonic=kernel.clock, pause=kernel.pause)
        if verifier:
            flow = ReelVerification(folder, kernel, store, self.screens.reference, CAPTION, references(), 'a'*64, 'fixture-uid', **options)
        else:
            flow = ReelCreationWorkflow(folder, kernel, store, self.screens.reference, CAPTION, references(), 'a'*64, 'fixture-uid',
                transfer_url=URL, download=self.download, video_bytes=VIDEO_BYTES, **options)
        kernel.cancelled = flow.cancelled
        return flow, kernel

    @staticmethod
    def semantic(kernel):
        return [c for c in kernel.calls if isinstance(c, tuple) and (c[0] in ('/mouse/click', '/mouse/up') or
                (c[0] == '/key/sendkey' and 'fn_key' in c[1] and c[1]['fn_key'] != 'Enter'))]

    def test_creation_then_independent_verification_pass_on_known_layouts(self):
        flow, kernel = self.fixture(); result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error'))
        self.assertEqual([], kernel.unexpected); self.assertEqual(1, kernel.saves); self.assertEqual(1, kernel.photos)
        self.assertEqual('profile', kernel.screen); self.assertEqual('confirmed', result['cleanup']); self.assertFalse(kernel.owned)
        self.assertEqual([0, 1], result['pickerCell']); self.assertEqual('offline_protocol_fixture', result['source'])
        self.assertTrue(all(a['state'] == 'answered' for a in result['actions']))
        self.assertFalse(any('share' in a['label'] and 'sheet' not in a['label'] for a in result['actions']))
        # A new owned run on the saved phone state; the fixture keeps one draft.
        flow2, kernel2 = self.fixture(saved=True, verifier=True)
        verified = flow2.run()
        self.assertEqual('validation_passed', verified['state'], verified.get('error'))
        self.assertTrue(verified['savedDraftVerified']); self.assertEqual('reels_drafts', verified['finalScreen'])
        self.assertEqual(2, kernel2.saves); self.assertEqual('drafts_kept', kernel2.screen)
        self.assertNotEqual(*verified['playback']['sampledFrameIndices'])
        self.assertEqual('consistent_sampled_history', verified['accountHistory']['status'])

    def test_lost_answer_at_every_creation_action_stops_without_replay(self):
        flow, kernel = self.fixture(); flow.run(); total = len(self.semantic(kernel))
        self.assertGreater(total, 20)
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

    def test_stop_at_each_dispatch_journal_sends_nothing_for_that_action(self):
        flow, kernel = self.fixture(); flow.run()
        labels = [a['label'] for a in flow.record['actions']]
        for index, label in enumerate(labels):
            with self.subTest(label=label):
                flow, kernel = self.fixture(); original = flow.save
                def save():
                    original()
                    commands = flow.record['commands']
                    if commands and commands[-1]['purpose'].startswith(label) and commands[-1]['state'] == 'outcome_unknown':
                        flow.cancelled.set()
                with patch.object(flow, 'save', save): result = flow.run()
                self.assertEqual('review_required', result['state'])
                self.assertEqual('not_sent', result['actions'][-1]['state'])
                self.assertEqual(label, result['actions'][-1]['label']); self.assertEqual('confirmed', result['cleanup'])

    def test_receiver_change_after_any_action_stops_before_more_input(self):
        flow, kernel = self.fixture(); flow.run(); total = len(self.semantic(kernel))
        for boundary in (1, 6, 12, 18, total-1):
            with self.subTest(boundary=boundary):
                flow, kernel = self.fixture(); original = kernel.send
                def send(phone, token, fun, **data):
                    value = original(phone, token, fun, **data)
                    if len(self.semantic(kernel)) == boundary: kernel.session = uuid.uuid4().hex
                    return value
                with patch.object(kernel, 'send', send): result = flow.run()
                self.assertEqual('review_required', result['state'])
                self.assertEqual(boundary, len(self.semantic(kernel))); self.assertEqual('release', kernel.calls[-1])

    def test_lost_save_answer_is_never_repeated(self):
        flow, kernel = self.fixture('lost_save'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(1, kernel.saves)
        self.assertEqual('save-reel-draft-once', result['actions'][-1]['label'])
        self.assertEqual('outcome_unknown', result['actions'][-1]['state'])

    def test_ambiguous_tile_wrong_media_prompt_stale_and_failed_ocr_stop_before_the_draft(self):
        cases = [('ambiguous_tile', None), ('prompt', 'details'), ('prompt', 'picker'), ('stale_frame', 'editor'),
                 ('failed_ocr', 'caption_blank'), ('no_drafts_chip', None)]
        for scenario, screen in cases:
            with self.subTest(scenario=scenario, screen=screen):
                flow, kernel = self.fixture(scenario, screen); result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertEqual('confirmed', result['cleanup'])
                if scenario != 'no_drafts_chip': self.assertEqual(0, kernel.saves)
        # Different package media: the Files preview does not match, so nothing
        # reaches Photos or Instagram.
        flow, kernel = self.fixture(); flow.video = self.other; result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(0, kernel.saves)
        self.assertEqual(0, kernel.photos); self.assertIn('package video', result['error'])

    def test_wrong_caption_on_details_never_saves(self):
        flow, kernel = self.fixture('wrong_caption'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(0, kernel.saves)
        self.assertIn('caption', result['error'].casefold())

    def test_verifier_refuses_frozen_preview_wrong_account_and_wrong_caption(self):
        for scenario in ('frozen_preview', 'wrong_account', 'wrong_caption'):
            with self.subTest(scenario=scenario):
                flow, kernel = self.fixture(scenario, saved=True, verifier=True); result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertFalse(result['savedDraftVerified'])
                self.assertEqual(1, kernel.saves); self.assertEqual('confirmed', result['cleanup'])

    def test_committing_purposes_name_real_creation_actions(self):
        flow, kernel = self.fixture(); flow.run()
        labels = {a['label'] for a in flow.record['actions']}
        self.assertTrue(set(COMMITTING) <= labels, set(COMMITTING) - labels)


if __name__ == '__main__':
    unittest.main()
