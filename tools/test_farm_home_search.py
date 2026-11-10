"""Home screen Search pill: template first, else the exact OCR word inside the pill box. No phone access."""
import io
import unittest

from PIL import Image

from farm_owned_capture import InspectionStopped
from farm_creation_layout import HOME_SEARCH_BOX, home_search


def frame(colour='#7fb2ff'):
    out = io.BytesIO(); Image.new('RGB', (500, 1080), colour).save(out, 'PNG'); return out.getvalue()


def ocr(*rows):
    return dict(width=500, height=1080, lines=[dict(text=t, words=[dict(text=w, x=x + 60 * i, y=y, width=8 * len(w), height=16) for i, w in enumerate(t.split())])
                       for t, x, y in rows])


class HomeSearchTests(unittest.TestCase):
    def test_a_wallpaper_tinted_pill_is_accepted_by_its_exact_label_only(self):
        # C24C on 20 Oct after a restart: 'Search *' at (235, 893); the template differed by 5.4%.
        self.assertEqual(list(HOME_SEARCH_BOX), home_search(frame(), ocr(('Search *', 235, 893))))
        for rows in ((), (('Search', 235, 700),), (('Searching', 235, 893),), (('Search', 235, 893), ('Search', 240, 900))):
            with self.subTest(rows=rows), self.assertRaises(InspectionStopped):
                home_search(frame(), ocr(*rows))


if __name__ == '__main__':
    unittest.main()
