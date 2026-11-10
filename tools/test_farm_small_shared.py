"""The 4.7-inch branches in the shared layout and start-screen modules (B5, iPhone 6s, 4-5 Nov 2026).
Frames are synthesized (letterbox bands only); OCR rows are transcribed positions, no captures or names."""
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from farm_carousel_inspection import InspectionStopped  # noqa: E402
import farm_creation_layout as layout  # noqa: E402
import farm_small_layout as small  # noqa: E402
from farm_start_screen import StartScreen  # noqa: E402
from test_farm_small_layout import (CONTROL_CENTER, PAGE_ONE, PAGE_TWO, PAGE_TWO_BANDS, SPOTLIGHT_NOTICE,  # noqa: E402
                                    line, text)


def frame(small_phone=True, tag=0):
    a = np.zeros((1080, 500, 3), dtype=np.uint8)
    if small_phone: a[95:986] = 120 + tag
    else: a[:] = 120 + tag
    out = io.BytesIO(); Image.fromarray(a).save(out, 'BMP'); return out.getvalue()


SMALL, XR = frame(), frame(False)
PAGE2_FRAME = frame(tag=2)


def bands(raw, band, scale=3):
    return PAGE_TWO_BANDS.get(band[1], []) if raw == PAGE2_FRAME else []


class ScreenSizeTests(unittest.TestCase):
    def test_letterbox_tells_a_small_phone(self):
        self.assertTrue(small.small_screen(SMALL)); self.assertTrue(layout.small_screen(SMALL))
        self.assertFalse(small.small_screen(XR)); self.assertFalse(layout.small_screen(None))
        self.assertFalse(small.small_screen(frame(tag=-120)))   # an all-black frame is not a small phone's screen
        self.assertFalse(small.small_screen(b'not an image'))


@mock.patch('farm_reel_layout.band_words', bands)
class SharedLayoutBranchTests(unittest.TestCase):
    def test_home_on_a_small_phone(self):
        self.assertTrue(layout.home(PAGE_ONE, SMALL))
        self.assertTrue(layout.home(PAGE_TWO, PAGE2_FRAME))
        with self.assertRaises(InspectionStopped): layout.home(CONTROL_CENTER, SMALL)
        with self.assertRaises(InspectionStopped): layout.home(PAGE_ONE, XR)   # the XR rules still apply to XR frames

    def test_no_search_pill_on_a_small_phone(self):
        with self.assertRaises(InspectionStopped): layout.home_search(SMALL, PAGE_ONE)

    def test_app_target_uses_the_small_icon_grid(self):
        self.assertEqual(layout.app_target(PAGE_TWO, 'TikTok', PAGE2_FRAME), (192, 175))
        self.assertEqual(layout.app_target(PAGE_TWO, 'X', PAGE2_FRAME), (308, 175))
        with self.assertRaises(InspectionStopped): layout.app_target(PAGE_ONE, 'TikTok', SMALL)

    def test_empty_spotlight(self):
        ready = text(line('Q Search', 21, 139, 101, 23), line('Cancel', 420, 142, 68, 18))
        self.assertTrue(layout.empty_search(ready, SMALL))
        typed = text(line('Q TikTok', 21, 139, 101, 23), line('Cancel', 420, 142, 68, 18))
        for other in (typed, SPOTLIGHT_NOTICE, PAGE_ONE):
            with self.subTest(other=other['lines'][0]['text']), self.assertRaises(InspectionStopped):
                layout.empty_search(other, SMALL)


class FakeStart:
    """StartScreen's input and frame methods replaced: each fresh() returns the next scripted screen."""
    def __init__(self, screens):
        self.screens, self.sent = list(screens), []

    def build(self):
        s = StartScreen.__new__(StartScreen)
        s.pause = lambda seconds: None
        s.command = lambda fun, purpose, **data: self.sent.append((fun, purpose))
        s.tap = lambda raw, text, point, role, purpose, only=None: self.sent.append(('tap', purpose, point))
        def fresh(role):
            raw, txt = self.screens.pop(0)
            return raw, txt, 0, 0
        s.fresh = fresh
        return s


@mock.patch('farm_reel_layout.band_words', bands)
class SmallStartScreenTests(unittest.TestCase):
    def test_page_one_swipes_then_taps_the_icon_and_never_sends_home(self):
        fake = FakeStart([(SMALL, PAGE_ONE), (PAGE2_FRAME, PAGE_TWO), (SMALL, text(line('Log in to TikTok', 46, 210)))])
        fake.build().open_from_home('TikTok')
        funs = [s[0] for s in fake.sent]
        self.assertNotIn('/key/sendkey', funs)
        self.assertEqual(funs, ['/mouse/reset', '/mouse/swipe', 'tap'])
        self.assertEqual(fake.sent[-1], ('tap', 'open-tiktok', (192, 175)))

    def test_control_center_is_never_sent_home(self):
        fake = FakeStart([(SMALL, CONTROL_CENTER)])
        with self.assertRaises(InspectionStopped): fake.build().open_from_home('X')
        self.assertEqual(fake.sent, [])

    def test_inside_an_app_home_then_the_page_two_icon(self):
        app = text(line('Welcome to YouTube', 107, 335, 285, 24))
        fake = FakeStart([(SMALL, app), (PAGE2_FRAME, PAGE_TWO), (SMALL, app)])
        fake.build().open_from_home('YouTube')
        self.assertEqual([s[0] for s in fake.sent], ['/key/sendkey', 'tap'])

    def test_home_opening_control_center_stops(self):
        app = text(line('Welcome to YouTube', 107, 335, 285, 24))
        fake = FakeStart([(SMALL, app), (SMALL, CONTROL_CENTER)])
        with self.assertRaises(InspectionStopped): fake.build().open_from_home('YouTube')
        self.assertEqual([s[0] for s in fake.sent], ['/key/sendkey'])

    def test_spotlight_notice_stops_before_typing(self):
        no_icon = text(*[l for l in PAGE_TWO['lines'] if l['text'] != 'Instagram'])   # icon label unread
        fake = FakeStart([(PAGE2_FRAME, no_icon), (SMALL, SPOTLIGHT_NOTICE)])
        unread = {y: [w for w in words if w[0] != 'Instagram'] for y, words in PAGE_TWO_BANDS.items()}
        with mock.patch('farm_reel_layout.band_words', lambda raw, band, scale=3: unread.get(band[1], []) if raw == PAGE2_FRAME else []):
            with self.assertRaises(InspectionStopped) as stop: fake.build().open_from_home('Instagram')
        self.assertIn('first-use', str(stop.exception))
        self.assertEqual([s[0] for s in fake.sent], ['/mouse/reset', '/mouse/swipe'])

    def test_xr_control_center_rule_still_holds(self):
        s = StartScreen.__new__(StartScreen)
        c24c = text(line('Focus', 60, 520, 56), line('100%', 420, 30, 40))
        self.assertTrue(s.control_center(c24c)); self.assertTrue(s.control_center(CONTROL_CENTER))
        self.assertFalse(s.control_center(PAGE_ONE))


if __name__ == '__main__':
    unittest.main()


CAPTURES = Path(__file__).resolve().parents[1] / 'output' / 'small-phone'


@unittest.skipUnless((CAPTURES / 'survey-1' / '03-page2.bmp').exists(), 'B5 captures sit untracked in the Small phone lane folder')
class SavedCaptureTests(unittest.TestCase):
    """B5's own frames and OCR (4 Nov), never committed: the shared branches on real 4.7-inch frames."""
    def load(self, name):
        import json
        return (CAPTURES / f'{name}.bmp').read_bytes(), json.loads((CAPTURES / f'{name}.json').read_text(encoding='utf-8'))

    def test_real_frames(self):
        for name, page in (('survey-1/02-look', 1), ('survey-1/03-page2', 2), ('survey-1/08-tt-home', 2), ('recover-1/01-look', 1)):
            raw, txt = self.load(name)
            with self.subTest(name=name):
                self.assertTrue(layout.small_screen(raw)); self.assertTrue(layout.home(txt, raw))
                self.assertEqual(small.home_page(txt, raw), page)
        raw, txt = self.load('survey-1/08-tt-home')
        self.assertEqual({a: layout.app_target(txt, a, raw) for a in ('Instagram', 'TikTok', 'X', 'YouTube')},
                         {'Instagram': (76, 175), 'TikTok': (192, 175), 'X': (308, 175), 'YouTube': (424, 175)})
        s = StartScreen.__new__(StartScreen)
        for name in ('start-3/02-home', 'survey-1/04-ig-open', 'survey-1/12-yt-open', 'cal-1/02-spotlight'):
            raw, txt = self.load(name)
            with self.subTest(name=name):
                self.assertTrue(layout.small_screen(raw))
                with self.assertRaises(InspectionStopped): layout.home(txt, raw)
        self.assertTrue(s.control_center(self.load('start-3/02-home')[1]))
        self.assertEqual(small.spotlight(self.load('cal-1/02-spotlight')[1])['state'], 'first_use_notice')
