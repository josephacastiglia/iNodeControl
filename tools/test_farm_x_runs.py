"""X admission, account policy, duplicate holds, package naming and HTTP routes. No phone access."""
import http.client
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid

from farm_draft_workflow import atomic_json
from farm_drafts import DraftConflict
from farm_jobs import FarmJobs
from farm_media_transfer import MediaTransferServer
from farm_reel_runs import ReelCreationRuns
from farm_test_network import allowed_ports
from farm_tiktok_runs import TikTokCreationRuns
from farm_video import VideoTransferPackage, download_name, NAME_ALPHABET
from farm_x_creation import COMMITTING
from farm_x_layout import caption_supported
from farm_x_runs import XCreationRuns
from imouse_social_automation import KernelSafetyError
import test_farm_http_jobs as http_jobs
from test_farm_reel_runs import CONFIG, ReelVideoFixture


class FixtureXs(XCreationRuns):
    """Records journals as the real workflow would; never constructs a transport."""
    outcome = 'unknown_add'
    executions = 0
    arguments = None

    def execute(self, folder, assets, caption, package_hash, cancelled):
        self.executions += 1
        purposes = {'unknown_add': [('home-from-x-feed', 'answered'), ('download-linked-file', 'answered'),
                                    ('save-video-to-photos', 'answered'), ('add-package-video', 'outcome_unknown')],
                    'pre_commit': [('home-from-x-feed', 'answered'), ('copy-caption', 'answered'),
                                   ('hold-download-link-release', 'not_sent')]}[self.outcome]
        result = dict(packageSha256=package_hash, state='review_required', source='candidate_phone_workflow',
                      cleanup='confirmed', evidenceExport='confirmed', savedDraftVerified=False, observations=[],
                      commands=[dict(purpose=p, state=s) for p, s in purposes],
                      actions=[dict(label=p, state=s) for p, s in purposes], error='Fixture stop.')
        atomic_json(folder/'record.json', result); return result


class XVideoFixture(ReelVideoFixture):
    def stage(self, root, caption='Fresh x acceptance', fmt='x_video'):
        return super().stage(root, caption, fmt)


class XServiceTests(unittest.TestCase, XVideoFixture):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='farm-x-test-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.videos, self.draft = self.stage(self.root)
        self.jobs = FarmJobs(journal_path=self.root/'jobs.db'); self.addCleanup(self.jobs.close)
        self.service = FixtureXs(self.root/'runs', self.videos, self.jobs, CONFIG)
        self.spec = dict(id=str(uuid.uuid4()), draft_id=self.draft['id'], revision=1, store_id=self.service.store_id)

    def wait(self, run_id=None):
        end = time.monotonic()+5
        while time.monotonic() < end:
            result = self.service.get(run_id or self.spec['id'])
            if result['terminal']: return result
            time.sleep(.01)
        self.fail('Fixture did not finish.')

    def test_account_policy_is_the_signed_in_account_not_a_fixed_handle(self):
        capability = self.service.capability()
        self.assertEqual(('x_video', None, 'first_signed_in'), (capability['format'], capability['account'], capability['accountPolicy']))
        self.assertIn('signed in first', capability['reason'])
        for fixed in (ReelCreationRuns, TikTokCreationRuns):
            other = fixed(self.root/fixed.__name__, self.videos, self.jobs, CONFIG).capability()
            self.assertEqual(('xs.halle.xo', 'fixed'), (other['account'], other['accountPolicy']))
        disabled = XCreationRuns(self.root/'disabled', self.videos, self.jobs).capability()
        self.assertFalse(disabled['enabled']); self.assertIn('X draft creation is disabled', disabled['reason'])
        with self.assertRaises(KernelSafetyError):
            XCreationRuns(self.root/'disabled2', self.videos, self.jobs).start(dict(self.spec, store_id=XCreationRuns(self.root/'disabled2', self.videos, self.jobs).store_id))

    def test_supported_content_is_one_short_ascii_line_and_never_truncated(self):
        self.assertTrue(self.service.eligibility(self.draft['id'], 1)['eligible'])
        for caption in ('Two\nlines', 'x'*33):
            with self.subTest(caption=caption):
                self.assertFalse(caption_supported(caption))
                root = self.root/str(uuid.uuid4()); root.mkdir()
                videos, draft = self.stage(root, caption)
                service = FixtureXs(root/'runs', videos, self.jobs, CONFIG)
                result = service.eligibility(draft['id'], 1)
                self.assertFalse(result['eligible']); self.assertIn('32 characters', result['contentReason'])
                with self.assertRaises(ValueError): service.start(dict(self.spec, draft_id=draft['id'], store_id=service.store_id))

    def test_formats_never_cross_routes(self):
        for fmt in ('ig_reel', 'tt_video'):
            with self.subTest(format=fmt):
                root = self.root/fmt; root.mkdir()
                videos, draft = self.stage(root, fmt=fmt)
                self.assertFalse(FixtureXs(root/'runs', videos, self.jobs, CONFIG).eligibility(draft['id'], 1)['eligible'])
        self.assertFalse(TikTokCreationRuns(self.root/'tt', self.videos, self.jobs, CONFIG).eligibility(self.draft['id'], 1)['eligible'])

    def test_unknown_add_is_retained_and_never_replayed_or_duplicated(self):
        self.service.start(self.spec); result = self.wait()
        self.assertEqual('review_required', result['state']); self.assertFalse(result['retryBeforeImportAllowed'])
        self.assertEqual(result, self.service.start(self.spec)); self.assertEqual(1, self.service.executions)
        eligibility = self.service.eligibility(self.draft['id'], 1)
        self.assertFalse(eligibility['eligible']); self.assertIn('X request', eligibility['contentReason'])
        with self.assertRaises(DraftConflict): self.service.start(dict(self.spec, id=str(uuid.uuid4())))

    def test_a_stop_before_any_import_allows_a_new_explicit_request(self):
        self.service.outcome = 'pre_commit'; self.service.start(self.spec)
        self.assertTrue(self.wait()['retryBeforeImportAllowed'])
        second = dict(self.spec, id=str(uuid.uuid4())); self.service.start(second); self.wait(second['id'])
        self.assertEqual(2, self.service.executions)

    def test_retry_rule_uses_the_x_committing_actions(self):
        self.assertIn('add-package-video', COMMITTING); self.assertIn('save-x-draft-once', COMMITTING)
        record = lambda purpose: dict(terminal=True, state='review_required', workflow=dict(
            source='candidate_phone_workflow', cleanup='confirmed', evidenceExport='confirmed',
            commands=[dict(purpose=purpose, state='answered')]))
        self.assertFalse(XCreationRuns.retry_allowed(record('save-x-draft-once')))
        self.assertTrue(XCreationRuns.retry_allowed(record('copy-caption')))
        self.assertTrue(TikTokCreationRuns.retry_allowed(record('add-package-video')))

    def test_request_cannot_override_account_phone_endpoint_or_action(self):
        for key, value in [('account', 'another'), ('device_id', 'C241'), ('api', 'http://127.0.0.1:9913/api'), ('action', 'publish')]:
            with self.subTest(key=key), self.assertRaises(ValueError): self.service.start(dict(self.spec, **{key: value}))
        self.assertEqual(0, self.service.executions)


class XPackageTests(unittest.TestCase, XVideoFixture):
    def test_download_name_is_package_bound_and_ocr_safe(self):
        name = download_name('ab'*32, 'x')
        self.assertRegex(name, '^imouse-x-[' + NAME_ALPHABET + ']{6}$')
        self.assertNotEqual(name, download_name('cd'*32, 'x'))

    def test_x_page_and_http_header_use_the_unique_name(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        videos, draft = self.stage(Path(temp.name))
        package = VideoTransferPackage(videos.export(draft['id'], 1))
        self.assertRegex(package.download_name, '^imouse-x-[a-z]{6}$')
        page = package.page('/t/x/', 'n').decode('utf-8')
        for label in ('<h1>X draft</h1>', 'File ' + package.download_name, '>Download video</a>', '>Copy caption</button>',
                      'Caption copied. Verify the pasted text in X.', 'Do not tap Post or Discard.', 'Save to drafts'):
            self.assertIn(label, page)
        self.assertNotIn('Instagram', page); self.assertNotIn('TikTok', page)
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


class XHttpTests(unittest.TestCase, XVideoFixture):
    setUp = http_jobs.FarmHttpJobsTests.setUp
    tearDown = http_jobs.FarmHttpJobsTests.tearDown
    request = http_jobs.FarmHttpJobsTests.request

    def test_default_backend_reports_disabled_x_route_and_sends_nothing(self):
        capability = self.request('/health')[1]['xCreation']
        self.assertFalse(capability['enabled']); self.assertEqual(('x_video', 'first_signed_in'), (capability['format'], capability['accountPolicy']))
        spec = dict(id=str(uuid.uuid4()), draft_id=str(uuid.uuid4()), revision=1, store_id=capability['storeId'])
        with http_jobs.no_kernel():
            self.assertEqual(409, self.request('/api/farm/x-creations', spec)[0])
        self.assertEqual(404, self.request('/api/farm/x-creations/'+spec['id'])[0])

    def test_configured_route_is_local_only_store_bound_and_never_replays(self):
        videos, draft = self.stage(self.root/'x-fixture')
        service = FixtureXs(self.root/'xs', videos, self.runtime.jobs, CONFIG)
        self.runtime.x_creations = service; self.runtime.execution_mode = 'live'
        spec = dict(id=str(uuid.uuid4()), draft_id=draft['id'], revision=1, store_id=service.store_id)
        route = '/api/farm/x-creations'
        with http_jobs.no_kernel():
            self.assertEqual(403, self.request(route, spec, origin='https://untrusted.invalid')[0])
            eligible = route+'/eligibility?draft_id='+draft['id']+'&revision=1'
            self.assertTrue(self.request(eligible)[1]['eligibility']['eligible'])
            status, body = self.request(route, spec); self.assertEqual(202, status, body)
            self.assertTrue(self.runtime.jobs._jobs[spec['id']].done.wait(4))
            result = self.request(route+'/'+spec['id'])[1]['run']
            self.assertFalse(result['savedDraftVerified']); self.assertEqual(result, self.request(route, spec)[1]['run'])
            self.assertEqual(1, service.executions)
            self.assertEqual(409, self.request(route, {**spec, 'id': str(uuid.uuid4())})[0])
            self.assertEqual(400, self.request(route+'/'+spec['id']+'/cancel', dict(store_id=self.runtime.tiktok_creations.store_id))[0])
            self.assertEqual(400, self.request(route, {**spec, 'device_id': 'C241'})[0])


if __name__ == '__main__':
    unittest.main()
