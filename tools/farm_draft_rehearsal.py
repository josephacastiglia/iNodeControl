"""Offline save/reopen contract. No live adapter or phone coordinates exist here.

Reuses the inspection journal, immutable frames, ownership guard and recognizers.
Synthetic frames exercise workflow logic, not OCR accuracy or Instagram behavior.
"""
import hashlib
import io
import json
import threading
import time
import uuid
import zipfile

from PIL import Image, ImageDraw, PngImagePlugin

from farm_carousel_inspection import CarouselInspections, OwnedCaptureRun, InspectionStopped
from farm_drafts import DraftConflict, identifier
from farm_draft_verification import caption_comparison, library_candidate
from farm_draft_media import media_comparison
from farm_observations import ObservationStore, classify
from farm_transitions import wait_for_transition


SCENARIOS = ('normal', 'save_reply_lost', 'reopen_reply_lost', 'permission_prompt',
             'account_changed', 'stale_frame', 'wrong_slide', 'wrong_caption', 'duplicate_cover')


def save_prompt(text):
    """Observed English exit sheet; generic Save text behind an overlay is not enough."""
    def at(label, lo, hi):
        return sum(1 for line in text.get('lines', []) if line.get('words')
                   and line['text'].casefold() == label
                   and lo <= min(w['y'] for w in line['words']) / text['height'] <= hi) == 1
    return (at('if you go back now, your edits will be discarded.', .71, .78)
            and at('discard', .78, .83) and at('save draft', .83, .89) and at('cancel', .90, .96))


class SyntheticOcr:
    """Reads generated fixture annotations only; never used for phone screenshots."""
    def read(self, raw):
        with Image.open(io.BytesIO(raw)) as image:
            value = json.loads(image.info['imouseSyntheticText'])
        return {**value, 'frameSha256': hashlib.sha256(raw).hexdigest()}


class DraftAppModel:
    """Small deterministic app/transport model, deliberately separate from live input.

The prepared editor is seeded, not imported via a pretend Photos/Instagram route.
Semantic transitions have no direct mapping to phone taps or gestures.
"""
    _is_live_http = False

    def __init__(self, assets, caption, scenario):
        self.assets, self.caption, self.scenario = assets, caption, scenario
        self.screen, self.index, self.sequence = 'profile', 1, 1
        self.saved, self.reopened = None, False
        self.token, self.owned, self.generation = None, False, 4
        self.session = uuid.uuid4().hex
        self.calls, self.saves = [], 0

    def resolve_device_id(self, phone):
        if phone != 'C24C': raise ValueError('Rehearsal is scoped to C24C.')
        return phone

    def kernel_status(self):
        return dict(receivers=[dict(deviceid='C24C', receiver_pid=1, receiver_restarts=0,
                    live=True, frames=self.sequence, frame_session=self.session)])

    def input_status(self):
        return {'C24C': dict(owned=self.owned, active=False, stopped=False, releasing=False,
                            release_failed=False, generation=self.generation)}

    def preflight_phone(self, phone):
        self.resolve_device_id(phone)
        if self.owned: raise RuntimeError('Another owner is active.')
        return dict(resolved_id='C24C', receiver=self.kernel_status()['receivers'][0])

    def acquire(self, ids, lease_ms):
        if ids != ['C24C'] or lease_ms != 30000 or self.owned: raise ValueError('Invalid model acquisition.')
        self.token = uuid.uuid4().hex; self.owned = True; self.calls.append('acquire')
        return {'C24C': self.token}

    def renew_if_needed(self, tokens, min_remaining_ms):
        if not self.owned or tokens != {'C24C': self.token}: raise RuntimeError('Ownership changed.')

    def release(self, tokens):
        self.renew_if_needed(tokens, 0)
        self.calls.append('release'); self.owned = False; self.token = None

    def perform(self, action, token):
        self.renew_if_needed({'C24C': token}, 0)
        kind = action['kind']; self.calls.append(kind)
        transitions = {'open_create': ('profile', 'create_menu'), 'choose_post_format': ('create_menu', 'picker'),
                       'open_prepared': ('library', 'editor'), 'details': ('editor', 'details'),
                       'back_to_editor': ('details', 'editor'), 'request_save': ('editor', 'save_prompt'),
                       'save_draft': ('save_prompt', 'picker'), 'open_drafts': ('picker', 'library'),
                       'reopen': ('library', 'editor'),
                       'view_account': ('details', 'profile')}
        if kind == 'next_slide':
            if self.screen != 'editor' or self.index >= len(self.assets): raise ValueError('Invalid slide transition.')
            self.index += 1
        elif kind in transitions:
            before, after = transitions[kind]
            if self.screen != before: raise ValueError('Unexpected model state.')
            if kind == 'save_draft':
                self.saved = (tuple(self.assets), self.caption); self.saves += 1
            if kind == 'reopen':
                if not self.saved: raise ValueError('No persisted draft.')
                self.assets, self.caption = list(self.saved[0]), self.saved[1]
                self.reopened = True
            self.screen = after
            if after == 'editor': self.index = 1
        else: raise ValueError('Unsupported semantic action; no publishing or messaging exists.')
        if ((kind == 'save_draft' and self.scenario == 'save_reply_lost')
                or (kind == 'reopen' and self.scenario == 'reopen_reply_lost')):
            raise TimeoutError('Simulated lost acknowledgement after the model changed state.')
        return dict(code=0)

    def shot(self, phone):
        self.resolve_device_id(phone); self.sequence += 1
        image = Image.new('RGB', (500, 1080), 'black'); rows = []
        def line(label, y, x=20, width=460):
            # Geometry/text are synthetic test data, not an OCR result from a phone.
            painter=ImageDraw.Draw(image)
            if painter.textlength(label)>460:
                while label and painter.textlength(label+'...')>460: label=label[:-1]
                label+='...'
            if y+14>1080: return
            rows.append(dict(text=label, words=[dict(text=label, x=x, y=y, width=width, height=14)]))
        with Image.open(io.BytesIO(self.assets[self.index-1])) as source:
            source = source.convert('RGB')
            if self.screen == 'editor':
                if self.scenario == 'wrong_slide' and self.reopened and self.index == 2:
                    source = Image.open(io.BytesIO(self.assets[0])).convert('RGB')
                image.paste(source.resize((500, 625)), (0, 164))
                draw = ImageDraw.Draw(image)
                for n in range(len(self.assets)):
                    x = 250 + (n-(len(self.assets)-1)/2)*12
                    draw.ellipse((x-3, 836, x+3, 842), fill='white' if n+1 == self.index else '#555555')
                for label,x,width in (('Audio',42,33),('Text',124,28),('Overlay',190,44),
                                      ('Filter',273,30),('Edit',353,23),('Ratio',427,29)):
                    line(label,921,x,width)
                draw.rounded_rectangle((396,980,477,1031),radius=26,fill=(70,83,255))
                line('Next',1001,411,33)
            elif self.screen == 'details':
                with Image.open(io.BytesIO(self.assets[0])) as first: image.paste(first.resize((240, 300)), (20, 126))
                for label, y in (('New post',78), ('Add audio',641), ('Tag people',754), ('Add location',812), ('Add AI Label',865), ('Share',991)): line(label,y)
                caption = 'Changed caption' if self.reopened and self.scenario == 'wrong_caption' else self.caption
                for n, label in enumerate(caption.splitlines() if caption else ['Add a caption...']): line(label,454+20*n)
            elif self.screen == 'library':
                line('Drafts',78); line('Select',78)
                with Image.open(io.BytesIO((self.saved[0] if self.saved else self.assets)[0])) as first:
                    side = min(first.size); x=(first.width-side)//2; y=(first.height-side)//2
                    thumbnail=first.crop((x,y,x+side,y+side)).resize((124,124))
                image.paste(thumbnail,(125,111))
                if self.saved is not None and self.scenario == 'duplicate_cover': image.paste(thumbnail,(250,111))
            elif self.screen == 'picker':
                # The preview changes at every capture, while navigation/grid stay fixed.
                image.paste((20 + self.sequence % 2 * 90,40,60),(0,112,500,612))
                image.paste(source.resize((124,124)),(125,679))
                for label,y,x,width in (('New post',78,208,88),('Next',78,435,44),
                                        ('Recents',637,20,78),('Drafts',637,135,58),('Select',637,417,49)):
                    line(label,y,x,width)
            elif self.screen == 'save_prompt':
                for label,y in [('If you go back now, your edits will be discarded.',793), ('Discard',858), ('Save draft',925), ('Cancel',1002)]: line(label,y)
            elif self.screen == 'create_menu':
                image.paste('white', (0, 466, 500, 1080))
                for label,y,x,width in (('Create',516,219,62),('Edits',621,70,41),('Post',675,70,37),
                                        ('Story',728,69,46),('Instants',781,70,67),('Highlights',833,70,86),
                                        ('Live',886,70,33),('Fundraiser',939,70,91)):
                    line(label,y,x,width)
            else:
                account = 'other.account' if self.reopened and self.scenario == 'account_changed' else 'simulation.account'
                for label,y in [(account,90),('Posts',180),('Following',180),('Edit profile',300),('Share profile',300)]: line(label,y)
        if self.scenario == 'permission_prompt' and self.screen == 'save_prompt':
            line("Don't Allow",600); line('Allow',650)
        # Draw labels outside the media areas; the fixture metadata is explicit and retained.
        draw=ImageDraw.Draw(image)
        for row in rows: draw.text((row['words'][0]['x'],row['words'][0]['y']),row['text'],
                                  fill='black' if self.screen=='create_menu' else 'white')
        info=PngImagePlugin.PngInfo()
        info.add_text('imouseSyntheticText',json.dumps(dict(width=500,height=1080,lines=rows)))
        output=io.BytesIO(); image.save(output,'PNG',pnginfo=info)
        age = '2000' if self.scenario == 'stale_frame' and self.screen == 'save_prompt' else '1'
        return output.getvalue(), {'X-iMouse-Frame-Session':self.session, 'X-iMouse-Frame-Sequence':str(self.sequence),
                                  'X-iMouse-Frame-Age-Ms':age, 'X-iMouse-Frame-Delivery':'flowing'}


class DraftRehearsals(CarouselInspections):
    """Same journal/evidence store as inspections, with offline-only semantic actions."""
    def __init__(self, path, drafts, clock=time.time, monotonic=time.monotonic):
        from pathlib import Path
        path=Path(path)
        observations=ObservationStore(path.with_name(path.stem+'-observations.db'),SyntheticOcr(),clock,monotonic)
        super().__init__(path,observations,drafts,clock,monotonic)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS cancellations(id TEXT PRIMARY KEY)')

    def cancel(self, run_id):
        run_id=identifier(run_id)
        # A Stop arriving before admission must survive a delayed POST or restart.
        with self.connect() as db: db.execute('INSERT OR IGNORE INTO cancellations VALUES (?)',(run_id,))
        super().cancel(run_id)
        return dict(id=run_id,cancellationRequested=True)

    def list(self, draft_id):
        draft_id=identifier(draft_id)
        with self.connect() as db:
            ids=[json.loads(row[0]) for row in db.execute('SELECT document FROM inspections ORDER BY rowid DESC')]
        selected=[v['id'] for v in ids if v['request']['draft_id']==draft_id][:30]
        return [self.get(run_id) for run_id in selected]

    def get(self, run_id):
        value=super().get(run_id)
        if value['state']=='review_required':
            value['recovery'] = ('Inspect the saved result and retained frames. Do not replay Save or reopen. '
                                 'This is a simulated run; it changed no phone draft.')
        value['draftChangedSinceRun']=self.drafts.get(value['request']['draft_id'])['revision']!=value['request']['revision']
        return value

    def observe(self, record, model, owned, assets, role, index=None):
        owned.check(model)
        observation_id=str(uuid.uuid4())
        record['observationIds'].append(observation_id); record['captureRoles'][observation_id]=role; self.save(record)
        request=dict(id=observation_id,device_id='C24C',platform='instagram',account='simulation.account',caption=record['caption'])
        self.observations.capture(request,model,owned_run=owned)
        value,frame=self.observations.evidence(observation_id)
        digest=self.retain(record,value,frame)
        if (value.get('freshness')!='recent' or not value.get('stable') or not value.get('inputSettled')
                or value.get('frameEvidence',{}).get('pairedMetadata') is not True):
            raise InspectionStopped('The transition has no fresh, settled paired frame.')
        sequence=value['frameEvidence']['sequence']
        if sequence<=record.get('lastFrameSequence',-1): raise InspectionStopped('Transition reused an old frame.')
        record['lastFrameSequence']=sequence
        result=classify(value['text'],request,frame)
        if result['screen'] in ('permission_prompt','share_sheet','sharing_dialog'):
            raise InspectionStopped('A dialog interrupted the workflow. Nothing was dismissed automatically.')
        check=dict(role=role,observationId=observation_id)
        if role in ('account_before','account_after'):
            if result['screen']!='profile' or result['accountStatus']!='exact_text_match':
                raise InspectionStopped('Account boundary did not match; do not continue or retry.')
        elif role.endswith('_slide'):
            comparison=media_comparison(frame,assets,result.get('layout')); position=comparison.get('position',{})
            if comparison.get('matchedIndex')!=index or position.get('index')!=index or position.get('count')!=len(assets):
                raise InspectionStopped('Full-size slide, order or carousel count did not match.')
            check.update(index=index,comparison=comparison)
        elif role.endswith('_caption'):
            if (result.get('layout')!='carousel_details' or media_comparison(frame,assets,'carousel_details').get('matchedIndex')!=1
                    or caption_comparison(value['text'],record['caption'])['status']!='exact_visible_lines'):
                raise InspectionStopped('The full visible caption or details media did not match.')
        elif role=='save_prompt':
            if not save_prompt(value['text']): raise InspectionStopped('The supported Save draft sheet is not visible.')
        elif role=='create_menu':
            if result.get('layout')!='post_create_sheet':
                raise InspectionStopped('The Create sheet is not independently recognized.')
        elif role=='library':
            comparison=media_comparison(frame,assets,'draft_library_candidate' if library_candidate(value['text'],result) else None)
            if comparison.get('matchedIndex')!=1 or comparison.get('matchingCovers')!=1:
                raise InspectionStopped('The saved library cover is missing or ambiguous. Do not guess which draft to open.')
            check['comparison']=comparison
        elif role.startswith('picker_') or role=='post_save':
            if result.get('layout')=='post_media_picker':
                check['layout']='post_media_picker'
            elif role=='post_save' and library_candidate(value['text'],result):
                comparison=media_comparison(frame,assets,'draft_library_candidate')
                if comparison.get('matchedIndex')!=1 or comparison.get('matchingCovers')!=1:
                    raise InspectionStopped('The post-save library is ambiguous.')
                check['comparison']=comparison
            else: raise InspectionStopped('Post-save picker controls are not independently recognized.')
        else: raise ValueError('Unknown transition check.')
        record['checks'].append(check); self.save(record)
        return {**value,'evidenceRecordSha256':digest}

    def validate_basis(self, record, action, owned, model):
        owned.check(model)
        basis=action['basis']; value,frame=self.observations.current_evidence(basis['observationId'])
        if (value.get('freshness')!='recent' or value.get('expired')
                or value.get('evidenceRecordSha256')!=basis['recordSha256']
                or hashlib.sha256(frame).hexdigest()!=basis['frameSha256']
                or value.get('ownershipEvidence',{}).get('runId')!=record['id']
                or value.get('inputGeneration')!=owned.generation
                or basis['packageSha256']!=record['packageSha256']):
            raise InspectionStopped('The exact decision frame expired or changed before the action.')
        owned.check_budget()

    def act(self, record, model, owned, assets, kind, role, index=None):
        # Re-observe immediately before every semantic action, not only after the last one.
        stability=None
        stage = 'picker' if kind=='open_drafts' else 'create' if kind=='choose_post_format' else 'editor' if role.endswith('_slide') else None
        if stage:
            def capture():
                value=self.observe(record,model,owned,assets,role,index)
                return value,self.observations.evidence(value['id'])[1]
            def journal(event):
                record.setdefault('transitionChecks',[]).append(event); self.save(record)
            value,_,stability=wait_for_transition(stage,capture,lambda:owned.check(model),
                self.observations.current_evidence,assets=assets,index=index,require_next=kind=='details',
                journal=journal,monotonic=self.monotonic)
        else: value=self.observe(record,model,owned,assets,role,index)
        action=dict(kind=kind,state='not_sent',basis=dict(observationId=value['id'],
            recordSha256=value['evidenceRecordSha256'],frameSha256=value['reviewFrameSha256'],
            packageSha256=record['packageSha256']))
        if stability is not None:
            action['transitionStability']=stability
            if stage=='picker': action['pickerStability']=stability
        record['actions'].append(action); self.save(record)
        try:
            self.validate_basis(record,action,owned,model)
            action['state']='outcome_unknown'; self.save(record)
            self.validate_basis(record,action,owned,model)
        except Exception:
            action['state']='not_sent'; self.save(record); raise
        response=model.perform(action,owned.tokens['C24C'])
        if not isinstance(response,dict) or type(response.get('code')) is not int or response['code']!=0:
            raise InspectionStopped('Action was not acknowledged; its outcome needs review.')
        action['state']='answered'; self.save(record)

    def reconcile(self, record, model, owned, assets):
        """One read-only check after a lost response, never another semantic action."""
        unknown=next((a for a in reversed(record['actions']) if a['state']=='outcome_unknown'),None)
        if unknown is None or unknown['kind'] not in ('save_draft','reopen'): return
        role,index=('post_save',None) if unknown['kind']=='save_draft' else ('reopened_slide',1)
        try:
            value=self.observe(record,model,owned,assets,role,index)
            status='picker_after_unknown_reply' if value['result'].get('layout')=='post_media_picker' else 'matching_screen_after_unknown_reply'
            record['reconciliation']=dict(status=status,action=unknown['kind'],observationId=value['id'],savedDraftVerified=False)
        except Exception:
            record['reconciliation']=dict(status='unresolved',action=unknown['kind'])

    def run(self, request, *, cancelled=None, model_factory=DraftAppModel):
        if set(request)!={'id','draft_id','revision','scenario'}:
            raise ValueError('Rehearsal accepts only a saved revision, request ID and named offline scenario.')
        if type(request['revision']) is not int or request['revision']<1 or request['scenario'] not in SCENARIOS:
            raise ValueError('Choose a valid saved revision and supported offline scenario.')
        spec=dict(id=identifier(request['id']),draft_id=identifier(request['draft_id']),revision=request['revision'],scenario=request['scenario'])
        fingerprint=json.dumps(spec,sort_keys=True)
        if not self.lock.acquire(False): raise DraftConflict('A draft rehearsal is running.')
        event=cancelled or threading.Event()
        try:
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                prior=db.execute('SELECT fingerprint FROM inspections WHERE id=?',(spec['id'],)).fetchone()
                if prior:
                    if prior[0]!=fingerprint: raise DraftConflict('Request ID already belongs to another rehearsal.')
                    return self.get(spec['id'])
                package=self.drafts.export(spec['draft_id'],spec['revision'])
                if len(package)>32*1024*1024: raise ValueError('Rehearsal package exceeds 32 MiB.')
                with zipfile.ZipFile(io.BytesIO(package)) as files:
                    manifest=json.loads(files.read('manifest.json')); assets=[files.read(a['file']) for a in manifest['assets']]
                if not 2<=len(assets)<=10: raise ValueError('Rehearsal needs 2–10 slides.')
                if any(hashlib.sha256(a).hexdigest()!=m['sha256'] for a,m in zip(assets,manifest['assets'])):
                    raise ValueError('Source checksum failed.')
                draft=self.drafts.get(spec['draft_id'])
                if draft['revision']!=spec['revision']: raise DraftConflict('Draft revision changed.')
                record=dict(id=spec['id'],request=spec,inspectionVersion=2,rehearsalVersion=1,state='running',
                    source='simulation',startedAt=self.clock(),caption=draft['caption'],observationIds=[],captureRoles={},
                    evidenceManifest={},checks=[],actions=[],evidenceBytes=len(package),packageSha256=hashlib.sha256(package).hexdigest(),
                    cleanup='not_needed',savedDraftVerified=False,accountContinuityProven=False,automaticInputAllowed=False,
                    reason='Offline model only; no phone input or live save claim.',recovery='Check the saved run by its ID; never retry an uncertain action.')
                # Register before publishing the row: a concurrent GET must not
                # mistake a newly admitted run for an abandoned process journal.
                with self.active_lock: self.active[spec['id']]=event
                db.execute('INSERT INTO inspections VALUES (?,?,?,?)',(spec['id'],fingerprint,json.dumps(record),package))
            with self.connect() as db:
                if db.execute('SELECT 1 FROM cancellations WHERE id=?',(spec['id'],)).fetchone(): event.set()
            owned=None; model=None
            try:
                model=model_factory(assets,draft['caption'],spec['scenario'])
                if not isinstance(model,DraftAppModel) or model._is_live_http:
                    raise InspectionStopped('Only the offline app model is accepted. No live adapter exists.')
                owned=OwnedCaptureRun(model,spec['id'],event,self.monotonic)
                owned.check_budget(); record['cleanup']='unconfirmed'; self.save(record); owned.acquire()
                # The model seeds an existing prepared draft; it does not simulate
                # importing media or claim this navigation has run on a phone.
                self.act(record,model,owned,assets,'open_create','account_before')
                self.act(record,model,owned,assets,'choose_post_format','create_menu')
                self.act(record,model,owned,assets,'open_drafts','picker_after')
                self.act(record,model,owned,assets,'open_prepared','library')
                for phase in ('prepared','reopened'):
                    for index in range(1,len(assets)+1):
                        self.observe(record,model,owned,assets,phase+'_slide',index)
                        if index<len(assets): self.act(record,model,owned,assets,'next_slide',phase+'_slide',index)
                    self.act(record,model,owned,assets,'details',phase+'_slide',len(assets))
                    self.observe(record,model,owned,assets,phase+'_caption')
                    if phase=='prepared':
                        self.act(record,model,owned,assets,'back_to_editor','prepared_caption')
                        self.act(record,model,owned,assets,'request_save','prepared_slide',1)
                        self.act(record,model,owned,assets,'save_draft','save_prompt')
                        returned=self.observe(record,model,owned,assets,'post_save')
                        if returned['result'].get('layout')=='post_media_picker':
                            self.act(record,model,owned,assets,'open_drafts','picker_after')
                        self.observe(record,model,owned,assets,'library')
                        self.act(record,model,owned,assets,'reopen','library')
                self.act(record,model,owned,assets,'view_account','reopened_caption')
                self.observe(record,model,owned,assets,'account_after')
                owned.check(model)
                record.update(state='simulation_passed',reason='The simulated save, library, reopen, all slides, caption and account boundaries matched. Live persistence remains unverified.')
            except Exception as error:
                record.update(state='review_required',reason=str(error) if isinstance(error,InspectionStopped) else type(error).__name__+': interrupted; no action was replayed.')
                if owned is not None and owned.tokens: self.reconcile(record,model,owned,assets)
            finally:
                if owned is not None and owned.tokens:
                    try: owned.release(); record['cleanup']='confirmed'
                    except Exception: record.update(state='review_required',cleanup='unconfirmed',reason='Cleanup was not confirmed; no automatic takeover or retry.')
                record['completedAt']=self.clock(); self.save(record)
            return self.get(spec['id'])
        finally:
            with self.active_lock: self.active.pop(spec['id'],None)
            self.lock.release()
