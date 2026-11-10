"""The one loader every platform's control matcher reads its templates through. Offline; reads the committed files."""
import base64
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import farm_creation_layout as layout
import farm_reel_layout as reel
import farm_tiktok_layout as tiktok
import farm_youtube_layout as youtube
from farm_owned_capture import InspectionStopped

TOOLS = Path(__file__).resolve().parent
FILES = ('farm_creation_controls.json', 'farm_reel_controls.json', 'farm_tiktok_controls.json', 'farm_youtube_controls.json')


class TemplateLoaderTests(unittest.TestCase):
    def setUp(self):
        layout._control_file.cache_clear(); layout._template.cache_clear()
        self.addCleanup(layout._control_file.cache_clear); self.addCleanup(layout._template.cache_clear)

    def test_every_committed_template_loads_as_its_recorded_bytes(self):
        for name in FILES:
            rows = json.loads((TOOLS / name).read_text(encoding='utf-8'))
            self.assertTrue(rows, name)
            for key, row in rows.items():
                with self.subTest(file=name, control=key):
                    box, raw = layout.template(name, key, 'damaged')
                    self.assertEqual(row['box'], box); self.assertIsInstance(box, list)
                    self.assertEqual(base64.b64decode(row['png']), raw)
                    self.assertEqual(row['sha256'], hashlib.sha256(raw).hexdigest())

    def test_a_file_is_read_once_and_a_caller_cannot_change_what_the_next_one_gets(self):
        reads = []
        real = Path.read_text
        def counted(path, *args, **kwargs):
            if path.name in FILES: reads.append(path.name)
            return real(path, *args, **kwargs)
        with patch.object(Path, 'read_text', counted):
            first, _ = layout.template('farm_reel_controls.json', 'next_pill', 'damaged')
            first[0] += 99                                         # A caller shifting its own copy...
            again, _ = layout.template('farm_reel_controls.json', 'next_pill', 'damaged')
            layout.template('farm_reel_controls.json', 'selection_one', 'damaged')
        self.assertEqual(['farm_reel_controls.json'], reads)
        self.assertEqual(first[0] - 99, again[0])                  # ...never moves the template.

    def test_a_damaged_template_stops_at_every_use_with_the_callers_own_message(self):
        rows = json.loads((TOOLS / 'farm_tiktok_controls.json').read_text(encoding='utf-8'))
        key = next(iter(rows)); rows[key] = dict(rows[key], sha256='0' * 64)
        with patch.object(layout, '_control_file', return_value=rows):
            for _ in range(2):
                with self.assertRaisesRegex(InspectionStopped, 'TikTok control reference is damaged'):
                    layout.template('farm_tiktok_controls.json', key, 'TikTok control reference is damaged.')
            other = next(k for k in rows if k != key)
            layout.template('farm_tiktok_controls.json', other, 'damaged')   # The others still load.
        with self.assertRaises(KeyError): layout.template('farm_reel_controls.json', 'no-such-control', 'damaged')
        with self.assertRaises(KeyError): layout.template('farm_reel_controls.json', 'no-such-control', 'damaged')   # Never remembered.

    def test_each_platforms_matcher_reads_through_the_loader_with_its_own_message(self):
        seen = []
        def stop(file_name, name, damaged):
            seen.append((file_name, name, damaged)); raise InspectionStopped(damaged)
        blank = b''
        cases = ((layout, lambda: layout._control(blank, 'ok'), 'farm_creation_controls.json', 'ok', 'Creation control reference is damaged.'),
                 (reel, lambda: reel.reel_control(blank, 'next_pill'), 'farm_reel_controls.json', 'next_pill', 'Reel control reference is damaged.'),
                 (reel, lambda: reel.numbered_one(None, (0, 0)), 'farm_reel_controls.json', 'selection_one', 'Reel control reference is damaged.'),
                 (tiktok, lambda: tiktok.control(blank, 'tt_badge_one'), 'farm_tiktok_controls.json', 'tt_badge_one', 'TikTok control reference is damaged.'),
                 (youtube, lambda: youtube._reference('yt_create_plus'), 'farm_youtube_controls.json', None, 'YouTube control reference is damaged.'))
        for module, call, file_name, name, message in cases:
            with self.subTest(file=file_name, name=name), patch.object(module, 'template', stop):
                with self.assertRaisesRegex(InspectionStopped, message): call()
                self.assertEqual((file_name, message), (seen[-1][0], seen[-1][2]))
                if name: self.assertEqual(name, seen[-1][1])


if __name__ == '__main__':
    unittest.main()
