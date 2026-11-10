"""Home screen Search pill: template first, else the exact OCR word inside the pill box. No phone access."""
import io
import unittest

from PIL import Image

from farm_owned_capture import InspectionStopped
from farm_creation_layout import HOME_SEARCH_BOX, home_search, pill_word


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

    def test_the_enlarged_read_of_the_pill_goes_through_the_shared_band_reader(self):
        from unittest.mock import patch
        import farm_reel_layout as reel
        left, top, right, bottom = HOME_SEARCH_BOX; picture = frame()
        for words, expected in ((['Search'], 'search'), (['Q', 'SEARCH'], 'search'), (['Search', 'x'], 'x'), ([], '')):
            with self.subTest(words=words), patch.object(reel, 'band_words', return_value=[(w, 0, 0, 1, 1) for w in words]) as band:
                self.assertEqual(expected, pill_word(picture))
                band.assert_called_once_with(picture, (left - 10, top - 8, right + 10, bottom + 4), 3)
        with patch.object(reel, 'band_words', return_value=[('Search', 0, 0, 1, 1)]):
            self.assertEqual(list(HOME_SEARCH_BOX), home_search(picture, ocr()))   # Read by neither the template nor full-frame OCR.

    def test_the_pill_is_submitted_to_the_reader_exactly_as_it_always_was(self):
        from unittest.mock import patch
        from PIL import ImageDraw, ImageOps
        import farm_observations
        image = Image.new('RGB', (500, 1080), '#7fb2ff'); ImageDraw.Draw(image).text((228, 892), 'Search', fill='white')
        out = io.BytesIO(); image.save(out, 'PNG'); picture = out.getvalue()
        left, top, right, bottom = HOME_SEARCH_BOX; submitted = []
        with patch.object(farm_observations.WindowsOcr, 'read', lambda self, raw: submitted.append(raw) or dict(lines=[])):
            self.assertEqual('', pill_word(picture))
        with Image.open(io.BytesIO(picture)) as source:   # The crop, enlargement and contrast pill_word applied before 9 Nov.
            crop = ImageOps.autocontrast(source.convert('L').crop((left-10, top-8, right+10, bottom+4)).resize(
                ((right-left+20)*3, (bottom-top+12)*3), Image.Resampling.LANCZOS))
        expected = io.BytesIO(); crop.convert('RGB').save(expected, 'BMP')
        self.assertEqual([expected.getvalue()], submitted)


if __name__ == '__main__':
    unittest.main()
