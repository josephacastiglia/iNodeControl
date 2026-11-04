"""X recognizers: synthetic boundary cases always run; retained C24C frames when present.

No phone, socket or desktop access. Retained frames/OCR are private local
artifacts (17 Oct supervised X routes). The signed-in handle is read at run
time and never written into this file.
"""
import json
from pathlib import Path
import tempfile
import unittest

import farm_reel_test_media as media
import farm_tiktok_layout as tt
import farm_x_layout as xl
from farm_carousel_inspection import InspectionStopped

ROOT = Path(__file__).resolve().parents[1]
R17 = ROOT/'analysis/farm-platform-drafts-20261017'
import farm_paths  # noqa: E402  (the archive beside the main folder, also from a lane worktree)
OCR = farm_paths.ARCHIVE/'20261019-farm-x-offline/ocr-20261017'
PRIVATE = (R17/'normalized-test.mp4').exists() and OCR.exists()
CAPTION = 'IMOUSE-VlDEO-DRAFT-TEST-20261017'   # The retained frames' exact OCR form.


class SyntheticXLayoutTests(unittest.TestCase):
    def test_text_rules_never_truncate_wrap_or_repair(self):
        self.assertTrue(xl.caption_supported('Fresh x acceptance'))
        for caption in ('', 'x'*33, 'two\nlines', ' lead', 'trail ', 'two  spaces', 'café'):
            self.assertFalse(xl.caption_supported(caption), repr(caption))

    def test_save_sheet_needs_save_above_discard(self):
        def ocr(*rows): return dict(width=500, height=1080, lines=[dict(text=t, words=[dict(text=t, x=x, y=y, width=len(t)*9, height=16)])
                                                                    for t, x, y in rows])
        rows = [('Save to drafts', 181, 464), ('Discard', 213, 531), ('Keep editing', 189, 599)]
        self.assertEqual((244, 472), xl.x_save_sheet(ocr(*rows))['target'])
        for missing in range(2):
            with self.assertRaises(InspectionStopped): xl.x_save_sheet(ocr(*(r for i, r in enumerate(rows) if i != missing)))
        # Slot 17's X shows only Save to drafts and Discard since 4 Nov; Keep editing, when shown, stays below Discard.
        self.assertEqual('two_rows', xl.x_save_sheet(ocr(('Save to drafts', 181, 498), ('Discard', 213, 565)))['layout'])
        with self.assertRaises(InspectionStopped): xl.x_save_sheet(ocr(('Save to drafts', 181, 464), ('Keep editing', 189, 520), ('Discard', 213, 590)))


@unittest.skipUnless(PRIVATE, 'Retained private C24C X frames/OCR are not available in this checkout.')
class RetainedXLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = tt.TikTokReference((R17/'normalized-test.mp4').read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            cls.alpha = tt.TikTokReference(media.render('alpha', Path(directory)/'a.mp4').read_bytes())

    def load(self, step, which='after'):
        text = json.loads((OCR/f'{step}__{which}.json').read_text(encoding='utf-8')); text.pop('source', None)
        return (R17/step/(which+'.png')).read_bytes(), text

    def test_every_route_screen_is_recognized_with_its_target(self):
        for step in ('30-x-loaded', '122-x-save-video-draft', '129-x-resave-verified-video'):
            f, t = self.load(step); self.assertEqual((454, 935), xl.x_feed(f, t)['composeTarget'])
        f, t = self.load('31-x-account'); menu = xl.x_menu(f, t)
        self.assertRegex(menu['handle'], r'^[A-Za-z0-9_]{1,15}$'); self.assertEqual((447, 83), menu['closeTarget'])
        f, t = self.load('115-x-video-composer'); self.assertEqual((344, 85), xl.x_composer_empty(f, t)['draftsTarget'])
        f, t = self.load('33-x-compose'); self.assertIsNone(xl.x_composer_empty(f, t)['draftsTarget'])
        f, t = self.load('116-x-video-caption'); self.assertEqual((26, 1009), xl.x_composer_text(f, t)['galleryTarget'])
        f, t = self.load('117-x-video-picker')
        with self.assertRaises(xl.Loading): xl.x_picker(f, t, self.ref)
        f, t = self.load('118-x-picker-loaded'); picker = xl.x_picker(f, t, self.ref)
        self.assertEqual(([0, 201, 166, 367], (83, 284)), (picker['tile'], picker['target']))
        self.assertGreaterEqual(picker['nearestOther'] - picker['match']['mean'], xl.UNIQUE_MARGIN)
        f, t = self.load('119-x-select-test-video'); self.assertEqual((456, 103), xl.x_picker_selected(f, t, self.ref, picker['tile'])['target'])
        f, t = self.load('120-x-attach-video'); self.assertTrue(xl.x_composer_media(f, t, self.ref)['media']['matched'])
        for step in ('121-x-video-save-dialog', '128-x-close-verified-video'):
            f, t = self.load(step); self.assertEqual((250, 472), xl.x_save_sheet(t)['target'])
        f, t = self.load('124-x-video-drafts-list'); drafts = xl.x_drafts(f, t, self.ref, CAPTION)
        self.assertEqual(((182, 225), 2), (drafts['target'], drafts['rows']))
        f, t = self.load('125-x-video-draft-reopen'); self.assertTrue(xl.x_composer_media(f, t, self.ref, reopened=True)['blank'])
        f, t = self.load('127-x-reopened-video-play'); self.assertFalse(xl.x_composer_media(f, t, self.ref, reopened=True)['blank'])

    def test_negative_controls_on_real_renderings(self):
        cases = [
            ('119-x-select-test-video', lambda f, t: xl.x_picker(f, t, self.ref)),                       # already selected
            ('118-x-picker-loaded', lambda f, t: xl.x_picker_selected(f, t, self.ref, [0, 201, 166, 367])),   # nothing selected
            ('119-x-select-test-video', lambda f, t: xl.x_picker_selected(f, t, self.ref, [167, 201, 333, 367])),  # another tile
            ('116-x-video-caption', lambda f, t: xl.x_composer_empty(f, t)),
            ('120-x-attach-video', lambda f, t: xl.x_composer_text(f, t)),                               # media already attached
            ('125-x-video-draft-reopen', lambda f, t: xl.x_composer_media(f, t, self.ref)),               # blank is reopened-only
            ('124-x-video-drafts-list', lambda f, t: xl.x_drafts(f, t, self.ref, 'IMOUSE-DRAFT-TEST-20261017')),   # no video thumbnail
            ('124-x-video-drafts-list', lambda f, t: xl.x_drafts(f, t, self.ref, 'Another text')),
            ('30-x-loaded', lambda f, t: xl.x_menu(f, t)),
            ('31-x-account', lambda f, t: xl.x_feed(f, t)),
        ]
        for step, check in cases:
            with self.subTest(step=step):
                frame, text = self.load(step)
                with self.assertRaises(InspectionStopped): check(frame, text)

    def test_new_test_media_never_matches_the_old_renderings(self):
        for step, call in [('118-x-picker-loaded', lambda f, t, r: xl.x_picker(f, t, r)),
                           ('120-x-attach-video', lambda f, t, r: xl.x_composer_media(f, t, r)),
                           ('124-x-video-drafts-list', lambda f, t, r: xl.x_drafts(f, t, r, CAPTION)),
                           ('127-x-reopened-video-play', lambda f, t, r: xl.x_composer_media(f, t, r, reopened=True))]:
            with self.subTest(step=step):
                frame, text = self.load(step)
                call(frame, text, self.ref)
                with self.assertRaises(InspectionStopped): call(frame, text, self.alpha)


if __name__ == '__main__':
    unittest.main()
