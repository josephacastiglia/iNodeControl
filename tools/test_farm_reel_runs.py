"""Reel admission, duplicate holds, package naming and HTTP routes. No phone access."""
import hashlib
import http.client
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from farm_draft_workflow import atomic_json
from farm_drafts import DraftConflict
from farm_jobs import FarmJobs
from farm_media_transfer import MediaTransferServer
from farm_reel_layout import caption_supported
from farm_reel_runs import ReelCreationRuns, reel_content
from farm_test_network import allowed_ports
from farm_video import VideoDrafts, VideoTransferPackage, download_name, run_media, NAME_ALPHABET, FORMATS, PAGES
from imouse_social_automation import KernelSafetyError
import test_farm_http_jobs as http_jobs

CONFIG = dict(version=1, api='http://127.0.0.1:9916/api', kernelSha256='a'*64, expectedUid='test-only',
              mediaBind='192.168.50.2', mediaClient='192.168.50.3', mediaPort=9917)


class FixtureReels(ReelCreationRuns):
    """Records journals as the real workflow would; never constructs a transport."""
    outcome = 'unknown_import'
    executions = 0

    def execute(self, folder, assets, caption, package_hash, cancelled):
        self.executions += 1
        purposes = {'unknown_import': [('home-from-profile', 'answered'), ('download-linked-file', 'outcome_unknown')],
                    'pre_commit': [('home-from-profile', 'answered'), ('copy-caption', 'answered'), ('hold-download-link-release', 'not_sent')],
                    'not_started': []}[self.outcome]
        result = dict(packageSha256=package_hash, state='review_required', source='candidate_phone_workflow',
                      cleanup='confirmed', evidenceExport='confirmed', savedDraftVerified=False, observations=[],
                      commands=[dict(purpose=p, state=s) for p, s in purposes],
                      actions=[dict(label=p, state=s) for p, s in purposes], error='Fixture stop.')
        atomic_json(folder/'record.json', result); return result


class ReelVideoFixture:
    @classmethod
    def encoded_reel(cls):
        if not hasattr(ReelVideoFixture, '_raw'):
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory)/'source.mp4'
                run_media('ffmpeg', ['-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'testsrc2=size=720x1280:rate=15:duration=3',
                                     '-pix_fmt', 'yuv420p', '-c:v', 'libx264', str(source)])
                ReelVideoFixture._raw = source.read_bytes()
        return ReelVideoFixture._raw

    def stage(self, root, caption='Fresh reel acceptance', fmt='ig_reel'):
        stage = root/'stage/C24C'; stage.mkdir(parents=True, exist_ok=True)
        raw = self.encoded_reel(); (stage/'reel.mp4').write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        (stage/'manifest.json').write_text(json.dumps({'deviceId': 'C24C', 'assets': [
            {'url': '/stage/C24C/reel.mp4', 'sha256': digest, 'bytes': len(raw)}]}), encoding='utf-8')
        videos = VideoDrafts(root/'videos.db', root/'stage')
        draft = videos.create(dict(id=str(uuid.uuid4()), device_id='C24C', format=fmt, name='reel.mp4', sha256=digest,
                                   title='Reel acceptance', caption=caption))
        return videos, draft


class ReelServiceTests(unittest.TestCase, ReelVideoFixture):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='farm-reel-test-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.videos, self.draft = self.stage(self.root)
        self.jobs = FarmJobs(journal_path=self.root/'jobs.db'); self.addCleanup(self.jobs.close)
        self.service = FixtureReels(self.root/'runs', self.videos, self.jobs, CONFIG)
        self.spec = dict(id=str(uuid.uuid4()), draft_id=self.draft['id'], revision=1, store_id=self.service.store_id)

    def wait(self, run_id=None):
        end = time.monotonic()+5
        while time.monotonic() < end:
            result = self.service.get(run_id or self.spec['id'])
            if result['terminal']: return result
            time.sleep(.01)
        self.fail('Fixture did not finish.')

    def test_disabled_without_isolated_configuration(self):
        service = ReelCreationRuns(self.root/'disabled', self.videos, self.jobs)
        capability = service.capability()
        self.assertFalse(capability['enabled']); self.assertFalse(capability['publishing']); self.assertFalse(capability['messaging'])
        with self.assertRaises(KernelSafetyError): service.start(dict(self.spec, store_id=service.store_id))
        self.assertEqual([], service.list(self.draft['id']))

    def test_supported_content_is_one_short_ascii_line_and_never_truncated(self):
        self.assertTrue(self.service.eligibility(self.draft['id'], 1)['eligible'])
        for caption in ('Two\nlines', 'x'*41, 'double  space', ' leading', 'café'):
            self.assertFalse(caption_supported(caption), caption)
        for caption in ('Two\nlines', 'x'*41):
            with self.subTest(caption=caption):
                root = self.root/str(uuid.uuid4()); root.mkdir()
                videos, draft = self.stage(root, caption)
                service = FixtureReels(root/'runs', videos, self.jobs, CONFIG)
                result = service.eligibility(draft['id'], 1)
                self.assertFalse(result['eligible']); self.assertFalse(result['supportedContent'])
                self.assertEqual(caption, videos.get(draft['id'])['caption'])
                with self.assertRaises(ValueError): service.start(dict(self.spec, draft_id=draft['id'], store_id=service.store_id))

    def test_other_formats_are_not_reel_candidates(self):
        root = self.root/'tiktok'; root.mkdir()
        videos, draft = self.stage(root, fmt='tt_video')
        self.assertFalse(FixtureReels(root/'runs', videos, self.jobs, CONFIG).eligibility(draft['id'], 1)['eligible'])

    def test_unknown_import_is_retained_and_never_replayed_or_duplicated(self):
        self.service.start(self.spec); result = self.wait()
        self.assertEqual('review_required', result['state']); self.assertFalse(result['retryBeforeImportAllowed'])
        self.assertEqual(result, self.service.start(self.spec)); self.assertEqual(1, self.service.executions)
        restarted = FixtureReels(self.root/'runs', self.videos, self.jobs, CONFIG)
        restarted.start(self.spec); self.assertEqual(0, restarted.executions)
        eligibility = self.service.eligibility(self.draft['id'], 1)
        self.assertFalse(eligibility['eligible']); self.assertEqual(self.spec['id'], eligibility['previousRunId'])
        with self.assertRaises(DraftConflict): self.service.start(dict(self.spec, id=str(uuid.uuid4())))
        self.assertEqual(1, self.service.executions)

    def test_a_stop_before_any_import_allows_a_new_explicit_request(self):
        self.service.outcome = 'pre_commit'; self.service.start(self.spec)
        self.assertTrue(self.wait()['retryBeforeImportAllowed'])
        self.assertTrue(self.service.eligibility(self.draft['id'], 1)['eligible'])
        second = dict(self.spec, id=str(uuid.uuid4())); self.service.start(second); self.wait(second['id'])
        self.assertEqual(2, self.service.executions)

    def test_request_cannot_override_account_phone_endpoint_or_action(self):
        for key, value in [('account', 'another'), ('device_id', 'C241'), ('api', 'http://127.0.0.1:9913/api'), ('action', 'publish')]:
            with self.subTest(key=key), self.assertRaises(ValueError): self.service.start(dict(self.spec, **{key: value}))
        self.assertEqual(0, self.service.executions)

    def test_cancel_before_admission_never_executes(self):
        self.service.cancel(self.spec['id']); self.service.start(self.spec); result = self.wait()
        self.assertEqual(0, self.service.executions); self.assertFalse(result['savedDraftVerified'])

    def test_content_identity_covers_video_and_caption(self):
        package = self.videos.export(self.draft['id'], 1)
        manifest, caption, content = reel_content(package)
        self.assertEqual('ig_reel', manifest['format']); self.assertEqual('Fresh reel acceptance', caption)
        self.assertRegex(content, '^[0-9a-f]{64}$')


class ReelPackageTests(unittest.TestCase, ReelVideoFixture):
    def test_download_name_is_package_bound_and_ocr_safe(self):
        name = download_name('ab'*32)
        self.assertRegex(name, '^imouse-reel-[' + NAME_ALPHABET + ']{6}$')
        self.assertEqual(name, download_name('ab'*32)); self.assertNotEqual(name, download_name('cd'*32))
        self.assertFalse(set('ilobgqjz') & set(NAME_ALPHABET))

    def test_reel_page_and_http_header_use_the_unique_name(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        videos, draft = self.stage(Path(temp.name))
        package = VideoTransferPackage(videos.export(draft['id'], 1))
        self.assertRegex(package.download_name, '^imouse-reel-[a-z]{6}$')
        page = package.page('/t/x/', 'n').decode('utf-8')
        for label in ('<h1>Reel draft</h1>', 'File ' + package.download_name, '>Download video</a>', '>Copy caption</button>',
                      'Caption copied. Verify the pasted text in Instagram.', 'Do not tap Share.'):
            self.assertIn(label, page)
        self.assertNotRegex(page, r'text-decoration:\s*underline')
        server = MediaTransferServer(package, '127.0.0.1', 0, '127.0.0.1', minutes=1)
        allowed_ports.add(server.server_port)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()
        try:
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            connection.request('HEAD', server.prefix + 'video.mp4'); response = connection.getresponse(); response.read()
            self.assertEqual(f'inline; filename="{package.download_name}.mp4"', response.headers['Content-Disposition'])
            connection.close()
        finally:
            server.shutdown(); server.close_clients(); server.server_close(); thread.join(2); allowed_ports.discard(server.server_port)

    def test_every_video_format_has_its_own_named_page(self):
        # TikTok, X and YouTube have their own automated pages too (test_farm_tiktok_runs, test_farm_x_runs,
        # test_farm_youtube_runs); no video format is left on the supervised 'imouse-draft' page.
        self.assertEqual(set(FORMATS), set(PAGES))
        self.assertEqual(len(PAGES), len({page['prefix'] for page in PAGES.values()}))


class ReelHttpTests(unittest.TestCase, ReelVideoFixture):
    setUp = http_jobs.FarmHttpJobsTests.setUp
    tearDown = http_jobs.FarmHttpJobsTests.tearDown
    request = http_jobs.FarmHttpJobsTests.request

    def test_default_backend_reports_disabled_reel_route_and_sends_nothing(self):
        capability = self.request('/health')[1]['reelCreation']
        self.assertFalse(capability['enabled']); self.assertEqual('ig_reel', capability['format'])
        spec = dict(id=str(uuid.uuid4()), draft_id=str(uuid.uuid4()), revision=1, store_id=capability['storeId'])
        with patch.object(self.runtime, 'get_kernel', side_effect=AssertionError('No kernel')):
            self.assertEqual(409, self.request('/api/farm/reel-creations', spec)[0])
        self.assertEqual(404, self.request('/api/farm/reel-creations/'+spec['id'])[0])
        formats = {row['id']: row for row in self.request('/api/farm/capabilities')[1]['formats']}
        self.assertEqual('/api/farm/reel-creations', formats['ig_reel']['candidateEndpoint'])

    def test_configured_route_is_local_only_store_bound_and_never_replays(self):
        videos, draft = self.stage(self.root/'reel-fixture')
        service = FixtureReels(self.root/'reels', videos, self.runtime.jobs, CONFIG)
        self.runtime.reel_creations = service; self.runtime.execution_mode = 'live'
        spec = dict(id=str(uuid.uuid4()), draft_id=draft['id'], revision=1, store_id=service.store_id)
        route = '/api/farm/reel-creations'
        with patch.object(self.runtime, 'get_kernel', side_effect=AssertionError('Default rack must not be used')):
            self.assertEqual(403, self.request(route, spec, origin='https://untrusted.invalid')[0])
            eligible = route+'/eligibility?draft_id='+draft['id']+'&revision=1'
            self.assertTrue(self.request(eligible)[1]['eligibility']['eligible'])
            self.assertEqual(403, self.request(eligible, origin='https://untrusted.invalid')[0])
            status, body = self.request(route, spec); self.assertEqual(202, status, body)
            self.assertTrue(self.runtime.jobs._jobs[spec['id']].done.wait(4))
            result = self.request(route+'/'+spec['id'])[1]['run']
            self.assertFalse(result['savedDraftVerified']); self.assertEqual(result, self.request(route, spec)[1]['run'])
            self.assertEqual(1, service.executions)
            self.assertEqual(409, self.request(route, {**spec, 'id': str(uuid.uuid4())})[0])
            self.assertEqual(400, self.request(route+'/'+spec['id']+'/cancel', dict(store_id=str(uuid.uuid4())))[0])
            self.assertEqual(400, self.request(route, {**spec, 'device_id': 'C241'})[0])


if __name__ == '__main__':
    unittest.main()
