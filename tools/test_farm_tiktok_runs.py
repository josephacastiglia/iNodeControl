"""TikTok admission, duplicate holds, package naming and HTTP routes. No phone access."""
import http.client
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid

from farm_draft_runs import ACCOUNT   # This machine's private default account.
from farm_draft_workflow import atomic_json
from farm_drafts import DraftConflict
from farm_jobs import FarmJobs
from farm_media_transfer import MediaTransferServer
from farm_reel_runs import ReelCreationRuns
from farm_test_network import allowed_ports
from farm_tiktok_creation import COMMITTING
from farm_tiktok_layout import caption_supported
from farm_tiktok_runs import TikTokCreationRuns
from farm_video import VideoTransferPackage, download_name, NAME_ALPHABET
from imouse_social_automation import KernelSafetyError
import test_farm_http_jobs as http_jobs
from test_farm_reel_runs import CONFIG, ReelVideoFixture


class FixtureTikToks(TikTokCreationRuns):
    """Records journals as the real workflow would; never constructs a transport."""
    outcome = 'unknown_sound'
    executions = 0

    def execute(self, folder, assets, caption, package_hash, cancelled):
        self.executions += 1
        purposes = {'unknown_sound': [('home-from-profile', 'answered'), ('download-linked-file', 'answered'),
                                      ('save-video-to-photos', 'answered'), ('remove-suggested-sound', 'outcome_unknown')],
                    'pre_commit': [('home-from-profile', 'answered'), ('copy-caption', 'answered'),
                                   ('hold-download-link-release', 'not_sent')]}[self.outcome]
        result = dict(packageSha256=package_hash, state='review_required', source='candidate_phone_workflow',
                      cleanup='confirmed', evidenceExport='confirmed', savedDraftVerified=False, observations=[],
                      commands=[dict(purpose=p, state=s) for p, s in purposes],
                      actions=[dict(label=p, state=s) for p, s in purposes], error='Fixture stop.')
        atomic_json(folder/'record.json', result); return result


class TikTokVideoFixture(ReelVideoFixture):
    def stage(self, root, caption='Fresh tiktok acceptance', fmt='tt_video'):
        return super().stage(root, caption, fmt)


class TikTokServiceTests(unittest.TestCase, TikTokVideoFixture):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='farm-tiktok-test-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.videos, self.draft = self.stage(self.root)
        self.jobs = FarmJobs(journal_path=self.root/'jobs.db'); self.addCleanup(self.jobs.close)
        self.service = FixtureTikToks(self.root/'runs', self.videos, self.jobs, CONFIG)
        self.spec = dict(id=str(uuid.uuid4()), draft_id=self.draft['id'], revision=1, store_id=self.service.store_id)

    def wait(self, run_id=None):
        end = time.monotonic()+5
        while time.monotonic() < end:
            result = self.service.get(run_id or self.spec['id'])
            if result['terminal']: return result
            time.sleep(.01)
        self.fail('Fixture did not finish.')

    def test_disabled_without_isolated_configuration(self):
        service = TikTokCreationRuns(self.root/'disabled', self.videos, self.jobs)
        capability = service.capability()
        self.assertFalse(capability['enabled']); self.assertEqual('tt_video', capability['format'])
        self.assertFalse(capability['publishing']); self.assertFalse(capability['messaging'])
        self.assertIn('TikTok draft creation is disabled', capability['reason'])
        with self.assertRaises(KernelSafetyError): service.start(dict(self.spec, store_id=service.store_id))
        enabled = self.service.capability()
        self.assertTrue(enabled['enabled']); self.assertIn("@" + ACCOUNT + "'s TikTok profile", enabled['reason'])

    def test_supported_content_is_one_short_ascii_line_and_never_truncated(self):
        self.assertTrue(self.service.eligibility(self.draft['id'], 1)['eligible'])
        for caption in ('Two\nlines', 'x'*25, 'Fresh reel acceptance today'):
            with self.subTest(caption=caption):
                self.assertFalse(caption_supported(caption))
                root = self.root/str(uuid.uuid4()); root.mkdir()
                videos, draft = self.stage(root, caption)
                service = FixtureTikToks(root/'runs', videos, self.jobs, CONFIG)
                result = service.eligibility(draft['id'], 1)
                self.assertFalse(result['eligible']); self.assertFalse(result['supportedContent'])
                self.assertIn('24 characters', result['contentReason'])
                with self.assertRaises(ValueError): service.start(dict(self.spec, draft_id=draft['id'], store_id=service.store_id))

    def test_reels_are_not_tiktok_candidates_and_tiktok_is_not_a_reel(self):
        root = self.root/'reel'; root.mkdir()
        videos, draft = self.stage(root, fmt='ig_reel')
        self.assertFalse(FixtureTikToks(root/'runs', videos, self.jobs, CONFIG).eligibility(draft['id'], 1)['eligible'])
        self.assertFalse(ReelCreationRuns(self.root/'reels', self.videos, self.jobs, CONFIG).eligibility(self.draft['id'], 1)['eligible'])

    def test_unknown_sound_removal_is_retained_and_never_replayed_or_duplicated(self):
        self.service.start(self.spec); result = self.wait()
        self.assertEqual('review_required', result['state']); self.assertFalse(result['retryBeforeImportAllowed'])
        self.assertEqual(result, self.service.start(self.spec)); self.assertEqual(1, self.service.executions)
        eligibility = self.service.eligibility(self.draft['id'], 1)
        self.assertFalse(eligibility['eligible']); self.assertEqual(self.spec['id'], eligibility['previousRunId'])
        self.assertIn('TikTok request', eligibility['contentReason'])
        with self.assertRaises(DraftConflict): self.service.start(dict(self.spec, id=str(uuid.uuid4())))
        self.assertEqual(1, self.service.executions)

    def test_a_stop_before_any_import_allows_a_new_explicit_request(self):
        self.service.outcome = 'pre_commit'; self.service.start(self.spec)
        self.assertTrue(self.wait()['retryBeforeImportAllowed'])
        second = dict(self.spec, id=str(uuid.uuid4())); self.service.start(second); self.wait(second['id'])
        self.assertEqual(2, self.service.executions)

    def test_retry_rule_uses_the_tiktok_committing_actions(self):
        self.assertIn('remove-suggested-sound', COMMITTING); self.assertIn('save-tiktok-draft-once', COMMITTING)
        record = lambda purpose: dict(terminal=True, state='review_required', workflow=dict(
            source='candidate_phone_workflow', cleanup='confirmed', evidenceExport='confirmed',
            commands=[dict(purpose=purpose, state='answered')]))
        self.assertFalse(TikTokCreationRuns.retry_allowed(record('save-tiktok-draft-once')))
        self.assertTrue(TikTokCreationRuns.retry_allowed(record('copy-caption')))
        # The Reel rule does not know TikTok's actions, and the reverse.
        self.assertTrue(ReelCreationRuns.retry_allowed(record('remove-suggested-sound')))
        self.assertTrue(TikTokCreationRuns.retry_allowed(record('save-reel-draft-once')))

    def test_request_cannot_override_account_phone_endpoint_or_action(self):
        for key, value in [('account', 'another'), ('device_id', 'C241'), ('api', 'http://127.0.0.1:9913/api'), ('action', 'publish')]:
            with self.subTest(key=key), self.assertRaises(ValueError): self.service.start(dict(self.spec, **{key: value}))
        self.assertEqual(0, self.service.executions)


class TikTokPackageTests(unittest.TestCase, TikTokVideoFixture):
    def test_download_name_is_package_bound_and_ocr_safe(self):
        name = download_name('ab'*32, 'tt')
        self.assertRegex(name, '^imouse-tt-[' + NAME_ALPHABET + ']{6}$')
        self.assertEqual(name[-6:], download_name('ab'*32)[-6:]); self.assertNotEqual(name, download_name('cd'*32, 'tt'))

    def test_tiktok_page_and_http_header_use_the_unique_name(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        videos, draft = self.stage(Path(temp.name))
        package = VideoTransferPackage(videos.export(draft['id'], 1))
        self.assertRegex(package.download_name, '^imouse-tt-[a-z]{6}$')
        page = package.page('/t/x/', 'n').decode('utf-8')
        for label in ('<h1>TikTok draft</h1>', 'File ' + package.download_name, '>Download video</a>', '>Copy caption</button>',
                      'Caption copied. Verify the pasted text in TikTok.', 'Do not tap Post, Share or Your Story.', 'remove any suggested sound'):
            self.assertIn(label, page)
        self.assertNotIn('Instagram', page)
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


class TikTokHttpTests(unittest.TestCase, TikTokVideoFixture):
    setUp = http_jobs.FarmHttpJobsTests.setUp
    tearDown = http_jobs.FarmHttpJobsTests.tearDown
    request = http_jobs.FarmHttpJobsTests.request

    def test_default_backend_reports_disabled_tiktok_route_and_sends_nothing(self):
        capability = self.request('/health')[1]['tiktokCreation']
        self.assertFalse(capability['enabled']); self.assertEqual('tt_video', capability['format'])
        spec = dict(id=str(uuid.uuid4()), draft_id=str(uuid.uuid4()), revision=1, store_id=capability['storeId'])
        with http_jobs.no_kernel():
            self.assertEqual(409, self.request('/api/farm/tiktok-creations', spec)[0])
        self.assertEqual(404, self.request('/api/farm/tiktok-creations/'+spec['id'])[0])

    def test_configured_route_is_local_only_store_bound_and_never_replays(self):
        videos, draft = self.stage(self.root/'tiktok-fixture')
        service = FixtureTikToks(self.root/'tiktoks', videos, self.runtime.jobs, CONFIG)
        self.runtime.tiktok_creations = service; self.runtime.execution_mode = 'live'
        spec = dict(id=str(uuid.uuid4()), draft_id=draft['id'], revision=1, store_id=service.store_id)
        route = '/api/farm/tiktok-creations'
        with http_jobs.no_kernel():
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
            # The Reel route's store cannot stop a TikTok request.
            self.assertEqual(400, self.request(route+'/'+spec['id']+'/cancel',
                                               dict(store_id=self.runtime.reel_creations.store_id))[0])


if __name__ == '__main__':
    unittest.main()
