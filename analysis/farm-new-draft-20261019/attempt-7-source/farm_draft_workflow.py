"""Candidate save/reopen sequence extracted from the two-run C24C diagnostic.

The service supplies an immutable saved draft and an explicit test-kernel identity.
No recovery replay, arbitrary actions, keyboard or publishing are exposed here.
"""
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid

import numpy as np
from PIL import Image

from farm_draft_transport import allowed_tap
from farm_carousel_inspection import OwnedCaptureRun, InspectionStopped
from farm_draft_media import media_comparison
from farm_draft_rehearsal import save_prompt
from farm_draft_verification import caption_comparison, library_candidate, account_history
from farm_frame_evidence import MAX_AGE_MS, capture_settled
from farm_live_verification import validate_runtime, idle
from farm_observations import classify
from farm_screen_layout import pixels, words_at, line_at, create_menu_controls, picker_controls, next_label
from farm_transitions import wait_for_transition, screen_ready
from imouse_social_automation import LIVE_TEST_DEVICE_ID

# Full save/reopen has two complete slide/caption passes and final restoration.
# Fixed candidate policy, never a request-controlled timeout.
WORKFLOW_BUDGET_SECONDS = 120
PROMPT_REFRESH_SECONDS = 4


class DecisionExpired(InspectionStopped):
    """A once-valid decision aged locally, before transport, in the same run."""


def prompt_context(value):
    return (value.get('observerSession'), value.get('resolvedDeviceId'), value.get('receiverPid'),
            value.get('inputGeneration'), value.get('frameEvidence', {}).get('session'),
            value.get('ownershipEvidence', {}).get('runId'), value.get('source'),
            value.get('expected', {}).get('account'), value.get('expected', {}).get('caption'))


def unchanged_save_prompt(before, first, after, second):
    """Require a new delivery of the same exact prompt and protected content."""
    context = prompt_context(before)
    if (any(part is None for part in context) or context != prompt_context(after)
            or before['id'] == after['id']
            or after['frameEvidence']['sequence'] <= before['frameEvidence']['sequence']
            or not save_prompt(before['text']) or not save_prompt(after['text'])):
        raise InspectionStopped('Save prompt refresh changed context or did not produce independent evidence.')
    # The status bar clock may change. Keep the entire modal, background media,
    # caption area and controls protected; a permission/account dialog is not
    # a reason to move the target or to click through it.
    delta = np.abs(pixels(first, exact=True)[65:].astype(float) - pixels(second, exact=True)[65:].astype(float)) / 255
    if delta.mean() > .002 or (delta.max(axis=2) > 35/255).mean() > .005:
        raise InspectionStopped('Protected prompt content changed; manual review is required.')


def atomic_json(path, value):
    temporary = path.with_suffix('.writing')
    with temporary.open('w', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.flush(); os.fsync(output.fileno())
    # Windows readers do not normally share deletion. A status read can keep
    # the old journal open for a moment and refuse this atomic replacement.
    # Retry only that local file operation, never the associated phone command.
    # Keep the old complete record until replacement succeeds; permanent access
    # errors still fail closed within a fixed part of the workflow age budget.
    deadline = time.monotonic() + .5
    while True:
        try:
            temporary.replace(path)
            break
        except OSError as error:
            if getattr(error, 'winerror', None) not in (5, 32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(.01)


def references():
    path = Path(__file__).with_name('farm_draft_anchors.json')
    anchors = json.loads(path.read_text(encoding='utf-8'))
    result = {}
    for name, row in anchors['icons'].items():
        raw = base64.b64decode(row['png'], validate=True)
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise InspectionStopped('Navigation reference is damaged.')
        image = Image.new('RGB', (500, 1080))
        with Image.open(io.BytesIO(raw)) as crop:
            image.paste(crop, tuple(row['box'][:2]))
        buffer = io.BytesIO(); image.save(buffer, 'PNG'); result[name] = buffer.getvalue()
    return result


def icon_matches(frame, reference, box):
    left, top, right, bottom = box
    first, second = pixels(frame, exact=True), pixels(reference, exact=True)
    delta = np.abs(first[top:bottom, left:right].astype(float)-second[top:bottom, left:right].astype(float))
    if delta.mean()/255 > .01 or (delta.max(axis=2) > 35).mean() > .02:
        raise InspectionStopped('The navigation icon changed; no guessed target is allowed.')


def centre(bounds):
    left, top, right, bottom = bounds
    return round((left+right)/2), round((top+bottom)/2)


class Workflow:
    def __init__(self, folder, kernel, store, assets, caption, templates, expected_hash, expected_uid,
                 *, account, package_hash, cancelled=None, monotonic=time.monotonic, pause=time.sleep):
        self.folder, self.kernel, self.store = Path(folder), kernel, store
        self.assets, self.caption, self.templates = assets, caption, templates
        self.account, self.package_hash = account, package_hash
        self.expected_hash, self.expected_uid = expected_hash, expected_uid
        self.cancelled, self.monotonic, self.pause = cancelled or threading.Event(), monotonic, pause
        self.owned = OwnedCaptureRun(kernel, str(uuid.uuid4()), self.cancelled, monotonic,
                                     budget_seconds=WORKFLOW_BUDGET_SECONDS)
        self.identity = None
        self.record = dict(id=self.owned.run_id, source='candidate_phone_workflow' if kernel._is_live_http else 'offline_protocol_fixture',
            state='not_started', cleanup='not_needed', commands=[], observations=[], transitionChecks=[], actions=[],
            promptRecoveries=[],
            publishing=False, messaging=False, desktopControl=False, savedDraftVerified=False,
            budgetSeconds=WORKFLOW_BUDGET_SECONDS,
            productionAdapterAccepted=False, packageSha256=self.package_hash, account=self.account)

    def save(self):
        atomic_json(self.folder / 'record.json', self.record)

    def runtime(self):
        return validate_runtime(self.kernel.kernel_status(), self.kernel.devices(), self.expected_hash, self.expected_uid)

    def check(self):
        if (self.folder / 'STOP').exists(): self.cancelled.set()
        self.owned.check(self.kernel)
        if self.runtime() != self.identity: raise InspectionStopped('Candidate process changed during the run.')

    def command(self, fun, *, basis=None, purpose, **data):
        self.check()
        item = dict(fun=fun, data=data, purpose=purpose, state='not_sent')
        self.record['commands'].append(item); self.save()
        def check_basis(stage):
            if basis is None: return
            value, frame = self.store.current_evidence(basis['id'])
            item.setdefault('decisionChecks', []).append(dict(stage=stage, observationId=value['id'],
                evidenceRecordSha256=value.get('evidenceRecordSha256'), freshness=value.get('freshness'),
                expired=value.get('expired'), frameAgeMs=value.get('frameEvidence', {}).get('currentAgeUpperBoundMs')))
            if value.get('evidenceRecordSha256') != basis.get('evidenceRecordSha256'):
                raise InspectionStopped('The exact action evidence changed.')
            self.validate(value, frame)
        try:
            check_basis('before_dispatch_journal')
            item['state'] = 'outcome_unknown'; self.save()
            # The journal write consumes the same age budget; never reset it.
            check_basis('before_transport')
            self.owned.check_budget()
        except Exception as error:
            # A locally refused dispatch is known not to have reached transport.
            # Once send() begins, a missing reply must instead stay uncertain.
            item.update(state='not_sent', refusal=type(error).__name__ + ': ' + str(error))
            self.save(); raise
        item['response'] = self.kernel.send('C24C', self.owned.tokens['C24C'], fun, **data)
        item['state'] = 'answered'; self.save()

    def validate(self, value, frame):
        if (value.get('state') != 'observed' or value.get('expired')
                or value.get('stable') is not True or value.get('inputSettled') is not True or not capture_settled(value)
                or value.get('frameEvidence', {}).get('pairedMetadata') is not True
                or value.get('ownershipEvidence', {}).get('runId') != self.owned.run_id
                or value.get('inputGeneration') != self.owned.generation
                or value.get('resolvedDeviceId') != LIVE_TEST_DEVICE_ID
                or value.get('observerSession') != self.store.session
                or value.get('receiverPid') != self.owned.stream[1]
                or value.get('frameEvidence', {}).get('session') != self.owned.stream[3]
                or value.get('expected', {}).get('device_id') != 'C24C'
                or value.get('expected', {}).get('platform') != 'instagram'
                or value.get('expected', {}).get('account') != self.account
                or value.get('expected', {}).get('caption') != self.caption
                or value.get('result', {}).get('accountStatus') == 'different_text'
                or not value.get('frameSha256')
                or value.get('text', {}).get('frameSha256') != value.get('frameSha256')
                or value.get('reviewFrameSha256') != hashlib.sha256(frame).hexdigest()):
            raise InspectionStopped('The decision has no fresh, intact C24C frame under this ownership.')
        evidence = value['frameEvidence']
        original, current = evidence.get('ageUpperBoundMs'), evidence.get('currentAgeUpperBoundMs')
        if value.get('freshness') != 'recent':
            if (value.get('freshness') == 'stale' and value.get('freshnessAtCapture') == 'recent'
                    and all(type(age) in (int, float) and math.isfinite(age) for age in (original, current))
                    and 0 <= original <= MAX_AGE_MS < current):
                raise DecisionExpired('Frame aged to %.1f ms before dispatch (limit %d ms).' % (current, MAX_AGE_MS))
            raise InspectionStopped('The decision has no recent frame; automatic refresh is unavailable.')

    def verify_screen(self, role, value, frame, index=None, require_next=False):
        result, text = value['result'], value['text']
        if role in ('create', 'picker', 'editor'):
            return screen_ready(role, frame, text, self.assets, index, require_next)
        if role == 'profile':
            if result['screen'] != 'profile' or result['accountStatus'] != 'exact_text_match':
                raise InspectionStopped('The exact authorized account is not visible on its profile.')
            return dict(account=self.account)
        if role == 'library':
            comparison = media_comparison(frame, self.assets, 'draft_library_candidate' if library_candidate(text, result) else None)
            if comparison.get('matchedIndex') != 1 or comparison.get('matchingCovers') != 1:
                raise InspectionStopped('The test draft cover is absent or ambiguous.')
            return comparison
        if role == 'details':
            comparison = caption_comparison(text, self.caption)
            if (result.get('layout') != 'carousel_details' or comparison['status'] != 'exact_visible_lines'
                    or media_comparison(frame, self.assets, 'carousel_details').get('matchedIndex') != 1):
                raise InspectionStopped('The full caption or details media does not match.')
            return comparison
        if role == 'save_prompt' and result.get('screen') == 'save_prompt' and save_prompt(text):
            return dict(sheet='exact_save_draft')
        raise InspectionStopped('Unsupported or interrupted workflow screen: ' + role)

    def capture(self, role, index=None, require_next=False):
        self.check()
        # Move only, never a tap: quiet video needs a new delivery. Its metadata,
        # recognition, and unchanged final comparison still have to pass.
        before = self.kernel.kernel_status()['receivers'][0]['frames']
        x = 480 if len(self.record['observations']) % 2 == 0 else 450
        self.command('/mouse/move', purpose='fresh_frame_challenge', x=x, y=300)
        self.pause(.12)
        key = str(uuid.uuid4())
        entry = dict(role=role, index=index, observationId=key, state='requested')
        self.record['observations'].append(entry); self.save()
        observed = self.store.capture(dict(id=key, device_id='C24C', platform='instagram', account=self.account, caption=self.caption),
                                     self.kernel, owned_run=self.owned)
        if observed.get('state') != 'observed':
            entry.update(state='failed',observation=observed); self.save()
            raise InspectionStopped('Capture failed: '+observed.get('reason','no completed evidence'))
        value, frame = self.store.current_evidence(key)
        path = self.folder / (str(len(self.record['observations'])).zfill(2)+'-'+role+'.png')
        # ObservationStore already committed the image and immutable record.
        # Export the second copy after releasing the phone, outside the decision
        # age budget. Dispatch still re-reads and hashes the committed image.
        entry.update(state='observed',frame=path.name,observation=value); self.save()
        self.validate(value, frame)
        sequence = value['frameEvidence']['sequence']
        if sequence <= max(before, self.record.get('lastSequence', -1)):
            raise InspectionStopped('The pointer challenge did not produce a new frame.')
        self.record['lastSequence'] = sequence
        if role not in ('create','picker','editor'):
            entry['screenCheck'] = self.verify_screen(role, value, frame, index, require_next)
            self.save()
        # The shared waiter validates every Create/picker/editor capture itself.
        # Do not decode and match the same image twice before its final age check.
        return self.store.current_evidence(key)

    def observe(self, role, index=None, require_next=False):
        if role in ('create', 'picker', 'editor'):
            def journal(event):
                self.record['transitionChecks'].append(event); self.save()
            value, frame, _ = wait_for_transition(role, lambda:self.capture(role,index,require_next), self.check,
                self.store.current_evidence, assets=self.assets, index=index, require_next=require_next,
                journal=journal, monotonic=self.monotonic, pause=self.pause)
            return value, frame
        return self.capture(role, index, require_next)

    def target(self, kind, value, frame):
        text = value['text']
        point = None
        if kind == 'profile_create':
            icon_matches(frame, self.templates['profile'], (15,69,57,108)); point=(35,88)
        elif kind == 'choose_post_format':
            point=centre(create_menu_controls(frame,text)['postBounds'])
        elif kind == 'open_drafts':
            bounds=words_at(text,'drafts',(120,610,210,680))
            if not bounds: raise InspectionStopped('The Drafts control is not uniquely located.')
            point=centre(bounds[0])
        elif kind == 'open_test_draft':
            cell=self.verify_screen('library',value,frame)['libraryCell']
            point=((cell['column']-1)*125+62, (cell['row']-1)*125+173)
        elif kind == 'details':
            if not next_label(frame,text): raise InspectionStopped('Exact Next proof is missing.')
            point=(438,1006)
        elif kind == 'back_to_editor':
            icon_matches(frame,self.templates['details'],(12,67,55,106)); point=(29,85)
        elif kind == 'request_save':
            icon_matches(frame,self.templates['editor3'],(17,76,62,122)); point=(40,100)
        elif kind == 'save_draft':
            bounds=line_at(text,'save draft',(120,897,380,960))
            if not bounds: raise InspectionStopped('Save draft target is not uniquely located.')
            point=centre(bounds[0])
        elif kind == 'leave_picker':
            icon_matches(frame,self.templates['picker_saved'],(19,66,58,105)); point=(39,84)
        elif kind != 'next_slide': raise InspectionStopped('No implementation for that action.')
        if point is not None: allowed_tap(text,*point,kind,frame=frame)
        return point

    def refresh_save_prompt(self, action, value, frame):
        """One new decision while this run still owns the same verified draft.

        This is not recovery of a stopped job or retry of an uncertain Save.
        Only a recorded local age refusal is eligible. Unknown dialogs, changes
        in content/context, cancellation and a second expiry remain review-only.
        """
        label = action['label']
        phase = label.removesuffix('-save-once')
        prior = self.record['actions'][:-1]
        expected = [phase + suffix for suffix in ('-details', '-back', '-exit-sheet')]
        command = self.record['commands'][-1]
        profile = next((entry['observation'] for entry in self.record['observations']
                        if entry.get('state') == 'observed' and entry['role'] == 'profile'), None)
        slides = {phase+'-slide-'+str(i+1) for i in range(1, len(self.assets))}
        if (phase not in ('prepared', 'reopened') or label != phase + '-save-once'
                or action['kind'] != 'save_draft' or action['state'] != 'not_sent'
                or command['purpose'] != label or command['state'] != 'not_sent'
                or not command.get('refusal', '').startswith('DecisionExpired:')
                or len(prior) < 3 or [a['label'] for a in prior[-3:]] != expected
                or not all(a['state'] == 'answered' for a in prior)
                or not slides <= {a['label'] for a in prior}
                or not profile or profile['result'].get('accountStatus') != 'exact_text_match'
                or prompt_context(profile) != prompt_context(value)
                or any(r['label'] == label for r in self.record['promptRecoveries'])):
            raise InspectionStopped('This prompt has no eligible unsent Save decision to refresh.')
        recovery = dict(label=label, kind='save_prompt_fresh_decision', state='checking',
            fromObservationId=value['id'], rejectedCommandIndex=len(self.record['commands'])-1,
            priorActionState='not_sent', maximumCaptures=1, budgetSeconds=PROMPT_REFRESH_SECONDS,
            phoneActionRetried=False)
        self.record['promptRecoveries'].append(recovery); self.save()
        deadline = self.monotonic() + PROMPT_REFRESH_SECONDS
        try:
            self.check()
            # Retained evidence must still be byte-identical. Re-aging it does
            # not make it actionable, but ensures tampering cannot be laundered
            # through a newly captured, superficially matching prompt.
            retained, retained_frame = self.store.current_evidence(value['id'])
            origin, _ = self.store.current_evidence(profile['id'])
            if (retained.get('evidenceRecordSha256') != value['evidenceRecordSha256']
                    or retained_frame != frame
                    or origin.get('evidenceRecordSha256') != profile['evidenceRecordSha256']):
                raise InspectionStopped('The refused decision evidence changed.')
            fresh, fresh_frame = self.observe('save_prompt')
            self.check()
            unchanged_save_prompt(value, frame, fresh, fresh_frame)
            if self.monotonic() >= deadline:
                raise InspectionStopped('Save prompt refresh exceeded its bounded time.')
            recovery.update(state='fresh_decision', observationId=fresh['id'],
                evidenceRecordSha256=fresh['evidenceRecordSha256'])
            self.save()
            return fresh, fresh_frame
        except Exception as error:
            recovery.update(state='held', reason=str(error)); self.save()
            raise

    def action(self, label, kind, role, index=None):
        if any(a['label'] == label for a in self.record['actions']):
            raise InspectionStopped('A semantic action cannot be replayed.')
        value, frame = self.observe(role, index, require_next=kind=='details')
        action=dict(label=label,kind=kind,observationId=value['id'],state='not_sent',attempts=[])
        self.record['actions'].append(action)
        for attempt in range(2):
            point = self.target(kind, value, frame)
            decision = dict(observationId=value['id'], state='not_sent')
            action['attempts'].append(decision)
            action.update(observationId=value['id'], state='not_sent'); self.save()
            action['state']='outcome_unknown'; self.save()
            command_count=len(self.record['commands'])
            try:
                if point is not None:
                    self.command('/mouse/click',basis=value,purpose=label,x=point[0],y=point[1],button=1)
                else:
                    self.command('/mouse/swipe',basis=value,purpose=label,x1=400,y1=480,x2=100,y2=480,duration=350)
            except BaseException as error:
                sent=self.record['commands'][command_count:]
                state=sent[-1]['state'] if sent else 'not_sent'
                decision.update(state=state,reason=str(error))
                action.update(state=state,reason=str(error)); self.save()
                if (attempt == 0 and kind == 'save_draft' and role == 'save_prompt'
                        and state == 'not_sent' and isinstance(error, DecisionExpired)):
                    value, frame = self.refresh_save_prompt(action, value, frame)
                    continue
                raise
            decision['state']='answered'; action['state']='answered'; action.pop('reason',None); self.save()
            break
        # Complete pointer parking before starting the next settling interval.
        # The overall operation budget still includes this movement. Uncertain
        # replies/cancellation never get here; no semantic action is repeated.
        self.command('/mouse/move',purpose='park_after_answered_action',x=480,y=300)
        self.pause(.65)

    def run(self):
        self.record['mode']='save_reopen'
        try:
            self.identity=self.runtime()
            if not idle(self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)):
                raise InspectionStopped('C24C is not free; no takeover is allowed.')
            raw,_=self.kernel.shot('C24C')
            text=self.store.ocr.read(raw)
            initial=classify(text,dict(platform='instagram',account=self.account,caption=self.caption),raw)
            if initial['screen']!='profile' or initial['accountStatus']!='exact_text_match':
                raise InspectionStopped('Start on the authorized Instagram profile. No input was sent.')
            # This old/quiet read can admit only the first move-only challenge.
            self.record['cleanup']='unconfirmed'; self.save(); self.owned.acquire()
            self.command('/mouse/reset',purpose='initial_pointer_reset')
            self.action('open-create','profile_create','profile')
            self.action('choose-post-format','choose_post_format','create')
            self.action('open-prepared-library','open_drafts','picker')
            self.action('open-prepared-test-draft','open_test_draft','library')
            for phase in ('prepared','reopened'):
                for index in range(1,len(self.assets)):
                    self.action(phase+'-slide-'+str(index+1),'next_slide','editor',index)
                self.action(phase+'-details','details','editor',len(self.assets))
                self.action(phase+'-back','back_to_editor','details')
                # Actual phone evidence retains slide 3 after returning from details.
                self.action(phase+'-exit-sheet','request_save','editor',len(self.assets))
                self.action(phase+'-save-once','save_draft','save_prompt')
                if phase=='prepared':
                    self.action('open-saved-library','open_drafts','picker')
                    self.action('reopen-saved-test-draft','open_test_draft','library')
            self.action('return-profile','leave_picker','picker')
            final,_=self.observe('profile')
            first=self.record['observations'][0]['observation']['id']
            timeline=self.store.interval(first,final['id'])
            history=account_history(dict(observations={}),timeline,dict(platform='instagram',account=self.account,caption=self.caption))
            self.record['accountHistory']=history
            if history['status']!='consistent_sampled_history':
                raise InspectionStopped('Sampled account history is incomplete.')
            self.record.update(state='validation_passed',savedDraftVerified=True,
                meaning='Existing draft saved/reopened with all visible slides/caption and sampled account boundaries; no app restart or server persistence proof.')
        except BaseException as error:
            self.record.update(state='review_required',error=type(error).__name__+': '+str(error))
        finally:
            self.finish()
        return self.record

    def finish(self):
        """Cleanup/export shared with the separately bounded new-draft workflow."""
        try:
            if self.owned.tokens: self.owned.release(); self.record['cleanup']='confirmed'
            self.record['finalInput']=self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)
            if not idle(self.record['finalInput']):
                self.record.update(state='review_required',cleanup='unconfirmed')
        except Exception as error:
            self.record.update(state='review_required',cleanup='unconfirmed',cleanupError=str(error))
        try:
            for entry in self.record['observations']:
                if entry.get('state') != 'observed': continue
                value, frame = self.store.evidence(entry['observationId'])
                if value['reviewFrameSha256'] != entry['observation']['reviewFrameSha256']:
                    raise InspectionStopped('Retained image changed before evidence export.')
                (self.folder/entry['frame']).write_bytes(frame)
            self.record['evidenceExport']='confirmed'
        except Exception as error:
            self.record.update(state='review_required',evidenceExport='failed',exportError=str(error))
        if self.record['state'] != 'validation_passed': self.record['savedDraftVerified'] = False
        self.save()
