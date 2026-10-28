"""YouTube creation/verification against retained C24C screens and a simulated HID kernel.

No socket, desktop or phone access. YouTube screens are retained 17 Oct frames
(MP4 Short 131-151, photo Short 46-66 for the search result and the trimmed
selection) with their OCR; Safari/Files screens are the retained 17 Oct
video-transfer frames and 19 Oct Home/Safari frames. Synthetic parts are
labelled: the transfer page, the Paste callout, and the title drawn into the
details and drafts frames (the retained title is 32 characters, longer than the
candidate allows). The selected picker joins two retained frames of that screen
so the supervised pointer covers neither the badge nor Next. The channel handle
is read from the retained details frame at run time and is never written into
this file. This tests the protocol and recognizers on known layouts. It is not
fresh-phone acceptance.
"""
from farm_phone_identity import LEGACY_C24C
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

from PIL import Image, ImageDraw

import farm_test_network  # noqa: F401  Refuse every real socket in this process.
import farm_permission_prompts as prompts
import farm_tiktok_layout as tt
from farm_draft_workflow import references
from farm_observations import ObservationStore
from farm_reel_test_media import font
from farm_youtube_creation import YouTubeCreationWorkflow, YouTubeVerification, COMMITTING, PENDING, guard
from farm_carousel_inspection import InspectionStopped
from imouse_social_automation import LIVE_TEST_DEVICE_ID, DEFAULT_SAFE_TEST_DEVICE
import test_farm_youtube_layout as layout

ROOT = Path(__file__).resolve().parents[1]
R17 = layout.R17
import farm_paths  # noqa: E402  (the archive beside the main folder, also from a lane worktree)
OCR_SAFARI = farm_paths.ARCHIVE/'20261019-farm-reel-offline/ocr-20261017'
OCR_YT = layout.OCR
P1 = farm_paths.ARCHIVE/'20261019-farm-new-draft/backend/draft-creations/b8c155e2-1670-4f60-a090-aeff921e162e'
PRIVATE = layout.PRIVATE and all(p.exists() for p in (OCR_SAFARI, P1/'record.json'))
CAPTION = 'Fresh yt acceptance'
URL = 'http://192.168.50.2:9917/t/fixture-token/'
VIDEO_BYTES = 78953
DOWNLOAD = 'imouse-yt-acdefh'
# The phone comes from configuration; the fixture names the one phone this branch's shared transport drives.
PHONE = dict(board=DEFAULT_SAFE_TEST_DEVICE, deviceId=LIVE_TEST_DEVICE_ID, receiver='iMouse2-' + DEFAULT_SAFE_TEST_DEVICE)


def png(image):
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


def line(text, x, y, width=None, height=18):
    words, cursor = [], x
    for part in text.split(' '):
        w = max(8, round((width or len(text)*9) * len(part)/max(1, len(text))))
        words.append(dict(text=part, x=cursor, y=y, width=w, height=height)); cursor += w + 6
    return dict(text=text, words=words)


def bounds(row):
    words = row.get('words') or [dict(x=0, y=0, width=0, height=0)]
    return min(w['x'] for w in words), min(w['y'] for w in words)


class Screens:
    def __init__(self):
        self.frames, self.texts = {}, {}
        p1 = json.loads((P1/'record.json').read_text(encoding='utf-8'))
        by_frame = {e['frame']: e['observation']['text'] for e in p1['observations'] if e.get('state') == 'observed'}
        def p1_state(key, name):
            self.frames[key] = (P1/name).read_bytes(); self.texts[key] = copy.deepcopy(by_frame[name])
        def r17(key, step, which='after', ocr=OCR_YT):
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
        r17('yt_home', '136-youtube-after-operator'); r17('yt_query', '48-youtube-query'); r17('yt_prompt', '132-youtube-loaded')
        r17('yt_old_home', '50-youtube-loaded'); r17('yt_camera', '137-youtube-create-video'); r17('yt_picker', '138-youtube-mp4-picker')
        r17('yt_trim', '140-youtube-mp4-trim-review'); r17('yt_trimmed', '55-youtube-editor'); r17('yt_editor', '141-youtube-mp4-editor')
        r17('yt_details_blank', '142-youtube-video-details'); r17('yt_details_focused', '143-youtube-video-caption-focus')
        r17('yt_home_saved', '145-youtube-save-video-draft'); r17('yt_camera_drafts', '146-youtube-draft-route')
        r17('yt_reopened', '148-youtube-video-draft-reopen'); r17('yt_reopened_later', '149-youtube-reopened-caption', 'before')
        r17('yt_home_kept', '150-youtube-resave-verified-video')
        r17('yt_camera_closing', '146-youtube-draft-route')   # The camera again after Drafts closes.
        self.frames['yt_selected'], self.texts['yt_selected'] = layout.selected_picker()
        if (layout.LIVE26/'gallery.bmp').exists():   # Slot 16, 26 Oct: Drafts only in the gallery.
            for key, name in (('yt_camera_white', 'camera-white'), ('yt_gallery', 'gallery'), ('yt_gallery_back', 'gallery-back')):
                self.frames[key], self.texts[key] = layout.live26(name)
        self.synthetic()

    def synthetic(self):
        page = Image.new('RGB', (500, 1080), '#f4f7fc'); draw = ImageDraw.Draw(page)
        rows = [('YouTube draft', 30, 120), ('File ' + DOWNLOAD, 30, 190), ('Download video', 170, 262), ('Copy caption', 180, 400)]
        for label, x, y in rows: draw.text((x, y), label, fill='black')
        self.frames['yt_page'] = png(page)
        self.texts['yt_page'] = dict(width=500, height=1080, lines=[line(t, x, y) for t, x, y in rows])
        def centre(label):
            words = next(r['words'] for r in self.texts['yt_page']['lines'] if r['text'] == label)
            return (round((min(w['x'] for w in words)+max(w['x']+w['width'] for w in words))/2),
                    round((min(w['y'] for w in words)+max(w['y']+w['height'] for w in words))/2))
        self.targets = dict(copy=centre('Copy caption'), download=centre('Download video'))
        copied = page.copy(); ImageDraw.Draw(copied).text((30, 450), 'Caption copied.', fill='black')
        self.frames['yt_copied'] = png(copied)
        self.texts['yt_copied'] = dict(width=500, height=1080, lines=[line(t, x, y) for t, x, y in rows]
                                       + [line('Caption copied. Verify the pasted text in', 30, 450), line('YouTube.', 30, 478)])
        # Paste callout above the press point (shape observed on the Instagram caption sheet).
        with Image.open(io.BytesIO(self.frames['yt_details_focused'])) as base:
            image = base.convert('RGB'); draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((60, 84, 230, 118), 8, fill='white', outline='#cccccc')
            draw.text((75, 94), 'Paste', fill='black'); draw.text((140, 94), 'AutoFill', fill='black')
            self.frames['yt_paste_menu'] = png(image)
        text = copy.deepcopy(self.texts['yt_details_focused'])
        text['lines'] += [line('Paste', 75, 94, 45), line('AutoFill', 140, 94, 70)]
        self.texts['yt_paste_menu'] = text
        self.targets['paste'] = (98, 102)
        # YouTube's 'Continue your draft video?' dialog over the Short camera after a cold start (slot 16, 26 Oct).
        for camera in ('yt_camera', 'yt_camera_drafts'):
            with Image.open(io.BytesIO(self.frames[camera])) as base:
                image = base.convert('RGB'); draw = ImageDraw.Draw(image)
                draw.rectangle((78, 450, 422, 648), fill='white')
                for label, x, y in (('Continue your draft video?', 107, 482), ('Start over', 215, 610), ('Continue', 323, 610)):
                    draw.text((x, y), label, fill='black')
                self.frames[camera + '_prompt'] = png(image)
            text = copy.deepcopy(self.texts[camera])
            text['lines'] += [line('Continue your draft video?', 107, 482, 284, 19), line('Starting over will save the draft and', 107, 530, 273),
                              line('start a new Short.', 107, 550, 136), line('Start over', 215, 610, 78, 13), line('Continue', 323, 610, 71, 13)]
            self.texts[camera + '_prompt'] = text
        # The candidate's title drawn into the title field, with and without the caret.
        self.titled('yt_details_titled', 'yt_details_focused', '143-youtube-video-caption-focus')
        self.titled('yt_reopened_details', None, '149-youtube-reopened-caption')
        with Image.open(io.BytesIO(self.frames['yt_details_titled'])) as base:
            image = base.convert('RGB'); ImageDraw.Draw(image).rectangle((330, 157, 331, 180), fill=(20, 20, 20))
            self.frames['yt_details_caret'] = png(image)
        self.texts['yt_details_caret'] = copy.deepcopy(self.texts['yt_details_titled'])
        # A drawn caret beside a field that does not hold the caption (the title area blanked).
        with Image.open(io.BytesIO(self.frames['yt_details_caret'])) as base:
            image = base.convert('RGB'); ImageDraw.Draw(image).rectangle((128, 150, 328, 186), fill='white')
            self.frames['yt_details_caret_wrong'] = png(image)
        self.texts['yt_details_caret_wrong'] = copy.deepcopy(self.texts['yt_details_titled'])
        # The drafts list with the candidate's title on the newest row (retained rows, thumbnails and times kept).
        step = '147-youtube-video-draft-library'
        with Image.open(R17/step/'after.png') as base:
            image = base.convert('RGB'); draw = ImageDraw.Draw(image)
            draw.rectangle((160, 190, 455, 232), fill='white'); draw.text((168, 194), CAPTION, font=font(15), fill=(30, 30, 30))
            self.frames['yt_drafts'] = png(image)
        text = json.loads((OCR_YT/f'{step}__after.json').read_text(encoding='utf-8')); text.pop('source', None)
        text['lines'] = [r for r in text['lines'] if r['text'] not in ('IMOUSE-VIDEO-DRAFT-', 'TEST-20261017')] + [line(CAPTION, 168, 194, 190, 15)]
        self.texts['yt_drafts'] = text
        self.reference = tt.TikTokReference((R17/'normalized-test.mp4').read_bytes())

    def titled(self, key, base_key, step):
        if base_key is None:
            frame = (R17/step/'after.png').read_bytes()
            text = json.loads((OCR_YT/f'{step}__after.json').read_text(encoding='utf-8')); text.pop('source', None)
        else:
            frame, text = self.frames[base_key], copy.deepcopy(self.texts[base_key])
        with Image.open(io.BytesIO(frame)) as base:
            image = base.convert('RGB'); draw = ImageDraw.Draw(image)
            draw.rectangle((128, 150, 492, 188), fill='white'); draw.text((135, 159), CAPTION, font=font(17), fill=(34, 33, 34))
            self.frames[key] = png(image)
        text['lines'] = [r for r in text['lines'] if not (128 <= bounds(r)[0] <= 495 and 150 <= bounds(r)[1] < 190)]
        text['lines'].append(line(CAPTION, 135, 158, 200, 17))
        self.texts[key] = text


class FixtureOcr:
    def __init__(self, kernel): self.kernel = kernel
    def read(self, raw):
        k = self.kernel
        text = copy.deepcopy(k.screens.texts[k.frame_key]); text['frameSha256'] = hashlib.sha256(raw).hexdigest()
        details = k.screen.startswith('yt_details') or k.screen == 'yt_reopened_details' or k.screen == 'yt_paste_menu'
        if details: k.details_reads += 1
        if k.scenario == 'other_channel' and details and k.details_reads > k.other_after:
            for row in text['lines']:
                if row['text'].startswith('@') and 65 <= bounds(row)[0] <= 90:
                    row['text'] = '@other_channel'; row['words'] = [dict(row['words'][0], text='@other_channel')]
        if k.scenario == 'wrong_text' and k.screen in ('yt_drafts', 'yt_drafts_final'):
            for row in text['lines']:
                if row['text'] == CAPTION: row['text'] = 'A different title'; row['words'] = [dict(row['words'][0], text='A different title')]
        if k.scenario == 'wrong_title' and k.screen == 'yt_details_titled':
            for row in text['lines']:
                if row['text'] == CAPTION: row['text'] = 'Clipboard leftover'; row['words'] = [dict(row['words'][0], text='Clipboard leftover')]
        if k.scenario in ('slow_recognition', 'changed_after_recognition') and k.screen == k.fault_screen:
            k.now += 1.6; k.recognitions += 1   # Recognition outlasts the 1.5 s frame-age budget (loaded PC).
        if k.scenario == 'prompt' and k.screen == k.fault_screen:
            text['lines'] += [line('Allow', 120, 600, 60), line("Don't Allow", 260, 600, 110)]
        if k.scenario == 'shifted_drafts_ocr' and k.screen == 'yt_drafts':
            k.drafts_reads = getattr(k, 'drafts_reads', 0) + 1
            if k.drafts_reads <= 2:   # Run 70 (26 Oct): every word of one frame placed about 40 px off.
                for row in text['lines']:
                    for word in row['words']: word['x'] = max(0, word['x'] - 40); word['y'] += 14
        return text


class FixtureKernel:
    _is_live_http = False
    phone = LEGACY_C24C   # The window's verified phone; PHONE below is the same C24C phone.

    def __init__(self, screens, scenario='normal', fault_screen=None, saved=False, start=None):
        self.screens, self.scenario, self.fault_screen = screens, scenario, fault_screen
        self.screen = start or ('yt_home_saved' if saved else 'yt_home'); self.leg = 'out'
        self.saves = 1 if saved else 0; self.owned = False
        self.generation, self.sequence, self.now = 4, 100, 1000.
        self.session = uuid.uuid4().hex; self.calls = []; self.typed = ''; self.searched = ''
        self.unexpected = []; self.cancelled = None; self.photos = 0; self.captures = {}; self.frame_key = None
        self.details_reads = 0; self.other_after = 2   # Creation binds on its second (settled) Add details read.
        self.recognitions = 0
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
        if s in ('yt_camera_prompt', 'yt_camera_drafts_prompt'): return s
        if s == 'yt_reopened': return 'yt_reopened_later' if n % 2 and self.scenario != 'frozen_video' else 'yt_reopened'
        if s == 'yt_details_titled' and self.scenario == 'caret_forever': return 'yt_details_caret'
        if s == 'yt_details_titled' and self.scenario == 'caret_wrong': return 'yt_details_caret_wrong'
        return {'yt_camera_final': 'yt_camera_drafts', 'yt_drafts_final': 'yt_drafts'}.get(s, s)

    def shot(self, phone):
        self.resolve_device_id(phone)   # The latest delivered frame; only a change on the phone delivers another.
        self.frame_key = self.key(); self.captures[self.screen] = self.captures.get(self.screen, 0) + 1
        raw = self.screens.frames[self.frame_key]
        if self.screen == 'yt_picker' and self.scenario == 'ambiguous_tile':
            with Image.open(io.BytesIO(raw)) as base:
                image = base.convert('RGB'); image.paste(image.crop((0, 298, 164, 589)), (168, 298)); raw = png(image)
        if self.scenario == 'changed_after_recognition' and self.screen == self.fault_screen and self.recognitions >= 2:
            with Image.open(io.BytesIO(raw)) as base:   # Changed after the decision frame settled (two recognitions).
                image = base.convert('RGB'); ImageDraw.Draw(image).rectangle((100, 600, 400, 700), fill='black'); raw = png(image)
        age = '2000' if self.scenario == 'stale_frame' and self.owned and self.screen == self.fault_screen else '0'
        return raw, {'X-iMouse-Frame-Session': self.session, 'X-iMouse-Frame-Sequence': str(self.sequence),
                     'X-iMouse-Frame-Age-Ms': age, 'X-iMouse-Frame-Delivery': 'flowing'}

    def send(self, phone, token, fun, **data):
        assert phone == 'C24C' and token == 'fixture-token' and self.owned
        self.calls.append((fun, dict(data)))
        if fun == '/mouse/reset':
            self.pointer = None; self.sequence += 1; return dict(code=0)
        if fun == '/mouse/move':
            # A move onto the pointer's current spot changes nothing on the phone, so no new frame arrives.
            if self.pointer != (data['x'], data['y']): self.pointer = (data['x'], data['y']); self.sequence += 1
            return dict(code=0)
        if fun == '/mouse/down': return dict(code=0)
        if fun == '/mouse/up': self.transition('hold', *self.position); return dict(code=0)
        if fun == '/mouse/click': self.pointer = (data['x'], data['y']); self.transition('click', data['x'], data['y']); return dict(code=0)
        if fun == '/key/sendkey':
            if 'key' in data:
                if self.screen == 'address': self.typed += data['key']; return dict(code=0)
                assert self.screen == 'search' and self.leg == 'back' and data['key'] == 'YouTube', (self.screen, data)
                self.searched += data['key']; self.screen = 'yt_query'; return dict(code=0)
            self.transition('key:' + data['fn_key']); return dict(code=0)
        raise AssertionError('Unapproved function ' + fun)

    @property
    def position(self):
        moves = [c[1] for c in self.calls if isinstance(c, tuple) and c[0] in ('/mouse/move', '/mouse/click')]
        return (moves[-1]['x'], moves[-1]['y']) if moves else (0, 0)

    def transition(self, kind, x=None, y=None):
        near = lambda tx, ty, r=14: x is not None and abs(x-tx) <= r and abs(y-ty) <= r
        s = self.screen
        dont_allow = prompts.detect(self.screens.texts['yt_prompt'])['buttons']["Don't Allow"]
        table = [
            ('yt_home', 'key:Home', None, 'home'),
            ('home', 'click', (250, 900), 'search'),
            ('search', 'click', None, 'safari'),
            ('safari', 'click', (245, 953), 'address'),
            ('yt_page', 'click', self.screens.targets['copy'], 'yt_copied'),
            ('yt_copied', 'hold', self.screens.targets['download'], 'link_menu'),
            ('link_menu', 'click', (161, 940), 'download_ready'),
            ('download_ready', 'click', (91, 955), 'page_menu'),
            ('page_menu', 'click', (100, 928), 'downloads'),
            ('downloads', 'click', (152, 594), 'quicklook_hidden'),
            ('quicklook_hidden', 'click', (40, 960), 'quicklook'),   # Reveal above the toolbar (21 Oct).
            ('quicklook', 'click', (40, 1012), 'share'),
            ('share', 'click', (100, 846), 'quicklook'),
            ('quicklook', 'key:Home', None, 'home'),
            ('yt_query', 'click', (87, 218), 'yt_prompt' if self.scenario == 'launch_prompt' else 'yt_home'),
            ('yt_prompt', 'click', dont_allow, 'yt_home'),
            ('yt_home', 'click', (311, 1020), 'yt_camera_prompt' if self.scenario == 'draft_prompt' else 'yt_camera'),
            ('yt_camera_prompt', 'click', (254, 616), 'yt_camera'),
            ('yt_camera', 'click', (46, 847), 'yt_picker'),
            ('yt_picker', 'click', (141, 320), 'yt_selected'),
            ('yt_selected', 'click', (367, 997), 'yt_trimmed' if self.scenario == 'trimmed' else 'yt_trim'),
            ('yt_trim', 'click', (449, 1005), 'yt_editor'),
            ('yt_editor', 'click', (368, 1006), 'yt_details_blank'),
            ('yt_details_blank', 'click', (256, 161), 'yt_details_focused'),
            ('yt_details_focused', 'hold', (220, 165), 'yt_paste_menu'),
            ('yt_paste_menu', 'click', self.screens.targets['paste'], 'yt_details_titled'),
            ('yt_details_titled', 'click', (130, 996), 'yt_home_saved'),
            # Verification.
            ('yt_home_saved', 'click', (311, 1020), {'draft_prompt': 'yt_camera_drafts_prompt', 'gallery_drafts': 'yt_camera_white'}
                .get(self.scenario, 'yt_camera_drafts')),
            ('yt_camera_white', 'click', (46, 847), 'yt_gallery'),
            ('yt_gallery', 'click', (128, 177), 'yt_drafts'),
            ('yt_gallery_back', 'click', (465, 87), 'yt_camera_closing'),
            ('yt_camera_drafts_prompt', 'click', (254, 616), 'yt_camera_drafts'),
            ('yt_camera_drafts', 'click', (455, 846), 'yt_drafts'),
            ('yt_drafts', 'click', (228, 264), 'yt_reopened'),
            ('yt_drafts', 'click', (44, 77), 'yt_gallery_back' if self.scenario == 'gallery_drafts' else 'yt_camera_closing'),   # Read-only verifier (23 Oct).
            ('yt_camera_closing', 'click', (44, 125), 'yt_home_kept'),
            ('yt_reopened', 'click', (368, 1006), 'yt_reopened_details'),
            ('yt_reopened_details', 'click', (130, 996), 'yt_home_kept'),
            ('yt_home_kept', 'click', (311, 1020), 'yt_camera_final'),
            ('yt_camera_final', 'click', (455, 846), 'yt_drafts_final'),
        ]
        if s == 'address' and kind == 'key:Enter':
            assert self.typed == URL, self.typed
            self.screen = 'yt_page'; return
        for state, k, target, after in table:
            if state == s and k == kind and (target is None or near(*target, r=40 if state == 'search' else 14)):
                if state == 'home' and self.leg == 'back': after = 'search'
                if state == 'search' and self.leg == 'back': continue
                if s == 'share': self.photos += 1
                if s in ('yt_details_titled', 'yt_reopened_details'):
                    self.saves += 1; self.screen = after
                    if self.scenario == 'lost_save' and s == 'yt_details_titled': raise TimeoutError('Fixture Save happened; answer lost.')
                    if self.scenario == 'lost_keep' and s == 'yt_reopened_details': raise TimeoutError('Fixture Save happened; answer lost.')
                    return
                if s == 'quicklook' and kind == 'key:Home': self.leg = 'back'
                self.screen = after; return
        self.unexpected.append((s, kind, x, y))
        raise AssertionError(f'Unexpected {kind} at {(x, y)} on {s}')


class YouTubeGuardTests(unittest.TestCase):
    def test_upload_record_live_post_and_draft_menus_are_never_targets(self):
        empty = dict(width=500, height=1080, lines=[])
        for role, point in (('yt_details', (370, 996)), ('yt_reopened_details', (370, 996)), ('yt_details_blank', (380, 345)),
                            ('yt_camera', (250, 845)), ('yt_camera', (326, 992)), ('yt_camera', (397, 992)), ('yt_camera', (457, 125)),
                            ('yt_drafts', (474, 205)), ('yt_picker_selected', (147, 995)), ('yt_editor', (266, 101)),
                            ('yt_editor', (130, 1005)), ('yt_draft_prompt', (358, 616)), ('yt_draft_prompt', (250, 845))):
            with self.subTest(role=role, point=point), self.assertRaises(InspectionStopped): guard(empty, *point, role)
        for role, point in (('yt_details', (130, 996)), ('yt_camera', (46, 847)), ('yt_camera', (455, 846)), ('yt_drafts', (228, 264)),
                            ('yt_picker_selected', (367, 997)), ('yt_editor', (368, 1006)), ('yt_draft_prompt', (254, 616))):
            guard(empty, *point, role)
        labelled = dict(width=500, height=1080, lines=[line('Upload Short', 318, 989, 106)])
        with self.assertRaises(InspectionStopped): guard(labelled, 300, 996, 'yt_trim')


@unittest.skipUnless(PRIVATE, 'Retained private C24C frames/OCR are not available in this checkout.')
class YouTubeProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.screens = Screens()
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory)/'other.mp4'
            subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=720x1280:rate=15:duration=3',
                            '-pix_fmt', 'yuv420p', '-c:v', 'libx264', str(other)], check=True)
            cls.other = tt.TikTokReference(other.read_bytes())

    def fixture(self, scenario='normal', fault_screen=None, saved=False, verifier=False, account=None, start=None, phone=PHONE):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        kernel = FixtureKernel(self.screens, scenario, fault_screen, saved, start)
        store = ObservationStore(folder/'observations.sqlite3', ocr=FixtureOcr(kernel), clock=kernel.clock, monotonic=kernel.clock,
                                 retained_limit=160)
        options = dict(package_hash='b'*64, monotonic=kernel.clock, pause=kernel.pause, phone=phone)
        if verifier:
            flow = YouTubeVerification(folder, kernel, store, self.screens.reference, CAPTION, references(), 'a'*64, 'fixture-uid',
                                       account=account, **options)
        else:
            flow = YouTubeCreationWorkflow(folder, kernel, store, self.screens.reference, CAPTION, references(), 'a'*64, 'fixture-uid',
                                           transfer_url=URL, download=DOWNLOAD, video_bytes=VIDEO_BYTES, **options)
        kernel.cancelled = flow.cancelled
        return flow, kernel

    @staticmethod
    def semantic(kernel):
        return [c for c in kernel.calls if isinstance(c, tuple) and (c[0] in ('/mouse/click', '/mouse/up') or
                (c[0] == '/key/sendkey' and 'fn_key' in c[1] and c[1]['fn_key'] != 'Enter'))]

    def create(self, scenario='normal'):
        flow, kernel = self.fixture(scenario); result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error'))
        return result, kernel

    def test_creation_binds_the_details_channel_then_verification_passes(self):
        result, kernel = self.create()
        self.assertEqual([], kernel.unexpected); self.assertEqual(1, kernel.saves); self.assertEqual(1, kernel.photos)
        self.assertEqual('yt_home_saved', kernel.screen); self.assertEqual('YouTube', kernel.searched)
        self.assertNotEqual(PENDING, result['account']); self.assertRegex(result['account'], r'^[A-Za-z0-9_.-]{1,50}$')
        self.assertEqual('add_details_channel_handle', result['accountBinding']['method'])
        self.assertEqual(layout.FIRST, result['pickerTile']); self.assertEqual('confirmed', result['cleanup'])
        self.assertTrue(result['draftSavedToast'])
        self.assertTrue(all(a['state'] == 'answered' for a in result['actions']))
        labels = [a['label'] for a in result['actions']]
        self.assertLess(labels.index('keep-whole-video'), labels.index('paste-exact-caption'))
        self.assertEqual('save-youtube-draft-once', labels[-1])
        # The binding observation is the first Add details frame, before the title field is touched.
        binding = next(i for i, e in enumerate(result['observations']) if e['observationId'] == result['accountBinding']['observationId'])
        focus = next(a for a in result['actions'] if a['label'] == 'focus-empty-title')['observationId']
        self.assertLess(binding, next(i for i, e in enumerate(result['observations']) if e['observationId'] == focus))
        flow, kernel2 = self.fixture(saved=True, verifier=True, account=result['account'])
        verified = flow.run()
        self.assertEqual('validation_passed', verified['state'], verified.get('error')); self.assertEqual([], kernel2.unexpected)
        # Read only (23 Oct): nothing is reopened or saved again; the Drafts list decides.
        self.assertEqual(1, kernel2.saves); self.assertEqual('yt_home_kept', kernel2.screen); self.assertFalse(verified['reopened'])
        self.assertNotIn('verify-open-saved-draft', [a['label'] for a in verified['actions']])
        self.assertEqual(([CAPTION], 2), (verified['draftsBefore']['title'], verified['draftsBefore']['rows']))
        self.assertTrue(verified['draftsBefore']['match']['matched'])
        self.assertEqual('consistent_sampled_history', verified['accountHistory']['status'])
        self.assertEqual(result['account'], verified['account'])

    def test_the_draft_prompt_over_the_camera_is_answered_with_start_over(self):
        # After a cold start the Short camera asks 'Continue your draft video?' (slot 16, 23-26 Oct); Start over
        # saves that draft. Creation and the verifier answer it once at Start over's centre, never Continue.
        result, kernel = self.create('draft_prompt')
        self.assertEqual([], kernel.unexpected); self.assertTrue(result['draftPromptSeen'])
        self.assertIn(('/mouse/click', dict(x=253, y=616, button=1)), [c[:2] for c in kernel.calls if isinstance(c, tuple)])
        labels = [a['label'] for a in result['actions']]
        self.assertEqual(labels.index('open-youtube-create') + 1, labels.index('create-start-over-saves-draft'))
        flow, kernel2 = self.fixture('draft_prompt', saved=True, verifier=True, account=result['account'])
        verified = flow.run()
        self.assertEqual('validation_passed', verified['state'], verified.get('error')); self.assertEqual([], kernel2.unexpected)
        self.assertIn('verify-start-over-saves-draft', [a['label'] for a in verified['actions']])
        flow, kernel3 = self.fixture(saved=True, verifier=True, account=result['account'])
        self.assertFalse(flow.run()['draftPromptSeen'])

    @unittest.skipUnless((layout.LIVE26/'gallery.bmp').exists(), 'Slot 16 frames of 26 Oct are not available.')
    def test_the_verifier_reaches_drafts_through_the_gallery_when_the_camera_has_none(self):
        result, _ = self.create()
        flow, kernel = self.fixture('gallery_drafts', saved=True, verifier=True, account=result['account'])
        verified = flow.run()
        self.assertEqual('validation_passed', verified['state'], verified.get('error')); self.assertEqual([], kernel.unexpected)
        self.assertEqual('gallery', verified['draftsRoute']); self.assertEqual('yt_home_kept', kernel.screen)
        labels = [a['label'] for a in verified['actions']]
        self.assertEqual(['verify-open-create', 'verify-open-gallery', 'verify-open-gallery-drafts', 'verify-close-drafts',
                          'verify-close-gallery', 'verify-close-camera'], labels)

    def test_a_mispositioned_drafts_read_is_read_again_without_input(self):
        result, _ = self.create()
        flow, kernel = self.fixture('shifted_drafts_ocr', saved=True, verifier=True, account=result['account'])
        verified = flow.run()
        self.assertEqual('validation_passed', verified['state'], verified.get('error')); self.assertEqual([], kernel.unexpected)
        self.assertTrue(verified['draftsRereads'])
        self.assertEqual(['verify-open-create', 'verify-open-drafts', 'verify-close-drafts', 'verify-close-camera'],
                         [a['label'] for a in verified['actions']])

    def test_a_different_channel_stops_creation_and_verification(self):
        flow, kernel = self.fixture('other_channel'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(0, kernel.saves)
        self.assertIn('different YouTube channel', result['error'])
        self.assertNotIn('paste-exact-caption', [a['label'] for a in result['actions'] if a['state'] == 'answered'])
        # The read-only verifier (23 Oct) never opens Add details, so it does not read the channel again;
        # creation's binding stands.

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

    def test_lost_save_draft_answer_is_never_repeated(self):
        flow, kernel = self.fixture('lost_save'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(1, kernel.saves)
        self.assertEqual('save-youtube-draft-once', result['actions'][-1]['label']); self.assertEqual('outcome_unknown', result['actions'][-1]['state'])

    def test_faults_stop_before_the_draft(self):
        cases = [('ambiguous_tile', None), ('prompt', 'yt_details_titled'), ('prompt', 'yt_camera'), ('stale_frame', 'yt_selected'),
                 ('trimmed', None), ('caret_wrong', None), ('wrong_title', None)]
        for scenario, screen in cases:
            with self.subTest(scenario=scenario, screen=screen):
                flow, kernel = self.fixture(scenario, screen); result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertEqual('confirmed', result['cleanup'])
                self.assertEqual(0, kernel.saves); self.assertEqual([], kernel.unexpected)
        flow, kernel = self.fixture('trimmed'); result = flow.run()
        self.assertIn('whole package video', result['error']); self.assertNotIn('keep-whole-video', [a['label'] for a in result['actions']])
        flow, kernel = self.fixture('caret_wrong'); result = flow.run()
        self.assertIn('caret', result['error']); self.assertNotIn('save-youtube-draft-once', [a['label'] for a in result['actions']])
        # A caret drawn in every frame (slot 16, run 74): the exact title read with the caret blanked decides.
        flow, kernel = self.fixture('caret_forever'); result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error')); self.assertEqual(1, kernel.saves)
        # Different package media: the Files preview does not match, so nothing reaches Photos or YouTube.
        flow, kernel = self.fixture(); flow.video = self.other; result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(0, kernel.photos); self.assertIn('package video', result['error'])

    def test_the_local_network_prompt_stops_with_a_one_time_request_unless_validated(self):
        # Retained 17 Oct prompt over the home feed, at admission: nothing is sent at all.
        flow, kernel = self.fixture(start='yt_prompt'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual([], kernel.calls)
        self.assertIn('one-time step per phone and app', result['error']); self.assertIn('No input was sent', result['error'])
        self.assertEqual(('local_network', 'stop'), (result['permissionPrompts'][0]['kind'], result['permissionPrompts'][0]['action']))
        # The same prompt when YouTube is reopened after the import: the run stops there, before any YouTube input.
        flow, kernel = self.fixture('launch_prompt'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual('yt_prompt', kernel.screen); self.assertEqual(0, kernel.saves)
        self.assertIn('"Don\'t Allow"', result['error']); self.assertEqual('confirmed', result['cleanup'])
        self.assertNotIn('open-youtube-create', [a['label'] for a in result['actions']])
        # A method proven in a validation window answers Don't Allow once and the run continues.
        flow, kernel = self.fixture('launch_prompt')
        flow.validated_prompt_methods = {('local_network', 'pointer_tap'): ('validated', 'fixture')}
        result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error')); self.assertEqual([], kernel.unexpected)
        self.assertIn('answer-local-network-prompt-1', [a['label'] for a in result['actions']])
        self.assertEqual(("Don't Allow", 'answer-local-network-prompt-1'),
                         (result['permissionPrompts'][-1]['answer'], result['permissionPrompts'][-1]['answeredBy']))
        self.assertEqual(1, kernel.saves)

    def test_admission_needs_the_observed_home_layout(self):
        # The labelled five-item home (yt_old_home) is accepted since 22 Oct (slot 16); the camera is not a start.
        flow, kernel = self.fixture(start='yt_camera'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual([], kernel.calls)
        self.assertIn('Start on the YouTube home feed', result['error'])

    def test_the_phone_is_the_configured_one_and_its_receiver_must_mirror_it(self):
        # The configured YouTube phone must be exactly the window's own verified phone, receiver name included:
        # anything else is refused before the workflow exists, so no input is possible.
        flow, kernel = self.fixture()
        with self.assertRaises(InspectionStopped):
            YouTubeCreationWorkflow(flow.folder, kernel, flow.store, self.screens.reference, CAPTION, references(), 'a'*64, 'fixture-uid',
                                    transfer_url=URL, download=DOWNLOAD, video_bytes=VIDEO_BYTES, package_hash='b'*64,
                                    phone=dict(PHONE, receiver='iMouse2-18'))
        self.assertEqual([], kernel.calls)
        # The slot 16 phone cannot be driven by this branch's shared transport: refused before anything starts.
        flow, kernel = self.fixture()
        slot16 = dict(board='F215', deviceId='02:00:00:00:00:16', receiver='iMouse2-16', slot=16)
        with self.assertRaises(InspectionStopped):
            YouTubeCreationWorkflow(flow.folder, kernel, flow.store, self.screens.reference, CAPTION, references(), 'a'*64, 'fixture-uid',
                                    transfer_url=URL, download=DOWNLOAD, video_bytes=VIDEO_BYTES, package_hash='b'*64, phone=slot16)
        self.assertEqual([], kernel.calls)

    def test_verifier_refuses_wrong_text_and_other_media(self):
        account = self.create()[0]['account']
        for scenario, reason in (('wrong_text', 'exact draft title is absent'), ('other_media', 'does not show the package video')):
            with self.subTest(scenario=scenario):
                flow, kernel = self.fixture(None if scenario == 'other_media' else scenario, saved=True, verifier=True, account=account)
                if scenario == 'other_media': flow.video = self.other   # The drafts thumbnail shows other media.
                result = flow.run()
                self.assertEqual('review_required', result['state']); self.assertFalse(result['savedDraftVerified'])
                self.assertEqual(1, kernel.saves); self.assertEqual('confirmed', result['cleanup']); self.assertIn(reason, result['error'])

    def test_a_slow_recognition_is_reconfirmed_by_a_newer_matching_frame(self):
        flow, kernel = self.fixture('slow_recognition', 'yt_picker'); result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error')); self.assertEqual(1, kernel.saves)
        confirmed = [c for c in result['decisionConfirmations'] if c['state'] == 'confirmed']
        self.assertEqual(1, len(confirmed))
        refused = [c for c in result['commands'] if c['state'] == 'not_sent']
        self.assertTrue(refused and all(c['refusal'].startswith(('FrameNotRecent', 'DecisionExpired')) for c in refused))
        bound = [c for c in result['commands'] if c.get('confirmation')]
        self.assertEqual(['select-package-video-position'], [c['purpose'] for c in bound])
        self.assertTrue(all(c['state'] == 'answered' and c['decisionChecks'][-1]['confirmationAgeMs'] <= 1500 for c in bound))
        self.assertTrue(all((flow.folder / c['frame']).is_file() for c in result['decisionConfirmations']))
        self.assertEqual([], kernel.unexpected)

    def test_a_paste_callout_that_aged_out_is_reconfirmed_before_pasting(self):
        flow, kernel = self.fixture('slow_recognition', 'yt_paste_menu'); result = flow.run()
        self.assertEqual('created_unverified', result['state'], result.get('error')); self.assertEqual(1, kernel.saves)
        bound = [c for c in result['commands'] if c.get('confirmation')]
        self.assertEqual(['paste-exact-caption-position'], [c['purpose'] for c in bound])
        self.assertEqual([], kernel.unexpected)

    def test_a_screen_that_changed_after_recognition_is_never_tapped(self):
        flow, kernel = self.fixture('changed_after_recognition', 'yt_picker'); result = flow.run()
        self.assertEqual('review_required', result['state']); self.assertEqual(0, kernel.saves)
        self.assertIn('No newer frame matched', result['error']); self.assertEqual('confirmed', result['cleanup'])
        self.assertTrue(all(c['state'] == 'rejected' for c in result['decisionConfirmations']))
        self.assertFalse(any(c[0] == '/mouse/click' and c[1] == {'x': 141, 'y': 320, 'button': 1} for c in kernel.calls if isinstance(c, tuple)))
        self.assertEqual([], kernel.unexpected)

    def test_committing_purposes_name_real_creation_actions(self):
        flow, kernel = self.fixture(); flow.run()
        labels = {a['label'] for a in flow.record['actions']}
        self.assertTrue(set(COMMITTING) <= labels, set(COMMITTING) - labels)


if __name__ == '__main__':
    unittest.main()
