"""Inspect a saved draft after an interruption, without repeating Save or imports.

The original request and its uncertain outcomes remain immutable. A separate,
explicit request checks what is in the library now; it never resumes old input.
"""
import hashlib
import re

from farm_carousel_inspection import InspectionStopped
from farm_draft_runs import DraftRuns, ACCOUNT
from farm_drafts import DraftConflict, identifier
from farm_draft_transport import StepKernel
from farm_draft_workflow import Workflow, references
from farm_live_verification import idle
from farm_observations import ObservationStore, classify
from imouse_social_automation import LIVE_TEST_DEVICE_ID


class RecoveryWorkflow(Workflow):
    """Open the unique saved cover, inspect all slides/caption, then release."""
    ACTIONS = {
        'inspect-open-create': 'profile_create',
        'inspect-choose-post': 'choose_post_format',
        'inspect-open-library': 'open_drafts',
        'inspect-open-draft': 'open_test_draft',
        'inspect-slide-2': 'next_slide',
        'inspect-slide-3': 'next_slide',
        'inspect-details': 'details',
    }

    def action(self, label, kind, role, index=None):
        if self.ACTIONS.get(label) != kind:
            raise InspectionStopped('Recovery inspection cannot save, import, type, or dismiss an unknown prompt.')
        return super().action(label, kind, role, index)

    def run(self):
        self.record.update(mode='inspect_saved_draft', inspectionOnly=True,
            originalOutcomeChanged=False, appRestartVerified=False, finalScreen='unknown')
        try:
            self.identity = self.runtime()
            if len(self.assets) != 3:
                raise InspectionStopped('Recovery supports the recorded three-slide candidate only.')
            if not idle(self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)):
                raise InspectionStopped('C24C is not free; inspection cannot take over a controller.')
            raw, _ = self.kernel.shot('C24C')
            initial = classify(self.store.ocr.read(raw),
                dict(platform='instagram', account=self.account, caption=self.caption), raw)
            if initial['screen'] != 'profile' or initial['accountStatus'] != 'exact_text_match':
                raise InspectionStopped('Start on the authorized Instagram profile. No input was sent.')
            self.record['cleanup'] = 'unconfirmed'; self.save(); self.owned.acquire()
            self.command('/mouse/reset', purpose='initial_pointer_reset')
            self.action('inspect-open-create', 'profile_create', 'profile')
            self.action('inspect-choose-post', 'choose_post_format', 'create')
            self.action('inspect-open-library', 'open_drafts', 'picker')
            self.action('inspect-open-draft', 'open_test_draft', 'library')
            for index in (1, 2):
                self.action('inspect-slide-' + str(index + 1), 'next_slide', 'editor', index)
            self.action('inspect-details', 'details', 'editor', 3)
            self.observe('details')  # Exact complete caption and first media, after Next.
            self.record.update(state='validation_passed', savedDraftVerified=True,
                finalScreen='carousel_details', accountCoverage='exact_profile_before_inspection',
                meaning='A unique matching draft was opened from the library; all three slides and the full caption matched. '
                        'No Save, import, typing, publishing or messaging was sent. The original outcome stays unchanged. '
                        'This checks current saved content, not an app restart or continuous account history.')
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__ + ': ' + str(error))
        finally:
            self.finish()
        return self.record


class RecoveryRuns(DraftRuns):
    action_name = 'inspect-saved-draft'
    SOURCE_FIELDS = {'creation_id', 'creation_store_id', 'creation_record_sha256'}

    def __init__(self, folder, drafts, jobs, creations):
        self.creations = creations
        super().__init__(folder, drafts, jobs, creations.config)

    @staticmethod
    def validate_request(spec):
        if not isinstance(spec, dict) or set(spec) != {'id', 'draft_id', 'revision', 'store_id'} | RecoveryRuns.SOURCE_FIELDS:
            raise ValueError('Inspection needs the retained creation, its store and record hash; actions cannot be supplied.')
        checked = DraftRuns.validate_request({k: v for k, v in spec.items() if k not in RecoveryRuns.SOURCE_FIELDS})
        for name in ('creation_id', 'creation_store_id'): checked[name] = identifier(spec[name])
        digest = spec['creation_record_sha256']
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('The original creation record hash is missing.')
        checked['creation_record_sha256'] = digest
        if checked['id'] == checked['creation_id']:
            raise ValueError('Inspection must use a separate request ID.')
        return checked

    def capability(self):
        return dict(version=1, storeId=self.store_id, enabled=self.config is not None,
            device='C24C', account=ACCOUNT, candidateOnly=True, inspectionOnly=True,
            publishing=False, messaging=False, desktopControl=False, automaticResume=False,
            integratedLiveValidated=False,
            reason='Checks a possibly saved three-slide draft without repeating Save, imports or caption entry. '
                   'Start on @' + ACCOUNT + "'s profile. Finishes on the draft details screen; no app-restart claim."
                   if self.config else 'Saved-draft inspection needs the explicit isolated creation candidate configuration.')

    def source(self, creation_id):
        value = self.creations.get(identifier(creation_id))  # Local journal/evidence only.
        spec, package, digest = self.creations.row(creation_id)
        workflow = value.get('workflow') or {}
        saves = [c for c in workflow.get('commands', [])
                 if c.get('purpose') == 'prepared-save-once' and c.get('state') in ('answered', 'outcome_unknown')]
        if (not value['terminal'] or workflow.get('source') != 'candidate_phone_workflow'
                or workflow.get('mode') != 'create_new_draft' or workflow.get('account') != ACCOUNT
                or len(saves) != 1 or not self.creations.supports(package)):
            raise DraftConflict('No terminal creation with a started Instagram Save is recorded. Inspect the original result; no action will be replayed.')
        path = self.creations.folder / creation_id / 'record.json'
        proof = dict(creationId=creation_id, creationStoreId=self.creations.store_id,
            creationRecordSha256=hashlib.sha256(path.read_bytes()).hexdigest(), packageSha256=digest,
            originalState=value['state'], originalSaveOutcome=saves[0]['state'],
            originalCleanup=workflow.get('cleanup', 'unconfirmed'), originalOutcomeChanged=False)
        return spec, package, proof

    def eligibility(self, creation_id):
        result = dict(**self.capability(), eligible=False, creationId=identifier(creation_id))
        try:
            spec, _, proof = self.source(result['creationId'])
        except DraftConflict as error:
            result['contentReason'] = str(error)
            return result
        result.update(eligible=self.config is not None, draftId=spec['draft_id'], revision=spec['revision'],
            sourceProof=proof,
            contentReason='A separate inspection can check the saved library. It cannot finish an unsaved editor or repeat an uncertain Save.')
        return result

    def package_for_request(self, spec):
        original, package, proof = self.source(spec['creation_id'])
        if (spec['creation_store_id'] != proof['creationStoreId']
                or spec['creation_record_sha256'] != proof['creationRecordSha256']
                or spec['draft_id'] != original['draft_id'] or spec['revision'] != original['revision']):
            raise DraftConflict('Original creation, revision or evidence changed. Nothing was started.')
        # Use the admitted immutable package, even if the local editor changed.
        return package

    def supports(self, package):
        return self.creations.supports(package)

    def execute(self, folder, assets, caption, package_hash, cancelled):
        spec, _, _ = self.row(folder.name)
        self.package_for_request(spec)  # Recheck before constructing a transport.
        _, _, proof = self.source(spec['creation_id'])
        workflow = RecoveryWorkflow(folder, StepKernel(self.config['api']),
            ObservationStore(folder / 'observations.sqlite3'), assets, caption, references(),
            self.config['kernelSha256'], self.config['expectedUid'], account=ACCOUNT,
            package_hash=package_hash, cancelled=cancelled)
        workflow.record['sourceCreation'] = proof
        workflow.save()
        return workflow.run()

    def get(self, run_id):
        value = super().get(run_id)
        value.update(inspectionOnly=True, originalOutcomeChanged=False, appRestartVerified=False)
        workflow = value.get('workflow')
        if workflow:
            proof, spec = workflow.get('sourceCreation', {}), value['request']
            if (proof.get('creationId') != spec['creation_id']
                    or proof.get('creationStoreId') != spec['creation_store_id']
                    or proof.get('creationRecordSha256') != spec['creation_record_sha256']
                    or proof.get('packageSha256') != value['packageSha256']):
                raise ValueError('Inspection lost its binding to the original creation evidence.')
        if value['savedDraftVerified']:
            if workflow.get('mode') != 'inspect_saved_draft' or workflow.get('inspectionOnly') is not True:
                raise ValueError('Inspection result is missing its restricted workflow evidence.')
            value['reason'] = 'Matching saved slides and caption observed. The original request is unchanged. The phone remains on draft details.'
        return value
