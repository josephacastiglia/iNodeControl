"""The Bonjour list the rack's connect scripts read. No phone, socket or desktop."""
import unittest

import farm_test_network  # noqa: F401  Refuse every real socket in this process.
import farm_mirroring as fm

BROWSE_13_OCT = """Browsing for _airplay._tcp.local
Timestamp     A/R Flags if Domain                    Service Type              Instance Name
 0:27:47.457  Add     3 21 local.                    _airplay._tcp.            Bedroom TV
 0:27:47.457  Add     3  6 local.                    _airplay._tcp.            iMouse2-C241
 0:27:47.457  Add     2  6 local.                    _airplay._tcp.            iMouse2-C24C
 0:27:47.503  Add     2 21 local.                    _airplay._tcp.            iMouse2-C24C
 0:27:48.100  Rmv     0 21 local.                    _airplay._tcp.            iMouse2-C241
"""


class BrowseTests(unittest.TestCase):
    def test_browse_output_is_parsed_with_removals(self):
        self.assertEqual({'Bedroom TV', 'iMouse2-C24C'}, fm.parse_browse(BROWSE_13_OCT))

    def test_natural_order_counts_digits_as_numbers_and_ignores_case(self):
        names = ['iMouse2-16', 'iMouse2-5', 'IMOUSE2-10', 'iMouse2-C24C']
        self.assertEqual(['iMouse2-5', 'IMOUSE2-10', 'iMouse2-16', 'iMouse2-C24C'], sorted(names, key=fm.natural))
        # The three orders a phone's list might use; the rack scripts act only where they agree.
        self.assertEqual(3, len(fm.COLLATIONS)); self.assertIs(fm.natural, fm.COLLATIONS[2])
        self.assertNotEqual(sorted(names), sorted(names, key=fm.natural))


if __name__ == '__main__':
    unittest.main()
