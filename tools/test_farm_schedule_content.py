"""Real prepared content -> a window: checked against its batch, refused when unfit, bound without changing what was approved."""
import datetime as dt
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import farm_schedule_content as content
import farm_schedule_runner as runner
from farm_schedule_queue import ReviewQueue
from test_farm_schedule_runner import FakeSteps, PREP

NOON = dt.datetime(2026, 11, 6, 12, 0, tzinfo=dt.timezone.utc).timestamp()
GENERATION = 'a' * 32


def batch(root, files, board='C24C'):
    """A prepared batch on disk, as the content factory leaves it; returns its content item."""
    folder = Path(root) / board; folder.mkdir(parents=True, exist_ok=True)
    assets = []
    for name, raw in files.items():
        (folder / name).write_bytes(raw)
        assets.append({'url': f'/stage/{board}/{name}', 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
    manifest = json.dumps({'deviceId': board, 'generation': GENERATION, 'assets': assets}).encode()
    (folder / f'manifest_{GENERATION}.json').write_bytes(manifest)
    return {'id': 21, 'platform': 'instagram', 'format': 'ig_reel', 'caption': 'A real caption', 'stagedFiles': list(files),
            'generation': GENERATION, 'manifest': f'/stage/{board}/manifest_{GENERATION}.json',
            'manifestSha256': hashlib.sha256(manifest).hexdigest()}


class CheckedFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'stage'; self.item = batch(self.root, {'clip.mp4': b'video bytes'})

    def test_good_files_pass_in_order(self):
        item = batch(self.root, {'2.jpg': b'two', '1.jpg': b'one'})
        self.assertEqual(['2.jpg', '1.jpg'], [f[0] for f in content.checked_files(item, self.root)])

    def test_a_changed_or_unlisted_file_or_batch_is_refused(self):
        (self.root / 'C24C/clip.mp4').write_bytes(b'other bytes')
        with self.assertRaisesRegex(content.ContentRefused, 'changed'): content.checked_files(self.item, self.root)
        fresh = batch(self.root, {'clip.mp4': b'video bytes'})
        for change, why in (({'stagedFiles': ['other.mp4']}, 'not in its batch'), ({'stagedFiles': ['../clip.mp4']}, 'Invalid'),
                            ({'stagedFiles': []}, 'names no files'), ({'manifestSha256': 'b' * 64}, 'checksum changed'),
                            ({'manifest': 'elsewhere'}, 'does not name')):
            with self.subTest(why), self.assertRaisesRegex(content.ContentRefused, why):
                content.checked_files({**fresh, **change}, self.root)
        (self.root / 'C24C/clip.mp4').unlink()
        with self.assertRaisesRegex(content.ContentRefused, 'missing'): content.checked_files(fresh, self.root)

    def test_formats(self):
        self.assertEqual('reel', content.platform_of('ig_reel')); self.assertEqual('tiktok-photo', content.platform_of('tt_photo'))
        with self.assertRaisesRegex(content.ContentRefused, 'ig_carousel'): content.platform_of('ig_carousel')
        for fmt, (_, module, name) in content.FORMATS.items():     # Every named runs class exists and can answer.
            with self.subTest(fmt): self.assertTrue(callable(getattr(importlib.import_module(module), name).supports))


class StageContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name); self.source = root / 'source'; self.backend = root / 'backend'
        self.stage = self.backend / 'stage/C24C'; self.stage.mkdir(parents=True)

    def test_a_video_reaches_a_draft_with_its_exact_caption(self):
        item = batch(self.source, {'clip.mp4': b'video bytes'})
        metadata = {'width': 720, 'height': 1280, 'seconds': 5}
        with mock.patch('farm_video.normalize_video', return_value=(b'encoded video', metadata)), \
             mock.patch('farm_video.VideoDrafts.export', return_value=b'package'), mock.patch('farm_video.VideoTransferPackage') as parsed:
            draft, package, transfer, media = content.stage_content(item, self.source, 'C24C', self.backend, self.stage, 'Title')
        self.assertEqual(('A real caption', 'ig_reel', False), (draft['caption'], draft['format'], draft['published']))
        self.assertEqual(b'video bytes', (self.stage / 'clip.mp4').read_bytes())
        self.assertEqual((b'package', transfer), (package, parsed.return_value))
        self.assertEqual(draft['id'], media['videoDraftId'])
        manifest = json.loads((self.stage / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual('C24C', manifest['deviceId']); self.assertEqual('/stage/C24C/clip.mp4', manifest['assets'][0]['url'])

    def test_two_files_for_a_video_format_and_a_refused_draft_stop(self):
        item = batch(self.source, {'a.mp4': b'one', 'b.mp4': b'two'})
        with self.assertRaisesRegex(content.ContentRefused, 'exactly one video'):
            content.stage_content(item, self.source, 'C24C', self.backend, self.stage, 'Title')
        item = batch(self.source, {'c.mp4': b'three'})
        with mock.patch('farm_video.normalize_video', side_effect=ValueError('The video is too long.')), \
             self.assertRaisesRegex(content.ContentRefused, 'too long'):
            content.stage_content(item, self.source, 'C24C', self.backend, self.stage, 'Title')

    def test_refusal_asks_the_platforms_own_runs_class(self):
        from farm_reel_runs import ReelCreationRuns
        with mock.patch.object(ReelCreationRuns, 'supports', return_value=True):
            self.assertIsNone(content.refusal('ig_reel', b'package', {}))
        with mock.patch.object(ReelCreationRuns, 'supports', return_value=False):
            self.assertEqual(ReelCreationRuns.UNSUPPORTED_REASON, content.refusal('ig_reel', b'package', {}))


class BindAndRunTests(unittest.TestCase):
    """An approved real package: bound to its window, planned, and run as a test window is."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.now = [NOON]; self.root = Path(self.temp.name)
        self.q = ReviewQueue(self.root / 'queue.json', clock=lambda: self.now[0])
        self.q.set_settings(window=[0, 24], utc_offset_hours=0)
        self.item = batch(self.root / 'stage', {'clip.mp4': b'video bytes'})
        report = self.q.intake([{**self.item, 'account': 'acct-a18', 'runId': 'r1'}])
        self.assertEqual([21], report['added'])
        self.staging = self.root / 'windows'
        self.steps = runner.WindowSteps(self.staging, folder=self.root / 'farm')

    def fake_prepare(self, caption='A real caption', test_package=False):
        def prepare(argv):
            self.argv = argv
            staged = self.staging / '21'; staged.mkdir(parents=True)
            (staged / 'preparation.json').write_text(json.dumps(dict(
                PREP, caption=caption, testPackage=test_package, packageSha256='c' * 64)), encoding='utf-8')
            return {'staged': '21'}
        return prepare

    def convert(self, **kw):
        return runner.convert_package(self.steps, self.q, 21, 18, '192.168.4.57', 'some.handle', self.root / 'stage', prepare=self.fake_prepare(**kw))

    def test_only_an_approved_package_is_converted(self):
        with self.assertRaisesRegex(ValueError, 'pending'): self.convert()
        self.assertFalse(self.staging.exists())

    def test_convert_binds_without_changing_what_was_approved(self):
        self.q.approve(21); before = self.q.reload().state['packages']['21']['fingerprint']
        self.convert()
        pkg = self.q.reload().state['packages']['21']
        self.assertEqual(('approved', before), (pkg['state'], pkg['fingerprint']))
        self.assertEqual(('window', 'reel-slot18', 18, 'c' * 64, False),
                         tuple(pkg['source'][k] for k in ('kind', 'window', 'slot', 'windowPackageSha256', 'testPackage')))
        self.assertEqual(self.item['manifestSha256'], pkg['source']['manifestSha256'])
        for flag in ('--into', '--package-id', '--content', '--content-stage'): self.assertIn(flag, self.argv)
        self.assertFalse(list(self.staging.glob('*.content.json')))     # The item handed over is not left behind.
        self.assertEqual([21], self.q.intake([{**self.item, 'account': 'acct-a18', 'runId': 'r1'}])['known'])   # Same content: no new package.
        with self.assertRaisesRegex(ValueError, 'already has a window'): self.convert()

    def test_a_window_that_differs_is_not_bound(self):
        self.q.approve(21)
        with self.assertRaisesRegex(ValueError, 'does not hold'): self.convert(caption='Another caption')
        self.assertNotIn('kind', self.q.reload().state['packages']['21']['source'])

    def test_binding_is_refused_once_planned(self):
        self.q.submit('plain', 'instagram', 'ig_reel', 'acct-a18', 'cap'); self.q.approve('plain'); self.q.plan(commit=True)
        with self.assertRaisesRegex(ValueError, 'planned'): self.q.bind_window('plain', 'reel-slot18', 18, 'c' * 64)

    def test_real_content_without_a_window_gets_no_slot(self):
        self.q.approve(21)
        plan = self.q.plan(commit=True)
        self.assertEqual([], plan['proposed']); self.assertIn('run `convert`', plan['unplaced'][0]['reason'])
        self.assertEqual([], self.q.schedule()['slots']); self.assertEqual([21], self.q.schedule()['approved'])

    def slot(self):
        self.q.approve(21); self.convert()
        slot, = [p['slot'] for p in self.q.plan(commit=True)['proposed']]; self.now[0] = slot
        fake = FakeSteps(); fake.prep = dict(PREP, packageSha256='c' * 64, caption='A real caption', slot=18)
        return fake

    def test_a_real_package_runs_a_slot_like_a_test_window(self):
        fake = self.slot()
        record = runner.SlotRunner(self.q, fake, 18, clock=lambda: self.now[0]).run_due()
        self.assertEqual('verified', record['outcome'])
        self.assertEqual(['read', 'ready', 'restore', 'start', 'ready', 'screen', 'create', 'stop', 'archive'], fake.calls)

    def test_changed_window_content_or_caption_is_not_run(self):
        for change in ({'packageSha256': 'd' * 64}, {'caption': 'Another caption'}):
            with self.subTest(change):
                self.setUp()
                fake = self.slot(); fake.prep = dict(fake.prep, **change)
                record = runner.SlotRunner(self.q, fake, 18, clock=lambda: self.now[0]).run_due()
                self.assertEqual('not_ready', record['outcome']); self.assertEqual(['read'], fake.calls)


class PrepareCommandTests(unittest.TestCase):
    def test_command_and_its_refusal(self):
        argv = runner.prepare_command('reel', 18, '192.168.4.57', 'some.handle', '/staging', python='python', folder='/farm')
        self.assertEqual(['--platform', 'reel', '--slot', '18', '--phone-ip', '192.168.4.57', '--into', '/staging', '--account', 'some.handle'], argv[2:])
        self.assertNotIn('--account', runner.prepare_command('x', 17, '192.168.4.57', None, '/staging'))
        with self.assertRaisesRegex(ValueError, 'Refused, nothing queued'):
            runner.run_prepare([sys.executable, '-c', 'raise SystemExit("Refused, nothing queued: too long")'])
        summary = runner.run_prepare([sys.executable, '-c', 'print("note"); print("{\\"staged\\": \\"reel18-abc\\"}")'])
        self.assertEqual('reel18-abc', summary['staged'])

    def test_queue_staged_enters_pending_as_a_test_package(self):
        with tempfile.TemporaryDirectory() as temp:
            staging = Path(temp) / 'windows'; steps = runner.WindowSteps(staging, folder=Path(temp))
            (staging / 'reel18-abc123').mkdir(parents=True)
            (staging / 'reel18-abc123/preparation.json').write_text(json.dumps(dict(
                PREP, testToken='abc123def456', downloadName='imouse-reel-x', backendSourceHash='h' * 64, caption='Fresh reel acceptance')), encoding='utf-8')
            pkg = runner.queue_staged(steps, ReviewQueue(Path(temp) / 'queue.json'), 'reel18-abc123', 'acct-a18')
            self.assertEqual(('pending', 'reel-slot18', True), (pkg['state'], pkg['source']['window'], pkg['source']['testPackage']))


if __name__ == '__main__':
    unittest.main()
