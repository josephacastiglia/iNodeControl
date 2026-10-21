"""Safari's Start Page (no tab open) and its focused, empty address field. OCR rows from C24C, 21 Oct."""
import unittest

from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import safari_address_empty, safari_blank, safari_start_page


def text(*rows):
    return dict(width=500, height=1080, lines=[dict(text=t, words=[dict(text=t, x=x0, y=y0, width=x1-x0, height=y1-y0)])
                                               for t, x0, y0, x1, y1 in rows])


PAGE = [('Favorites', 60, 121, 172, 142), ('Privacy Report', 27, 315, 205, 340), ('Recently Closed Tabs', 27, 509, 289, 534),
        ('Reel draft transfer', 41, 564, 189, 578), ('Edit', 233, 663, 268, 679)]
ENTRY = text(*PAGE, ('Q', 53, 945, 72, 965), ('Search or enter website name', 115, 947, 385, 963))
FOCUSED = text(*PAGE, ('x', 450, 77, 465, 92), ('Search or enter webse name', 38, 939, 309, 963))


class SafariStartPageTests(unittest.TestCase):
    def test_start_page_is_recognized_before_focus_only(self):
        self.assertTrue(safari_start_page(ENTRY)['startPage'])
        with self.assertRaises(InspectionStopped): safari_start_page(FOCUSED)
        with self.assertRaises(InspectionStopped): safari_start_page(text(*PAGE))

    def test_focused_field_must_be_empty_with_its_close_button(self):
        self.assertTrue(safari_address_empty(FOCUSED)['addressEmpty'])
        with self.assertRaises(InspectionStopped): safari_address_empty(ENTRY)   # Not focused yet.
        typed = text(*PAGE, ('x', 450, 77, 465, 92), ('example.com', 38, 939, 140, 963))
        with self.assertRaises(InspectionStopped): safari_address_empty(typed)   # Existing text is never overwritten.
        no_close = text(*PAGE, ('Search or enter website name', 38, 947, 309, 963))   # 21 Oct frame: OCR missed the close button.
        self.assertTrue(safari_blank(ENTRY)['startPage'] and safari_blank(FOCUSED)['addressEmpty'])
        with self.assertRaises(InspectionStopped): safari_blank(typed)
        self.assertTrue(safari_address_empty(no_close)['addressEmpty'] and safari_blank(no_close)['startPage'])


class DownloadsListTests(unittest.TestCase):
    def test_a_split_file_name_is_matched_by_its_unique_code(self):
        import farm_reel_layout as reel
        header = [('Done', 27, 523, 75, 538), ('Downloads', 199, 522, 303, 538), ('Clear', 428, 522, 475, 538)]
        split = text(*header, ('mouse', 94, 590, 158, 601), ('-cpfypm', 202, 586, 279, 605), ('31 KB', 94, 615, 133, 625),
                     ('mouse-', 94, 682, 167, 694), ('cvrfec', 211, 678, 268, 694), ('31 KB', 94, 707, 133, 718))
        self.assertEqual((186, 596), reel.downloads_list(split, 'imouse-reel-cpfypm', 31166)['target'])   # 21 Oct, slot 18.
        for name, size in (('imouse-reel-aaaaaa', 31166), ('imouse-reel-cpfypm', 64000)):
            with self.subTest(name=name, size=size), self.assertRaises(InspectionStopped): reel.downloads_list(split, name, size)
        twice = text(*header, ('imouse-reel-cpfypm', 94, 586, 279, 605), ('31 KB', 94, 615, 133, 625),
                     ('imouse-reel-cpfypm', 94, 678, 279, 694), ('31 KB', 94, 707, 133, 718))
        with self.assertRaises(InspectionStopped): reel.downloads_list(twice, 'imouse-reel-cpfypm', 31166)   # Ambiguous.


if __name__ == '__main__':
    unittest.main()
