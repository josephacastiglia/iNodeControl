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


if __name__ == '__main__':
    unittest.main()
