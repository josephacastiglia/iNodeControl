"""TikTok creation/verification against retained C24C screens and a simulated HID kernel.

No socket, desktop or phone access. TikTok screens are retained 17 Oct frames
(supervised steps 94-113) with their OCR; Safari/Files screens are the retained
17 Oct video-transfer frames and 19 Oct Home/Safari frames. Synthetic parts are
labelled: the transfer page, the Paste callout, a caret drawn on the focused
blank description, a profile count read as 1 before the save, and the one-line
description substituted for the wrapped 17 Oct caption in OCR. This tests the
protocol and recognizers on known layouts. It is not fresh-phone acceptance.
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
import farm_permission_prompts as prompts
import farm_tiktok_layout as tt
from farm_carousel_inspection import InspectionStopped
from farm_draft_workflow import references
from farm_observations import ObservationStore
from farm_tiktok_creation import TikTokCreationWorkflow, TikTokVerification, COMMITTING, tiktok_guard
from imouse_social_automation import LIVE_TEST_DEVICE_ID

ROOT = Path(__file__).resolve().parents[1]
R17 = ROOT/'analysis/farm-platform-drafts-20261017'
OCR_SAFARI = ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-reel-offline/ocr-20261017'
OCR_TIKTOK = ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-tiktok-offline/ocr-20261017'
P1 = ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-new-draft/backend/draft-creations/b8c155e2-1670-4f60-a090-aeff921e162e'
PRIVATE = all(p.exists() for p in (R17/'normalized-test.mp4', OCR_SAFARI, OCR_TIKTOK, P1/'record.json'))
ACCOUNT = 'xs.halle.xo'
CAPTION = 'IMOUSE-TT-DRAFT-TEST'      # Synthetic one-line description (the 17 Oct caption wrapped).
URL = 'http://192.168.50.2:9917/t/fixture-token/'
VIDEO_BYTES = 78953
DOWNLOAD = 'imouse-tt-acdefh'


def png(image):
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


def line(text, x, y, width=None, height=18):
    words, cursor = [], x
    for part in text.split(' '):
        w = max(8, round((width or len(text)*9) * len(part)/max(1, len(text))))
        words.append(dict(text=part, x=cursor, y=y, width=w, height=height)); cursor += w + 6
    return dict(text=text, words=words)


def one_line_caption(text, caption):
    """Synthetic OCR substitution: the wrapped 17 Oct caption rows become one description line."""
    rows = [r for r in text['lines'] if r.get('words') and 120 <= min(w['y'] for w in r['words']) < 330
            and min(w['x'] for w in r['words']) < 340]
    assert rows, 'fixture frame has no caption rows'
    first = min(rows, key=lambda r: min(w['y'] for w in r['words']))
    x, y = min(w['x'] for w in first['words']), min(w['y'] for w in first['words'])
    text['lines'] = [r for r in text['lines'] if r not in rows] + [line(caption, x, y, len(caption)*9, 16)]
    return text


class Screens:
    """Retained frames/OCR keyed by fixture state. Built once per test class."""
    def __init__(self):
        self.frames, self.texts = {}, {}
        p1 = json.loads((P1/'record.json').read_text(encoding='utf-8'))
        by_frame = {e['frame']: e['observation']['text'] for e in p1['observations'] if e.get('state') == 'observed'}
        def p1_state(key, name):
            self.frames[key] = (P1/name).read_bytes(); self.texts[key] = copy.deepcopy(by_frame[name])
        def r17(key, step, which='after', ocr=OCR_TIKTOK):
            self.frames[key] = (R17/step/(which+'.png')).read_bytes()
            text = json.loads((ocr/f'{step}__{which}.json').read_text(encoding='utf-8'))
            text.pop('source', None)
            for row in text['lines']:  # Synthetic substitution: the new package name, same pixels.
                row['text'] = row['text'].replace('imouse-draft', DOWNLOAD)
                for word in row['words']: word['text'] = word['text'].replace('imouse-draft', DOWNLOAD)
            self.texts[key] = text
        p1_state('home_out', '02-home.png'); p1_state('search_out', '04-app_search_entry.png')
        p1_state('safari', '07-safari.png'); p1_state('address', '08-address_selected.png')
        for key, step, which in (('link_menu', '77-download-test-video', 'before'), ('download_ready', '78-downloads-menu', 'before'),
                                 ('page_menu', '79-downloads-list', 'before'), ('downloads', '80-downloaded-video-preview', 'before'),
                                 ('quicklook_hidden', '81-file-preview-controls', 'before'), ('quicklook', '89-video-test-home', 'before'),
                                 ('share', '87-save-options-settled', 'after')):
            r17(key, step, which, OCR_SAFARI)
        r17('home_back', '94-tiktok-video-start', 'before'); r17('tt_feed', '95-tiktok-loaded')
        r17('profile_after', '107-tiktok-video-profile'); r17('tt_camera', '96-tiktok-create-video')
        r17('tt_picker', '100-tiktok-settled-gallery-click'); r17('tt_selected', '101-tiktok-select-test-video')
        r17('tt_editor_loading', '102-tiktok-video-editor'); r17('tt_editor_sound', '109-tiktok-video-reopen')
        r17('tt_editor_silent', '110-tiktok-remove-suggested-sound')
        r17('tt_details_blank', '103-tiktok-video-details'); r17('tt_details_focused', '104-tiktok-video-caption-focus')
        r17('tt_details_caret', '105-tiktok-video-caption'); r17('tt_details_pasted', '106-tiktok-save-video-draft', 'before')
        r17('tt_feed_saved', '106-tiktok-save-video-draft'); r17('tt_drafts', '113-tiktok-to-home', 'before')
        r17('tt_drafts_sound', '108-tiktok-video-library'); r17('tt_reopened_details', '111-tiktok-video-caption-verify')
        r17('tt_drafts_kept', '112-tiktok-resave-silent-video')
        self.synthetic()

    def synthetic(self):
        # Profile before the save: the same pixels, the Drafts count read as 1.
        self.frames['profile'] = self.frames['profile_after']
        text = copy.deepcopy(self.texts['profile_after'])
        for row in text['lines']:
            if row['text'] == 'Drafts: 2':
                row['text'] = 'Drafts: 1'
                for word in row['words']: word['text'] = word['text'].replace('2', '1')
        self.texts['profile'] = text
        # One-line description in OCR on caret-free details frames.
        for key in ('tt_details_pasted', 'tt_reopened_details'): one_line_caption(self.texts[key], CAPTION)
        # Transfer page.
        page = Image.new('RGB', (500, 1080), '#f4f7fc'); draw = ImageDraw.Draw(page)
        rows = [('TikTok draft', 30, 120), ('File ' + DOWNLOAD, 30, 190), ('Download video', 170, 262), ('Copy caption', 180, 400)]
        for label, x, y in rows: draw.text((x, y), label, fill='black')
        self.frames['tt_page'] = png(page)
        self.texts['tt_page'] = dict(width=500, height=1080, lines=[line(t, x, y) for t, x, y in rows])
        def centre(label):
            words = next(r['words'] for r in self.texts['tt_page']['lines'] if r['text'] == label)
            return (round((min(w['x'] for w in words)+max(w['x']+w['width'] for w in words))/2),
                    round((min(w['y'] for w in words)+max(w['y']+w['height'] for w in words))/2))
        self.targets = dict(copy=centre('Copy caption'), download=centre('Download video'))
        copied = page.copy(); ImageDraw.Draw(copied).text((30, 450), 'Caption copied.', fill='black')
        self.frames['tt_copied'] = png(copied)
        self.texts['tt_copied'] = dict(width=500, height=1080, lines=[line(t, x, y) for t, x, y in rows]
                                       + [line('Caption copied. Verify the pasted text in TikTok.', 30, 450)])
        # The focused blank description with the caret drawn in its blink phase.
        with Image.open(io.BytesIO(self.frames['tt_details_focused'])) as base:
            image = base.convert('RGB'); ImageDraw.Draw(image).rectangle((25, 128, 26, 150), fill=(246, 90, 130))
            self.frames['tt_focused_caret'] = png(image)
        self.texts['tt_focused_caret'] = copy.deepcopy(self.texts['tt_details_focused'])
        # Profile reached directly after Drafts (17 Oct photo route), with the toast read in OCR.
        self.frames['profile_saved'] = self.frames['profile_after']
        self.texts['profile_saved'] = copy.deepcopy(self.texts['profile_after'])
        self.texts['profile_saved']['lines'].append(line('Draft saved', 205, 147, 90, 13))
        # First-time Photos access prompt over the camera (synthetic composite; iOS wording).
        with Image.open(io.BytesIO(self.frames['tt_camera'])) as base:
            image = base.convert('RGB'); draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((60, 260, 440, 860), 18, fill=(242, 242, 242))
            for label, y in (('Allow "TikTok" to access', 300), ('your photos?', 322), ('Limit Access...', 700),
                             ('Allow Full Access', 760), ("Don't Allow", 820)):
                draw.text((120, y), label, fill='black')
            self.frames['tt_photos_prompt'] = png(image)
        prompt_text = copy.deepcopy(self.texts['tt_camera'])
        prompt_text['lines'] += [line('Allow "TikTok" to access', 120, 300), line('your photos?', 120, 322),
                                 line('Limit Access...', 120, 700), line('Allow Full Access', 120, 760), line("Don't Allow", 120, 820)]
        self.texts['tt_photos_prompt'] = prompt_text
        self.targets['allow_full'] = prompts.detect(prompt_text)['buttons']['Allow Full Access']
        # Paste callout above the press point (shape observed on the Instagram caption sheet).
        with Image.open(io.BytesIO(self.frames['tt_details_focused'])) as base:
            image = base.convert('RGB'); draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((30, 84, 200, 120), 8, fill='white', outline='#cccccc')
            draw.text((45, 96), 'Paste', fill='black'); draw.text((110, 96), 'AutoFill', fill='black')
            self.frames['tt_paste_menu'] = png(image)
        text = copy.deepcopy(self.texts['tt_details_focused'])
        text['lines'] += [line('Paste', 45, 96, 45), line('AutoFill', 110, 96, 70)]
        self.texts['tt_paste_menu'] = text
        self.reference = tt.TikTokReference((R17/'normalized-test.mp4').read_bytes())


class FixtureOcr:
    def __init__(self, kernel): self.kernel = kernel
    def read(self, raw):
        k = self.kernel
        if k.scenario == 'failed_ocr' and k.owned and k.screen == k.fault_screen: raise RuntimeError('Fixture OCR failure')
        text = copy.deepcopy(k.screens.texts[k.frame_key]); text['frameSha256'] = hashlib.sha256(raw).hexdigest()
        if k.scenario == 'wrong_account' and k.owned and k.screen in ('profile', 'profile_after'):
            for row in text['lines']:
                row['text'] = row['text'].replace(ACCOUNT, 'wrong.account')
                for word in row['words']: word['text'] = word['text'].replace(ACCOUNT, 'wrong.account')
        if k.scenario == 'wrong_caption' and k.screen in ('tt_details_pasted', 'tt_reopened_details'):
            for row in text['lines']:
                if row['text'] == CAPTION: row['text'] = 'A different caption'
        if k.scenario == 'prompt' and k.screen == k.fault_screen:
            text['lines'] += [line('Allow', 120, 600, 60), line("Don't Allow", 260, 600, 110)]
        return text


class FixtureKernel:
    _is_live_http = False

    def __init__(self, screens, scenario='normal', fault_screen=None, saved=False):
        self.screens, self.scenario, self.fault_screen = screens, scenario, fault_screen
        self.screen = 'profile_after' if saved else 'profile'; self.leg = 'out'
        self.saves = 1 if saved else 0; self.owned = False
        self.generation, self.sequence, self.now = 4, 100, 1000.
        self.session = uuid.uuid4().hex; self.calls = []; self.typed = ''
        self.unexpected = []; self.cancelled = None; self.photos = 0; self.removed = 0; self.captures = {}
        self.frame_key = None

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
        """The retained frame shown for the current state and capture count."""
        s, n = self.screen, self.captures.get(self.screen, 0)
        if s in ('home', 'search'): return s + '_' + self.leg
        if s == 'tt_editor':
            if self.removed: return 'tt_editor_sound' if self.scenario == 'sound_returns' else 'tt_editor_silent'
            if n < 2: return 'tt_editor_loading'
            return 'tt_editor_silent' if self.scenario == 'no_suggestion' else 'tt_editor_sound'
        if s == 'tt_details_focused' and n < 2: return 'tt_focused_caret'
        if s == 'tt_details_pasted' and (n < 2 or self.scenario == 'caret_forever'): return 'tt_details_caret'
        if s == 'tt_drafts' and self.scenario == 'sound_kept': return 'tt_drafts_sound'
        if s == 'tt_reopened': return 'tt_editor_sound' if self.scenario == 'sound_kept' and not self.removed else 'tt_editor_silent'
        if s == 'tt_drafts_kept' and self.scenario == 'sound_stays': return 'tt_drafts_sound'
        return s

    def shot(self, phone):
        self.resolve_device_id(phone); self.sequence += 1
        self.frame_key = self.key(); self.captures[self.screen] = self.captures.get(self.screen, 0) + 1
        raw = self.screens.frames[self.frame_key]
        if self.screen == 'tt_picker' and self.scenario == 'ambiguous_tile':
            with Image.open(io.BytesIO(raw)) as base:
                image = base.convert('RGB'); image.paste(image.crop((334, 804, 500, 967)), (167, 804)); raw = png(image)
        age = '2000' if self.scenario == 'stale_frame' and self.owned and self.screen == self.fault_screen else '0'
        return raw, {'X-iMouse-Frame-Session': self.session, 'X-iMouse-Frame-Sequence': str(self.sequence),
                     'X-iMouse-Frame-Age-Ms': age, 'X-iMouse-Frame-Delivery': 'flowing'}

    def send(self, phone, token, fun, **data):
        assert phone == 'C24C' and token == 'fixture-token' and self.owned
        self.calls.append((fun, dict(data)))
        if fun in ('/mouse/reset', '/mouse/move'):
            self.sequence += 1; return dict(code=0)
        if fun == '/mouse/down': return dict(code=0)
        if fun == '/mouse/up': self.transition('hold', *self.position); return dict(code=0)
        if fun == '/mouse/click': self.transition('click', data['x'], data['y']); return dict(code=0)
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
            ('search', 'click', None, 'safari'),
            ('safari', 'click', (245, 953), 'address'),
            ('tt_page', 'click', self.screens.targets['copy'], 'tt_copied'),
            ('tt_copied', 'hold', self.screens.targets['download'], 'link_menu'),
            ('link_menu', 'click', (161, 940), 'download_ready'),
            ('download_ready', 'click', (91, 955), 'page_menu'),
            ('page_menu', 'click', (100, 928), 'downloads'),
            ('downloads', 'click', (152, 594), 'quicklook_hidden'),
            ('quicklook_hidden', 'click', (250, 300), 'quicklook'),
            ('quicklook', 'click', (40, 1012), 'share'),
            ('share', 'click', (100, 846), 'quicklook'),
            ('quicklook', 'key:Home', None, 'home'),
            ('home', 'click', (192, 128), 'tt_feed'),
            ('tt_feed', 'click', (450, 1005), 'profile'),
            ('profile', 'click', (250, 1009), 'tt_camera'),
            ('tt_camera', 'click', (40, 1000), 'tt_photos_prompt' if self.scenario == 'photos_prompt' else 'tt_picker'),
            ('tt_photos_prompt', 'click', self.screens.targets['allow_full'], 'tt_picker'),
            ('tt_picker', 'click', (478, 825), 'tt_selected'),
            ('tt_selected', 'click', (367, 1006), 'tt_editor'),
            ('tt_editor', 'click', (339, 115), 'tt_editor'),
            ('tt_editor', 'click', (367, 1006), 'tt_details_blank'),
            ('tt_details_blank', 'click', (155, 139), 'tt_details_focused'),
            ('tt_details_focused', 'hold', (80, 140), 'tt_paste_menu'),
            ('tt_paste_menu', 'click', None, 'tt_details_pasted'),
            ('tt_details_pasted', 'click', (130, 1005), 'tt_feed_saved'),
            ('tt_feed_saved', 'click', (450, 1005), 'profile_after'),
            ('profile_after', 'click', (79, 478), 'tt_drafts'),
            ('tt_drafts', 'click', (81, 345), 'tt_reopened'),
            ('tt_reopened', 'click', (339, 115), 'tt_reopened'),
            ('tt_reopened', 'click', (367, 1006), 'tt_reopened_details'),
            ('tt_reopened_details', 'click', (130, 1005), 'tt_drafts_kept'),
        ]
        if s == 'address' and kind == 'key:Enter':
            assert self.typed == URL, self.typed
            self.screen = 'tt_page'; return
        for state, k, target, after in table:
            if state == s and k == kind and (target is None or near(*target, r=40 if state == 'search' else 14)):
                if s == 'share': self.photos += 1
                if target == (339, 115): self.removed += 1
                if s == 'home' and self.leg != ('back' if after == 'tt_feed' else 'out'): continue
                if s in ('tt_details_pasted', 'tt_reopened_details'):
                    self.saves += 1
                    self.screen = 'profile_saved' if self.scenario == 'lands_on_profile' and s == 'tt_details_pasted' else after
                    if self.scenario == 'lost_save' and s == 'tt_details_pasted': raise TimeoutError('Fixture Save happened; answer lost.')
                    return
                if s == 'quicklook' and kind == 'key:Home': self.leg = 'back'
                self.screen = after; return
        self.unexpected.append((s, kind, x, y))
        raise AssertionError(f'Unexpected {kind} at {(x, y)} on {s}')


class TikTokGuardTests(unittest.TestCase):
    def test_publishing_controls_are_never_targets_even_when_ocr_misreads_them(self):
        empty = dict(width=500, height=1080, lines=[])
        for role, point in (('tiktok_details', (370, 1005)), ('tiktok_editor', (130, 1005)), ('tiktok_camera', (440, 1000))):
            with self.assertRaises(InspectionStopped): tiktok_guard(empty, *point, role)
        story = dict(width=500, height=1080, lines=[line('Your Story', 103, 1000, 94)])
        with self.assertRaises(InspectionStopped): tiktok_guard(story, 150, 1006, 'tiktok_selected')
        tiktok_guard(empty, 130, 1005, 'tiktok_details'); tiktok_guard(empty, 367, 1006, 'tiktok_editor')


@unittest.skipUnless(PRIVATE, 'Retained private C24C frames/OCR are not available in this checkout.')
class TikTokProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shutil, subprocess
        cls.screens = Screens()
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory)/'other.mp4'
            subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=720x1280:rate=15:duration=3',
                            '-pix_fmt', 'yuv420p', '-c:v', 'libx264', str(other)], check=True)
            cls.other = tt.TikTokReference(other.read_bytes())

    def fixture(self, scenario='normal', fault_screen=None, saved=False, verifier=False):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        kernel = FixtureKernel(self.screens, scenario, fault_screen, saved)
        store = ObservationStore(folder/'observations.sqlite3', ocr=FixtureOcr(kernel), clock=kernel.clock, monotonic=kernel.clock,
                                 retained_limit=160)
        options = dict(account=ACCOUNT, package_hash='b'*64, monotonic=kernel.clock, pause=kernel.pause)
        if verifier:
            flow = TikTokVerification(folder, kernel, store, self.screens.reference, CAPTION, references(), 'a'*64, 'fixture-uid', **options)
        else:
            flow = TikTokCreationWorkflow(folder, kernel, store, self.screens.reference, CAPTION, references(), 'a'*64, 'fixture-uid',
                transfer_url=URL, download=DOWNLOAD, video_bytes=VIDEO_BYTES, **options)
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
        self.assertEqual(1, kernel.removed); self.assertEqual('profile_after', kernel.screen)
        self.assertEqual('confirmed', result['cleanup']); self.assertFalse(kernel.owned)
        self.assertEqual(dict(before=1, after=2), result['draftsCount'])
        self.assertEqual(dict(initial='attached', suggested='Whispers in.„', removed=True, final='none'), result['sound'])
        self.assertEqual([334, 804, 500, 967], result['pickerTile']); self.assertTrue(result['draftSavedToast'])
        self.assertEqual('feed', result['landedAfterSave'])
        self.assertTrue(all(a['state'] == 'answered' for a in result['actions']))
        self.assertTrue(any(isinstance(c.get('screenCheck'), dict) and c['screenCheck'].get('caretVisible')
                            for c in result['observations']))
        self.assertLess(len(result['observations']), 140)   # Retained-frame budget is 160 for both runs' exports.
        # Every TikTok tap rested on its target first; Safari taps stayed plain clicks.
        clicks = [i for i, c in enumerate(kernel.calls) if isinstance(c, tuple) and c[0] == '/mouse/click']
        settled = [i for i in clicks if kernel.calls[i-1][0] == '/mouse/move' and kernel.calls[i-1][1] == {k: kernel.calls[i][1][k] for k in ('x', 'y')}]
        self.assertGreaterEqual(len(settled), 10)
        flow2, kernel2 = self.fixture(saved=True, verifier=True)
        verified = flow2.run()
        self.assertEqual('validation_passed', verified['state'], verified.get('error'))
        self.assertTrue(verified['savedDraftVerified']); self.assertEqual('tiktok_drafts', verified['finalScreen'])
        self.assertEqual(2, kernel2.saves); self.assertEqual('tt_drafts_kept', kernel2.screen); self.assertEqual(0, kernel2.removed)
        self.assertEqual(2, verified['draftsAfter']['count']); self.assertIsNone(verified['draftsAfter']['soundLabel'])
        self.assertEqual('consistent_sampled_history', verified['accountHistory']['status'])

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
                self.assertLessEqual(kernel.removed, 1)

    def test_stop_at_each_dispatch_journal_sends_nothing_for_that_action(self):
        flow, kernel = self.fixture(); flow.run()
        labels = [a['label'] for a in flow.record['actions']]
        for label in labels:
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
        for boundary in (1, 8, 16, 22, total-1):
            with self.subTest(boundary=boundary):
                flow, kernel = self.fixture(); original = kernel.send
                def send(phone, token, fun, **data):
                    value = original(phone, token, fun, **data)
                    if len(self.semantic(kernel)) == boundary: kernel.session = uuid.uuid4().hex
                    return value
                with patch.object(kernel, 'send', send): result = flow.run()
                self.assertEqual('review_required', result['state'])
                self.assertEqual(boundary, len(self.semantic(kernel))); self.assertEqual('release', kernel.calls[-1])

    def test_tiktok_may_land_on_the_profile_after_drafts(self):
        flow, kernel = self.fixture('lands_on_profile'); result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error')); self.assertEqual([], kernel.unexpected)
        self.assertEqual(('profile', True), (result['landedAfterSave'], result['draftSavedToast']))
        self.assertEqual(dict(before=1, after=2), result['draftsCount']); self.assertEqual(1, kernel.saves)
        self.assertNotIn('open-profile-after-save', [a['label'] for a in result['actions']])

    def test_permission_prompt_stops_unless_a_method_is_validated(self):
        flow, kernel = self.fixture('photos_prompt'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(0, kernel.saves)
        self.assertIn('one-time step per phone and app', result['error']); self.assertEqual('tt_photos_prompt', kernel.screen)
        prompt = result['permissionPrompts'][0]
        self.assertEqual(('photos', 'TikTok', 'Allow Full Access', 'stop'), (prompt['kind'], prompt['app'], prompt['answer'], prompt['action']))
        self.assertEqual('confirmed', result['cleanup'])
        # A method proven in a validation window answers once and the run continues.
        flow, kernel = self.fixture('photos_prompt')
        flow.validated_prompt_methods = {('photos', 'pointer_tap'): ('validated', 'fixture')}
        result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error')); self.assertEqual([], kernel.unexpected)
        self.assertIn('answer-photos-prompt-1', [a['label'] for a in result['actions']])
        self.assertEqual('answer-photos-prompt-1', result['permissionPrompts'][-1]['answeredBy'])
        self.assertEqual(1, kernel.saves)

    def test_lost_drafts_answer_is_never_repeated(self):
        flow, kernel = self.fixture('lost_save'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(1, kernel.saves)
        self.assertEqual('save-tiktok-draft-once', result['actions'][-1]['label'])
        self.assertEqual('outcome_unknown', result['actions'][-1]['state'])

    def test_faults_stop_before_the_draft(self):
        cases = [('ambiguous_tile', None), ('prompt', 'tt_details_pasted'), ('prompt', 'tt_picker'), ('stale_frame', 'tt_selected'),
                 ('failed_ocr', 'tt_details_focused'), ('sound_returns', None), ('caret_forever', None), ('wrong_caption', None)]
        for scenario, screen in cases:
            with self.subTest(scenario=scenario, screen=screen):
                flow, kernel = self.fixture(scenario, screen); result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertEqual('confirmed', result['cleanup'])
                self.assertEqual(0, kernel.saves); self.assertEqual([], kernel.unexpected)
        flow, kernel = self.fixture('sound_returns'); result = flow.run()
        self.assertEqual(1, kernel.removed); self.assertIn('sound', result['error'])
        self.assertNotIn('open-tiktok-details', [a['label'] for a in result['actions']])
        # No suggestion: nothing is removed and the draft is saved silent.
        flow, kernel = self.fixture('no_suggestion'); result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error')); self.assertEqual(0, kernel.removed)
        self.assertEqual('none', result['sound']['initial'])
        # Different package media: the Files preview does not match, so nothing
        # reaches Photos or TikTok.
        flow, kernel = self.fixture(); flow.video = self.other; result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(0, kernel.saves)
        self.assertEqual(0, kernel.photos); self.assertIn('package video', result['error'])

    def test_verifier_removes_a_kept_suggested_sound_and_refuses_wrong_state(self):
        flow, kernel = self.fixture('sound_kept', saved=True, verifier=True); result = flow.run()
        self.assertEqual('validation_passed', result['state'], result.get('error')); self.assertEqual(1, kernel.removed)
        self.assertEqual('Whispers', result['draftsBefore']['soundLabel']); self.assertTrue(result['sound']['removed'])
        for scenario in ('wrong_account', 'wrong_caption', 'sound_stays'):
            with self.subTest(scenario=scenario):
                flow, kernel = self.fixture(scenario, saved=True, verifier=True); result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertFalse(result['savedDraftVerified'])
                self.assertEqual('confirmed', result['cleanup'])
                self.assertEqual(1 if scenario != 'sound_stays' else 2, kernel.saves)

    def test_committing_purposes_name_real_creation_actions(self):
        flow, kernel = self.fixture(); flow.run()
        labels = {a['label'] for a in flow.record['actions']}
        self.assertTrue(set(COMMITTING) <= labels, set(COMMITTING) - labels)


if __name__ == '__main__':
    unittest.main()
