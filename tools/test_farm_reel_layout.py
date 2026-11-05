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
import farm_paths  # noqa: E402  (the archive beside the main folder, also from a lane worktree)
OCR17 = farm_paths.ARCHIVE/'20261019-farm-reel-offline/ocr-20261017'
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

    def test_link_menu_rows_are_fixed_but_its_column_may_shift(self):
        # C24C on 20 Oct: the 17 Oct rows, about 85 px further right, with two more items.
        rows = [('Open', 139, 773), ('Open in New Tab', 139, 826), ('> Open in Tab Group', 119, 879),
                ('Download Linked File', 140, 932), ('Add to Reading List', 139, 985), ('Copy Link', 139, 1038),
                ('Hide preview', 372, 100)]
        self.assertEqual((227, 941), reel.link_menu(ocr(*rows))['target'])
        misaligned = [('Download Linked File', 170, 932) if r[0] == 'Download Linked File' else r for r in rows]
        with self.assertRaises(InspectionStopped): reel.link_menu(ocr(*misaligned))
        with self.assertRaises(InspectionStopped): reel.link_menu(ocr(*(r for r in rows if r[0] != 'Hide preview')))
        with self.assertRaises(InspectionStopped): reel.link_menu(ocr(*(r for r in rows if r[0] != 'Download Linked File')))
        far = [(t, x+120, y) if t != 'Hide preview' else (t, x, y) for t, x, y in rows]
        with self.assertRaises(InspectionStopped): reel.link_menu(ocr(*far))

    def test_downloads_icon_is_accepted_filled_or_outlined_only(self):
        # 17 Oct: filled icon; 20 Oct: outlined after the download. Both templates sit in the same box.
        import base64, json
        from PIL import Image as PImage
        rows = json.loads(Path(reel.__file__).with_name('farm_reel_controls.json').read_text(encoding='utf-8'))
        for name in ('safari_download', 'safari_download_outline'):
            with self.subTest(name=name):
                image = PImage.new('RGB', (500, 1080), 'white')
                image.paste(PImage.open(io.BytesIO(base64.b64decode(rows[name]['png']))).convert('RGB'), tuple(rows[name]['box'][:2]))
                self.assertEqual((91, 955), reel.download_badge(png(image))['target'])
        with self.assertRaises(InspectionStopped): reel.download_badge(png(PImage.new('RGB', (500, 1080), 'white')))

    def test_page_menu_tolerates_only_the_known_promo(self):
        base = [('Downloads', 51, 920)]
        self.assertEqual((92, 929), reel.page_menu(ocr(*base, ('Not Now', 109, 759), ('Turn On', 321, 759)))['target'])
        with self.assertRaises(InspectionStopped): reel.page_menu(ocr(*base, ('Allow', 120, 600), ("Don't Allow", 260, 600)))


class TypedAddressTests(unittest.TestCase):
    """The address field before Enter (4 Nov, slot 18: Enter once loaded an unknown address)."""
    URL = 'http://192.168.4.26:9917/t/UUi-uxM76j8_6mfMfHGXwfCw/'

    @staticmethod
    def field(shown, y=945):
        return {'width': 500, 'height': 1080, 'lines': [
            {'text': 'Recently Closed Tabs', 'words': [{'text': 'Recently', 'x': 26, 'y': 510, 'width': 90, 'height': 22}]},
            {'text': shown, 'words': [{'text': shown, 'x': 34, 'y': y, 'width': 340, 'height': 20}]}]}

    def test_the_end_of_this_address_passes(self):
        self.assertTrue(reel.typed_transfer_address(self.field('68.4.26:9917/t/UUi-uxM76j8_6mfMfHGXwfCw/'), self.URL)['addressTyped'])
        # OCR confusions in small type: I/l/1, 0/O.
        self.assertTrue(reel.typed_transfer_address(self.field('68.4.26:99l7/t/UUl-uxM76j8_6mfMfHGXwfCw'), self.URL)['addressTyped'])

    def test_previous_or_damaged_addresses_stop_before_enter(self):
        for shown in ('192.168.4.26:9917/t/H8iV9agHEpUc1',           # The previous transfer (4 Nov frame).
                      '192.168.4.26:9917j8_6mfMfHGXwfCw/',          # A chunk dropped.
                      'fMfHGXwfCw/'):                                # Too little to tell.
            with self.subTest(shown), self.assertRaises(InspectionStopped):
                reel.typed_transfer_address(self.field(shown), self.URL)
        with self.assertRaises(InspectionStopped): reel.typed_transfer_address(self.field('x' * 30, y=500), self.URL)


class DetailsRowsTests(unittest.TestCase):
    """Reel details rows: audio below location (22 Oct), or the 'Add link' row that pushed audio
    under the button bar (4 Nov, slot 18). Word boxes as Windows OCR reported them on those frames."""
    @staticmethod
    def text(*words):
        return {'width': 500, 'height': 1080, 'lines': [{'text': w, 'words': [{'text': w, 'x': x, 'y': y, 'width': 60, 'height': 20}]}
                                                        for w, x, y in words]}

    def test_old_layout_audio_below_location(self):
        self.assertEqual('audio', reel.details_rows(self.text(('location', 100, 807), ('original', 345, 865))))

    def test_new_layout_link_row_stands_in_for_hidden_audio(self):
        self.assertEqual('link', reel.details_rows(self.text(('location', 100, 805), ('link', 105, 860), ('meta', 140, 886))))

    def test_missing_or_misplaced_rows_stop(self):
        for words in ([('location', 100, 805)], [('original', 345, 865)], [('location', 100, 805), ('link', 105, 900)],
                      [('location', 100, 805), ('link', 105, 815)]):
            with self.subTest(words), self.assertRaises(InspectionStopped): reel.details_rows(self.text(*words))


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


import farm_paths as _paths  # noqa: E402
import farm_reel_layout as _rl  # noqa: E402

_A12 = _paths.ARCHIVE/'20261105-fleet-a12'


@unittest.skipUnless((_A12/'reel-create.png').exists(), 'A12 frames of 5 Nov are not available in this checkout.')
class A12CreateSheetTests(unittest.TestCase):
    """A12's Create sheet (5 Nov): no Instants row, every row 53 px apart from 'Create' at y 569."""
    def setUp(self):
        self.frame = (_A12/'reel-create.png').read_bytes()
        self.text = json.loads((_A12/'reel-create.json').read_text(encoding='utf-8'))

    def without(self, label):
        return dict(self.text, lines=[l for l in self.text['lines'] if ' '.join(l['text'].casefold().split()) != label])

    def test_the_reel_row_read_by_ocr_is_the_target(self):
        found = _rl.reel_create(self.frame, self.text)
        self.assertEqual(('ocr_rows_sheet_and_reel_icon', (88, 628)), (found['method'], found['target']))

    def test_every_row_and_the_header_are_required(self):
        for label in ('create',) + _rl.CREATE_ROWS:
            with self.subTest(label):
                self.assertIsNone(_rl.create_rows(self.frame, self.without(label)))
                with self.assertRaises(InspectionStopped): _rl.reel_create(self.frame, self.without(label))

    def test_an_extra_row_breaks_the_even_spacing(self):
        moved = json.loads(json.dumps(self.text))
        for line in moved['lines']:
            if ' '.join(line['text'].casefold().split()) in ('highlights', 'live', 'fundraiser'):
                for w in line['words']: w['y'] += 53   # An Instants row between Story and Highlights, as on A18.
        self.assertIsNone(_rl.create_rows(self.frame, moved))

    def test_the_icon_must_sit_beside_the_reel_row(self):
        moved = json.loads(json.dumps(self.text))
        for line in moved['lines']:
            if ' '.join(line['text'].casefold().split()) == 'reel':
                for w in line['words']: w['y'] += 10
        with self.assertRaises(InspectionStopped): _rl.reel_create(self.frame, moved)
