"""Explicit candidate admission for new media -> verified Instagram draft."""
import hashlib
import json
from pathlib import Path
import threading

from farm_draft_runs import DraftRuns, source_content, load_config, ACCOUNT
from farm_drafts import DraftConflict
from farm_draft_creation import CreationWorkflow
from farm_draft_workflow import Workflow, references, atomic_json
from farm_draft_transport import CreationKernel
from farm_media_transfer import MediaTransferServer, TransferPackage, checked_address
from farm_observations import ObservationStore
from imouse_social_automation import KernelSafetyError


def creation_config(path,mode):
    if path is None: return None
    value=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(value,dict) or set(value)!={'version','api','kernelSha256','expectedUid','mediaBind','mediaClient','mediaPort'}:
        raise ValueError('Creation needs an explicit isolated kernel and C24C-only media configuration.')
    # Reuse the same strict kernel identity rules, without weakening the old route.
    core={k:v for k,v in value.items() if not k.startswith('media')}
    import tempfile
    with tempfile.TemporaryDirectory(prefix='farm-creation-config-') as directory:
        file=Path(directory)/'config.json';file.write_text(json.dumps(core),encoding='utf-8')
        load_config(file,mode)
    value['mediaBind']=checked_address(value['mediaBind']);value['mediaClient']=checked_address(value['mediaClient'])
    if value['mediaBind']==value['mediaClient'] or type(value['mediaPort']) is not int or value['mediaPort']!=9917:
        raise ValueError('Use a separate C24C LAN address and the dedicated media port 9917.')
    return value


class CreationRuns(DraftRuns):
    action_name='create-phone-draft'

    def capability(self):
        return dict(version=1,storeId=self.store_id,enabled=self.config is not None,
            device='C24C',account=ACCOUNT,candidateOnly=True,integratedLiveValidated=False,
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
        with self.connect() as db: rows=db.execute('SELECT id,package FROM runs').fetchall()
        previous=[key for key,package in rows if source_content(package)[2]==content]
        if previous:
            result.update(eligible=False,previousRunId=previous[0],
                contentReason='This exact content already has a creation request. Select its saved result below; uncertain imports and Saves are never repeated.')
        return result

    def get(self,run_id):
        result=super().get(run_id)
        child=self.folder/run_id/'verification/record.json'
        if not result['terminal'] and child.exists():
            progress=json.loads(child.read_bytes())
            if progress.get('packageSha256')!=result['packageSha256']:
                raise ValueError('Verification progress belongs to different content.')
            workflow=dict(result['workflow'] or {})
            workflow['actions']=workflow.get('actions',[])+[{**a,'label':'verification-'+a['label']} for a in progress['actions']]
            result.update(workflow=workflow,reason='New media and caption were saved. Independently reopening and checking every slide and caption; nothing is published.')
        return result

    def start(self,spec):
        spec=self.validate_request(spec)
        if spec['store_id']!=self.store_id: raise DraftConflict('The candidate data store changed.')
        with self.lock:
            try: self.row(spec['id'])
            except KeyError:
                if not self.config: raise KernelSafetyError('New-draft phone execution is disabled.')
                content=source_content(self.drafts.export(spec['draft_id'],spec['revision']))[2]
                with self.connect() as db: packages=db.execute('SELECT package FROM runs').fetchall()
                if any(source_content(row[0])[2]==content for row in packages):
                    raise DraftConflict('This exact content already has a creation request. Retrieve its result; do not duplicate an uncertain import or Save.')
            return super().start(spec)

    def execute(self,folder,assets,caption,package_hash,cancelled):
        spec,package,digest=self.row(folder.name)
        if digest!=package_hash: raise ValueError('Creation source package changed.')
        parsed=TransferPackage(package)
        # Short fixed navigation heading; retain the user's full local title in
        # the immutable package. Image/caption checks establish content identity.
        parsed.title='Carousel draft'
        delivered=[]
        server=MediaTransferServer(parsed,self.config['mediaBind'],9917,self.config['mediaClient'],
            minutes=15,on_event=delivered.append)
        stopped=threading.Event()
        def serve():
            while not stopped.is_set() and server.clock()<server.deadline: server.handle_request()
        worker=threading.Thread(target=serve,daemon=True)
        try:
            worker.start()
            kernel=CreationKernel(self.config['api']);store=ObservationStore(folder/'observations.sqlite3',retained_limit=160)
            arguments=dict(account=ACCOUNT,package_hash=package_hash,cancelled=cancelled)
            creator=CreationWorkflow(folder,kernel,store,assets,caption,references(),
                self.config['kernelSha256'],self.config['expectedUid'],transfer_url=server.url,
                transfer_title=parsed.title,**arguments)
            result=creator.run()
        finally:
            stopped.set();server.close_clients()
            if worker.ident is not None: worker.join(timeout=4)
            server.server_close()
        result['mediaDelivery']=dict(stopped=not worker.is_alive(),events=delivered,
            imagesDelivered=sorted(server.served_images),photosSaveProvenByHttp=False)
        if (worker.is_alive() or result['state']!='created_unverified' or result.get('cleanup')!='confirmed'
                or result.get('evidenceExport')!='confirmed' or sorted(server.served_images)!=['01.jpg','02.jpg','03.jpg']):
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
