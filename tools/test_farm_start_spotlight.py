"""Spotlight's app result is confirmed on its own row and the search field (A18, 5 Nov: an animated
'Create wallpaper' row below the Siri Suggestions kept every newer frame from matching)."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageDraw

from farm_carousel_inspection import InspectionStopped
import farm_start_screen as start
from farm_start_screen import StartScreen, result_band


def png(image):
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


def spotlight(thumbnail_shade=0, row_shade=None):
    """Siri Suggestions with Instagram at (88, 182), an animated row at y 280-440, the search field at the bottom."""
    image = Image.new('RGB', (500, 1080), (90, 60, 120)); draw = ImageDraw.Draw(image)
    draw.rectangle((25, 100, 475, 245), fill=(200, 190, 210)); draw.rectangle((50, 125, 125, 200), fill=(220, 60, 140))
    if row_shade is not None: draw.rectangle((50, 125, 125, 200), fill=row_shade)
    draw.rectangle((20, 270, 480, 440), fill=(120 + thumbnail_shade, 80, 140 - thumbnail_shade))
    draw.rectangle((25, 978, 475, 1035), fill=(150, 170, 200))
    return png(image)


class Kernel:
    def __init__(self, raw): self.raw, self.frames = raw, 10
    def kernel_status(self): return {}
    def shot(self, board):
        self.frames += 1
        return self.raw, {'X-iMouse-Frame-Sequence': str(self.frames), 'X-iMouse-Frame-Age-Ms': '20'}


def screen(later):
    s = StartScreen.__new__(StartScreen)
    s.kernel = Kernel(later); s.phone = mock.Mock(board='C24C'); s.pointer = (480, 300)
    s.command = lambda *a, **k: None; s.pause = lambda seconds: None; s.await_frame = lambda before: None
    s.clock = lambda: 0.0; s.record = {'observations': []}; s.save = lambda: None
    s.folder = Path(tempfile.mkdtemp())
    return s


@mock.patch.object(start, 'own_receiver', lambda status, phone: {'frames': 10})
class SpotlightConfirmTests(unittest.TestCase):
    def test_band_is_the_targets_row_and_the_field(self):
        self.assertEqual(((0, 112, 500, 252), (0, 960, 500, 1060)), result_band((88, 182)))
        self.assertEqual((0, 65, 500, 110), result_band((88, 40))[0])

    def test_an_animated_row_below_does_not_block_the_tap(self):
        recognized, later = spotlight(), spotlight(thumbnail_shade=40)
        with self.assertRaises(InspectionStopped):   # Whole frame: the moving row differs (as on 5 Nov).
            screen(later).confirm_unchanged(recognized, 'app_result')
        screen(later).confirm_unchanged(recognized, 'app_result', only=result_band((88, 182)))

    def test_a_change_in_the_targets_row_still_stops(self):
        recognized, later = spotlight(), spotlight(row_shade=(40, 200, 90))
        with self.assertRaises(InspectionStopped):
            screen(later).confirm_unchanged(recognized, 'app_result', only=result_band((88, 182)))

    def test_both_routes_pass_the_band(self):
        source = Path(start.__file__).read_text(encoding='utf-8')
        self.assertEqual(2, source.count("'app_result', 'open-' + name.casefold(), only=result_band(point))"))


if __name__ == '__main__':
    unittest.main()
