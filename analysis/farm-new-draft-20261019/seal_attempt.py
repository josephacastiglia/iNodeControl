"""Seal a fresh candidate attempt, retaining every earlier failure. Read-only phone preflight."""
import ast,hashlib,json,sys
from pathlib import Path
record=Path(__file__).resolve().parent;root=record.parents[1];sys.path.insert(0,str(root/'tools'))
from farm_live_verification import ReadOnlyKernel,validate_runtime,idle
from imouse_social_automation import LIVE_TEST_DEVICE_ID
from farm_observations import WindowsOcr,classify
from farm_creation_layout import home,empty_search,control,test_video_preview,restored_app_search
from farm_draft_creation import CreationWorkflow
from farm_draft_runs import source_content
from farm_creation_runs import CreationRuns
attempt=int(sys.argv[1]);assert 4<=attempt<=18
prep=json.loads((record/'preparation.json').read_text(encoding='utf-8'));processes=json.loads((record/'processes.json').read_text(encoding='utf-8-sig'))
k=ReadOnlyKernel('http://127.0.0.1:9916/api');s=k.kernel_status();assert validate_runtime(s,k.devices(),prep['kernelSha256'],prep['expectedUid'])[0]==processes['kernel']['pid'];assert s['receivers'][0]['receiver_pid']==43232 and s['receivers'][0]['live'];assert idle(k.input_status()[LIVE_TEST_DEVICE_ID])
raw,_=k.shot('C24C');text=WindowsOcr().read(raw);c=classify(text,dict(platform='instagram',account='xs.halle.xo',caption=prep['caption']),raw)
state='exact_profile' if c['screen']=='profile' and c['accountStatus']=='exact_text_match' else None
if state is None:
 for name,check in [('home',lambda:home(text,raw)),('empty_ios_search',lambda:empty_search(text,raw)),('restored_app_search',lambda:restored_app_search(text)),('instagram_feed',lambda:all(control(raw,n) for n in ('instagram_logo','feed_home','feed_reels','feed_search'))),('readonly_test_preview',lambda:test_video_preview(text))]:
  try:check();state=name;break
  except Exception:pass
if state is None:
 assets,caption,_=source_content((record/'new-carousel.zip').read_bytes())
 workflow=object.__new__(CreationWorkflow);workflow.assets=assets;workflow.caption=caption;workflow.title='Carousel draft';workflow.package_hash=prep['packageSha256']
 for number in (1,2,3):
  try:workflow.verify_screen('transfer_slide',dict(text=text,result={}),raw,number);state='retained_transfer_slide';break
  except Exception:pass
if state is None:
 assets,_,_=source_content((record/'new-carousel.zip').read_bytes())
 value=json.loads((record/('live-attempt-%d/result.json'%(attempt-1))).read_bytes())['run']
 from farm_creation_layout import picker_grid
 assert CreationRuns.imported_checkpoint(value)
 assert value['packageSha256']==prep['packageSha256']
 assert k.input_status()[LIVE_TEST_DEVICE_ID]['generation']==value['workflow']['finalInput']['generation']
 purposes={c.get('purpose') for c in value['workflow']['commands'] if c.get('state')=='answered'}
 selected=([1] if 'enable-multiple-selection' in purposes else [])+[n for n in (2,3) if 'select-slide-'+str(n) in purposes]
 cells=picker_grid(raw,text,assets,selected)
 if selected:
  from farm_creation_layout import selected_badges
  selected_badges(raw,text,cells,selected)
 state='confirmed_import_picker'
assert state,'Phone is not at a supported safe entry state.'
for node in ast.walk(ast.parse((root/'tools/imouse_farm_server.py').read_text(encoding='utf-8'))):
 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='source_hash' for t in node.targets):names=ast.literal_eval(next(n for n in ast.walk(node.value) if isinstance(n,ast.Tuple)));break
snapshot=record/('attempt-%d-source'%attempt);snapshot.mkdir(exist_ok=False)
for name in names:(snapshot/name).write_bytes((root/'tools'/name).read_bytes())
prep['backendSourceHash']=hashlib.sha256(b''.join((root/'tools'/name).read_bytes() for name in names)).hexdigest();assert hashlib.sha256(Path(prep['nativeAssembly']).read_bytes()).hexdigest()==prep['nativeSha256']
(record/'preparation.json').write_text(json.dumps(prep,indent=2),encoding='utf-8');(record/('attempt-%d-preparation.json'%attempt)).write_text(json.dumps(prep,indent=2),encoding='utf-8')
options=dict(output=str(record/('live-attempt-%d'%attempt)),assembly=prep['nativeAssembly'],nativeSha256=prep['nativeSha256'],backendSourceHash=prep['backendSourceHash'],draftId=prep['draftId'],revision=prep['revision'],dataDirectory=prep.get('nativeDataDirectory',str(record/'live-attempt-1/data')))
(record/('live-attempt-%d.options.json'%attempt)).write_text(json.dumps(options,indent=2),encoding='utf-8')
print(json.dumps(dict(ready=True,phoneState=state,free=True,receiverUnchanged=True,phoneInput=False)))
