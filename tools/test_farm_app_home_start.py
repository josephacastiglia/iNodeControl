"""The YouTube start screen on A14 (5 Nov): the lease is renewed before the launch waits; the bare gallery closes."""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import farm_start_screen as start  # noqa: E402
import farm_youtube_layout as yl  # noqa: E402
from farm_paths import MAIN  # noqa: E402
from farm_start_screen import InspectionStopped, StartScreen  # noqa: E402

FRAMES = Path(os.environ.get('IMOUSE_HOVER_FRAMES', Path(MAIN).parent / 'iMouseXP-2.0-evidence-archive' / '20261105-hover-tint'))


def refused(*a, **k): raise InspectionStopped('No.')


def screen():
    s = StartScreen.__new__(StartScreen)
    s.record = {'observations': [], 'commands': []}; s.save = lambda: None; s.pause = lambda seconds: None
    s.kernel = mock.Mock(); s.kernel.acquire.return_value = {'B': 'token'}; s.phone = mock.Mock(board='B')
    s.command = lambda *a, **k: None
    return s


class LaunchWaitTests(unittest.TestCase):
    def test_the_lease_is_renewed_before_each_launch_wait(self):
        s, order = screen(), []
        s.kernel.renew_if_needed.side_effect = lambda tokens, least: order.append(('renew', least))
        reads = iter(('before', 'after-launch-1', 'after-launch-2'))
        def fresh(role): order.append(role); next(reads); return b'', {'at': role}, 0, 0
        s.fresh = fresh; s.open_from_home = lambda name: (b'', {'at': 'opened'}, 0, 0)
        def check(raw, text):
            if text['at'] != 'after-launch-2': raise InspectionStopped('Not yet.')
        s.to_app_home('YouTube', 'youtube_home', check)
        self.assertEqual(['before', ('renew', 20000), 'after-launch-1', ('renew', 20000), 'after-launch-2'], order)
        self.assertEqual('at_start', s.record['state'])

    def test_no_renew_when_the_app_is_already_open(self):
        s = screen(); s.fresh = lambda role: (b'', {}, 0, 0)
        s.to_app_home('YouTube', 'youtube_home', lambda raw, text: None)
        s.kernel.renew_if_needed.assert_not_called()


class BackOutTests(unittest.TestCase):
    def back_out(self):
        s = screen(); captured = {}
        s.to_app_home = lambda name, target, check, back_out=None: captured.update(back_out=back_out)
        s.to_youtube_home()
        return captured['back_out']

    def patched(self, header):
        patches = [mock.patch.object(yl, 'yt_draft_prompt', refused), mock.patch.object(yl, 'drafts_notice', lambda text: False),
                   mock.patch.object(yl, 'yt_gallery', refused), mock.patch.object(yl, 'yt_camera', refused),
                   mock.patch.object(yl, '_picker_header', header)]
        for p in patches: p.start(); self.addCleanup(p.stop)

    def test_the_bare_gallery_closes_with_the_same_x(self):
        self.patched(lambda frame, text, role: (None, yl.BARE_DY))
        self.assertEqual((yl.GALLERY_CLOSE, 'youtube_gallery', 'close-gallery', ((0, 60, 500, 205),)), self.back_out()(b'', {}))

    def test_another_gallery_without_drafts_still_stops(self):
        self.patched(lambda frame, text, role: (None, -86))
        self.assertIsNone(self.back_out()(b'', {}))

    def test_an_unrecognized_screen_still_stops(self):
        self.patched(refused)
        self.assertIsNone(self.back_out()(b'', {}))

    @unittest.skipUnless((FRAMES / 'A14-bare-gallery.bmp').is_file(), 'The A14 frame is private and kept outside Git.')
    def test_a14s_gallery_frame(self):
        raw = (FRAMES / 'A14-bare-gallery.bmp').read_bytes()
        text = json.loads((FRAMES / 'A14-bare-gallery.json').read_text(encoding='utf-8'))
        move = self.back_out()(raw, text)
        self.assertEqual(yl.GALLERY_CLOSE, move[0]); self.assertEqual('close-gallery', move[2])
        start.allowed_tap(text, *move[0], 'open_app')


if __name__ == '__main__':
    unittest.main()
