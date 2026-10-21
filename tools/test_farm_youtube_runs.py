"""YouTube admission, channel policy, duplicate holds, package naming, routes and the source fingerprint. No phone access."""
import http.client
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import json

from farm_creation_runs import creation_config
from farm_draft_workflow import atomic_json
from farm_drafts import DraftConflict
from farm_jobs import FarmJobs
from farm_media_transfer import MediaTransferServer
from farm_reel_runs import ReelCreationRuns
from farm_test_network import allowed_ports
from farm_tiktok_runs import TikTokCreationRuns
from farm_video import VideoTransferPackage, download_name, NAME_ALPHABET
from farm_x_runs import XCreationRuns
from farm_youtube_creation import COMMITTING
from farm_youtube_layout import caption_supported
from farm_youtube_runs import YouTubeCreationRuns
from imouse_social_automation import KernelSafetyError, DEFAULT_SAFE_TEST_DEVICE, LIVE_TEST_DEVICE_ID
import test_farm_http_jobs as http_jobs
from test_farm_reel_runs import CONFIG, ReelVideoFixture

ROOT = Path(__file__).resolve().parents[1]
# The one phone this branch's shared transport drives, and the rack phone YouTube is meant for (box slot 16).
PHONE = dict(board=DEFAULT_SAFE_TEST_DEVICE, deviceId=LIVE_TEST_DEVICE_ID, receiver='iMouse2-' + DEFAULT_SAFE_TEST_DEVICE)
SLOT16 = dict(board='F215', deviceId='02:00:00:00:00:16', receiver='iMouse2-16', slot=16)   # fixture device ID
YT_CONFIG = dict(CONFIG, phone=PHONE)


class FixtureYouTubes(YouTubeCreationRuns):
    """Records journals as the real workflow would; never constructs a transport."""
    outcome = 'unknown_select'
    executions = 0

    def execute(self, folder, assets, caption, package_hash, cancelled):
        self.executions += 1
        purposes = {'unknown_select': [('home-from-youtube', 'answered'), ('download-linked-file', 'answered'),
                                       ('save-video-to-photos', 'answered'), ('select-package-video', 'outcome_unknown')],
                    'pre_commit': [('home-from-youtube', 'answered'), ('copy-caption', 'answered'),
                                   ('hold-download-link-release', 'not_sent')]}[self.outcome]
        result = dict(packageSha256=package_hash, state='review_required', source='candidate_phone_workflow',
                      cleanup='confirmed', evidenceExport='confirmed', savedDraftVerified=False, observations=[],
                      commands=[dict(purpose=p, state=s) for p, s in purposes],
                      actions=[dict(label=p, state=s) for p, s in purposes], error='Fixture stop.')
        atomic_json(folder/'record.json', result); return result


class YouTubeVideoFixture(ReelVideoFixture):
    def stage(self, root, caption='Fresh yt acceptance', fmt='yt_short'):
        return super().stage(root, caption, fmt)


class YouTubeServiceTests(unittest.TestCase, YouTubeVideoFixture):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='farm-youtube-test-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.videos, self.draft = self.stage(self.root)
        self.jobs = FarmJobs(journal_path=self.root/'jobs.db'); self.addCleanup(self.jobs.close)
        self.service = FixtureYouTubes(self.root/'runs', self.videos, self.jobs, YT_CONFIG)
        self.spec = dict(id=str(uuid.uuid4()), draft_id=self.draft['id'], revision=1, store_id=self.service.store_id)

    def wait(self, run_id=None):
        end = time.monotonic()+5
        while time.monotonic() < end:
            result = self.service.get(run_id or self.spec['id'])
            if result['terminal']: return result
            time.sleep(.01)
        self.fail('Fixture did not finish.')

    def test_channel_policy_is_the_signed_in_channel_not_a_fixed_handle(self):
        capability = self.service.capability()
        self.assertEqual(('yt_short', None, 'first_signed_in'), (capability['format'], capability['account'], capability['accountPolicy']))
        self.assertIn('channel signed in on the configured phone', capability['reason'])
        self.assertEqual((PHONE['board'], dict(board=PHONE['board'], receiver=PHONE['receiver'])), (capability['device'], capability['phone']))
        self.assertEqual((False, False, False), (capability['publishing'], capability['messaging'], capability['automaticResume']))
        for fixed in (ReelCreationRuns, TikTokCreationRuns):
            other = fixed(self.root/fixed.__name__, self.videos, self.jobs, CONFIG).capability()
            self.assertEqual(('xs.halle.xo', 'fixed'), (other['account'], other['accountPolicy']))
        disabled = YouTubeCreationRuns(self.root/'disabled', self.videos, self.jobs).capability()
        self.assertFalse(disabled['enabled']); self.assertIn('YouTube draft creation is disabled', disabled['reason'])
        self.assertIsNone(disabled['phone'])
        with self.assertRaises(KernelSafetyError):
            service = YouTubeCreationRuns(self.root/'disabled2', self.videos, self.jobs)
            service.start(dict(self.spec, store_id=service.store_id))

    def test_the_phone_comes_from_configuration_never_a_default(self):
        # No phone in the configuration: disabled, whatever else is configured.
        bare = FixtureYouTubes(self.root/'bare', self.videos, self.jobs, CONFIG)
        self.assertFalse(bare.capability()['enabled']); self.assertIn('names no YouTube phone', bare.capability()['reason'])
        self.assertIsNone(bare.capability()['device']); self.assertFalse(bare.eligibility(self.draft['id'], 1)['eligible'])
        # The slot 16 phone: named and reported, but this backend's shared transport cannot drive it yet.
        slot16 = FixtureYouTubes(self.root/'slot16', self.videos, self.jobs, dict(CONFIG, phone=SLOT16))
        capability = slot16.capability()
        self.assertEqual(('F215', dict(board='F215', receiver='iMouse2-16', slot=16), False),
                         (capability['device'], capability['phone'], capability['enabled']))
        self.assertIn('F215 (iMouse2-16) needs the multi-phone farm', capability['reason'])
        with self.assertRaises(KernelSafetyError): slot16.start(dict(self.spec, store_id=slot16.store_id))
        self.assertEqual(0, slot16.executions + bare.executions)
        # A malformed phone block stops the backend at start.
        for phone in (dict(SLOT16, board='f215'), dict(SLOT16, deviceId='serial'), dict(SLOT16, receiver='Bedroom TV'),
                      dict(SLOT16, slot='16'), {k: v for k, v in SLOT16.items() if k != 'receiver'}, dict(SLOT16, account='x')):
            with self.subTest(phone=phone), self.assertRaises(ValueError):
                YouTubeCreationRuns(self.root/'bad', self.videos, self.jobs, dict(CONFIG, phone=phone))

    def test_a_saved_copy_must_be_for_the_configured_phone(self):
        self.assertTrue(self.service.supports(self.videos.export(self.draft['id'], 1)))
        other = FixtureYouTubes(self.root/'other', self.videos, self.jobs, dict(CONFIG, phone=dict(PHONE, board='F215')))
        # A phone whose board differs from the staged copy's: unsupported (and undrivable here as well).
        self.assertFalse(other.supports(self.videos.export(self.draft['id'], 1)))

    def test_the_creation_configuration_may_name_a_phone(self):
        path = self.root/'config.json'
        path.write_text(json.dumps(YT_CONFIG), encoding='utf-8'); self.assertEqual(YT_CONFIG, creation_config(path, 'live'))
        path.write_text(json.dumps(CONFIG), encoding='utf-8'); self.assertEqual(CONFIG, creation_config(path, 'live'))
        path.write_text(json.dumps(dict(YT_CONFIG, device='F215')), encoding='utf-8')
        with self.assertRaises(ValueError): creation_config(path, 'live')

    def test_supported_content_is_one_short_ascii_title_and_never_truncated(self):
        self.assertTrue(self.service.eligibility(self.draft['id'], 1)['eligible'])
        for caption in ('Two\nlines', 'y'*25, 'IMOUSE-VIDEO-DRAFT-TEST-20261017'):
            with self.subTest(caption=caption):
                self.assertFalse(caption_supported(caption))
                root = self.root/str(uuid.uuid4()); root.mkdir()
                videos, draft = self.stage(root, caption)
                service = FixtureYouTubes(root/'runs', videos, self.jobs, YT_CONFIG)
                result = service.eligibility(draft['id'], 1)
                self.assertFalse(result['eligible']); self.assertIn('24 characters', result['contentReason'])
                with self.assertRaises(ValueError): service.start(dict(self.spec, draft_id=draft['id'], store_id=service.store_id))
        self.assertEqual(0, self.service.executions)

    def test_formats_never_cross_routes(self):
        for fmt in ('ig_reel', 'tt_video', 'x_video'):
            with self.subTest(format=fmt):
                root = self.root/fmt; root.mkdir()
                videos, draft = self.stage(root, fmt=fmt)
                self.assertFalse(FixtureYouTubes(root/'runs', videos, self.jobs, YT_CONFIG).eligibility(draft['id'], 1)['eligible'])
        for other in (TikTokCreationRuns, XCreationRuns, ReelCreationRuns):
            self.assertFalse(other(self.root/('o'+other.__name__), self.videos, self.jobs, CONFIG).eligibility(self.draft['id'], 1)['eligible'])

    def test_unknown_selection_is_retained_and_never_replayed_or_duplicated(self):
        self.service.start(self.spec); result = self.wait()
        self.assertEqual('review_required', result['state']); self.assertFalse(result['retryBeforeImportAllowed'])
        self.assertEqual(result, self.service.start(self.spec)); self.assertEqual(1, self.service.executions)
        eligibility = self.service.eligibility(self.draft['id'], 1)
        self.assertFalse(eligibility['eligible']); self.assertIn('YouTube request', eligibility['contentReason'])
        with self.assertRaises(DraftConflict): self.service.start(dict(self.spec, id=str(uuid.uuid4())))

    def test_a_stop_before_any_import_allows_a_new_explicit_request(self):
        self.service.outcome = 'pre_commit'; self.service.start(self.spec)
        self.assertTrue(self.wait()['retryBeforeImportAllowed'])
        second = dict(self.spec, id=str(uuid.uuid4())); self.service.start(second); self.wait(second['id'])
        self.assertEqual(2, self.service.executions)

    def test_retry_rule_uses_the_youtube_committing_actions(self):
        for purpose in ('keep-whole-video', 'paste-exact-caption', 'save-youtube-draft-once'): self.assertIn(purpose, COMMITTING)
        record = lambda purpose: dict(terminal=True, state='review_required', workflow=dict(
            source='candidate_phone_workflow', cleanup='confirmed', evidenceExport='confirmed',
            commands=[dict(purpose=purpose, state='answered')]))
        self.assertFalse(YouTubeCreationRuns.retry_allowed(record('save-youtube-draft-once')))
        self.assertFalse(YouTubeCreationRuns.retry_allowed(record('keep-whole-video-position')))
        self.assertTrue(YouTubeCreationRuns.retry_allowed(record('copy-caption')))
        self.assertTrue(XCreationRuns.retry_allowed(record('keep-whole-video')))

    def test_request_cannot_override_channel_phone_endpoint_or_action(self):
        for key, value in [('account', 'another'), ('device_id', 'C241'), ('api', 'http://127.0.0.1:9913/api'), ('action', 'upload')]:
            with self.subTest(key=key), self.assertRaises(ValueError): self.service.start(dict(self.spec, **{key: value}))
        self.assertEqual(0, self.service.executions)


class YouTubePackageTests(unittest.TestCase, YouTubeVideoFixture):
    def test_download_name_is_package_bound_and_ocr_safe(self):
        name = download_name('ab'*32, 'yt')
        self.assertRegex(name, '^imouse-yt-[' + NAME_ALPHABET + ']{6}$')
        self.assertNotEqual(name, download_name('cd'*32, 'yt'))

    def test_youtube_page_and_http_header_use_the_unique_name(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        videos, draft = self.stage(Path(temp.name))
        package = VideoTransferPackage(videos.export(draft['id'], 1))
        self.assertRegex(package.download_name, '^imouse-yt-[a-z]{6}$')
        page = package.page('/t/x/', 'n').decode('utf-8')
        for label in ('<h1>YouTube draft</h1>', 'File ' + package.download_name, '>Download video</a>', '>Copy caption</button>',
                      'Caption copied. Verify the pasted text in YouTube.', 'Do not tap Upload Short, Post or Live.', 'Save draft'):
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

    def test_a_leftover_youtube_preview_is_recognized_by_every_video_route(self):
        import farm_tiktok_layout as tt
        self.assertRegex('imouse-yt-acdefh', r'imouse-((reel|tt|x|yt)-[acdefhkmnprtuvwxy]{6}|draft)')
        source = Path(tt.__file__).read_text(encoding='utf-8')
        self.assertIn("imouse-((reel|tt|x|yt)-[acdefhkmnprtuvwxy]{6}|draft)", source)


class YouTubeSourceFingerprintTests(unittest.TestCase):
    def test_server_and_launcher_pin_the_same_files_in_the_same_order(self):
        server = (ROOT/'tools/imouse_farm_server.py').read_text(encoding='utf-8')
        launcher = (ROOT/'Open Marketing Farm Candidate.ps1').read_text(encoding='utf-8')
        pinned = re.findall(r'"([^"]+)"', re.search(r'b"".join\(\(source / name\)\.read_bytes\(\) for name in \(([^)]*)\)', server).group(1))
        checked = re.findall(r"'([^']+)'", re.search(r"foreach \(\$name in @\(([^)]*)\)\)", launcher).group(1))
        self.assertEqual(pinned, checked)
        self.assertEqual(len(pinned), len(set(pinned)))
        for name in ('farm_youtube_layout.py', 'farm_youtube_controls.json', 'farm_youtube_creation.py', 'farm_youtube_runs.py'):
            self.assertIn(name, pinned)
        self.assertTrue(all((ROOT/'tools'/name).is_file() for name in pinned))
        self.assertIn("[bool]$health.youtubeCreation.enabled -and -not $DraftCreationConfig", launcher)


class YouTubeHttpTests(unittest.TestCase, YouTubeVideoFixture):
    setUp = http_jobs.FarmHttpJobsTests.setUp
    tearDown = http_jobs.FarmHttpJobsTests.tearDown
    request = http_jobs.FarmHttpJobsTests.request

    def test_default_backend_reports_disabled_youtube_route_and_sends_nothing(self):
        capability = self.request('/health')[1]['youtubeCreation']
        self.assertFalse(capability['enabled']); self.assertEqual(('yt_short', 'first_signed_in'), (capability['format'], capability['accountPolicy']))
        spec = dict(id=str(uuid.uuid4()), draft_id=str(uuid.uuid4()), revision=1, store_id=capability['storeId'])
        with patch.object(self.runtime, 'get_kernel', side_effect=AssertionError('No kernel')):
            self.assertEqual(409, self.request('/api/farm/youtube-creations', spec)[0])
        self.assertEqual(404, self.request('/api/farm/youtube-creations/'+spec['id'])[0])
        formats = {row['id']: row for row in self.request('/api/farm/capabilities')[1]['formats']}
        self.assertEqual(('/api/farm/youtube-creations', 'integrated_offline'), (formats['yt_short']['candidateEndpoint'], formats['yt_short']['level']))
        features = {row['id'] for row in self.request('/api/farm/capabilities')[1]['features']}
        self.assertIn('youtube-draft', features)

    def test_configured_route_is_local_only_store_bound_and_never_replays(self):
        videos, draft = self.stage(self.root/'yt-fixture')
        service = FixtureYouTubes(self.root/'yts', videos, self.runtime.jobs, YT_CONFIG)
        self.runtime.youtube_creations = service; self.runtime.execution_mode = 'live'
        spec = dict(id=str(uuid.uuid4()), draft_id=draft['id'], revision=1, store_id=service.store_id)
        route = '/api/farm/youtube-creations'
        with patch.object(self.runtime, 'get_kernel', side_effect=AssertionError('Default rack must not be used')):
            self.assertEqual(403, self.request(route, spec, origin='https://untrusted.invalid')[0])
            self.assertEqual(403, self.request(route+'/'+spec['id'], origin='https://untrusted.invalid')[0])
            eligible = route+'/eligibility?draft_id='+draft['id']+'&revision=1'
            self.assertTrue(self.request(eligible)[1]['eligibility']['eligible'])
            status, body = self.request(route, spec); self.assertEqual(202, status, body)
            self.assertTrue(self.runtime.jobs._jobs[spec['id']].done.wait(4))
            result = self.request(route+'/'+spec['id'])[1]['run']
            self.assertFalse(result['savedDraftVerified']); self.assertEqual(result, self.request(route, spec)[1]['run'])
            self.assertEqual(1, service.executions)
            self.assertEqual(spec['id'], self.request(route+'?draft_id='+draft['id'])[1]['runs'][0]['id'])
            self.assertEqual(409, self.request(route, {**spec, 'id': str(uuid.uuid4())})[0])
            self.assertEqual(400, self.request(route+'/'+spec['id']+'/cancel', dict(store_id=self.runtime.x_creations.store_id))[0])
            self.assertEqual(400, self.request(route, {**spec, 'device_id': 'C241'})[0])


if __name__ == '__main__':
    unittest.main()
