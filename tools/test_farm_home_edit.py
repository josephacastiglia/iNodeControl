"""Long-press safety on the Home screen (A12 14:29, A13 14:37, 5 Nov): settled clicks and the icon-edit-mode stop."""
import os
from pathlib import Path
import unittest
from unittest import mock

from farm_carousel_inspection import InspectionStopped
from farm_home_edit import edit_mode
import farm_start_screen as start
from farm_start_screen import StartScreen


def line(text, x, y, width=None, height=20):
    words, cursor = [], x
    for part in text.split(' '):
        w = width or max(8, len(part) * 10); words.append(dict(text=part, x=cursor, y=y, width=w, height=height)); cursor += w + 6
    return dict(text=text, words=words)


def ocr(*lines): return dict(width=500, height=1080, lines=list(lines))


HOME = ocr(line('FaceTime', 45, 170), line('Calendar', 160, 170), line('Search', 235, 890), line('Safari', 285, 674))
# As OCR read A13's frame (5 Nov 14:36): Edit and Done where the status bar was; the '-' badges were not read.
EDIT = ocr(line('Edit', 54, 27), line('Done', 408, 28), line('Drive', 59, 170), line('Mint Mobile', 37, 424))
BADGES_ONLY = ocr(line('FaceTime', 45, 170), *[line('-', 30 + 115 * i, 95, 12) for i in range(4)])
DONE_AND_BADGE = ocr(line('Done', 430, 75), line('-', 30, 95, 12), line('Safari', 285, 674))


class RecognizerTests(unittest.TestCase):
    def test_edit_mode_is_recognized(self):
        for text in (EDIT, BADGES_ONLY, DONE_AND_BADGE):
            with self.subTest(text=text['lines'][0]['text']): self.assertTrue(edit_mode(text))

    def test_normal_screens_are_not(self):
        lower_done = ocr(line('Downloads', 185, 520), line('Done', 30, 520), line('Clear', 430, 520))   # Safari's sheet.
        profile = ocr(line('Edit profile', 40, 330), line('Share profile', 260, 330))
        for text in (HOME, lower_done, profile, ocr(), 'placeholder'):
            self.assertIsNone(edit_mode(text))


class StartScreenTests(unittest.TestCase):
    def build(self, screens):
        s = StartScreen.__new__(StartScreen); s.sent = []
        s.pause = lambda seconds: None
        s.command = lambda fun, purpose, **data: s.sent.append((fun, purpose, data.get('x'), data.get('y')))
        s.control_center = lambda text: False
        frames = list(screens)
        s.fresh = lambda role: (b'frame', frames.pop(0), 0, 0)
        return s

    def test_edit_mode_gets_one_home_and_a_stop(self):
        s = self.build([EDIT])
        with self.assertRaises(InspectionStopped) as stop: s.open_from_home('Instagram')
        self.assertIn('icon-edit mode', str(stop.exception))
        self.assertEqual([('/key/sendkey', 'leave-icon-edit-mode', None, None)], s.sent)

    def test_edit_mode_after_home_gets_one_more_home_and_a_stop(self):
        app = ocr(line('Welcome to YouTube', 107, 335))
        s = self.build([app, EDIT])
        with mock.patch('farm_creation_layout.home', side_effect=InspectionStopped('not home')), self.assertRaises(InspectionStopped):
            s.open_from_home('YouTube')
        self.assertEqual(['home-before-start-screen', 'leave-icon-edit-mode'], [p for _, p, _, _ in s.sent])

    def test_edit_mode_after_the_search_pill_gets_one_home_and_a_stop(self):
        s = self.build([HOME, EDIT]); s.clock = lambda: 0.0
        s.confirm_unchanged = lambda raw, role, only=None, near=None: (0.0, 50.0)
        patches = (mock.patch('farm_creation_layout.home', return_value=True), mock.patch('farm_creation_layout.small_screen', return_value=False),
                   mock.patch('farm_creation_layout.app_target', side_effect=InspectionStopped('no icon')),
                   mock.patch('farm_creation_layout.home_search', return_value=(200, 880, 300, 920)), mock.patch.object(start, 'allowed_tap', lambda *a: None))
        for p in patches: p.start(); self.addCleanup(p.stop)
        with self.assertRaises(InspectionStopped) as stop: s.open_from_home('X')
        self.assertIn('icon-edit mode', str(stop.exception))
        self.assertEqual(['open-app-search-position', 'open-app-search', 'park_after_answered_action', 'leave-icon-edit-mode'],
                         [p for _, p, _, _ in s.sent])

    def test_a_tap_moves_rests_then_clicks_where_the_pointer_is(self):
        s = self.build([]); s.clock = lambda: 0.0
        def confirm(raw, role, only=None, near=None):   # After the move, nudging only around the target (A18 16:09).
            self.assertEqual((('/mouse/move', 'open-app-search-position', 250, 900), (250, 900)), (s.sent[-1], near))
            return 0.0, 50.0
        s.confirm_unchanged = confirm
        with mock.patch.object(start, 'allowed_tap', lambda *a: None):
            s.tap(b'frame', HOME, (250, 900), 'home', 'open-app-search')
        self.assertEqual([('/mouse/move', 'open-app-search-position', 250, 900), ('/mouse/click', 'open-app-search', 250, 900),
                          ('/mouse/move', 'park_after_answered_action', 480, 300)], s.sent)

    def test_no_tap_on_a_home_screen_in_edit_mode(self):
        s = self.build([]); s.confirm_unchanged = lambda *a, **k: self.fail('No confirmation, no tap.')
        with mock.patch.object(start, 'allowed_tap', lambda *a: None), self.assertRaises(InspectionStopped):
            s.tap(b'frame', EDIT, (250, 900), 'home', 'open-app-search')
        self.assertEqual([], s.sent)


class WorkflowStepTests(unittest.TestCase):
    """CreationWorkflow.step on Home-screen roles: settled clicks; edit mode stops before any command."""
    def step(self, text, role='home', point=(250, 900)):
        from farm_draft_creation import CreationWorkflow
        flow = CreationWorkflow.__new__(CreationWorkflow); sent = []
        flow.record = {'actions': [], 'commands': []}; flow.save = lambda: None; flow.pause = lambda seconds: None
        flow.observe = lambda role, index=None: ({'id': 'obs', 'text': text}, b'frame')
        def command(fun, **data): sent.append((fun, data.get('purpose'))); flow.record['commands'].append({'state': 'answered'})
        flow.command = command
        flow.bound_command = lambda fun, **data: command(fun, **data)
        flow.step('return-search-Instagram', role, point=point)
        return sent

    def test_home_clicks_are_settled(self):
        self.assertEqual([('/mouse/move', 'return-search-Instagram-position'), ('/mouse/click', 'return-search-Instagram'),
                          ('/mouse/move', 'park_after_answered_action')], self.step(HOME))

    def test_other_roles_keep_their_click(self):
        self.assertEqual([('/mouse/click', 'return-search-Instagram'), ('/mouse/move', 'park_after_answered_action')],
                         self.step(HOME, role='instagram_navigation', point=(447, 1008)))

    def test_edit_mode_stops_before_any_command(self):
        sent = []
        with self.assertRaises(InspectionStopped): sent = self.step(EDIT)
        self.assertEqual([], sent)


# The A12/A13 frames stay in the private archive; set FARM_EDIT_MODE_FRAMES to a folder holding their
# OCR json (and a normal Home json) to check the recognizer on them.
FRAMES = Path(os.environ.get('FARM_EDIT_MODE_FRAMES', '-'))


@unittest.skipUnless(FRAMES.is_dir(), 'A12/A13 edit-mode frames are in the private archive only.')
class RealFrameTests(unittest.TestCase):
    def test_retained_frames(self):
        import json
        for path in sorted(FRAMES.glob('*.json')):
            with self.subTest(path.name):
                text = json.loads(path.read_text(encoding='utf-8'))
                if 'edit' in path.stem: self.assertTrue(edit_mode(text))
                else: self.assertIsNone(edit_mode(text))


if __name__ == '__main__':
    unittest.main()
