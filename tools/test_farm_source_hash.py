"""The backend's source hash covers every file its phone-driving behaviour comes from. Offline; reads source only."""
from pathlib import Path
import shutil
import tempfile
import unittest

import imouse_farm_server as server

TOOLS = Path(__file__).resolve().parent
# The modules and data each verified format drives a phone with, and what they all share.
FORMATS = {
    'ig_reel': ('farm_reel_runs.py', 'farm_reel_creation.py', 'farm_reel_layout.py', 'farm_reel_controls.json'),
    'tt_video': ('farm_tiktok_runs.py', 'farm_tiktok_creation.py', 'farm_tiktok_layout.py', 'farm_tiktok_controls.json'),
    'x_video': ('farm_x_runs.py', 'farm_x_creation.py', 'farm_x_layout.py'),
    'yt_short': ('farm_youtube_runs.py', 'farm_youtube_creation.py', 'farm_youtube_layout.py', 'farm_youtube_controls.json'),
    'x_image': ('farm_x_runs.py', 'farm_x_image_creation.py', 'farm_x_image_layout.py'),
    'tt_photo': ('farm_tiktok_photo_runs.py', 'farm_tiktok_photo_creation.py', 'farm_tiktok_photo_layout.py'),
}
SHARED = ('imouse_farm_server.py', 'imouse_social_automation.py', 'farm_phone_identity.py', 'farm_paths.py', 'farm_owned_capture.py',
          'farm_draft_runs.py', 'farm_draft_workflow.py', 'farm_draft_transport.py', 'farm_live_verification.py',
          'farm_observations.py', 'Read-FarmImageText.ps1', 'farm_frame_evidence.py', 'farm_screen_layout.py',
          'farm_creation_layout.py', 'farm_creation_controls.json', 'farm_small_layout.py', 'farm_permission_prompts.py',
          'farm_media_transfer.py', 'farm_video.py', 'farm_image.py', 'farm_reel_test_media.py', 'farm_jobs.py',
          'farm_schedule_queue.py', 'farm_creation_runs.py', 'farm_draft_creation.py', 'farm_transitions.py', 'farm_home_edit.py')


class SourceHashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = server.source_files()

    def test_every_phone_driving_file_of_every_format_is_hashed(self):
        for fmt, names in FORMATS.items():
            for name in names:
                with self.subTest(format=fmt, name=name): self.assertIn(name, self.files)
        for name in SHARED:
            with self.subTest(shared=name): self.assertIn(name, self.files)
        self.assertEqual(sorted(self.files), list(self.files))   # One fixed order.
        self.assertTrue(all((TOOLS / name).read_bytes() == raw for name, raw in self.files.items()))

    def test_nothing_outside_the_backend_is_hashed(self):
        self.assertFalse([name for name in self.files if name.startswith('test_')])
        for name in ('farm_test_network.py', 'farm_carousel_inspection.py', 'farm_release.py', 'farm_install.py'):
            self.assertNotIn(name, self.files)
        self.assertTrue(all((TOOLS / name).is_file() for name in self.files))

    def test_a_change_to_any_hashed_file_changes_the_hash_and_nothing_else_does(self):
        with tempfile.TemporaryDirectory(prefix='farm-source-hash-') as directory:
            copy = Path(directory)
            for name in self.files: shutil.copyfile(TOOLS / name, copy / name)
            original = server.compute_source_hash(copy)
            self.assertEqual(server.compute_source_hash(), original)          # The same bytes anywhere give the same hash.
            self.assertEqual(original, server.compute_source_hash(copy))      # And the same hash every time.
            seen = {original}
            for name in sorted({n for names in FORMATS.values() for n in names} | set(SHARED)):
                path = copy / name; before = path.read_bytes()
                path.write_bytes(before + (b' ' if name.endswith('.json') else b'\n# changed\n'))
                changed = server.compute_source_hash(copy)
                with self.subTest(name=name): self.assertNotIn(changed, seen)
                seen.add(changed)
                path.write_bytes(before)
            self.assertEqual(original, server.compute_source_hash(copy))
            (copy / 'farm_not_imported.py').write_text('import farm_jobs\n', encoding='utf-8')
            (copy / 'notes.json').write_text('{}', encoding='utf-8')
            self.assertEqual(original, server.compute_source_hash(copy))      # Files the backend never loads do not count.
            (copy / 'farm_jobs.py').write_bytes((copy / 'farm_jobs.py').read_bytes() + b'\nimport farm_not_imported\n')
            self.assertIn('farm_not_imported.py', server.source_files(copy))  # A newly imported module is covered at once.

    def test_the_running_backend_reports_this_hash(self):
        with tempfile.TemporaryDirectory(prefix='farm-source-hash-runtime-') as directory:
            runtime = server.FarmBackendRuntime(Path(directory) / 'farm.db', Path(directory) / 'stage')
            self.addCleanup(runtime.transfers.close)
            self.assertEqual(server.compute_source_hash(), runtime.source_hash)
            self.assertRegex(runtime.source_hash, '^[0-9a-f]{64}$')

    def test_no_import_is_hidden_from_the_reader(self):
        # A module named only at run time would escape the hash, so the backend's files may not load one that way.
        for name, raw in self.files.items():
            if name.endswith('.py'):
                with self.subTest(name=name):
                    self.assertNotIn(b'import_module(', raw); self.assertNotIn(b'__import__(', raw)


if __name__ == '__main__':
    unittest.main()
