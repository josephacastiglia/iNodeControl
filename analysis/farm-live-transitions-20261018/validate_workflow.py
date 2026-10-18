"""Bounded C24C-only validation of an existing Instagram test draft.

Explicit CLI diagnostic, not a production HTTP adapter. No arbitrary action,
account, endpoint, publishing, messaging, keyboard or desktop API is exposed.
Every uncertain command ends the run; only scoped lease cleanup follows.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
import uuid
import zipfile

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(HERE.parent / 'farm-live-layout-20261018'))
from phone_step import StepKernel, allowed_tap
from farm_carousel_inspection import OwnedCaptureRun, InspectionStopped
from farm_draft_media import media_comparison
from farm_draft_rehearsal import save_prompt
from farm_draft_verification import caption_comparison, library_candidate, account_history
from farm_frame_evidence import capture_settled
from farm_live_verification import validate_runtime, idle
from farm_observations import ObservationStore, WindowsOcr, classify
from farm_screen_layout import pixels, words_at, line_at, create_menu_controls, picker_controls, next_label
from farm_transitions import wait_for_transition, screen_ready
from imouse_social_automation import LIVE_TEST_DEVICE_ID

ACCOUNT = 'xs.halle.xo'
PACKAGE_HASH = '7f910284d9c7dc26d3c443183fdda33c78bdd4553036dabc75e38d158f48b616'


def atomic_json(path, value):
    temporary = path.with_suffix('.writing')
    with temporary.open('w', encoding='utf-8', newline='\n') as output:
        json.dump(value, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.flush(); os.fsync(output.fileno())
    temporary.replace(path)


def references():
    result = {}
    for label, row in json.loads((HERE / 'reference-frames.json').read_text(encoding='utf-8')).items():
        raw = Path(row['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise InspectionStopped('A retained reference changed: ' + label)
        result[label] = raw
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
                 *, cancelled=None, monotonic=time.monotonic, pause=time.sleep):
        self.folder, self.kernel, self.store = Path(folder), kernel, store
        self.assets, self.caption, self.templates = assets, caption, templates
        self.expected_hash, self.expected_uid = expected_hash, expected_uid
        self.cancelled, self.monotonic, self.pause = cancelled or threading.Event(), monotonic, pause
        self.owned = OwnedCaptureRun(kernel, str(uuid.uuid4()), self.cancelled, monotonic)
        self.identity = None
        self.record = dict(id=self.owned.run_id, source='bounded_live_diagnostic' if kernel._is_live_http else 'offline_protocol_fixture',
            state='not_started', cleanup='not_needed', commands=[], observations=[], transitionChecks=[], actions=[],
            publishing=False, messaging=False, desktopControl=False, savedDraftVerified=False,
            productionAdapterAccepted=False, packageSha256=PACKAGE_HASH, account=ACCOUNT)

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
        if basis is not None:
            value, frame = self.store.current_evidence(basis['id'])
            self.validate(value, frame)
            if value['evidenceRecordSha256'] != basis['evidenceRecordSha256']:
                raise InspectionStopped('The exact action evidence changed.')
        item['state'] = 'outcome_unknown'; self.save()
        # The write above consumes the same age budget; do not reset it.
        if basis is not None:
            try:
                value, frame = self.store.current_evidence(basis['id']); self.validate(value, frame)
                if value['evidenceRecordSha256'] != basis['evidenceRecordSha256']:
                    raise InspectionStopped('Action evidence changed before dispatch.')
            except Exception:
                item['state'] = 'not_sent'; self.save(); raise
        self.owned.check_budget()
        item['response'] = self.kernel.send('C24C', self.owned.tokens['C24C'], fun, **data)
        item['state'] = 'answered'; self.save()

    def validate(self, value, frame):
        if (value.get('state') != 'observed' or value.get('freshness') != 'recent' or value.get('expired')
                or value.get('stable') is not True or value.get('inputSettled') is not True or not capture_settled(value)
                or value.get('frameEvidence', {}).get('pairedMetadata') is not True
                or value.get('ownershipEvidence', {}).get('runId') != self.owned.run_id
                or value.get('inputGeneration') != self.owned.generation
                or value.get('resolvedDeviceId') != LIVE_TEST_DEVICE_ID
                or value.get('expected', {}).get('account') != ACCOUNT
                or value.get('reviewFrameSha256') != hashlib.sha256(frame).hexdigest()):
            raise InspectionStopped('The decision has no fresh, intact C24C frame under this ownership.')

    def verify_screen(self, role, value, frame, index=None, require_next=False):
        result, text = value['result'], value['text']
        if role in ('create', 'picker', 'editor'):
            return screen_ready(role, frame, text, self.assets, index, require_next)
        if role == 'profile':
            if result['screen'] != 'profile' or result['accountStatus'] != 'exact_text_match':
                raise InspectionStopped('The exact authorized account is not visible on its profile.')
            return dict(account=ACCOUNT)
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
        if role == 'save_prompt' and save_prompt(text): return dict(sheet='exact_save_draft')
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
        observed = self.store.capture(dict(id=key, device_id='C24C', platform='instagram', account=ACCOUNT, caption=self.caption),
                                     self.kernel, owned_run=self.owned)
        if observed.get('state') != 'observed':
            entry.update(state='failed',observation=observed); self.save()
            raise InspectionStopped('Capture failed: '+observed.get('reason','no completed evidence'))
        value, frame = self.store.current_evidence(key)
        path = self.folder / (str(len(self.record['observations'])).zfill(2)+'-'+role+'.png')
        path.write_bytes(frame)
        entry.update(state='observed',frame=path.name,observation=value); self.save()
        self.validate(value, frame)
        sequence = value['frameEvidence']['sequence']
        if sequence <= max(before, self.record.get('lastSequence', -1)):
            raise InspectionStopped('The pointer challenge did not produce a new frame.')
        self.record['lastSequence'] = sequence
        entry['screenCheck'] = self.verify_screen(role, value, frame, index, require_next)
        self.save()
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

    def action(self, label, kind, role, index=None):
        if any(a['label'] == label for a in self.record['actions']):
            raise InspectionStopped('A semantic action cannot be replayed.')
        value, frame = self.observe(role, index, require_next=kind=='details')
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
        action=dict(label=label,kind=kind,observationId=value['id'],state='not_sent')
        self.record['actions'].append(action); self.save()
        action['state']='outcome_unknown'; self.save()
        if point is not None:
            self.command('/mouse/click',basis=value,purpose=label,x=point[0],y=point[1],button=1)
        else:
            self.command('/mouse/swipe',basis=value,purpose=label,x1=400,y1=480,x2=100,y2=480,duration=350)
        action['state']='answered'; self.save(); self.pause(.65)

    def run(self):
        try:
            self.identity=self.runtime()
            if not idle(self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)):
                raise InspectionStopped('C24C is not free; no takeover is allowed.')
            raw,_=self.kernel.shot('C24C')
            initial=classify(self.store.ocr.read(raw),dict(platform='instagram',account=ACCOUNT,caption=self.caption),raw)
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
            history=account_history(dict(observations={}),timeline,dict(platform='instagram',account=ACCOUNT,caption=self.caption))
            self.record['accountHistory']=history
            if history['status']!='consistent_sampled_history':
                raise InspectionStopped('Sampled account history is incomplete.')
            self.record.update(state='validation_passed',savedDraftVerified=True,
                meaning='Existing draft saved/reopened with all visible slides/caption and sampled account boundaries; no app restart or server persistence proof.')
        except BaseException as error:
            self.record.update(state='review_required',error=type(error).__name__+': '+str(error))
        finally:
            try:
                if self.owned.tokens: self.owned.release(); self.record['cleanup']='confirmed'
                self.record['finalInput']=self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)
                if not idle(self.record['finalInput']):
                    self.record.update(state='review_required',cleanup='unconfirmed')
            except Exception as error:
                self.record.update(state='review_required',cleanup='unconfirmed',cleanupError=str(error))
            self.save()
        return self.record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    sources=json.loads((HERE/'validation-sources.json').read_text(encoding='utf-8-sig'))
    for path,digest in sources['files'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:
            raise InspectionStopped('A prepared validation source changed: '+path)
    preparation=json.loads((HERE/'preparation.json').read_text(encoding='utf-8'))
    expected_hash=preparation['validation']['build']['sha256']
    if hashlib.sha256(Path(preparation['kernel']).with_suffix('.dll').read_bytes()).hexdigest()!=expected_hash:
        raise InspectionStopped('Prepared kernel changed.')
    package=ROOT/'analysis/farm-phone-transfer-20261017/test-carousel.zip'
    raw=package.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PACKAGE_HASH: raise InspectionStopped('Test media package changed.')
    with zipfile.ZipFile(io.BytesIO(raw)) as files:
        manifest=json.loads(files.read('manifest.json')); assets=[files.read(a['file']) for a in manifest['assets']]
    if len(assets)!=3: raise InspectionStopped('This validation requires the existing three-slide package.')
    templates=references()
    args.out.mkdir(parents=True,exist_ok=False)
    cancelled=threading.Event()
    signal.signal(signal.SIGINT,lambda *_:cancelled.set())
    result=Workflow(args.out,StepKernel('http://127.0.0.1:9916/api'),ObservationStore(args.out/'observations.sqlite3'),
        assets,manifest['caption'],templates,expected_hash,preparation['expectedUid'],cancelled=cancelled).run()
    print(json.dumps(dict(state=result['state'],cleanup=result['cleanup'],error=result.get('error'),folder=str(args.out))))
    return 0 if result['state']=='validation_passed' else 2


if __name__=='__main__': raise SystemExit(main())
