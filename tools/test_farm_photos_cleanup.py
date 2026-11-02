"""Photos cleanup on synthetic frames: no phone captures are kept in Git (LANES.md)."""
import unittest

import numpy as np

import farm_photos_cleanup as fp
from farm_reel_layout import SQUARE
from PIL import Image

BACKGROUND = (244, 243, 249)


def blocks(seed):
    """A farm-like picture: six coloured blocks on white, as the package videos' centre crop."""
    rng = np.random.default_rng(seed)
    palette = np.array([(230, 60, 60), (250, 160, 0), (100, 150, 20), (0, 160, 240), (20, 100, 200), (240, 90, 160), (40, 140, 70)])
    picture = np.full((99, 99, 3), 245, dtype=np.uint8)
    for i in range(3):
        for j in range(2):
            picture[8 + 30 * i:34 + 30 * i, 8 + 43 * j:47 + 43 * j] = palette[rng.integers(len(palette))]
    return picture


def reference(picture, sha):
    square = np.asarray(Image.fromarray(picture).resize(SQUARE, Image.Resampling.LANCZOS), dtype=float) / 255
    return fp.Squares(sha, [square, square])


def person(seed):
    rng = np.random.default_rng(seed)
    return rng.integers(20, 120, (99, 99, 3)).astype(np.uint8)


def frame(cells, floor=908, empty=()):
    """Select-mode frame of a full 8-row library: account-like tiles except the given cell pictures and
    empty cells, a white header, 1 px light separators, then background down past the toolbar's top."""
    image = np.zeros((1080, 500, 3), dtype=np.uint8); image[:] = BACKGROUND
    image[:108] = 250
    for row in range(8):
        for column in range(5):
            if (row, column) in empty: continue
            top = floor - 100 * (8 - row)
            image[top + 1:top + 100, 100 * column + 1:100 * column + 100] = cells.get((row, column), person(10 * row + column))
    for k in range(1, 9): image[floor - 100 * k] = 250
    return image


class GridTests(unittest.TestCase):
    def test_cells_follow_the_separators_up_from_the_grid_floor(self):
        cells = fp.grid_cells(frame({}))
        self.assertEqual(len(cells), 40)
        self.assertEqual(cells[-1]['box'], (401, 809, 500, 908))
        self.assertEqual(cells[0]['box'], (1, 109, 100, 208))

    def test_the_grid_is_found_wherever_photos_left_it_scrolled(self):
        cells = fp.grid_cells(frame({}, floor=967))   # Rows from y 168, as phone 16 showed it on 1 Nov.
        self.assertEqual(len(cells), 40)
        self.assertEqual(cells[0]['box'], (1, 168, 100, 267))
        self.assertEqual(cells[-1]['box'], (401, 868, 500, 967))

    def test_a_frame_without_a_grid_floor_stops(self):
        image = np.zeros((1080, 500, 3), dtype=np.uint8)
        with self.assertRaises(fp.Stopped): fp.grid_cells(image)

    def test_empty_cells_and_the_header_gradient_are_not_tiles(self):
        image = frame({}, empty={(0, 0), (0, 1)})
        image[109:208, 1:100] = np.linspace(200, 250, 99, dtype=np.uint8)[:, None, None]   # Smooth vertical gradient.
        empty = [(c['row'], c['column']) for c in fp.grid_cells(image) if not fp.occupied(image, c['box'])]
        self.assertEqual(empty, [(0, 0), (0, 1)])


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.farm = {seed: blocks(seed) for seed in (1, 2, 3)}
        self.refs = {f'sha{seed}': reference(p, f'sha{seed}') for seed, p in self.farm.items()}

    def test_farm_videos_match_their_package_and_account_content_is_other(self):
        image = frame({(7, 0): self.farm[1], (7, 1): self.farm[3], (6, 4): person(5)})
        tiles = {(t['row'], t['column']): t for t in fp.classify(image, fp.grid_cells(image), self.refs)}
        self.assertEqual(len(tiles), 40)
        self.assertEqual({k for k, t in tiles.items() if t['status'] == 'farm'}, {(7, 0), (7, 1)})
        self.assertEqual((tiles[(7, 0)]['status'], tiles[(7, 0)]['package']), ('farm', 'sha1'))
        self.assertEqual((tiles[(7, 1)]['status'], tiles[(7, 1)]['package']), ('farm', 'sha3'))
        self.assertEqual((tiles[(6, 4)]['status'], tiles[(6, 4)]['package']), ('other', None))

    def test_a_near_miss_is_unsure_and_never_planned(self):
        near = self.farm[2].copy(); near[8:64, 8:47] = (90, 60, 200)   # Two blocks recoloured.
        image = frame({(7, 2): near})
        tile, = [t for t in fp.classify(image, fp.grid_cells(image), self.refs) if (t['row'], t['column']) == (7, 2)]
        self.assertNotEqual(tile['status'], 'farm')
        self.assertIsNone(tile['package'])

    def test_the_plan_id_changes_when_the_library_does(self):
        image = frame({(7, 0): self.farm[1]})
        tiles = fp.classify(image, fp.grid_cells(image), self.refs)
        moved = [dict(t, column=(t['column'] + 1) % 5) if t['status'] == 'farm' else t for t in tiles]
        self.assertNotEqual(fp.plan_id('F215', 40, tiles), fp.plan_id('F215', 40, moved))
        self.assertNotEqual(fp.plan_id('F215', 40, tiles), fp.plan_id('F215', 41, tiles))
        self.assertTrue(fp.same_library(tiles, [dict(t) for t in tiles]))
        self.assertFalse(fp.same_library(tiles, moved))


class BadgeTests(unittest.TestCase):
    def check(self, picture):
        image = frame({(7, 0): picture})
        return fp.badge(image, fp.grid_cells(image)[-5]['box'])

    def test_a_blue_disk_with_light_space_beside_it_is_a_check(self):
        picture = np.full((99, 99, 3), 245, dtype=np.uint8)
        yy, xx = np.mgrid[:99, :99]
        picture[(yy - 84) ** 2 + (xx - 82) ** 2 <= 64] = (10, 132, 255)
        self.assertTrue(self.check(picture))

    def test_a_blue_block_under_the_duration_shading_is_not(self):
        picture = np.full((99, 99, 3), 245, dtype=np.uint8)
        picture[60:99, 50:99] = (0, 150, 240)
        picture[70:99, :] = (picture[70:99, :] * .6).astype(np.uint8)   # The bottom-edge shading.
        self.assertFalse(self.check(picture))


class TextTests(unittest.TestCase):
    @staticmethod
    def text(*rows):
        return dict(lines=[dict(text=t, words=[dict(text=t, x=x, y=y, width=w, height=18)]) for t, x, y, w in rows])

    def test_toolbar_counts(self):
        self.assertEqual(fp.selected_count(self.text(('Select Items', 191, 1004, 120))), 0)
        self.assertEqual(fp.selected_count(self.text(('1 Video Selected', 172, 1004, 160))), 1)
        self.assertEqual(fp.selected_count(self.text(('18 Videos Selected', 160, 1004, 180))), 18)
        self.assertIsNone(fp.selected_count(self.text(('Recent Days >', 31, 756, 150))))

    def test_item_count_and_modes(self):
        select = self.text(('Library', 32, 67, 130), ('— 38 Items', 1, 114, 110), ('Select Items', 191, 1004, 120))
        self.assertEqual(fp.item_count(select), 38)
        self.assertTrue(fp.in_select(select)); self.assertFalse(fp.in_main(select))
        main = self.text(('Photos', 32, 68, 130), ('Recent Days >', 31, 756, 150))
        self.assertTrue(fp.in_main(main)); self.assertFalse(fp.in_select(main))

    def test_the_delete_button_must_name_exactly_the_planned_count(self):
        sheet = self.text(('Delete 18 Videos', 170, 900, 160))
        self.assertEqual(fp.delete_target(sheet, 18), (250, 909))
        self.assertIsNone(fp.delete_target(sheet, 17))
        self.assertIsNone(fp.delete_target(self.text(('Delete 1 Video', 180, 900, 140)), 2))
        self.assertIsNotNone(fp.delete_target(self.text(('Delete 1 Video', 180, 900, 140)), 1))


if __name__ == '__main__':
    unittest.main()
