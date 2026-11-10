"""Explicit candidate admission for new media -> verified Instagram draft."""
import hashlib
import json
from pathlib import Path
import threading

from farm_draft_runs import DraftRuns, source_content, load_config, read_journal, ACCOUNT, phone_of, allowed_of, account_of
from farm_drafts import DraftConflict, identifier
from farm_draft_creation import CreationWorkflow
from farm_draft_workflow import Workflow, references, atomic_json
from farm_draft_transport import CreationKernel
from farm_media_transfer import MediaTransferServer, TransferPackage, checked_address
from farm_observations import ObservationStore, WindowsOcr
from farm_live_verification import idle
from imouse_social_automation import KernelSafetyError


# Each window's own (backend, media) port, by rack A box slot; 0 is the pre-rack C24C window.
# Slots 16-18 and 20 keep the ports their windows were prepared with (99x5/99x7, beside the kernel's 9913/9916
# and the planned rack B kernel on 9926). Every other rack A slot n gets 9600+10n+5 / +7 (9615-9797, 5 Nov):
# clear of every 99xx service port and of the receivers' AirPlay ports (7110-7499). Rack B slots get none yet.
LEGACY_PORTS={0:(9915,9917),18:(9915,9917),20:(9925,9927),17:(9935,9937),16:(9945,9947)}


def window_ports(slot):
    """(backend port, media port) of a rack A slot's window."""
    if slot in LEGACY_PORTS: return LEGACY_PORTS[slot]
    if type(slot) is not int or not 1<=slot<=20: raise ValueError(f'No window ports for slot {slot!r}.')
    return 9600+10*slot+5,9600+10*slot+7


MEDIA_PORTS={slot:window_ports(slot)[1] for slot in range(21)}


def creation_config(path,mode):
    if path is None: return None
    value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    media={'mediaBind','mediaClient','mediaPort'}
    if not isinstance(value,dict) or not media<=set(value) or set(value)-media not in (
            {'version','api','kernelSha256','expectedUid'},{'version','api','kernelSha256','expectedUid','phone','allowed','account'}):
        raise ValueError("Creation needs an explicit isolated kernel and this phone's own media configuration.")
    # Reuse the same strict kernel identity rules, without weakening the old route.
    core={k:v for k,v in value.items() if not k.startswith('media')}
    import tempfile
    with tempfile.TemporaryDirectory(prefix='farm-creation-config-') as directory:
        file=Path(directory)/'config.json';file.write_text(json.dumps(core),encoding='utf-8')
        load_config(file,mode)
    value['mediaBind']=checked_address(value['mediaBind']);value['mediaClient']=checked_address(value['mediaClient'])
    port=MEDIA_PORTS[phone_of(value).slot] if phone_of(value).slot in MEDIA_PORTS else None
    if value['mediaBind']==value['mediaClient'] or type(value['mediaPort']) is not int or value['mediaPort']!=port:
        raise ValueError("Use the phone's own LAN address and this slot's dedicated media port.")
    return value


class CreationRuns(DraftRuns):
    action_name='create-phone-draft'

    @staticmethod
    def before_import_retry(value):
        if value.get('request',{}).get('continue_imported_from'): return False
        workflow=value.get('workflow') or {}
        if (value.get('terminal') and value.get('state')=='review_required' and workflow.get('state')=='review_required'
                and workflow.get('source')=='candidate_phone_workflow' and workflow.get('cleanup') in ('confirmed','not_needed')
                and workflow.get('evidenceExport')=='confirmed' and workflow.get('commands')==[]
                and workflow.get('actions')==[] and workflow.get('observations')==[]):
            return True  # Read-only admission failed; no phone command ever began.
        return bool(value.get('terminal') and value.get('state')=='review_required'
            and workflow.get('source')=='candidate_phone_workflow' and workflow.get('cleanup')=='confirmed'
            and workflow.get('evidenceExport')=='confirmed' and workflow.get('state')=='review_required'
            and workflow.get('commands') and all(c.get('state') in ('answered','not_sent') for c in workflow['commands'])
            and all(a.get('state') in ('answered','not_sent') for a in workflow.get('actions',[]))
            and not any(c.get('state')!='not_sent' and c.get('purpose','').startswith(('save-photo-','open-new-carousel-editor','paste-exact-caption','prepared-save-once'))
                        for c in workflow['commands'])
            and not workflow.get('verification'))

    @staticmethod
    def imported_checkpoint(value):
        """A new explicit request may reuse imports, never an editor or Save."""
        workflow=value.get('workflow') or {}
        commands=workflow.get('commands',[])
        if not (value.get('terminal') and value.get('state')=='review_required'
                and workflow.get('state')=='review_required' and workflow.get('source')=='candidate_phone_workflow'
                and workflow.get('cleanup')=='confirmed' and workflow.get('evidenceExport')=='confirmed'
                and workflow.get('account')==ACCOUNT and workflow.get('mediaDelivery',{}).get('stopped') is True
                and all(c.get('state') in ('answered','not_sent') for c in commands)
                and all(a.get('state') in ('answered','not_sent') for a in workflow.get('actions',[]))
                and not workflow.get('verification')
                and not any(c.get('state')!='not_sent' and c.get('purpose','').startswith(
                    ('open-new-carousel-editor','paste-exact-caption','prepared-save-once')) for c in commands)):
            return False
        saves=[c['purpose'] for c in commands if c.get('state')=='answered' and c.get('purpose','').startswith('save-photo-')]
        return (sorted(saves)==['save-photo-1','save-photo-2','save-photo-3']
                or bool(value.get('request',{}).get('continue_imported_from') and workflow.get('importedMedia')))

    @staticmethod
    def validate_request(spec):
        if not isinstance(spec,dict): raise ValueError('Invalid creation request.')
        core={k:v for k,v in spec.items() if k!='continue_imported_from'}
        checked=DraftRuns.validate_request(core)
        if 'continue_imported_from' in spec:
            checked['continue_imported_from']=identifier(spec['continue_imported_from'])
            if checked['continue_imported_from']==checked['id']: raise ValueError('A request cannot continue itself.')
        return checked

    def imported_proof(self,run_id,package_hash,seen=()):
        if run_id in seen or len(seen)>=4: raise DraftConflict('Imported-media history is cyclic or too long; review it.')
        value=self.get(run_id)
        if value['packageSha256']!=package_hash or not self.imported_checkpoint(value):
            raise DraftConflict('Imports or cleanup are uncertain, or an editor already opened. Nothing will be replayed.')
        spec,_,_=self.row(run_id);workflow=value['workflow']
        if spec.get('continue_imported_from'):
            parent=self.imported_proof(spec['continue_imported_from'],package_hash,seen+(run_id,))
            if workflow.get('importedMedia')!=parent: raise DraftConflict('Imported-media provenance changed.')
            if any(c.get('purpose','').startswith('save-photo-') and c.get('state')!='not_sent' for c in workflow['commands']):
                raise DraftConflict('A continuation must not repeat Photos saves.')
        observed=[e for e in workflow.get('observations',[]) if e.get('state')=='observed']
        final=workflow.get('finalInput',{})
        if not idle(final): raise DraftConflict('The prior phone state is unconfirmed.')
        if observed:evidence=observed[-1]['observation']
        elif spec.get('continue_imported_from') and not workflow.get('commands') and not workflow.get('actions'):
            # Acquisition/release failed before the first phone command. Keep
            # the parent's media/session proof and the confirmed new generation.
            evidence=dict(receiverPid=parent['receiverPid'],frameEvidence=dict(session=parent['frameSession']))
        else:raise DraftConflict('The prior visual checkpoint is missing.')
        pin=dict(priorRunId=run_id,priorRecordSha256=hashlib.sha256((self.folder/run_id/'record.json').read_bytes()).hexdigest(),
            generation=final['generation'],receiverPid=evidence.get('receiverPid'),
            frameSession=evidence.get('frameEvidence',{}).get('session'))
        answered={c.get('purpose') for c in workflow['commands'] if c.get('state')=='answered'}
        selection=([1] if 'enable-multiple-selection' in answered else [])
        selection += [n for n in (2,3) if 'select-slide-'+str(n) in answered]
        if selection:pin['selection']=selection
        if not pin['receiverPid'] or not pin['frameSession']: raise DraftConflict('Imported-media receiver identity is missing.')
        return pin

    def content_holds(self,content):
        with self.connect() as db: rows=db.execute('SELECT id,package,request FROM runs ORDER BY rowid').fetchall()
        held=[(key,json.loads(request)) for key,package,request in rows
              if source_content(package)[2]==content and not self.before_import_retry(self.get(key))]
        consumed={spec.get('continue_imported_from') for _,spec in held}
        leaves=[key for key,_ in held if key not in consumed]
        return held,leaves

    def capability(self):
        return dict(version=1,storeId=self.store_id,enabled=self.config is not None,
            device=phone_of(self.config).board if self.config else 'C24C',account=account_of(self.config) if self.config else ACCOUNT,
            candidateOnly=True,integratedLiveValidated=False,
            publishing=False,messaging=False,desktopControl=False,
            reason='Creates a new three-slide draft from this saved revision, pastes its caption, and verifies save/reopen. '
                   'Start on @'+ACCOUNT+"'s Instagram profile. Media import adds images to Photos and replaces the phone clipboard."
                   if self.config else 'New-draft creation is disabled. Prepare the isolated C24C candidate first.')

    def supports(self,package):
        parsed=TransferPackage(package)
        assets,caption,_=source_content(package)
        lines=caption.split('\n')
        return (len(assets)==3 and len(set(map(lambda raw:hashlib.sha256(raw).hexdigest(),assets)))==3
                and 1<=len(lines)<=3 and all(0<len(line)<=50 for line in lines)
                and all(c=='\n' or 32<=ord(c)<=126 for c in caption))

    def content_reason(self,supported):
        return ('This saved revision fits the creation candidate.' if supported else
                'Creation currently requires three distinct slides and 1–3 nonempty ASCII caption lines up to 50 characters each. Nothing is truncated.')

    def eligibility(self,draft_id,revision):
        result=super().eligibility(draft_id,revision)
        content=source_content(self.drafts.export(draft_id,revision))[2]
        previous,leaves=self.content_holds(content)
        if previous:
            result.update(eligible=False,previousRunId=leaves[-1] if leaves else previous[-1][0],
                contentReason='This exact content already has a creation request. Select its saved result below; uncertain imports and Saves are never repeated.')
            if len(leaves)==1:
                try:self.imported_proof(leaves[0],result['packageSha256'])
                except DraftConflict:pass
                else:result.update(eligible=self.config is not None and result['supportedContent'],continueImportedFrom=leaves[0],
                    contentReason='Continue with the three confirmed imported images. Recheck the account and media; no Photos saves or prior actions are replayed.')
        return result

    def get(self,run_id):
        result=super().get(run_id)
        result['retryBeforeImportAllowed']=self.before_import_retry(result)
        result['continueImportedAllowed']=self.imported_checkpoint(result)
        verified=(result.get('workflow') or {}).get('verification')
        if result['terminal'] and isinstance(verified,dict) and 'finalInput' in verified:
            # The outer journal retains the creation phase. Present the later
            # verifier's release state as final, without rewriting that evidence.
            workflow=dict(result['workflow'])
            workflow['creationFinalInput']=workflow.get('finalInput')
            workflow['finalInput']=verified['finalInput']
            result['workflow']=workflow
        if not result['terminal']:
            result['reason']='Creating a new C24C draft from the saved slides and exact caption. No publishing or messaging.'
        child=self.folder/run_id/'verification/record.json'
        if not result['terminal'] and child.exists():
            progress=json.loads(read_journal(child))
            if progress.get('packageSha256')!=result['packageSha256']:
                raise ValueError('Verification progress belongs to different content.')
            workflow=dict(result['workflow'] or {})
            workflow['actions']=workflow.get('actions',[])+[{**a,'label':'verification-'+a['label']} for a in progress['actions']]
            workflow['cleanup']=progress.get('cleanup','unconfirmed')
            result.update(workflow=workflow,cleanup=workflow['cleanup'],reason='New media and caption were saved. Independently reopening and checking every slide and caption; nothing is published.')
        return result

    def start(self,spec):
        spec=self.validate_request(spec)
        if spec['store_id']!=self.store_id: raise DraftConflict('The candidate data store changed.')
        with self.lock:
            try: self.row(spec['id'])
            except KeyError:
                if not self.config: raise KernelSafetyError('New-draft phone execution is disabled.')
                content=source_content(self.drafts.export(spec['draft_id'],spec['revision']))[2]
                previous,leaves=self.content_holds(content)
                origin=spec.get('continue_imported_from')
                if origin:
                    if leaves!=[origin]: raise DraftConflict('Only the latest confirmed imported-media checkpoint can continue.')
                    self.imported_proof(origin,hashlib.sha256(self.drafts.export(spec['draft_id'],spec['revision'])).hexdigest())
                elif previous:
                    raise DraftConflict('This exact content already has a creation request. Retrieve its result; do not duplicate an uncertain import or Save.')
            return super().start(spec)

    def execute(self,folder,assets,caption,package_hash,cancelled):
        spec,package,digest=self.row(folder.name)
        if digest!=package_hash: raise ValueError('Creation source package changed.')
        imported=self.imported_proof(spec['continue_imported_from'],package_hash) if spec.get('continue_imported_from') else None
        parsed=TransferPackage(package)
        # Short fixed navigation heading; retain the user's full local title in
        # the immutable package. Image/caption checks establish content identity.
        parsed.title='Carousel draft'
        delivered=[]
        server=MediaTransferServer(parsed,self.config['mediaBind'],self.config['mediaPort'],self.config['mediaClient'],
            minutes=15,on_event=delivered.append)
        stopped=threading.Event()
        def serve():
            while not stopped.is_set() and server.clock()<server.deadline: server.handle_request()
        worker=threading.Thread(target=serve,daemon=True)
        try:
            worker.start()
            kernel=CreationKernel(self.config['api'],phone=phone_of(self.config));store=ObservationStore(folder/'observations.sqlite3',WindowsOcr(next_control=True),retained_limit=160)
            arguments=dict(account=account_of(self.config),package_hash=package_hash,cancelled=cancelled,allowed=allowed_of(self.config))
            creator=CreationWorkflow(folder,kernel,store,assets,caption,references(),
                self.config['kernelSha256'],self.config['expectedUid'],transfer_url=server.url,
                transfer_title=parsed.title,imported_media=imported,**arguments)
            result=creator.run()
        finally:
            stopped.set();server.close_clients()
            if worker.ident is not None: worker.join(timeout=4)
            server.server_close()
        result['mediaDelivery']=dict(stopped=not worker.is_alive(),events=delivered,
            imagesDelivered=sorted(server.served_images),photosSaveProvenByHttp=False)
        if (worker.is_alive() or result['state']!='created_unverified' or result.get('cleanup')!='confirmed'
                or result.get('evidenceExport')!='confirmed'
                or sorted(server.served_images)!=([] if imported else ['01.jpg','02.jpg','03.jpg'])):
            result.update(state='review_required',savedDraftVerified=False,
                error=result.get('error') or 'Creation or media cleanup is unconfirmed; no automatic retry.')
        else:
            child=folder/'verification';child.mkdir(exist_ok=False)
            # Independent bounded run: admit only a fresh exact account profile,
            # acquire a new lease, find the newly saved cover, and check all
            # media/caption twice. A completed import is never treated as proof.
            verified=Workflow(child,kernel,store,assets,caption,references(),
                self.config['kernelSha256'],self.config['expectedUid'],**arguments).run()
            result['creationState']='created_unverified';result['verification']=verified
            result['actions'] += [{**a,'label':'verification-'+a['label']} for a in verified['actions']]
            result['observations'] += [{**e,'frame':'verification/'+e['frame']} for e in verified['observations']]
            result.update(state=verified['state'],savedDraftVerified=verified['savedDraftVerified'],
                cleanup=verified['cleanup'],evidenceExport=verified.get('evidenceExport','failed'),
                createdDraftVerified=verified['savedDraftVerified'],
                meaning='New saved-revision media imported, ordered, caption pasted exactly, draft saved and independently reopened. No publication or app-restart persistence claim.')
            if verified.get('error'): result['error']=verified['error']
        atomic_json(folder/'record.json',result)
        return result
