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
from farm_owned_capture import InspectionStopped

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


class MenuWithMoneyRowTests(unittest.TestCase):
    """A17, 4 Nov evening: X added 'Money' and 'History' rows; Communities, Grok and Settings moved 62 px down."""
    def menu(self, *rows):
        lines = [dict(text=t, words=[dict(text=t, x=x0, y=y0, width=x1-x0, height=y1-y0)]) for t, x0, y0, x1, y1 in rows]
        return dict(width=500, height=1080, lines=lines)

    BASE = [('@lane_handle', 40, 160, 160, 180), ('Profile', 98, 271, 175, 292)]
    NEW = [('Money', 98, 402, 176, 425), ('History', 99, 465, 184, 489), ('Communities', 98, 528, 256, 551),
           ('Try Grok Bot', 92, 852, 202, 871), ('Settings and privacy', 92, 908, 271, 928)]

    def test_the_shifted_menu_needs_both_new_rows_in_place(self):
        self.assertEqual('lane_handle', xl.x_menu(b'', self.menu(*self.BASE, *self.NEW))['handle'])
        for missing in ('Money', 'History'):
            with self.subTest(missing=missing), self.assertRaises(InspectionStopped):
                xl.x_menu(b'', self.menu(*self.BASE, *[r for r in self.NEW if r[0] != missing]))
        old = [('Communities', 98, 466, 256, 489), ('Try Grok Bot', 92, 790, 202, 809), ('Settings and privacy', 92, 845, 271, 865)]
        self.assertEqual('lane_handle', xl.x_menu(b'', self.menu(*self.BASE, *old))['handle'])
        with self.assertRaises(InspectionStopped):   # The new rows never excuse the old positions.
            xl.x_menu(b'', self.menu(*self.BASE, *self.NEW[:2], *old))

    def test_a_pointer_clipped_following_tab_is_accepted_only_as_followi(self):
        from unittest import mock
        # A17, 4 Nov: the parked pointer covered 'ng'; OCR read 'Followi' at x 154.
        for word, ok in (('Followi', True), ('Follow', False), ('Followix', False)):
            text = self.menu(('For you', 31, 130, 101, 150), (word, 154, 130, 220, 150))
            with self.subTest(word=word), mock.patch.object(xl, 'blue_fraction', return_value=1.0),                     mock.patch.object(xl, 'pixels', return_value=None):
                if ok: self.assertEqual((454, 935), xl.x_feed(b'', text)['composeTarget'])
                else:
                    with self.assertRaises(InspectionStopped): xl.x_feed(b'', text)
    def test_a_header_with_following_covered_is_marked_by_its_other_tabs(self):
        from unittest import mock
        # A17, 4 Nov prep 11: the pointer covered 'Following' ('FOIA' at 154,115; 'ing Add +' at 212,130).
        cases = ((('FOIA', 154, 115, 200, 135), ('ing Add +', 212, 130, 300, 150), ('Crypto', 361, 130, 420, 150)), True),                 ((('ing Add +', 212, 130, 300, 150),), True), ((('Crypto', 361, 130, 420, 150),), True),                 ((('Crypto', 361, 300, 420, 320),), False), ((('Add +', 268, 400, 320, 420),), False), ((), False)
        for rows, ok in cases:
            text = self.menu(('For you', 31, 130, 101, 150), *rows)
            with self.subTest(rows=rows), mock.patch.object(xl, 'blue_fraction', return_value=1.0),                     mock.patch.object(xl, 'pixels', return_value=None):
                if ok: self.assertEqual((454, 935), xl.x_feed(b'', text)['composeTarget'])
                else:
                    with self.assertRaises(InspectionStopped): xl.x_feed(b'', text)
        with mock.patch.object(xl, 'blue_fraction', return_value=1.0), mock.patch.object(xl, 'pixels', return_value=None),                 self.assertRaises(InspectionStopped):   # 'For you' stays required.
            xl.x_feed(b'', self.menu(('Crypto', 361, 130, 420, 150)))


class PickerBadgeTests(unittest.TestCase):
    def test_only_system_blue_is_a_selection_badge(self):
        # A17, 4 Nov prep 5: a test image's sky-blue corner block read as a selection badge.
        import numpy as np
        tile = (0, 201, 166, 367)
        for colour, badge in (((9, 123, 250), True), ((14, 165, 233), False), ((21, 101, 192), False), ((29, 155, 240), False)):
            image = np.full((1080, 500, 3), 255, np.uint8); image[201:367, 0:166] = colour
            with self.subTest(colour=colour): self.assertEqual(badge, xl._badge(image, tile))


if __name__ == '__main__':
    unittest.main()


import farm_paths as _paths  # noqa: E402
import farm_x_layout as _xl  # noqa: E402

_A14 = _paths.ARCHIVE/'20261105-fleet-a14'


@unittest.skipUnless((_A14/'x-feed.bmp').exists(), 'A14 frames of 5 Nov are not available in this checkout.')
class A14SpreadHeaderTests(unittest.TestCase):
    """A14's timeline header: three evenly spaced tabs, 'For you' at x 74-138 (5 Nov)."""
    def setUp(self):
        self.frame = (_A14/'x-feed.bmp').read_bytes()
        self.text = json.loads((_A14/'x-feed.json').read_text(encoding='utf-8'))

    def edited(self, keep):
        return dict(self.text, lines=[l for l in self.text['lines'] if keep(' '.join(l['text'].casefold().split()))])

    def test_the_spread_header_is_the_timeline(self):
        self.assertEqual(dict(menuTarget=(45, 85), composeTarget=(454, 935)), _xl.x_feed(self.frame, self.text))

    def test_the_whole_set_is_required(self):
        for missing in ('following', 'add +', 'for you'):
            with self.subTest(missing=missing), self.assertRaises(InspectionStopped):
                _xl.x_feed(self.frame, self.edited(lambda t: not t.startswith(missing)))


_A13 = _paths.ARCHIVE/'20261105-fleet-a13'


@unittest.skipUnless((_A13/'x-feed-terms-sheet.bmp').exists(), 'A13 frames of 5 Nov are not available in this checkout.')
class A13SpreadHeaderTests(unittest.TestCase):
    """A13's header read as 'For you v' from x 46 and '• Add +' (5 Nov)."""
    def load(self, name):
        return (_A13/f'{name}.bmp').read_bytes(), json.loads((_A13/f'{name}.json').read_text(encoding='utf-8'))

    def test_the_timeline_is_recognized(self):
        self.assertEqual(dict(menuTarget=(45, 85), composeTarget=(454, 935)), _xl.x_feed(*self.load('x-feed')))

    def test_the_terms_sheet_still_stops_at_the_compose_button(self):
        # The header now fits; X's Terms of Service sheet over the timeline covers compose, so nothing is decided there.
        with self.assertRaisesRegex(InspectionStopped, 'compose button'): _xl.x_feed(*self.load('x-feed-terms-sheet'))
