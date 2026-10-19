"""One explicit diagnostic finish of attempt 14; never resume its saved job.

All prior media/paste answers must be known, with no OK or Save sent. The
ordinary product details and reopen verifiers still require the exact caption.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import uuid

record=Path(__file__).resolve().parent;root=record.parents[1];sys.path.insert(0,str(root/'tools'))
from farm_draft_runs import source_content,ACCOUNT
from farm_draft_creation import CreationWorkflow
from farm_draft_workflow import Workflow,references,atomic_json,centre
from farm_creation_layout import require,control,caption_editor
from farm_draft_transport import CreationKernel
from farm_observations import ObservationStore
from farm_live_verification import idle
from imouse_social_automation import LIVE_TEST_DEVICE_ID

folder=record/'caption-recovery'
if folder.exists():raise RuntimeError('The recovery already exists; retain its outcome instead of repeating it.')
prior=json.loads((record/'live-attempt-14/result.json').read_bytes())['run'];w=prior['workflow']
backend=root/'output/candidate-runs/farm-new-draft-20261019/backend'
old=backend/'draft-creations'/prior['id']/'record.json'
with sqlite3.connect(backend/'draft-creations/runs.db') as db:
    spec,package,digest=db.execute('SELECT request,package,package_hash FROM runs WHERE id=?',(prior['id'],)).fetchone()
with sqlite3.connect(backend/'jobs.db') as db:
    job=json.loads(db.execute('SELECT record FROM farm_jobs WHERE id=?',(prior['id'],)).fetchone()[0])
require(job['terminal'] and job['result']['recordSha256']==hashlib.sha256(old.read_bytes()).hexdigest(),'Prior journal changed.')
require(hashlib.sha256(package).hexdigest()==digest==prior['packageSha256'],'Prior package changed.')
require(prior['terminal'] and prior['state']=='review_required' and w['source']=='candidate_phone_workflow'
    and w['cleanup']=='confirmed' and w['evidenceExport']=='confirmed','Prior cleanup is unconfirmed.')
require(all(c['state'] in ('answered','not_sent') for c in w['commands']) and all(a['state']=='answered' for a in w['actions']),'An earlier outcome is unknown.')
answered={c['purpose'] for c in w['commands'] if c['state']=='answered'}
require({'prepared-slide-2','prepared-slide-3','prepared-details','paste-exact-caption'}<=answered,'The exact media/paste checkpoint is missing.')
require(not any(c['state']!='not_sent' and ('save-once' in c['purpose'] or c['purpose'] in ('confirm-pasted-caption','close-caption-editor')) for c in w['commands']),'OK or Save may already have been sent.')
require(w['observations'][-1]['role']=='caption_filled','This is not the reviewed Caption hold.')
e=w['observations'][-1]['observation'];assets,caption,_=source_content(package)
config=json.loads((record/'creation-config.json').read_bytes())
kernel=CreationKernel(config['api']);state=kernel.input_status().get(LIVE_TEST_DEVICE_ID)
receiver=kernel.kernel_status()['receivers'][0]
require(idle(state) and state['generation']==w['finalInput']['generation']
    and receiver['receiver_pid']==e['receiverPid'] and receiver['frame_session']==e['frameEvidence']['session'],'Phone context changed.')
raw,_=kernel.shot('C24C');caption_editor(ObservationStore(record/'caption-admission.sqlite3').ocr.read(raw),None,raw)
folder.mkdir();atomic_json(folder/'intent.json',dict(id=str(uuid.uuid4()),priorRunId=prior['id'],priorRecordSha256=job['result']['recordSha256'],
    expectedGeneration=state['generation'],packageSha256=digest,publishing=False,messaging=False,desktopControl=False))

class FinishCaption(CreationWorkflow):
    def run(self):
        try:
            self.identity=self.runtime()
            require(self.kernel.input_status()[LIVE_TEST_DEVICE_ID]==state,'Ownership changed before admission.')
            self.record['cleanup']='unconfirmed';self.save();self.owned.acquire()
            require(self.owned.generation==state['generation'] and self.owned.stream[1]==e['receiverPid']
                and self.owned.stream[3]==e['frameEvidence']['session'],'Ownership changed while acquiring.')
            self.record['mode']='explicit_reviewed_caption_finish';self.phase('finish-caption')
            self.command('/mouse/reset',purpose='initial_pointer_reset')
            self.step('close-caption-editor','caption_pasted_editor',point=lambda v,f:centre(control(f,'ok')))
            self.observe('details')  # Exact visible lines and matching first media, with no caret.
            self.action('recovery-back','back_to_editor','details')
            self.action('recovery-exit','request_save','editor',3)
            self.action('recovery-save-once','save_draft','save_prompt')
            self.action('return-profile','leave_picker','picker');self.observe('profile')
            self.record.update(state='created_unverified')
        except BaseException as error:self.record.update(state='review_required',error=type(error).__name__+': '+str(error))
        finally:self.finish()
        return self.record

store=ObservationStore(folder/'observations.sqlite3',retained_limit=160)
args=dict(account=ACCOUNT,package_hash=digest)
workflow=FinishCaption(folder,kernel,store,assets,caption,references(),config['kernelSha256'],config['expectedUid'],
    transfer_url='unused',transfer_title='unused',**args)
result=workflow.run()
require(result['state']=='created_unverified' and result['cleanup']=='confirmed',result.get('error','Finish failed.'))
child=folder/'verification';child.mkdir()
verified=Workflow(child,kernel,store,assets,caption,references(),config['kernelSha256'],config['expectedUid'],**args).run()
atomic_json(folder/'result.json',dict(priorRunId=prior['id'],finish=result,verification=verified,
    accepted=verified['savedDraftVerified'],originalJobUnchanged=hashlib.sha256(old.read_bytes()).hexdigest()==job['result']['recordSha256']))
require(verified['savedDraftVerified'],'The independent verifier held; review its saved outcome.')
print(json.dumps(dict(accepted=True,originalJobUnchanged=True,photosReimported=False)))
