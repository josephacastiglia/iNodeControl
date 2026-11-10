"""search_clear's fallback on tinted wallpapers. Offline.

Frames stay out of Git, so each case is rebuilt from what was measured on the 5 Nov frames (A11, A12, A14,
A15): the field's median colour beside the button, the glyph's colour, the rest of the box, and the share of
the 34 x 32 box the glyph covers.
"""
import io
import unittest

import numpy as np
from PIL import Image

from farm_owned_capture import InspectionStopped
from farm_creation_layout import search_clear

BOX = (430, 988, 462, 1022)
CASES = {   # name: (field RGB, glyph RGB or None, rest of box RGB, glyph share, white share then, button shown)
    'A14 teal wallpaper': ((104, 184, 196), (211, 255, 255), (92, 183, 191), .39, .06, True),
    'A12 button': ((105, 115, 126), (242, 255, 255), (94, 107, 117), .40, .34, True),
    'A15 button': ((114, 109, 115), (255, 251, 255), (117, 108, 118), .41, .35, True),
    'A11 button': ((134, 129, 135), (255, 251, 255), (137, 128, 138), .41, .36, True),
    'A12 empty field': ((105, 115, 126), None, (93, 106, 117), 0, 0, False),
    'A14 empty field': ((93, 173, 185), None, (82, 173, 181), 0, 0, False),
    'A11 alert over Home': ((65, 59, 69), (177, 174, 177), (5, 3, 5), .20, 0, False),
    'A15 alert over Home': ((64, 59, 68), (176, 172, 176), (6, 3, 6), .21, 0, False),
}


def frame(field, glyph, rest, share):
    a = np.zeros((1080, 500, 3), dtype=np.uint8); a[:] = field
    left, top, right, bottom = BOX
    box = np.empty((bottom - top, right - left, 3), dtype=np.uint8); box[:] = rest
    if glyph is not None:
        flat = box.reshape(-1, 3); flat[:round(share * len(flat))] = glyph
    a[top:bottom, left:right] = box
    out = io.BytesIO(); Image.fromarray(a).save(out, 'PNG'); return out.getvalue()


class SearchClear(unittest.TestCase):
    def test_measured_cases(self):
        for name, (field, glyph, rest, share, _, shown) in CASES.items():
            with self.subTest(name):
                if shown: self.assertEqual(list(BOX), search_clear(frame(field, glyph, rest, share)))
                else:
                    with self.assertRaises(InspectionStopped): search_clear(frame(field, glyph, rest, share))

    def test_white_glyph_still_decides_first(self):
        # A white glyph in the old band passes as before, even where the relative share would be out of band.
        self.assertEqual(list(BOX), search_clear(frame((230, 230, 230), (255, 255, 255), (200, 200, 200), .35)))

    def test_too_much_light_is_not_a_button(self):
        with self.assertRaises(InspectionStopped): search_clear(frame((104, 184, 196), (211, 255, 255), (92, 183, 191), .8))


if __name__ == '__main__':
    unittest.main()
