"""instagram_logo accepts the current wordmark (A18) or the older script one (A12); nothing else. Offline."""
import unittest

import farm_paths
from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import CONTROL_VARIANTS, _matches, control

FRAMES = farm_paths.ARCHIVE/'20261105-fleet-a12'


class Variants(unittest.TestCase):
    def test_only_instagram_logo_has_a_variant(self):
        self.assertEqual({'instagram_logo': ('instagram_logo', 'instagram_logo_script')}, CONTROL_VARIANTS)


@unittest.skipUnless((FRAMES/'ig-feed-a12.png').exists(), 'Fleet frames of 5 Nov are not available in this checkout.')
class InstagramLogo(unittest.TestCase):
    def frame(self, name): return (FRAMES/name).read_bytes()

    def test_a18_keeps_the_current_template(self):
        raw = self.frame('ig-feed-a18.png')
        self.assertTrue(_matches(raw, 'instagram_logo'))
        self.assertFalse(_matches(raw, 'instagram_logo_script'))
        self.assertEqual([166, 72, 310, 107], control(raw, 'instagram_logo'))

    def test_a12_script_wordmark_is_accepted(self):
        raw = self.frame('ig-feed-a12.png')
        self.assertFalse(_matches(raw, 'instagram_logo'))
        self.assertEqual([164, 68, 312, 115], control(raw, 'instagram_logo'))

    def test_another_screen_still_stops_naming_the_control(self):
        with self.assertRaisesRegex(InspectionStopped, 'Creation control changed: instagram_logo$'):
            control(self.frame('not-instagram.bmp'), 'instagram_logo')

    def test_other_controls_get_no_variant(self):
        with self.assertRaises(InspectionStopped): control(self.frame('ig-feed-a12.png'), 'empty_ios_search')


if __name__ == '__main__':
    unittest.main()
