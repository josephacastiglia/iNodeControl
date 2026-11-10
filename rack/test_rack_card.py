"""Offline tests for the Screen Mirroring card helpers in card_survey.py and auto_connect.py: where a
receiver's row is on a surveyed card, and the Home-twice routine. No kernel, phone or socket.

  python -m unittest test_rack_card    (from this folder)
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auto_connect as ac  # noqa: E402
import card_survey as cs  # noqa: E402

NAMES = ['iMouse2-2', 'iMouse2-5', 'iMouse2-B19', 'iMouse2-B20']


def survey(*rows, **extra):
    """A survey whose name rows sit 69 px apart from y 483, as card_survey.py records them."""
    lines = [dict(text=text, cy=483 + 69 * i) for i, text in enumerate(rows)] + [dict(text='Stop Mirroring', cy=729)]
    return dict(advertised=sorted(NAMES), lines=lines, **extra)


class SurveyedPointTests(unittest.TestCase):
    def test_the_row_is_the_line_that_reads_as_the_receiver(self):
        card = survey('iMouse2-2', 'iMouse2-5', 'iMouse2-B19')
        self.assertEqual(ac.surveyed_point('iMouse2-5', NAMES, card), (250, 552))
        self.assertEqual(ac.surveyed_point('iMouse2-B19', NAMES, survey('iMouse2-2', 'iMouse2-5', 'IMouse2-8l9')), (250, 621))   # OCR's B/8, l/1

    def test_a_name_ocr_cut_short_is_the_one_unread_row_in_natural_order(self):
        card = survey('iMouse2-2', 'iMouse2-', 'iMouse2-B19')
        self.assertEqual(ac.surveyed_point('iMouse2-5', NAMES, card), (250, 552))
        with self.assertRaises(SystemExit): ac.surveyed_point('iMouse2-B20', NAMES, card)   # sorts below the last read row
        with self.assertRaises(SystemExit): ac.surveyed_point('iMouse2-5', NAMES, survey('iMouse2-', 'iMouse2-', 'iMouse2-B19'))

    def test_refuses_a_changed_list_an_absent_row_or_a_scrolled_survey(self):
        card = survey('iMouse2-2', 'iMouse2-5', 'iMouse2-B19')
        with self.assertRaises(SystemExit): ac.surveyed_point('iMouse2-5', NAMES + ['Bedroom TV'], card)
        with self.assertRaises(SystemExit): ac.surveyed_point('iMouse2-B20', NAMES, card)
        for old in ('scroll', 'nudge'):   # Records from before 9 Nov could be read on a scrolled card.
            with self.assertRaises(SystemExit): ac.surveyed_point('iMouse2-5', NAMES, survey('iMouse2-2', 'iMouse2-5', 'iMouse2-B19', **{old: True}))


class CardHelperTests(unittest.TestCase):
    def test_to_send_maps_a_small_phone_frame_point_onto_the_placeholder_calibration(self):
        self.assertEqual(cs.to_send((250, 500)), (250, 500))
        self.assertEqual(cs.to_send((0, 95), cs.SMALL), (14, 14))
        self.assertEqual(cs.to_send(cs.SMALL_TILE, cs.SMALL), (190, 442))

    def test_home_twice_sends_two_homes_each_followed_by_the_pause(self):
        events = []
        with mock.patch.object(cs.time, 'sleep', lambda s: events.append(('sleep', s))):
            cs.home_twice(lambda fun, purpose, **data: events.append((fun, purpose, data)), 'first', 'second', pause=1.8)
        self.assertEqual(events, [('/key/sendkey', 'first', dict(fn_key='Home')), ('sleep', 1.8),
                                  ('/key/sendkey', 'second', dict(fn_key='Home')), ('sleep', 1.8)])

    def test_control_center_needs_its_focus_tile_and_a_status_row(self):
        def line(text, y): return dict(text=text, words=[dict(y=y)])
        self.assertTrue(cs.control_center(dict(lines=[line('Focus', 520), line('82%', 60)])))
        self.assertTrue(cs.control_center(dict(lines=[line('Focus', 520), line('SOS only', 60)])))
        self.assertFalse(cs.control_center(dict(lines=[line('Focus', 520)])))
        self.assertFalse(cs.control_center(dict(lines=[line('Focus', 900), line('82%', 60)])))


if __name__ == '__main__':
    unittest.main()
