"""Reel recognizers: synthetic boundary cases always run; retained C24C frames when present.

No phone, socket or desktop access. Retained frames/OCR are private local
artifacts (17 Oct supervised Reel route); they check known layouts only.
"""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

import farm_reel_layout as reel
import farm_reel_test_media as media
from farm_carousel_inspection import InspectionStopped

ROOT = Path(__file__).resolve().parents[1]
R17 = ROOT/'analysis/farm-platform-drafts-20261017'
OCR17 = ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-reel-offline/ocr-20261017'
PRIVATE = (R17/'normalized-test.mp4').exists() and OCR17.exists()


def words(text, x, y, height=18, width=None):
    out, cursor = [], x
    for part in text.split(' '):
        w = max(8, len(part)*(width or 9)); out.append(dict(text=part, x=cursor, y=y, width=w, height=height)); cursor += w+6
    return dict(text=text, words=out)


def ocr(*rows): return dict(width=500, height=1080, lines=[words(*row) for row in rows])


def png(image):
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


class SyntheticReelLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.alpha = reel.VideoReference(media.render('alpha', Path(cls.temp.name)/'a.mp4').read_bytes())
        cls.bravo = reel.VideoReference(media.render('bravo', Path(cls.temp.name)/'b.mp4').read_bytes())

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def screen(self, index=0, token='alpha', box=(0, 56, 500, 945), background='white'):
        image = Image.new('RGB', (500, 1080), background)
        l, t, r, b = box
        image.paste(media.frame(token, index, 60).resize((r-l, b-t)), (l, t))
        return png(image)

    def test_caption_rules_never_truncate_or_repair(self):
        self.assertTrue(reel.caption_supported('Fresh reel acceptance'))
        for caption in ('', 'x'*41, 'two\nlines', ' lead', 'trail ', 'two  spaces', 'café', 'tab\there'):
            self.assertFalse(reel.caption_supported(caption), repr(caption))
        self.assertEqual('0:04', reel.duration_label(4.0)); self.assertEqual('1:05', reel.duration_label(65.2))
        self.assertEqual('79 KB', reel.size_label(78953)); self.assertEqual('1.2 MB', reel.size_label(1_234_567))

    def test_video_match_accepts_the_package_and_refuses_other_media(self):
        frame = self.screen(30)
        self.assertTrue(reel.video_match(frame, (0, 56, 500, 945), self.alpha)['matched'])
        self.assertFalse(reel.video_match(frame, (0, 56, 500, 945), self.bravo)['matched'])
        flat = png(Image.new('RGB', (500, 1080), 'white'))
        self.assertEqual('insufficient_detail', reel.video_match(flat, (0, 56, 500, 945), self.alpha)['status'])
        self.assertFalse(reel.video_match(flat, (0, 56, 500, 945), self.alpha)['matched'])

    def test_playing_frames_resolve_to_different_sample_indices(self):
        first = reel.video_match(self.screen(3), (0, 56, 500, 945), self.alpha)
        later = reel.video_match(self.screen(45), (0, 56, 500, 945), self.alpha)
        self.assertTrue(first['matched'] and later['matched']); self.assertLess(first['index'], later['index'])

    def test_settling_protects_controls_but_lets_video_play(self):
        compare = reel.reel_compare('reel_editor')
        self.assertEqual('ready', compare(self.screen(3), {}, self.screen(40), {})['state'])
        moved = Image.open(io.BytesIO(self.screen(3))); moved.paste((0, 0, 0), (100, 960, 300, 1000))
        self.assertEqual('wait', compare(self.screen(3), {}, png(moved), {})['state'])
        self.assertEqual('wait', reel.reel_compare('reel_picker')(self.screen(3), {}, self.screen(40), {})['state'])

    def test_paste_menu_must_be_unique_and_adjacent(self):
        good = ocr(('Paste', 40, 96), ('AutoFill', 110, 96))
        self.assertEqual((62, 105), reel.reel_paste_menu(None, good)['target'])
        for text in (ocr(('Paste', 40, 96)), ocr(('Paste', 40, 96), ('AutoFill', 110, 96), ('Paste', 40, 200)),
                     ocr(('Paste', 40, 400), ('AutoFill', 110, 400)), ocr(('AutoFill', 40, 96), ('Paste', 130, 96))):
            with self.assertRaises(InspectionStopped): reel.reel_paste_menu(None, text)

    def test_downloads_list_needs_the_unique_complete_package_file(self):
        name = 'imouse-reel-acdefh'
        header = [('Done', 27, 523), ('Downloads', 199, 522), ('Clear', 428, 522)]
        good = ocr(*header, (name, 94, 586), ('79 KB', 93, 612))
        self.assertEqual((175, 595), reel.downloads_list(good, name, 78953)['target'])
        for text in (ocr(*header, (name, 94, 586), ('31 KB of 79 KB', 93, 612)),
                     ocr(*header, (name, 94, 586), ('79 KB', 93, 612), (name, 94, 650), ('79 KB', 93, 676)),
                     ocr(*header, ('imouse-draft', 94, 586), ('79 KB', 93, 612))):
            with self.assertRaises(InspectionStopped): reel.downloads_list(text, name, 78953)

    def test_share_sheet_targets_save_video_only_for_this_file(self):
        name = 'imouse-reel-acdefh'
        rows = [(name, 69, 521), ('Copy', 50, 765), ('Save Video', 50, 837), ('Add Tags', 50, 899), ('Save to Files', 50, 959),
                ('Add to Shared Album', 50, 1020)]
        self.assertEqual((94, 846), reel.share_sheet(ocr(*rows), name)['target'])
        with self.assertRaises(InspectionStopped): reel.share_sheet(ocr(*rows[1:]), name)
        with self.assertRaises(InspectionStopped): reel.share_sheet(ocr(*[r for r in rows if r[0] != 'Save Video']), name)

    def test_transfer_page_order_and_copy_confirmation(self):
        name = 'imouse-reel-acdefh'
        rows = [('Reel draft', 30, 120), ('File ' + name, 30, 190), ('Download video', 170, 262), ('Copy caption', 180, 400)]
        page = reel.reel_transfer_page(ocr(*rows), name)
        self.assertTrue(page['downloadTarget'][1] < page['copyTarget'][1])
        with self.assertRaises(InspectionStopped): reel.reel_transfer_page(ocr(*rows[:1], *rows[2:]), name)
        swapped = [rows[0], rows[1], ('Download video', 170, 500), ('Copy caption', 180, 400)]
        with self.assertRaises(InspectionStopped): reel.reel_transfer_page(ocr(*swapped), name)
        with self.assertRaises(InspectionStopped): reel.caption_copied(ocr(*rows))
        self.assertTrue(reel.caption_copied(ocr(*rows, ('Caption copied. Verify the pasted text in Instagram.', 30, 450)))['copied'])
        # On C24C (20 Oct) the sentence wrapped: the exact text may span rows, never be repaired.
        wrapped = (('Caption copied. Verify the pasted text in', 26, 508), ('Instagram.', 27, 536))
        self.assertTrue(reel.caption_copied(ocr(*rows, *wrapped))['copied'])
        with self.assertRaises(InspectionStopped): reel.caption_copied(ocr(*rows, wrapped[0]))
        with self.assertRaises(InspectionStopped): reel.caption_copied(ocr(*rows, wrapped[0], ('Instagram', 27, 536)))

    def test_page_menu_tolerates_only_the_known_promo(self):
        base = [('Downloads', 51, 920)]
        self.assertEqual((92, 929), reel.page_menu(ocr(*base, ('Not Now', 109, 759), ('Turn On', 321, 759)))['target'])
        with self.assertRaises(InspectionStopped): reel.page_menu(ocr(*base, ('Allow', 120, 600), ("Don't Allow", 260, 600)))


@unittest.skipUnless(PRIVATE, 'Retained private C24C Reel frames/OCR are not available in this checkout.')
class RetainedReelLayoutTests(unittest.TestCase):
    CAPTION = 'IMOUSE-VlDEO-DRAFT-TEST-20261017'   # Exact OCR form in the retained frames.

    @classmethod
    def setUpClass(cls):
        cls.ref = reel.VideoReference((R17/'normalized-test.mp4').read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            cls.alpha = reel.VideoReference(media.render('alpha', Path(directory)/'a.mp4').read_bytes())

    def load(self, step, which='after', download=None):
        frame = (R17/step/(which+'.png')).read_bytes()
        text = json.loads((OCR17/f'{step}__{which}.json').read_text(encoding='utf-8')); text.pop('source', None)
        return frame, text

    def test_every_route_screen_is_recognized_with_its_target(self):
        f, t = self.load('155-instagram-create-menu'); self.assertEqual((105, 576), reel.reel_create(f, t)['target'])
        f, t = self.load('156-instagram-reel-picker'); picker = reel.reel_picker(f, t, self.ref)
        self.assertEqual(([0, 1], (311, 280)), (picker['cell'], picker['target']))
        self.assertGreaterEqual(picker['nearestOther'] - picker['match']['mean'], reel.UNIQUE_MARGIN)
        f, t = self.load('158-instagram-reel-edit'); self.assertTrue(reel.reel_editor(f, t, self.ref)['media']['matched'])
        f, t = self.load('159-instagram-reel-details'); self.assertFalse(reel.reel_details(f, t, self.ref)['captionExact'])
        f, t = self.load('160-instagram-reel-caption-focus'); reel.reel_caption(f, t, blank=True)
        f, t = self.load('161-instagram-reel-caption'); reel.reel_caption(f, t, blank=False)
        f, t = self.load('162-instagram-reel-caption-ok'); self.assertTrue(reel.reel_details(f, t, self.ref, self.CAPTION)['captionExact'])
        f, t = self.load('163-instagram-save-reel-draft'); self.assertEqual(1, reel.reel_saved_picker(f, t)['draftsCount'])
        reel.reel_selected(f, t, self.ref, (0, 1))
        f, t = self.load('164-instagram-reel-drafts-library'); self.assertEqual((66, 169), reel.reels_drafts(f, t, self.ref)['target'])
        f, t = self.load('165-instagram-reel-reopen'); reel.reel_details(f, t, self.ref, self.CAPTION, reopened=True)
        f, t = self.load('166-instagram-reel-playback'); self.assertTrue(reel.reel_preview(f, t, self.ref, 'xs.halle.xo', self.CAPTION)['accountVerified'])
        f, t = self.load('77-download-test-video', 'before'); self.assertEqual((161, 940), reel.link_menu(t)['target'])
        f, t = self.load('78-downloads-menu', 'before'); reel.download_badge(f)
        f, t = self.load('79-downloads-list', 'before'); reel.page_menu(t)
        f, t = self.load('80-downloaded-video-preview', 'before'); reel.downloads_list(t, 'imouse-draft', 78953)
        f, t = self.load('81-file-preview-controls', 'before'); self.assertFalse(reel.quicklook(f, t, 'imouse-draft', self.ref)['controls'])
        f, t = self.load('89-video-test-home', 'before'); self.assertTrue(reel.quicklook(f, t, 'imouse-draft', self.ref)['controls'])
        self.assertTrue(reel.leftover_preview(f, t)['leftoverPreview'])
        f, t = self.load('87-save-options-settled'); self.assertEqual((100, 846), reel.share_sheet(t, 'imouse-draft')['target'])

    def test_negative_controls_on_real_renderings(self):
        cases = [
            ('157-instagram-select-test-mp4', 'after', lambda f, t: reel.reel_selected(f, t, self.ref, (0, 1))),   # mid-animation badge
            ('163-instagram-save-reel-draft', 'after', lambda f, t: reel.reel_picker(f, t, self.ref)),             # settled selection
            ('162-instagram-reel-caption-ok', 'after', lambda f, t: reel.reel_details(f, t, self.ref, 'IMOUSE-VIDEO-DRAFT-TEST-20261017')),
            ('159-instagram-reel-details', 'after', lambda f, t: reel.reel_details(f, t, self.ref, reopened=True)),
            ('165-instagram-reel-reopen', 'after', lambda f, t: reel.reel_details(f, t, self.ref, self.CAPTION)),  # header differs
            ('166-instagram-reel-playback', 'after', lambda f, t: reel.reel_preview(f, t, self.ref, 'another.account', self.CAPTION)),
            ('80-downloaded-video-preview', 'before', lambda f, t: reel.downloads_list(t, 'imouse-reel-acdefh', 78953)),
            ('154-instagram-account-confirm', 'after', lambda f, t: reel.reel_create(f, t)),
        ]
        for step, which, check in cases:
            with self.subTest(step=step):
                frame, text = self.load(step, which)
                with self.assertRaises(InspectionStopped): check(frame, text)

    def test_new_test_media_never_matches_the_old_renderings(self):
        for step, which, call in [
                ('156-instagram-reel-picker', 'after', lambda f, t, r: reel.reel_picker(f, t, r)),
                ('158-instagram-reel-edit', 'after', lambda f, t, r: reel.reel_editor(f, t, r)),
                ('159-instagram-reel-details', 'after', lambda f, t, r: reel.reel_details(f, t, r)),
                ('164-instagram-reel-drafts-library', 'after', lambda f, t, r: reel.reels_drafts(f, t, r)),
                ('166-instagram-reel-playback', 'after', lambda f, t, r: reel.reel_preview(f, t, r, 'xs.halle.xo', self.CAPTION)),
                ('89-video-test-home', 'before', lambda f, t, r: reel.quicklook(f, t, 'imouse-draft', r))]:
            with self.subTest(step=step):
                frame, text = self.load(step, which)
                call(frame, text, self.ref)
                with self.assertRaises(InspectionStopped): call(frame, text, self.alpha)


if __name__ == '__main__':
    unittest.main()
