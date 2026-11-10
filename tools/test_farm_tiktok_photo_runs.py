"""TikTok photo admission: lane class wiring, content limits, pinned account, retry rule and execute. No phone access."""
from pathlib import Path
import tempfile
import time
import unittest
import uuid
from unittest.mock import MagicMock, patch

import farm_reel_runs
from farm_image import ImageReference
from farm_jobs import FarmJobs
from farm_tiktok_photo_creation import COMMITTING, TikTokPhotoCreationWorkflow, TikTokPhotoVerification
from farm_tiktok_photo_runs import TikTokPhotoCreationRuns
from test_farm_image import CONFIG, PHONE, stage, FakeImageWorkflow, FakeImageVerification

BOARD = 'C214'
A20 = dict(CONFIG, phone=dict(PHONE, board=BOARD, slot=20, receiver='iMouse2-20'), allowed=[BOARD], account='fixture.account')


class FakeRuns(TikTokPhotoCreationRuns):
    workflow, verifier = FakeImageWorkflow, FakeImageVerification


class TikTokPhotoRunsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='farm-tt-photo-runs-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.drafts, self.draft, _ = stage(self.root, 'tt_photo', 3, board=BOARD, caption='Fresh tiktok photo test')
        self.jobs = FarmJobs(journal_path=self.root/'jobs.db'); self.addCleanup(self.jobs.close)
        FakeImageWorkflow.calls, FakeImageVerification.calls, FakeImageWorkflow.fetch = [], [], ('01.jpg', '02.jpg', '03.jpg')

    def spec(self, service):
        return dict(id=str(uuid.uuid4()), draft_id=self.draft['id'], revision=1, store_id=service.store_id)

    def wait(self, service, run_id):
        end = time.monotonic() + 10
        while time.monotonic() < end:
            result = service.get(run_id)
            if result['terminal']: return result
            time.sleep(.02)
        self.fail('Run did not finish.')

    def test_the_route_serves_this_lane_class(self):
        import imouse_farm_server as server
        runtime = server.FarmBackendRuntime(self.root/'backend'/'farm.db', self.root/'backend'/'stage')
        self.addCleanup(runtime.transfers.close)
        self.assertEqual('tiktok_photo_creations', server.IMAGE_CREATION_ROUTES['tiktok-photo-creations'][1])
        self.assertIs(TikTokPhotoCreationRuns, type(runtime.tiktok_photo_creations))
        self.assertEqual(('tt_photo', 'create-tiktok-photo-draft', True), (TikTokPhotoCreationRuns.FORMAT,
                         TikTokPhotoCreationRuns.action_name, TikTokPhotoCreationRuns.PINNED_ACCOUNT))
        self.assertIs(TikTokPhotoCreationWorkflow, TikTokPhotoCreationRuns.workflow)
        self.assertIs(TikTokPhotoVerification, TikTokPhotoCreationRuns.verifier)

    def test_capability_is_pinned_to_the_window_account_and_phone(self):
        service = TikTokPhotoCreationRuns(self.root/'runs', self.drafts, self.jobs, A20)
        capability = service.capability()
        self.assertEqual((True, 'tt_photo', BOARD, 'fixture.account', 'fixed', False, False),
                         (capability['enabled'], capability['format'], capability['device'], capability['account'],
                          capability['accountPolicy'], capability['publishing'], capability['messaging']))
        self.assertIn('@fixture.account', capability['reason'])
        self.assertFalse(TikTokPhotoCreationRuns(self.root/'off', self.drafts, self.jobs).capability()['enabled'])

    def test_supported_content_is_this_phones_photo_package_and_one_short_line(self):
        service = TikTokPhotoCreationRuns(self.root/'runs', self.drafts, self.jobs, A20)
        result = service.eligibility(self.draft['id'], 1)
        self.assertTrue(result['eligible'], result['contentReason'])
        for caption in ('x'*25, ' leading', 'two  spaces', 'café'):
            folder = self.root/str(uuid.uuid4()); folder.mkdir()
            drafts, draft, _ = stage(folder, 'tt_photo', 2, board=BOARD, caption=caption)
            self.assertFalse(TikTokPhotoCreationRuns(folder/'runs', drafts, self.jobs, A20).eligibility(draft['id'], 1)['eligible'], caption)
        folder = self.root/'x'; folder.mkdir()
        drafts, draft, _ = stage(folder, 'x_image', 1, board=BOARD)
        self.assertFalse(TikTokPhotoCreationRuns(folder/'runs', drafts, self.jobs, A20).eligibility(draft['id'], 1)['supportedContent'])
        other = TikTokPhotoCreationRuns(self.root/'other', self.drafts, self.jobs, dict(A20, phone=dict(A20['phone'], board='724E')))
        self.assertFalse(other.supports(self.drafts.export(self.draft['id'], 1)))

    def test_retry_is_refused_once_a_photo_save_or_draft_step_was_sent(self):
        def stopped(purposes):
            return dict(terminal=True, state='review_required', workflow=dict(source='candidate_phone_workflow', cleanup='confirmed',
                        evidenceExport='confirmed', commands=[dict(purpose=p, state='answered') for p in purposes]))
        self.assertTrue(TikTokPhotoCreationRuns.retry_allowed(stopped(['home-from-profile', 'copy-caption', 'hold-slide-image-1-press'])))
        for purpose in ('save-photo-2', 'select-package-photo-1-position', 'open-tiktok-photo-editor', 'paste-exact-caption',
                        'save-tiktok-photo-draft-once'):
            self.assertFalse(TikTokPhotoCreationRuns.retry_allowed(stopped(['copy-caption', purpose])), purpose)
        self.assertTrue(all(p.startswith(('save-', 'select-', 'open-', 'paste-')) for p in COMMITTING))

    def test_execute_serves_every_slide_and_verifies_with_the_pinned_account(self):
        service = FakeRuns(self.root/'runs', self.drafts, self.jobs, A20)
        spec = self.spec(service)
        with patch.object(farm_reel_runs, 'CreationKernel', MagicMock()), patch.object(farm_reel_runs, 'ObservationStore', MagicMock()), \
                patch.object(farm_reel_runs, 'references', lambda: {}):
            service.start(spec); result = self.wait(service, spec['id'])
        self.assertEqual('verified', result['state']); self.assertTrue(result['savedDraftVerified'])
        call = FakeImageWorkflow.calls[0]
        self.assertEqual(['01.jpg', '02.jpg', '03.jpg'], call['slides']); self.assertEqual('TikTok photo draft', call['transfer_title'])
        self.assertRegex(call['package_name'], '^imouse-tp-[a-z]{6}$'); self.assertEqual('fixture.account', call['account'])
        self.assertIsInstance(call['images'], ImageReference); self.assertEqual(3, call['images'].count)
        self.assertEqual('fixture.account', FakeImageVerification.calls[0]['account'])   # Pinned, not the bound one.
        self.assertTrue(result['workflow']['mediaDelivery']['everyImageDelivered'])
        with self.assertRaises(Exception): service.start(dict(spec, id=str(uuid.uuid4())))   # Held: never a second draft.


if __name__ == '__main__':
    unittest.main()
