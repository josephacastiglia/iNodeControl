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

    def test_a_cut_first_glyph_and_a_slash_read_as_l_pass(self):
        # A19, 5 Nov: the field scrolled, its first visible '9' cut by the edge (read '3'), the final '/' read 'l'.
        url = 'http://192.168.4.26:9797/t/zp2d8nq76ydz6ss7h8wpn3qf/'
        self.assertTrue(reel.typed_transfer_address(self.field('3797/t/zp2d8nq76ydz6ss7h8wpn3qfl'), url)['addressTyped'])
        # The glyphs beside the caret may be misread ('qbyw/' read 'qbyv•d', A19, 5 Nov).
        self.assertTrue(reel.typed_transfer_address(self.field('9797/t/nmpskdu286qcj2pgvrskqbyv•d'),
                                                    'http://192.168.4.26:9797/t/nmpskdu286qcj2pgvrskqbyw/')['addressTyped'])
        for shown in ('3797/t/zp2d8nq76ydz6ss7x8wpn3qfl',      # A different character inside the path is still refused.
                      '3797/t/zp2d8nq76ydz6ssh8wpn3qfl',       # A dropped character too.
                      'zz7/t/zp2d8nq76ydz6ss7h8wpn3qfl'):      # Only one cut glyph is forgiven.
            with self.subTest(shown), self.assertRaises(InspectionStopped):
                reel.typed_transfer_address(self.field(shown), url)
        with self.assertRaises(InspectionStopped): reel.typed_transfer_address(self.field('wpn3qfl' * 3), url)   # Too little.

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

    def test_first_draft_missed_by_full_frame_ocr_is_read_in_its_band(self):
        # A18, 5 Nov 16:54: full-frame OCR read nothing of the white pill over a dark tray; the band read it.
        from unittest.mock import patch
        f, t = self.load('163-instagram-save-reel-draft')
        missed = dict(t, lines=[l for l in t['lines'] if not {'first', 'draft'} & {w['text'].casefold() for w in l.get('words', [])}])
        with patch.object(reel, 'band_words', return_value=[('First', 300, 980, 340, 1000), ('draft', 345, 980, 385, 1000)]):
            self.assertEqual([0, 1], reel.reel_selected(f, missed, self.ref, (0, 1))['cell'])
        with patch.object(reel, 'band_words', return_value=[('Next', 300, 980, 340, 1000)]):
            with self.assertRaisesRegex(InspectionStopped, 'First draft'): reel.reel_selected(f, missed, self.ref, (0, 1))


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
import farm_tiktok_layout as _tt  # noqa: E402


@unittest.skipUnless((_A12/'reel-selected-no-first-draft.png').exists(), 'A12 frames of 5 Nov are not available in this checkout.')
class A12SelectedTests(unittest.TestCase):
    """A12's selected picker (5 Nov): no First draft button; Next on the right, white on blue."""
    def setUp(self):
        self.frame = (_A12/'reel-selected-no-first-draft.png').read_bytes()
        self.text = json.loads((_A12/'reel-selected-no-first-draft.json').read_text(encoding='utf-8'))
        self.reference = _tt.TikTokReference((_A12/'reel-selected-package.mp4').read_bytes())

    def test_next_alone_is_enough_here(self):
        self.assertEqual((444, 993), _rl.reel_selected(self.frame, self.text, self.reference, (0, 1))['target'])

    def test_another_cell_is_not_selected(self):
        with self.assertRaises(InspectionStopped): _rl.reel_selected(self.frame, self.text, self.reference, (0, 2))

    def test_another_word_where_first_draft_sits_stops(self):
        from unittest import mock
        with mock.patch.object(_rl, 'band_words', side_effect=[[('Other', 300, 985, 340, 1000)], [('Next', 418, 988, 450, 1000)]]):
            with self.assertRaises(InspectionStopped): _rl.reel_selected(self.frame, self.text, self.reference, (0, 1))

    def test_next_elsewhere_stops(self):
        from unittest import mock
        with mock.patch.object(_rl, 'band_words', side_effect=[[], [('Next', 100, 988, 140, 1000)]]):
            with self.assertRaises(InspectionStopped): _rl.reel_selected(self.frame, self.text, self.reference, (0, 1))


@unittest.skipUnless((_A12/'reel-editor-icons.png').exists(), 'A12 frames of 5 Nov are not available in this checkout.')
class A12EditorTests(unittest.TestCase):
    """A12's editor (5 Nov): an unlabelled row of icon tiles under the video."""
    def setUp(self):
        self.frame = (_A12/'reel-editor-icons.png').read_bytes()
        self.text = json.loads((_A12/'reel-editor-icons.json').read_text(encoding='utf-8'))
        self.reference = _tt.TikTokReference((_A12/'reel-editor-package.mp4').read_bytes())

    def test_the_icon_row_is_the_editor(self):
        self.assertEqual((444, 993), _rl.reel_editor(self.frame, self.text, self.reference)['target'])

    def test_without_the_icon_row_it_is_not(self):
        from PIL import Image
        image = Image.open(io.BytesIO(self.frame)).convert('RGB'); image.paste((255, 255, 255), (0, 885, 500, 945))
        out = io.BytesIO(); image.save(out, 'PNG')
        with self.assertRaisesRegex(InspectionStopped, 'toolbar'): _rl.reel_editor(out.getvalue(), self.text, self.reference)

    def test_edit_video_is_still_required(self):
        text = dict(self.text, lines=[l for l in self.text['lines'] if l['text'] != 'Edit video'])
        with self.assertRaises(InspectionStopped): _rl.reel_editor(self.frame, text, self.reference)


@unittest.skipUnless((_A12/'reel-details-link-chip.png').exists(), 'A12 frames of 5 Nov are not available in this checkout.')
class A12DetailsTests(unittest.TestCase):
    def test_the_caption_sheet_chips_move_only_with_link_a_reel(self):
        from unittest import mock
        def row(label, x): return dict(text=label, words=[dict(text=w, x=x + 12 * i, y=250, width=10 * len(w), height=18) for i, w in enumerate(label.split())])
        title = dict(text='Caption', words=[dict(text='Caption', x=215, y=72, width=70, height=20)])
        moved = dict(width=500, height=1080, lines=[title, row('Hashtags', 60), row('Link a reel', 200), row('Poll', 347), row('Prompt', 430)])
        plain = dict(width=500, height=1080, lines=[title, row('Hashtags', 60), row('Poll', 347), row('Prompt', 430)])
        with mock.patch.object(_rl, 'control'), mock.patch.object(_rl, 'present', return_value=True):
            self.assertTrue(_rl.reel_caption(None, moved, blank=True)['blank'])
            with self.assertRaises(InspectionStopped): _rl.reel_caption(None, plain, blank=True)

    """A12's details (6 Nov frame): Hashtags, Link a reel, Poll, Prompt across the chip row."""
    def setUp(self):
        self.frame = (_A12/'reel-details-link-chip.png').read_bytes()
        self.text = json.loads((_A12/'reel-details-link-chip.json').read_text(encoding='utf-8'))
        self.reference = _tt.TikTokReference((_A12/'reel-details-package.mp4').read_bytes())

    def test_the_moved_chips_are_the_blank_details(self):
        self.assertIn('captionTarget', _rl.reel_details(self.frame, self.text, self.reference))

    def test_without_link_a_reel_the_moved_chips_do_not_count(self):
        text = dict(self.text, lines=[l for l in self.text['lines'] if l['text'] != 'Link a reel'])
        with self.assertRaisesRegex(InspectionStopped, 'poll'): _rl.reel_details(self.frame, text, self.reference)

    def test_every_chip_is_still_needed(self):
        for label in ('Poll', 'Q Prompt'):
            text = dict(self.text, lines=[l for l in self.text['lines'] if l['text'] != label])
            with self.subTest(label), self.assertRaises(InspectionStopped): _rl.reel_details(self.frame, text, self.reference)


@unittest.skipUnless((_A12/'downloads-clipped-newest.png').exists(), 'A12 frames of 5 Nov are not available in this checkout.')
class A12DownloadsTests(unittest.TestCase):
    """A12's Downloads list (6 Nov frame): full-frame OCR reads only 'mouse' on the newest row."""
    def setUp(self):
        self.frame = (_A12/'downloads-clipped-newest.png').read_bytes()
        self.text = json.loads((_A12/'downloads-clipped-newest.json').read_text(encoding='utf-8'))

    def test_the_newest_row_read_alone_is_the_package(self):
        found = _rl.downloads_list(self.text, 'imouse-reel-yfwmrx', 31000, self.frame)
        self.assertEqual('31 KB', found['size'])
        self.assertLess(abs(found['target'][1] - 595), 25)

    def test_a_name_the_newest_row_does_not_read_stops(self):
        with self.assertRaises(InspectionStopped): _rl.downloads_list(self.text, 'imouse-reel-zzqqkk', 31000, self.frame)

    def test_without_the_frame_it_still_stops(self):
        with self.assertRaises(InspectionStopped): _rl.downloads_list(self.text, 'imouse-reel-yfwmrx', 31000)


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


_A19 = _paths.ARCHIVE/'20261105-fleet-a19'


@unittest.skipUnless((_A19/'share-sheet.png').exists(), 'A19 frames of 5 Nov are not available in this checkout.')
class A19ShareSheetTests(unittest.TestCase):
    """A19's share sheet (5 Nov): Copy, Save Video, then Save to Files before Add Tags."""
    def setUp(self):
        self.frame = (_A19/'share-sheet.png').read_bytes()
        self.text = json.loads((_A19/'share-sheet.json').read_text(encoding='utf-8'))
        self.name = (_A19/'share-name.txt').read_text(encoding='utf-8')

    def without(self, *labels):
        return dict(self.text, lines=[l for l in self.text['lines'] if l['text'].strip() not in labels])

    def test_save_video_is_the_target(self):
        found = _rl.share_sheet(self.text, self.name, self.frame)
        self.assertLess(abs(found['target'][1] - 877), 8)

    def test_a_third_row_is_still_required(self):
        with self.assertRaises(InspectionStopped): _rl.share_rows(self.without('Save to Files', 'Add Tags'), 30)
        self.assertEqual({'Copy', 'Save Video', 'Add Tags'}, set(_rl.share_rows(self.without('Save to Files'), 30)))


@unittest.skipUnless((_A19/'reel-create.png').exists(), 'A19 frames of 5 Nov are not available in this checkout.')
class A19CreateSheetTests(unittest.TestCase):
    """A19's Create sheet (5 Nov): no Live row; 'Create' at y 622, rows 53 px apart."""
    def setUp(self):
        self.frame = (_A19/'reel-create.png').read_bytes()
        self.text = json.loads((_A19/'reel-create.json').read_text(encoding='utf-8'))

    def test_the_reel_row_read_by_ocr_is_the_target(self):
        found = _rl.reel_create(self.frame, self.text)
        self.assertEqual('ocr_rows_sheet_and_reel_icon', found['method'])
        self.assertLess(abs(found['target'][1] - 681), 5)

    def test_only_live_may_be_absent(self):
        for label in ('create', 'reel', 'edits', 'post', 'story', 'highlights', 'fundraiser'):
            with self.subTest(label):
                text = dict(self.text, lines=[l for l in self.text['lines'] if ' '.join(l['text'].casefold().split()) != label])
                self.assertIsNone(_rl.create_rows(self.frame, text))


@unittest.skipUnless((_A19/'reel-editor.png').exists(), 'A19 frames of 5 Nov are not available in this checkout.')
class A19EditorTests(unittest.TestCase):
    """A19's editor (5 Nov): seven tools under the video, a Suggested audio pill and a swipe hint over it."""
    @classmethod
    def setUpClass(cls):
        cls.ref = _rl.VideoReference((_A19/'reel-package.mp4').read_bytes())

    def setUp(self):
        self.frame = (_A19/'reel-editor.png').read_bytes()
        self.text = json.loads((_A19/'reel-editor.json').read_text(encoding='utf-8'))

    def test_the_seven_tool_editor_shows_the_package_video(self):
        found = _rl.reel_editor(self.frame, self.text, self.ref)
        self.assertEqual((444, 993), found['target'])
        self.assertTrue(found['media']['matched'])

    def test_edit_video_is_still_required(self):
        text = dict(self.text, lines=[l for l in self.text['lines'] if l['text'] != 'Edit video'])
        with self.assertRaises(InspectionStopped): _rl.reel_editor(self.frame, text, self.ref)

    def test_too_few_tools_stop(self):
        from unittest.mock import patch
        with patch.object(_rl, 'toolbar_words', return_value=[('text', 33, 57), ('audio', 168, 202)]):
            with self.assertRaisesRegex(InspectionStopped, 'toolbar'): _rl.reel_editor(self.frame, self.text, self.ref)


@unittest.skipUnless((_A19/'reel-saved-picker.png').exists(), 'A19 frames of 5 Nov are not available in this checkout.')
class A19SavedPickerTests(unittest.TestCase):
    """A19's picker after Save draft (5 Nov): the toolbar row reads Edits, Drafts, Templates."""
    def setUp(self):
        self.frame = (_A19/'reel-saved-picker.png').read_bytes()
        self.text = json.loads((_A19/'reel-saved-picker.json').read_text(encoding='utf-8'))

    def test_the_drafts_chip_is_found(self):
        found = _rl.reel_saved_picker(self.frame, self.text)
        self.assertLess(abs(found['chipTarget'][0] - 170), 30)

    def test_the_wider_boxes_need_edits_on_that_row(self):
        text = json.loads(json.dumps(self.text))
        for line in text['lines']:
            line['words'] = [w for w in line.get('words', []) if w['text'].casefold() != 'edits']
        with self.assertRaises(InspectionStopped): _rl.reel_saved_picker(self.frame, text)
