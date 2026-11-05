"""A restored app-search query: the farm's own apps are recognized for clearing; anything else stops. Offline."""
import unittest

from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import RESTORED_QUERIES, restored_app_search


def line(text, x, y, w=80, h=20):
    return dict(text=text, words=[dict(text=text, x=x, y=y, width=w, height=h)])


def spotlight(query):
    # A14, 5 Nov: Top Hit header, the app's label under its icon, then Suggestions.
    return dict(width=500, height=1080, lines=[line('Top Hit', 25, 76), line(query, 55, 205), line('Suggestions', 26, 275),
                       line(query, 70, 330), line('Search in Apps', 26, 842)])


class RestoredSearch(unittest.TestCase):
    def test_farm_apps_are_recognized(self):
        self.assertEqual(('Safari', 'Instagram', 'YouTube', 'TikTok'), RESTORED_QUERIES)
        for app in RESTORED_QUERIES:
            with self.subTest(app=app):
                found = restored_app_search(spotlight(app))
                self.assertEqual(app, found['app'])
                self.assertEqual((95, 215), found['target'])

    def test_other_queries_stop(self):
        for query in ('Settings', 'Photos', 'Messages'):
            with self.subTest(query=query), self.assertRaises(InspectionStopped):
                restored_app_search(spotlight(query))

    def test_needs_the_top_hit_header(self):
        text = spotlight('YouTube'); text['lines'] = text['lines'][1:]
        with self.assertRaises(InspectionStopped): restored_app_search(text)


if __name__ == '__main__':
    unittest.main()
