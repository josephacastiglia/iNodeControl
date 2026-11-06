"""TikTok recognizers: synthetic boundary cases always run; retained C24C frames when present.

No phone, socket or desktop access. Retained frames/OCR are private local
artifacts (17 Oct supervised TikTok video route); they check known layouts only.
"""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

import farm_tiktok_layout as tt
import farm_reel_test_media as media
from farm_carousel_inspection import InspectionStopped

ROOT = Path(__file__).resolve().parents[1]
R17 = ROOT/'analysis/farm-platform-drafts-20261017'
import farm_paths  # noqa: E402  (the archive beside the main folder, also from a lane worktree)
OCR = farm_paths.ARCHIVE/'20261019-farm-tiktok-offline/ocr-20261017'
PRIVATE = (R17/'normalized-test.mp4').exists() and OCR.exists()
CAPTION = 'IMOUSE-VIDEO-DRAFT-TEST-20261017'   # The 17 Oct description, which TikTok wrapped onto two lines.


def words(text, x, y, height=18, width=None):
    out, cursor = [], x
    for part in text.split(' '):
        w = max(8, len(part)*(width or 9)); out.append(dict(text=part, x=cursor, y=y, width=w, height=height)); cursor += w+6
    return dict(text=text, words=out)


def ocr(*rows): return dict(width=500, height=1080, lines=[words(*row) for row in rows])


def png(image):
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


class SyntheticTikTokLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.alpha = tt.TikTokReference(media.render('alpha', Path(cls.temp.name)/'a.mp4').read_bytes())
        cls.bravo = tt.TikTokReference(media.render('bravo', Path(cls.temp.name)/'b.mp4').read_bytes())

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_description_rules_never_truncate_wrap_or_repair(self):
        self.assertTrue(tt.caption_supported('Fresh tiktok acceptance'))
        for caption in ('', 'x'*25, 'two\nlines', ' lead', 'trail ', 'two  spaces', 'café', CAPTION):
            self.assertFalse(tt.caption_supported(caption), repr(caption))
        self.assertEqual('00:04', tt.clock_label(4.0)); self.assertEqual('01:05', tt.clock_label(65.2))

    def test_each_crop_model_matches_its_own_video_only(self):
        for model, box in (('fill', (0, 71, 500, 960)), ('square', (100, 300, 266, 466)), ('portrait', (0, 238, 163, 453)),
                           ('card', (345, 122, 475, 313))):
            with self.subTest(model=model):
                image = Image.new('RGB', (500, 1080), 'white')
                l, t, r, b = box
                full = media.frame('alpha', 30, 60).resize((360, 640))
                height = tt.MODELS[model][0]; top = (640-height)//2
                image.paste(full.crop((0, top, 360, top+height)).resize((r-l, b-t)), (l, t))
                frame = png(image)
                self.assertTrue(tt.media_match(frame, box, self.alpha, model)['matched'])
                self.assertFalse(tt.media_match(frame, box, self.bravo, model)['matched'])
        flat = png(Image.new('RGB', (500, 1080), 'white'))
        self.assertEqual('insufficient_detail', tt.media_match(flat, (0, 71, 500, 960), self.alpha, 'fill')['status'])

    def test_caret_detection_needs_a_thin_vertical_accent_run(self):
        image = Image.new('RGB', (500, 1080), 'white')
        self.assertFalse(tt.caret_visible(np.asarray(image)))
        ImageDraw.Draw(image).rectangle((152, 149, 152, 171), fill=(246, 90, 130))
        self.assertTrue(tt.caret_visible(np.asarray(image)))
        dot = Image.new('RGB', (500, 1080), 'white'); ImageDraw.Draw(dot).rectangle((152, 149, 156, 153), fill=(246, 90, 130))
        self.assertFalse(tt.caret_visible(np.asarray(dot)))

    def test_transfer_page_order_and_copy_confirmation(self):
        name = 'imouse-tt-acdefh'
        rows = [('TikTok draft', 30, 120), ('File ' + name, 30, 190), ('Download video', 170, 262), ('Copy caption', 180, 400)]
        page = tt.transfer_page(ocr(*rows), name)
        self.assertTrue(page['downloadTarget'][1] < page['copyTarget'][1])
        with self.assertRaises(InspectionStopped): tt.transfer_page(ocr(('Reel draft', 30, 120), *rows[1:]), name)
        with self.assertRaises(InspectionStopped): tt.transfer_page(ocr(*rows[:1], *rows[2:]), name)
        with self.assertRaises(InspectionStopped): tt.caption_copied(ocr(*rows))
        with self.assertRaises(InspectionStopped):
            tt.caption_copied(ocr(*rows, ('Caption copied. Verify the pasted text in Instagram.', 30, 450)))
        self.assertTrue(tt.caption_copied(ocr(*rows, ('Caption copied. Verify the pasted text in TikTok.', 30, 450)))['copied'])
        # On C24C (20 Oct) the sentence wrapped: the exact text may span rows, never be repaired.
        wrapped = (('Caption copied. Verify the pasted text in', 26, 508), ('TikTok.', 27, 536))
        self.assertTrue(tt.caption_copied(ocr(*rows, *wrapped))['copied'])
        self.assertTrue(tt.caption_copied(ocr(*rows, wrapped[0], ('X.', 27, 536)), app='X')['copied'])
        with self.assertRaises(InspectionStopped): tt.caption_copied(ocr(*rows, wrapped[0], ('Instagram.', 27, 536)))
        with self.assertRaises(InspectionStopped): tt.caption_copied(ocr(*rows, wrapped[0]))

    def test_feed_ignores_content_but_not_dialogs(self):
        nav = [('Home', 35, 1021, 18, 8), ('Friends', 130, 1021, 18, 6), ('Inbox', 334, 1021, 18, 7), ('Profile', 425, 1021, 18, 7),
               ('Following', 174, 77)]
        self.assertFalse(tt.tiktok_feed(None, ocr(*nav, ('Not now', 30, 900)))['toastSeen'])
        self.assertTrue(tt.tiktok_feed(None, ocr(*nav, ('Draft saved', 205, 147)))['toastSeen'])
        with self.assertRaises(InspectionStopped): tt.tiktok_feed(None, ocr(*nav, ('Allow', 120, 600), ("Don't Allow", 260, 600)))
        with self.assertRaises(InspectionStopped): tt.tiktok_feed(None, ocr(*nav[1:]))


@unittest.skipUnless(PRIVATE, 'Retained private C24C TikTok frames/OCR are not available in this checkout.')
class RetainedTikTokLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = tt.TikTokReference((R17/'normalized-test.mp4').read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            cls.alpha = tt.TikTokReference(media.render('alpha', Path(directory)/'a.mp4').read_bytes())

    def load(self, step, which='after'):
        frame = (R17/step/(which+'.png')).read_bytes()
        text = json.loads((OCR/f'{step}__{which}.json').read_text(encoding='utf-8')); text.pop('source', None)
        return frame, text

    def test_every_route_screen_is_recognized_with_its_target(self):
        f, t = self.load('95-tiktok-loaded'); self.assertEqual((450, 1005), tt.tiktok_feed(f, t)['profileTarget'])
        f, t = self.load('106-tiktok-save-video-draft'); self.assertTrue(tt.tiktok_feed(f, t)['toastSeen'])
        f, t = self.load('107-tiktok-video-profile'); profile = tt.tiktok_profile(f, t, 'xs.halle.xo')
        self.assertEqual((2, (79, 478), (250, 1009)), (profile['draftsCount'], profile['draftsTarget'], profile['createTarget']))
        for step, which in (('96-tiktok-create-video', 'after'), ('100-tiktok-settled-gallery-click', 'before')):
            f, t = self.load(step, which); self.assertEqual((40, 1000), tt.tiktok_camera(f, t)['galleryTarget'])
        f, t = self.load('100-tiktok-settled-gallery-click'); picker = tt.tiktok_picker(f, t, self.ref)
        self.assertEqual(([334, 804, 500, 967], (478, 825), '00:03'), (picker['tile'], picker['target'], picker['durationRead']))
        self.assertGreaterEqual(picker['nearestOther'] - picker['match']['mean'], tt.UNIQUE_MARGIN)
        f, t = self.load('101-tiktok-select-test-video'); selected = tt.tiktok_selected(f, t, self.ref)
        self.assertEqual(([334, 657, 500, 820], (367, 1006)), (selected['tile'], selected['target']))
        for step, sound in (('102-tiktok-video-editor', 'loading'), ('109-tiktok-video-reopen', 'attached'),
                            ('110-tiktok-remove-suggested-sound', 'none')):
            f, t = self.load(step); editor = tt.tiktok_editor(f, t, self.ref)
            self.assertEqual(sound, editor['sound'], step); self.assertTrue(editor['media']['matched'])
        f, t = self.load('103-tiktok-video-details'); self.assertFalse(tt.tiktok_details(f, t, self.ref)['captionExact'])
        f, t = self.load('104-tiktok-video-caption-focus'); self.assertEqual((80, 140), tt.tiktok_details(f, t, self.ref)['pressTarget'])
        f, t = self.load('108-tiktok-video-library'); drafts = tt.tiktok_drafts(f, t, self.ref)
        self.assertEqual((2, 'Whispers', (81, 345)), (drafts['count'], drafts['tile']['soundLabel'], drafts['target']))
        f, t = self.load('112-tiktok-resave-silent-video'); drafts = tt.tiktok_drafts(f, t, self.ref)
        self.assertEqual((2, None, True), (drafts['count'], drafts['tile']['soundLabel'], drafts['toastSeen']))
        # The photo route landed on the profile after Drafts, with the same toast.
        f, t = self.load('22-tiktok-save-draft'); landed = tt.tiktok_profile(f, t, 'xs.halle.xo')
        self.assertEqual((1, True), (landed['draftsCount'], landed['toastSeen']))
        with self.assertRaises(InspectionStopped): tt.tiktok_feed(f, t)
        f, t = self.load('107-tiktok-video-profile'); self.assertFalse(tt.tiktok_profile(f, t, 'xs.halle.xo')['toastSeen'])

    def test_the_real_tiktok_callout_without_paste_is_refused(self):
        # 17 Oct photo route: a long press on the description showed only AutoFill
        # (nothing to paste then). Paste must be read uniquely beside AutoFill.
        f, t = self.load('20-tiktok-paste-menu')
        self.assertTrue(any(w['text'] == 'AutoFill' for line in t['lines'] for w in line['words']))
        with self.assertRaises(InspectionStopped): tt.tiktok_paste_menu(f, t)

    def test_description_checks_on_real_renderings(self):
        f, t = self.load('105-tiktok-video-caption')            # Caret drawn after the text.
        with self.assertRaises(tt.CaretVisible): tt.tiktok_details(f, t, self.ref, CAPTION)
        f, t = self.load('106-tiktok-save-video-draft', 'before')  # Caret off, but the description wrapped.
        self.assertEqual(['IMOUSE-VIDEO-DRAFT-', 'TEST-20261017'], tt.rows_between(t, 120, 330, 15, 340))
        with self.assertRaises(InspectionStopped): tt.tiktok_details(f, t, self.ref, CAPTION)
        f, t = self.load('111-tiktok-video-caption-verify')
        with self.assertRaises(InspectionStopped): tt.tiktok_details(f, t, self.ref, CAPTION, reopened=True)
        # Same frame, OCR of a one-line description: reopened header required, new-draft header refused.
        one = copy.deepcopy(t)
        one['lines'] = [r for r in one['lines'] if not r['text'].startswith(('IMOUSE', 'TEST'))] + [words('Fresh tiktok acceptance', 27, 132)]
        self.assertTrue(tt.tiktok_details(f, one, self.ref, 'Fresh tiktok acceptance', reopened=True)['captionExact'])
        with self.assertRaises(InspectionStopped): tt.tiktok_details(f, one, self.ref, 'Fresh tiktok acceptance')

    def test_negative_controls_on_real_renderings(self):
        cases = [
            ('101-tiktok-select-test-video', 'after', lambda f, t: tt.tiktok_picker(f, t, self.ref)),       # a selection exists
            ('100-tiktok-settled-gallery-click', 'after', lambda f, t: tt.tiktok_selected(f, t, self.ref)),  # nothing selected
            ('103-tiktok-video-details', 'after', lambda f, t: tt.tiktok_editor(f, t, self.ref)),
            ('102-tiktok-video-editor', 'after', lambda f, t: tt.tiktok_details(f, t, self.ref)),
            ('103-tiktok-video-details', 'after', lambda f, t: tt.tiktok_details(f, t, self.ref, reopened=True)),
            ('107-tiktok-video-profile', 'after', lambda f, t: tt.tiktok_profile(f, t, 'another.account')),
            ('106-tiktok-save-video-draft', 'after', lambda f, t: tt.tiktok_profile(f, t, 'xs.halle.xo')),
            ('107-tiktok-video-profile', 'after', lambda f, t: tt.tiktok_feed(f, t)),
            ('95-tiktok-loaded', 'after', lambda f, t: tt.tiktok_camera(f, t)),
            ('108-tiktok-video-library', 'after', lambda f, t: tt.tiktok_picker(f, t, self.ref)),
        ]
        for step, which, check in cases:
            with self.subTest(step=step):
                frame, text = self.load(step, which)
                with self.assertRaises(InspectionStopped): check(frame, text)

    def test_new_test_media_never_matches_the_old_renderings(self):
        for step, call in [
                ('100-tiktok-settled-gallery-click', lambda f, t, r: tt.tiktok_picker(f, t, r)),
                ('101-tiktok-select-test-video', lambda f, t, r: tt.tiktok_selected(f, t, r)),
                ('110-tiktok-remove-suggested-sound', lambda f, t, r: tt.tiktok_editor(f, t, r)),
                ('103-tiktok-video-details', lambda f, t, r: tt.tiktok_details(f, t, r)),
                ('112-tiktok-resave-silent-video', lambda f, t, r: tt.tiktok_drafts(f, t, r))]:
            with self.subTest(step=step):
                frame, text = self.load(step)
                call(frame, text, self.ref)
                with self.assertRaises(InspectionStopped): call(frame, text, self.alpha)


class CoveredFeedHeaderTests(unittest.TestCase):
    """A20 after a cold start (4 Nov): a video's caption box covered the whole feed header."""
    def frame(self, nav=(0, 0, 0), tile=True):
        image = Image.new('RGB', (500, 1080), (90, 70, 60)); draw = ImageDraw.Draw(image)
        draw.rectangle((0, 985, 499, 1079), fill=nav)
        if tile:
            draw.rectangle((222, 994, 278, 1024), fill=(255, 255, 255))
            draw.rectangle((222, 994, 228, 1024), fill=(40, 230, 235)); draw.rectangle((272, 994, 278, 1024), fill=(250, 40, 100))
            draw.rectangle((246, 1000, 254, 1018), fill=(0, 0, 0))
        out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()

    def text(self):
        rows = [('Home', 34, 1021, 40), ('Friends', 130, 1021, 50), ('Inbox', 334, 1021, 40), ('Profile', 431, 1020, 45),
                ('Do Not Post From The', 34, 41, 420)]
        return dict(width=500, height=1080, lines=[dict(text=t, words=[dict(text=t, x=x, y=y, width=w, height=16)]) for t, x, y, w in rows])

    def test_the_create_button_on_the_dark_nav_marks_the_feed(self):
        from unittest import mock
        with mock.patch.object(tt, 'band_words', return_value=[]):
            self.assertEqual((450, 1005), tt.tiktok_feed(self.frame(), self.text())['profileTarget'])
            for frame in (self.frame(tile=False), self.frame(nav=(250, 250, 250))):
                with self.assertRaises(InspectionStopped): tt.tiktok_feed(frame, self.text())
            missing = self.text(); missing['lines'] = [l for l in missing['lines'] if l['text'] != 'Inbox']
            with self.assertRaises(InspectionStopped): tt.tiktok_feed(self.frame(), missing)


if __name__ == '__main__':
    unittest.main()


import farm_paths as _paths  # noqa: E402

_A13 = _paths.ARCHIVE/'20261105-fleet-a13'


@unittest.skipUnless((_A13/'tt-feed-split.bmp').exists(), 'A13 frames of 5 Nov are not available in this checkout.')
class A13ShopNavTests(unittest.TestCase):
    """A13's feed: Shop where A20 shows Friends; Inbox read whole or as 'Inb ox'."""
    def load(self, name):
        return (_A13/f'{name}.bmp').read_bytes(), json.loads((_A13/f'{name}.json').read_text(encoding='utf-8'))

    @staticmethod
    def without(text, *labels):
        out = json.loads(json.dumps(text))
        for line in out['lines']: line['words'] = [w for w in line['words'] if w['text'] not in labels]
        out['lines'] = [l for l in out['lines'] if l['words']]
        return out

    def test_both_reads_of_the_feed(self):
        frame, text = self.load('tt-feed-split')
        self.assertEqual((450, 1005), tt.tiktok_feed(frame, text)['profileTarget'])
        whole = json.loads(json.dumps(text))   # Inbox read as one word (A13's frames that read it so had the dialog up).
        for line in whole['lines']:
            for word in line['words']:
                if word['text'] == 'Inb': word['text'] = 'Inbox'
            line['words'] = [w for w in line['words'] if w['text'] != 'ox']
        self.assertEqual((450, 1005), tt.tiktok_feed(frame, whole)['profileTarget'])

    def test_every_label_of_the_variant_is_needed(self):
        frame, text = self.load('tt-feed-split')
        for labels in (('Home',), ('Shop',), ('Profile',), ('Inb',), ('ox',)):
            with self.subTest(labels), self.assertRaises(InspectionStopped):
                tt.tiktok_feed(frame, self.without(text, *labels))

    def test_a_caption_covering_the_header_needs_the_create_button(self):
        from unittest import mock
        frame, text = self.load('tt-feed-covered')
        self.assertEqual((450, 1005), tt.tiktok_feed(frame, text)['profileTarget'])
        with mock.patch.object(tt, 'feed_create_button', return_value=False), self.assertRaises(InspectionStopped):
            tt.tiktok_feed(frame, text)

    def test_shop_in_the_header_is_not_the_feed_with_shop_in_the_nav(self):
        from unittest import mock
        frame, text = self.load('tt-feed-covered')
        with mock.patch.object(tt, 'feed_create_button', return_value=False),                 mock.patch.object(tt, 'band_words', return_value=[('Shop', 150, 77, 190, 95)]), self.assertRaises(InspectionStopped):
            tt.tiktok_feed(frame, text)

    def test_a_split_inbox_is_not_accepted_with_friends(self):
        # A20's nav with 'Inb ox' stays refused: the split read belongs to the Shop variant only.
        frame, text = self.load('tt-feed-split')
        changed = json.loads(json.dumps(text))
        for line in changed['lines']:
            for word in line['words']:
                if word['text'] == 'Shop': word['text'] = 'Friends'
        with self.assertRaises(InspectionStopped): tt.tiktok_feed(frame, changed)

    def test_shop_only_in_the_nav_slot(self):
        frame, text = self.load('tt-feed-split')
        moved = json.loads(json.dumps(text))
        for line in moved['lines']:
            for word in line['words']:
                if word['text'] == 'Shop': word['y'] = 900
        with self.assertRaises(InspectionStopped): tt.tiktok_feed(frame, moved)

    def test_the_editor_with_the_avatar_joined_to_story(self):
        frame = (_A13/'tt-editor.png').read_bytes()
        text = json.loads((_A13/'tt-editor.json').read_text(encoding='utf-8'))
        reference = tt.TikTokReference((_A13/'tt-package.mp4').read_bytes())
        found = tt.tiktok_editor(frame, text, reference)
        self.assertEqual(('attached', (367, 1006)), (found['sound'], found['nextTarget']))
        self.assertLess(abs(found['removeTarget'][0] - 339), 5)
        for word in ('Story', '24h'):
            with self.subTest(word), self.assertRaises(InspectionStopped):
                tt.tiktok_editor(frame, self.without(text, word), reference)

    def test_tiktoks_contacts_dialog_over_the_variant_still_stops(self):
        frame, text = self.load('tt-feed-contacts')
        self.assertTrue(tt.shop_nav(text))
        with self.assertRaises(InspectionStopped): tt.tiktok_feed(frame, text)


_A14 = _paths.ARCHIVE/'20261105-fleet-a14'


@unittest.skipUnless((_A14/'tt-profile.bmp').exists(), 'A14 frames of 5 Nov are not available in this checkout.')
class A14CentredProfileTests(unittest.TestCase):
    """A14's newer TikTok profile: avatar on top, handle centred at y 267, counters at y 324, a navy + button."""
    def setUp(self):
        self.frame = (_A14/'tt-profile.bmp').read_bytes()
        self.text = json.loads((_A14/'tt-profile.json').read_text(encoding='utf-8'))
        self.account = (_A14/'tt-account.txt').read_text(encoding='utf-8').strip()

    def test_the_centred_profile_is_the_exact_account(self):
        found = tt.tiktok_profile(self.frame, self.text, self.account)
        self.assertEqual((250, 1009), found['createTarget'])
        self.assertIsNone(found['draftsCount'])   # No drafts yet on A14.

    def test_another_account_is_refused(self):
        with self.assertRaises(InspectionStopped): tt.tiktok_profile(self.frame, self.text, 'someone.else')

    def test_the_layouts_are_never_mixed(self):
        # The handle read where A20 shows it, over this frame's centred counters, is not a profile:
        # A20's counter row (and its enlarged reread) is empty here.
        moved = json.loads(json.dumps(self.text))
        for line in moved['lines']:
            if line['text'].startswith('@'):
                for w in line['words']: w['x'], w['y'] = 40, 175
        with self.assertRaises(InspectionStopped): tt.tiktok_profile(self.frame, moved, self.account)

    def test_the_slot20_create_template_does_not_fit_a14(self):
        self.assertFalse(tt.present(self.frame, 'tt_nav_create'))
        self.assertTrue(tt.present(self.frame, 'tt_nav_create_centred'))
