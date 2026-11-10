"""Image windows: prepare_window rows and staging, verify_window lane loading, window name patterns. Offline."""
import hashlib
import importlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / 'analysis/farm-multiphone-20261020'
sys.path.insert(0, str(WINDOWS))
prepare_window = importlib.import_module('prepare_window')
verify_window = importlib.import_module('verify_window')

import imouse_farm_server as server  # noqa: E402
from farm_image import ImageDrafts, SLIDES  # noqa: E402
from farm_media_transfer import TransferPackage  # noqa: E402

BOARD = '724E'


class PrepareWindowTests(unittest.TestCase):
    def test_image_rows_match_routes_capabilities_and_lane_phones(self):
        self.assertEqual(('x_image', 'x-image-creations', 'xImageCreation', False), tuple(prepare_window.PLATFORMS['x-image'][i] for i in (0, 3, 4, 5)))
        self.assertEqual(('tt_photo', 'tiktok-photo-creations', 'tiktokPhotoCreation', True),
                         tuple(prepare_window.PLATFORMS['tiktok-photo'][i] for i in (0, 3, 4, 5)))
        self.assertEqual({'x-image': 17, 'tiktok-photo': 20}, {k: v['slot'] for k, v in prepare_window.IMAGE_PLATFORMS.items()})
        for platform, row in prepare_window.IMAGE_PLATFORMS.items():
            self.assertIn(row['slot'], prepare_window.BACKEND_PORTS)
            self.assertIn(prepare_window.PLATFORMS[platform][3], server.IMAGE_CREATION_ROUTES)
            low, high = SLIDES[prepare_window.PLATFORMS[platform][0]]
            self.assertTrue(low <= row['slides'] <= high)
        self.assertEqual(set(prepare_window.IMAGE_PLATFORMS), set(verify_window.IMAGE_PLATFORMS))
        for platform, (fmt, _) in verify_window.IMAGE_PLATFORMS.items():
            self.assertEqual(prepare_window.PLATFORMS[platform][0], fmt)
            pinned = prepare_window.PLATFORMS[platform][5]
            self.assertEqual('config' if pinned else 'workflow', verify_window.IMAGE_PLATFORMS[platform][1])

    def test_stage_images_saves_one_image_draft_per_platform(self):
        for platform in prepare_window.IMAGE_PLATFORMS:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory:
                backend = Path(directory) / 'backend'; stage = backend / 'stage' / BOARD; stage.mkdir(parents=True)
                fmt, caption, label = prepare_window.PLATFORMS[platform][:3]
                draft, package, media = prepare_window.stage_images(platform, fmt, label, caption, 'title', 'abcdef123456',
                                                                    BOARD, backend, stage)
                parsed = TransferPackage(package, BOARD)
                self.assertEqual(prepare_window.IMAGE_PLATFORMS[platform]['slides'], len(parsed.images))
                self.assertEqual(media['imageSha256s'], [hashlib.sha256(d).hexdigest() for d in parsed.images.values()])
                self.assertEqual(len(parsed.images), len(set(map(tuple, media['colourCodes']))))
                self.assertEqual(draft, ImageDrafts(backend / 'image-drafts.db', backend / 'stage', BOARD).get(draft['id']))


class VerifyWindowTests(unittest.TestCase):
    def test_each_image_window_gets_its_own_lane_verifier(self):
        from farm_tiktok_photo_runs import TikTokPhotoCreationRuns
        from farm_x_runs import XImageCreationRuns
        self.assertIs(XImageCreationRuns, verify_window.lane_runs('x-image'))
        self.assertIs(TikTokPhotoCreationRuns, verify_window.lane_runs('tiktok-photo'))
        for platform, (fmt, _) in verify_window.IMAGE_PLATFORMS.items():
            runs = verify_window.lane_runs(platform)
            self.assertEqual(fmt, runs.FORMAT); self.assertIsNotNone(runs.verifier)

    def test_admitted_returns_the_ordered_package_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); backend = root / 'backend'; stage = backend / 'stage' / BOARD; stage.mkdir(parents=True)
            fmt, caption, label = prepare_window.PLATFORMS['tiktok-photo'][:3]
            _, package, _ = prepare_window.stage_images('tiktok-photo', fmt, label, caption, 't', 'abcdef123456', BOARD, backend, stage)
            config = dict(version=2, phone=dict(board=BOARD, deviceId='02:00:00:00:00:20', receiver='iMouse2-20', slot=20))
            (root / 'config.json').write_text(json.dumps(config), encoding='utf-8')
            (backend / 'tiktok-photo-creations').mkdir()
            run_id = str(uuid.uuid4())
            with sqlite3.connect(backend / 'tiktok-photo-creations' / 'runs.db') as db:
                db.execute('CREATE TABLE runs(id TEXT PRIMARY KEY, request TEXT, package BLOB, package_hash TEXT)')
                db.execute('INSERT INTO runs VALUES (?,?,?,?)', (run_id, '{}', package, hashlib.sha256(package).hexdigest()))
            db.close()
            prep = dict(platform='tiktok-photo', config=str(root / 'config.json'), backendData=str(backend), route='tiktok-photo-creations')
            run = dict(id=run_id, workflow=dict(packageSha256=hashlib.sha256(package).hexdigest()))
            _, got_caption, images = verify_window.admitted(prep, run)
            self.assertEqual(caption, got_caption)
            self.assertEqual(list(TransferPackage(package, BOARD).images.values()), images)
            with self.assertRaisesRegex(SystemExit, 'missing or changed'):
                verify_window.admitted(prep, dict(run, workflow=dict(packageSha256='0'*64)))
            import gc; gc.collect()   # admitted()'s sqlite 'with' commits but never closes; release it on Windows.


class WindowNameTests(unittest.TestCase):
    def test_start_and_stop_accept_image_window_names(self):
        for name in ('Start-Window.ps1', 'Stop-Window.ps1'):
            pattern = re.search(r"ValidatePattern\('([^']+)'\)", (WINDOWS / name).read_text(encoding='utf-8')).group(1)
            for window in ('x-slot17', 'reel-slot18', 'x-image-slot17', 'tiktok-photo-slot20'):
                self.assertTrue(re.fullmatch(pattern, window), (name, window))
            for window in ('x-image', 'x--slot17', 'a-b-c-slot1', '../x-slot17'):
                self.assertFalse(re.fullmatch(pattern, window), (name, window))

    def test_relaunch_check_knows_the_image_apps(self):
        source = (WINDOWS / 'relaunch_check.py').read_text(encoding='utf-8')
        self.assertIn("'x-image': ('X', 'x-timeline')", source); self.assertIn("'tiktok-photo': ('TikTok', 'tiktok-profile')", source)

    def test_run_window_reads_draft_id_for_image_windows(self):
        source = (WINDOWS / 'run_window.py').read_text(encoding='utf-8')
        self.assertIn("prep.get('draftId') or prep['videoDraftId']", source)
        self.assertEqual(2, source.count('draft_id=draft_id'))


class FingerprintTests(unittest.TestCase):
    def test_farm_image_is_pinned_by_server_and_launcher(self):
        launcher = (ROOT / 'Open Marketing Farm Candidate.ps1').read_text(encoding='utf-8')
        source = (ROOT / 'tools/imouse_farm_server.py').read_text(encoding='utf-8')
        self.assertIn('"farm_video.py", "farm_image.py"', source); self.assertIn("'farm_video.py', 'farm_image.py'", launcher)


if __name__ == '__main__':
    unittest.main()
