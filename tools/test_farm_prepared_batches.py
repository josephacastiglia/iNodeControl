"""Exact local preparation outputs; no rack, desktop, transfer or publisher."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

from PIL import Image
from farm_drafts import CarouselDrafts, DraftConflict
from farm_preparation_schedule import PreparationSchedule
import farm_test_network as network
import imouse_farm_server as server


class PreparedBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.enterContext(patch('urllib.request.urlopen', side_effect=AssertionError('Network forbidden')))
        self.outside = network.mark()
        self.runtime = server.FarmBackendRuntime(self.root / 'data/farm.db', self.root / 'stage')
        self.schedule = self.runtime.preparation
        self.addCleanup(self.schedule.close)
        self.now = 1000.0; self.schedule.clock = lambda: self.now
        self.request = dict(id=str(uuid.uuid4()), device_id='C24C', action='create-content', interval_minutes=60, max_runs=2)

    def batch(self, caption='First batch', colors=('red', 'green'), **changes):
        generation = uuid.uuid4().hex
        folder = self.root / 'stage/C24C'; folder.mkdir(parents=True, exist_ok=True)
        assets = []
        for index, color in enumerate(colors):
            out = io.BytesIO(); Image.new('RGB', (40, 50), color).save(out, 'PNG')
            name = f'{generation}-{index}.png'; raw = out.getvalue(); (folder / name).write_bytes(raw)
            assets.append(dict(url='/stage/C24C/' + name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw)))
        manifest = dict(deviceId='C24C', generation=generation, caption=caption, assets=assets)
        manifest.update(changes)
        raw = json.dumps(manifest).encode(); checksum = hashlib.sha256(raw).hexdigest()
        (folder / f'manifest_{generation}.json').write_bytes(raw)
        (folder / 'manifest.json').write_bytes(raw)
        item = dict(id=1, platform='instagram', format='ig_carousel', caption=caption,
                    stagedFiles=[a['url'].rsplit('/', 1)[-1] for a in assets], generation=generation,
                    manifest=f'/stage/C24C/manifest_{generation}.json', manifestSha256=checksum)
        return item, manifest

    def snapshot(self, item, draft_id=None):
        return self.runtime.drafts.create(draft_id or str(uuid.uuid4()), 'Prepared', True,
                                         source_generation=item['generation'], manifest_sha256=item['manifestSha256'])

    def video_batch(self, caption='Original video copy'):
        item, manifest = self.batch(caption)
        name = f"video_{item['generation']}.mp4"; raw = b'local-video-source-' + item['generation'].encode()
        (self.root / 'stage/C24C' / name).write_bytes(raw)
        manifest['assets'].append(dict(url='/stage/C24C/' + name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        encoded = json.dumps(manifest).encode(); item['manifestSha256'] = hashlib.sha256(encoded).hexdigest()
        for path in ('manifest.json', f"manifest_{item['generation']}.json"):
            (self.root / 'stage/C24C' / path).write_bytes(encoded)
        item['stagedFiles'].append(name)
        return item, raw

    def test_historical_video_can_be_prepared_after_another_batch_and_recovered_without_source(self):
        item, raw = self.video_batch(); self.video_batch('Latest copy')
        videos = self.runtime.videos; sources = videos.sources(item['generation'], item['manifestSha256'])
        self.assertEqual('Original video copy', sources[0]['caption'])
        request = dict(id=str(uuid.uuid4()), device_id='C24C', format='tt_video', title='Batch video', caption=sources[0]['caption'],
                       name=sources[0]['name'], sha256=sources[0]['sha256'], source_generation=item['generation'], manifest_sha256=item['manifestSha256'])
        with patch('farm_video.normalize_video', return_value=(b'encoded-video', {'seconds': 3})) as encode:
            saved = videos.create(request); encode.assert_called_once_with(raw)
            self.assertEqual(item['generation'], saved['sourceGeneration']); self.assertFalse(saved['savedInApp'])
            package = videos.export(saved['id'], 1)
            for path in (self.root / 'stage/C24C').iterdir(): path.unlink()
            self.assertEqual(saved, videos.create(request)); self.assertEqual(1, encode.call_count)
            with patch('zipfile.time.localtime', return_value=(2030, 1, 1, 12, 0, 0, 0, 0, 0)):
                self.assertEqual(package, videos.export(saved['id'], 1))

    def test_historical_video_refuses_missing_manifest_or_changed_source_without_latest_fallback(self):
        item, _ = self.video_batch(); self.video_batch('Latest copy')
        sources = self.runtime.videos.sources(item['generation'], item['manifestSha256'])
        request = dict(id=str(uuid.uuid4()), device_id='C24C', format='tt_video', title='Batch video', caption='Original',
                       name=sources[0]['name'], sha256=sources[0]['sha256'], source_generation=item['generation'], manifest_sha256=item['manifestSha256'])
        (self.root / 'stage/C24C' / sources[0]['name']).write_bytes(b'damaged')
        with self.assertRaises(ValueError): self.runtime.videos.create(request)
        (self.root / 'stage/C24C' / f"manifest_{item['generation']}.json").unlink()
        with self.assertRaises(ValueError): self.runtime.videos.sources(item['generation'], item['manifestSha256'])
        self.assertEqual([], self.runtime.videos.list())

    def test_exact_batch_opens_after_latest_changes_and_survives_source_deletion(self):
        first, _ = self.batch(); second, _ = self.batch('Second batch', ('blue', 'yellow'))
        draft = self.snapshot(first)
        self.assertEqual('First batch', draft['caption'])
        self.assertEqual(first['generation'], draft['sourceGeneration'])
        self.assertNotEqual(second['generation'], draft['sourceGeneration'])
        before = self.runtime.drafts.export(draft['id'], draft['revision'])
        for path in (self.root / 'stage/C24C').iterdir(): path.unlink()
        restarted = CarouselDrafts(self.runtime.drafts.database, self.runtime.stage_root)
        self.assertEqual(draft, restarted.create(draft['id'], 'Prepared', True,
                         source_generation=first['generation'], manifest_sha256=first['manifestSha256']))
        with patch('zipfile.time.localtime', return_value=(2030, 1, 1, 12, 0, 0, 0, 0, 0)):
            self.assertEqual(before, restarted.export(draft['id'], draft['revision']))

    def test_reply_recovery_does_not_overwrite_later_local_edits(self):
        first, _ = self.batch(); draft = self.snapshot(first)
        edited = self.runtime.drafts.save(draft['id'], draft['revision'], 'Edited title', 'Keep my edits', list(reversed(draft['slideIds'])))
        self.assertEqual(edited, self.snapshot(first, draft['id']))
        second, _ = self.batch('Other batch')
        with self.assertRaises(DraftConflict): self.snapshot(second, draft['id'])
        self.assertEqual(1, len(self.runtime.drafts.list()))

    def test_changed_missing_or_foreign_manifest_never_falls_back_to_latest(self):
        first, _ = self.batch(); path = self.root / 'stage/C24C' / f"manifest_{first['generation']}.json"
        original = path.read_bytes(); self.batch('Latest')
        for raw in (None, b'{}'):
            if raw is None: path.unlink()
            else: path.write_bytes(raw)
            with self.assertRaises(ValueError): self.snapshot(first)
        path.write_bytes(original)
        for changes in (dict(deviceId='C241'), dict(generation='0' * 32)):
            item, _ = self.batch(**changes)
            with self.assertRaises(ValueError): self.snapshot(item)
        self.assertEqual([], self.runtime.drafts.list())

    def test_partial_or_ambiguous_images_roll_back_all_assets(self):
        for colors in (('red',), ('red', 'red')):
            item, _ = self.batch(colors=colors)
            with self.assertRaises(ValueError): self.snapshot(item)
        item, manifest = self.batch()
        (self.root / 'stage/C24C' / manifest['assets'][1]['url'].rsplit('/', 1)[-1]).write_bytes(b'damaged')
        with self.assertRaises(ValueError): self.snapshot(item)
        with self.runtime.drafts.connection() as db:
            self.assertEqual(0, db.execute('SELECT count(*) FROM carousel_assets').fetchone()[0])
            self.assertEqual(0, db.execute('SELECT count(*) FROM carousel_drafts').fetchone()[0])

    def test_bad_generation_paths_and_incomplete_identity_are_refused(self):
        item, _ = self.batch()
        for generation, digest in (('../manifest', item['manifestSha256']), ('bad', item['manifestSha256']),
                                    (item['generation'], None), (None, item['manifestSha256'])):
            with self.assertRaises(ValueError):
                self.runtime.drafts.create(str(uuid.uuid4()), 'Prepared', True, source_generation=generation, manifest_sha256=digest)

    def test_schedule_retains_two_distinct_drafts_and_reading_does_not_repeat_work(self):
        first, _ = self.batch(); second, _ = self.batch('Later batch', ('blue', 'yellow'))
        with patch.object(self.runtime.factory, 'generate_daily_slate_for_device', side_effect=[[first], [second]]) as render:
            self.schedule.configure(self.request); self.schedule.tick(); self.now += 3600; self.schedule.tick()
            status = self.schedule.status(); self.assertEqual('complete', status['config']['state'])
            records = [run['contentItems'][0] for run in status['runs']]
            self.assertEqual({'First batch', 'Later batch'}, {self.runtime.drafts.get(row['localDraft']['id'])['caption'] for row in records})
            self.assertEqual(2, len({row['localDraft']['id'] for row in records}))
            restarted = PreparationSchedule(self.schedule.path, lambda: self.fail('No render on restart'),
                                            lambda: {}, threading.Lock(), clock=lambda: self.now)
            restarted.tick(); self.assertEqual(status['runs'], restarted.status()['runs']); self.assertEqual(2, render.call_count)
        self.assertEqual([], network.since(self.outside))

    def test_snapshot_failure_holds_schedule_without_retry_or_discarding_previous_draft(self):
        first, _ = self.batch(); second, manifest = self.batch('Broken batch')
        with patch.object(self.runtime.factory, 'generate_daily_slate_for_device', side_effect=[[first], [second]]) as render:
            self.schedule.configure(self.request); self.schedule.tick()
            (self.root / 'stage/C24C' / manifest['assets'][1]['url'].rsplit('/', 1)[-1]).write_bytes(b'bad')
            self.now += 3600; self.schedule.tick(); self.now += 3600; self.schedule.tick()
            state = self.schedule.status()
            self.assertEqual('needs_review', state['config']['state']); self.assertEqual('failed', state['runs'][0]['state'])
            self.assertEqual(2, render.call_count); self.assertEqual(1, len(self.runtime.drafts.list()))
            saved = state['runs'][1]['contentItems'][0]['localDraft']
            self.assertEqual('First batch', self.runtime.drafts.get(saved['id'])['caption'])

    def test_missing_or_mixed_batch_identity_cannot_claim_preparation_success(self):
        first, _ = self.batch(); second, _ = self.batch('Other')
        for rows in ([{**first, 'generation': None}], [first, {**second, 'format': 'ig_reel'}]):
            with patch.object(self.runtime.factory, 'generate_daily_slate_for_device', return_value=rows), self.assertRaises(ValueError):
                self.runtime.prepare_local_content('C24C')
        self.assertEqual([], self.runtime.drafts.list())

    def test_placeholder_output_cannot_be_recorded_as_success(self):
        for rows in ([{}], [{'id': True}], ['not a record']):
            self.schedule.configure({**self.request, 'id': str(uuid.uuid4())}); self.schedule.prepare = lambda: rows
            self.schedule.tick()
            self.assertEqual('failed', self.schedule.status()['runs'][0]['state'])
            self.assertFalse(self.schedule.status()['config']['enabled'])


if __name__ == '__main__': unittest.main()
