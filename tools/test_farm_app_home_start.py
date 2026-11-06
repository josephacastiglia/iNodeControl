"""The start screen on A14 and A12 (5 Nov): every input renews the lease first; the bare gallery closes."""
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


class LeaseTests(unittest.TestCase):
    def built(self):
        s = StartScreen.__new__(StartScreen)
        s.record = {'commands': []}; s.save = lambda: None; s.pointer = None; s.tokens = {'B': 'token'}
        s.kernel = mock.Mock(); s.phone = mock.Mock(board='B')
        return s

    def test_every_input_renews_the_lease_first(self):
        s, order = self.built(), []
        s.kernel.renew_if_needed.side_effect = lambda tokens, least: order.append(('renew', tokens, least))
        s.kernel.send.side_effect = lambda board, token, fun, **data: order.append(('send', fun))
        s.command('/mouse/move', 'fresh_frame_challenge', x=1, y=2)
        self.assertEqual([('renew', {'B': 'token'}, 20000), ('send', '/mouse/move')], order)

    def test_a_lost_lease_sends_and_records_nothing(self):
        s = self.built(); s.kernel.renew_if_needed.side_effect = RuntimeError('Renew failed')
        with self.assertRaises(RuntimeError): s.command('/mouse/click', 'open', x=1, y=2, button=1)
        s.kernel.send.assert_not_called(); self.assertEqual([], s.record['commands'])


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
