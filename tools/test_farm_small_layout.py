"""4.7-inch layouts. OCR text below is transcribed from B5 frames (4 Nov 2026): positions and labels
only, no captures and no account names."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from farm_owned_capture import InspectionStopped  # noqa: E402
import farm_small_layout as L  # noqa: E402


def line(text, x, y, w=60, h=13):
    return dict(text=text, words=[dict(text=text, x=x, y=y, width=w, height=h)])


def text(*lines):
    return dict(width=500, height=1080, lines=list(lines))


PAGE_ONE = text(line('FaceTime', 40, 225, 72), line('Calendar', 158, 225, 68), line('Camera', 278, 225, 59),
                line('Mail', 409, 225, 30), line('Notes', 54, 343, 43), line('lock', 182, 342, 31),
                line('App Store', 270, 343, 76), line('Maps', 404, 343, 40), line('Health', 52, 460, 48),
                line('Utilities', 163, 460, 57), line('Phone', 284, 460, 47), line('afari', 412, 460, 33),
                line('Messages', 38, 578, 75), line('3', 340, 878, 11, 16))
# Full-frame OCR of page 2 missed TikTok, Threads and Bluesky and cut YouTube to 'Tube'.
PAGE_TWO = text(line('Instagram', 38, 225, 75, 16), line('x', 303, 225, 10, 12), line('Clapper', 278, 342, 60, 16),
                line('Tube', 419, 225, 37, 16), line('Likee', 404, 342, 40), line('3', 340, 878, 11, 16))
PAGE_TWO_BANDS = {215: [('Instagram', 38, 225, 113, 241), ('TikTok', 167, 225, 217, 241), ('x', 303, 225, 313, 237),
                        ('YouTube', 391, 225, 456, 241)],
                  332: [('Threads', 44, 342, 107, 358), ('Bluesky', 162, 342, 222, 358), ('Clapper', 278, 342, 338, 358),
                        ('Likee', 404, 342, 444, 355)]}
SPOTLIGHT_NOTICE = text(line('Q Search', 21, 139, 101, 23), line('Cancel', 420, 142, 68, 18),
                        line('You can search the web, your contacts,', 51, 334, 396, 22),
                        line('suggestions as you type. You can adjust this', 26, 388, 448, 22), line('Continue', 203, 502, 94, 18))
CONTROL_CENTER = text(line('No SIM', 75, 245), line('Not Playing', 302, 345, 120), line('Focus', 131, 671, 56))
INSTAGRAM_OUT = text(line('Username, email or mobile number', 44, 417, 320), line('Password', 44, 513),
                     line('Log in', 223, 598), line('Forgot password?', 168, 665), line('Create new account', 157, 860))
X_OUT = text(line("See what's happening", 43, 512, 397, 36), line('in the world right now.', 44, 561, 399, 36),
             line('Oops, your device appears to be offline. Please check', 43, 932, 382, 15))


def reader_for(bands):
    def reader(frame, band, scale):
        return bands.get(band[1], []) if frame == b'page2' else []
    return reader


class LayoutTests(unittest.TestCase):
    def test_home_pages(self):
        self.assertEqual(L.home_page(PAGE_ONE), 1)
        self.assertEqual(L.home_page(PAGE_TWO, b'page2', reader_for(PAGE_TWO_BANDS)), 2)
        for other in (SPOTLIGHT_NOTICE, CONTROL_CENTER, INSTAGRAM_OUT, X_OUT):
            with self.assertRaises(InspectionStopped): L.home_page(other)

    def test_icons_need_the_enlarged_read_for_missed_labels(self):
        with self.assertRaises(InspectionStopped): L.app_icon(PAGE_TWO, 'TikTok')
        reader = reader_for(PAGE_TWO_BANDS)
        self.assertEqual({a: L.app_icon(PAGE_TWO, a, b'page2', reader) for a in ('Instagram', 'TikTok', 'X', 'YouTube')},
                         {'Instagram': (76, 175), 'TikTok': (192, 175), 'X': (308, 175), 'YouTube': (424, 175)})
        self.assertEqual(L.app_icon(PAGE_ONE, 'Safari'), (424, 410))
        with self.assertRaises(InspectionStopped): L.app_icon(PAGE_ONE, 'Instagram')

    def test_short_fragments_do_not_match(self):
        self.assertFalse(L._label_matches('ube', 'YouTube'))
        self.assertTrue(L._label_matches('tube', 'YouTube'))
        self.assertFalse(L._label_matches('x', 'Mail'))

    def test_spotlight_notice_is_a_stop(self):
        got = L.spotlight(SPOTLIGHT_NOTICE)
        self.assertEqual(got['state'], 'first_use_notice'); self.assertIsNone(got['answer'])
        ready = text(line('Q Search', 21, 139, 101, 23), line('Cancel', 420, 142, 68, 18))
        self.assertEqual(L.spotlight(ready)['state'], 'ready')
        with self.assertRaises(InspectionStopped): L.spotlight(PAGE_ONE)

    def test_control_center(self):
        self.assertTrue(L.control_center(CONTROL_CENTER))
        self.assertFalse(L.control_center(PAGE_ONE))


if __name__ == '__main__':
    unittest.main()
