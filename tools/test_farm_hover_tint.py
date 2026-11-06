"""The settled tap's confirmation and the hover tint (A19, 5 Nov): only the target's own even tint is left out."""
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import farm_start_screen as start  # noqa: E402
from farm_paths import MAIN  # noqa: E402
from farm_start_screen import InspectionStopped, hover_tint  # noqa: E402

TARGET = (250, 556)
FRAMES = Path(os.environ.get('IMOUSE_HOVER_FRAMES', Path(MAIN).parent / 'iMouseXP-2.0-evidence-archive' / '20261105-hover-tint'))


def dialog():
    """A dark dialog with three labelled rows over brighter video, as the Start over dialog (values from the A19 frames)."""
    frame = np.full((1080, 500, 3), [142 / 255, 58 / 255, 93 / 255])
    frame[400:765, 95:410] = [27 / 255, 27 / 255, 33 / 255]
    for top in (525, 588, 655):
        frame[top - 1, 95:410] = [34 / 255, 34 / 255, 40 / 255]
        frame[top + 22:top + 40, 190:310:3] = [235 / 255, 90 / 255, 120 / 255]
    return frame


def tinted(frame, top=525, bottom=588, level=(17, 20, 24)):
    out = frame.copy(); out[top:bottom, 95:410] = np.clip(out[top:bottom, 95:410] + np.array(level) / 255, 0, 1)
    return out


def with_pointer(frame, x=250, y=556):
    out = frame.copy(); yy, xx = np.ogrid[:1080, :500]
    out[(xx - x) ** 2 + (yy - y) ** 2 <= 14 ** 2] = [.6, .6, .6]
    return out


class HoverTintTests(unittest.TestCase):
    def test_the_rows_even_tint_is_its_own_box(self):
        self.assertEqual((95, 525, 410, 588), hover_tint(dialog(), tinted(dialog()), TARGET))

    def test_the_pointer_on_the_tint_is_allowed(self):
        self.assertEqual((95, 525, 410, 588), hover_tint(dialog(), with_pointer(tinted(dialog())), TARGET))

    def test_a_darkening_highlight_counts(self):
        a = dialog(); a[525:588, 95:410] = .9
        self.assertEqual((95, 525, 410, 588), hover_tint(a, tinted(a, level=(-20, -20, -20)), TARGET))

    def test_no_change_is_no_tint(self):
        self.assertIsNone(hover_tint(dialog(), dialog(), TARGET))

    def test_a_changed_label_is_not_a_tint(self):
        b = tinted(dialog()); b[547:565, 120:190:2] = [1, 1, 1]
        self.assertIsNone(hover_tint(dialog(), b, TARGET))

    def test_a_tall_change_is_a_new_screen(self):
        self.assertIsNone(hover_tint(dialog(), tinted(dialog(), top=400, bottom=765), TARGET))

    def test_a_strong_flat_change_is_not_a_tint(self):
        self.assertIsNone(hover_tint(dialog(), tinted(dialog(), level=(90, 90, 90)), TARGET))

    def test_a_tint_on_another_row_does_not_cover_the_target(self):
        self.assertIsNone(hover_tint(dialog(), tinted(dialog(), top=588, bottom=655), TARGET))


class ConfirmTests(unittest.TestCase):
    """confirm_unchanged end to end with a fake kernel."""
    def confirm(self, later, near=TARGET, only=((80, 360, 420, 720),)):
        def bmp(array):
            out = io.BytesIO(); Image.fromarray((array * 255).round().astype('uint8')).save(out, 'BMP'); return out.getvalue()
        screen = start.StartScreen.__new__(start.StartScreen)
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        screen.folder = Path(folder.name); screen.record = {'observations': [], 'commands': []}; screen.save = lambda: None
        screen.pause = lambda seconds: None; screen.clock = lambda: 0.0; screen.pointer = TARGET
        screen.command = lambda *a, **k: None; screen.await_frame = lambda before: None
        screen.phone = mock.Mock(board='B')
        screen.kernel = mock.Mock()
        screen.kernel.shot.return_value = (bmp(later), {'X-iMouse-Frame-Sequence': '9', 'X-iMouse-Frame-Age-Ms': '5'})
        patch = mock.patch.object(start, 'own_receiver', lambda status, phone: {'frames': 1}); patch.start(); self.addCleanup(patch.stop)
        try: screen.confirm_unchanged(bmp(dialog()), 'start_over_dialog', only, near=near)
        finally: self.entry = screen.record['observations'][-1]

    def test_the_tinted_row_confirms_and_is_recorded(self):
        self.confirm(with_pointer(tinted(dialog())))
        self.assertEqual('fresh_unchanged', self.entry['state']); self.assertEqual([95, 525, 410, 588], self.entry['hoverBox'])

    def test_a_change_elsewhere_in_the_dialog_still_stops(self):
        b = tinted(dialog()); b[600:640, 100:400] = [.8, .8, .8]
        with self.assertRaises(InspectionStopped): self.confirm(b)
        self.assertEqual('stale_or_changed', self.entry['state'])

    def test_without_a_settled_target_the_tint_still_stops(self):
        with self.assertRaises(InspectionStopped): self.confirm(tinted(dialog()), near=None)

    def test_a_box_covering_all_that_is_compared_stops(self):
        with self.assertRaises(InspectionStopped): self.confirm(tinted(dialog()), only=((95, 525, 410, 588),))


@unittest.skipUnless(FRAMES.is_dir(), 'The A19 frames are private and kept outside Git.')
class A19FrameTests(unittest.TestCase):
    def test_the_frames_that_stopped_now_match_outside_the_row(self):
        load = lambda name: np.asarray(Image.open(FRAMES / name).convert('RGB'), dtype=float) / 255
        for run in ('A19-10', 'A19-11'):
            a, b = load(run + '-before.bmp'), load(run + '-confirm.bmp')
            box = hover_tint(a, b, TARGET)
            self.assertIsNotNone(box, run); left, top, right, bottom = box
            self.assertTrue(520 <= top <= 530 and 583 <= bottom <= 592 and left < 100 and right > 400, box)
            mask = np.zeros(a.shape[:2], dtype=bool); mask[360:720, 80:420] = True; mask[top:bottom, left:right] = False
            self.assertLessEqual(float(np.abs(a - b)[mask].mean()), .003, run)


if __name__ == '__main__':
    unittest.main()
