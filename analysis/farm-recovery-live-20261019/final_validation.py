"""Verify this completed window from files only; no sockets or desktop control."""
import hashlib
import io
import json
from pathlib import Path
from PIL import Image

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
prep=load(HERE/'preparation.json')
offline=load(ROOT/'analysis/farm-recovery-20261019/validation.json')
checks=[]
def check(name,passed):
    checks.append(dict(name=name,passed=bool(passed)))
    if not passed:raise AssertionError(name)
check('Original native assembly and kernel unchanged',sha(Path(prep['assembly']))==prep['nativeSha256'] and sha(Path(prep['kernel']).with_suffix('.dll'))==prep['kernelSha256'])
check('All offline-validated product source unchanged',all(sha(ROOT/name)==digest for name,digest in offline['productSourceFiles'].items()))
copied=load(ROOT/'analysis/farm-recovery-20261019/copied-data.json')
check('Every original source-data file unchanged',all(sha(Path(copied['source'])/name)==digest for name,digest in copied['sha256'].items()))
check('Four acceptance records pass',all(load(HERE/f'acceptance-{i}.json')['accepted'] for i in (1,2,3,4)))
runs={i:load(HERE/f'native-inspection-{i}/result.json')['run'] for i in (1,2,3,4)}
check('Four distinct explicit requests',len({v['id'] for v in runs.values()})==4)
check('Three full inspections and one deliberate stop',all(runs[i]['savedDraftVerified'] for i in (1,2,4)) and runs[3]['jobStatus']=='cancelled' and not runs[3]['savedDraftVerified'])
check('Every request ended with confirmed cleanup',all(v['terminal'] and v['cleanup']=='confirmed' for v in runs.values()))
check('All requests retain draft-only scope',all(v['inspectionOnly'] and not any(v[k] for k in ('publishing','messaging','desktopControl','originalOutcomeChanged','automaticResume','appRestartVerified')) for v in runs.values()))
check('No Save import or text commands',all(c['fun'] in ('/mouse/reset','/mouse/move','/mouse/click','/mouse/swipe') for v in runs.values() for c in v['workflow']['commands']))
frames=[]
for attempt,value in runs.items():
    folder=Path(prep['backendData'])/'draft-recoveries'/value['id']
    for entry in value['workflow']['observations']:
        if entry['state']!='observed':continue
        path=folder/entry['frame']
        check(f'Attempt {attempt} frame {entry["observationId"]}',sha(path)==entry['observation']['reviewFrameSha256'] and entry['observation']['resolvedDeviceId']==prep['expectedDeviceId'])
        frames.append(dict(attempt=attempt,id=entry['observationId'],role=entry['role'],sha256=sha(path)))
events=load(HERE/'native-inspection-2/http-events.json')
check('One admission despite two suppressed replies',sum(e['method']=='POST' for e in events)==1 and sum(e['suppressed'] for e in events)==2)
reopened=load(HERE/'native-result-recovery/http-events.json')
check('Reopened native result used GETs only',reopened and all(e['method']=='GET' and not e['suppressed'] for e in reopened))
check('Native result recovery assertions pass',all(c['pass'] for c in load(HERE/'native-result-recovery/checks.json')))
check('Backend restart did not restart receivers or change input',load(HERE/'backend-restart.json')['passed'] and load(HERE/'durable-after.json')['unchanged'])
check('Stopped request stayed terminal beside a new live worker',load(HERE/'stopped-during-new-run.json')['passed'])
final=load(HERE/'final-live-state.json')
phone=final['input']['phones'][0]
check('C24C free before shutdown',phone['id']==prep['expectedDeviceId'] and not any(phone[k] for k in ('owned','active','stopped','releasing','release_failed')))
check('C24C-only receiver and input scope throughout',final['kernel']['allowed']==['C24C'] and len(final['kernel']['receivers'])==1 and final['kernel']['receivers'][0]['receiver_restarts']==0 and len(final['input']['phones'])==1)
restoration=load(HERE/'restoration.json')
check('Original stopped state restored',restoration['restored'] and not restoration['processes'] and not restoration['tcp'] and not restoration['udp'] and not restoration['installedReleaseStarted'])
check('All protected installed files unchanged',len(restoration['protectedFiles'])==25 and all(v['unchanged'] for v in restoration['protectedFiles']))
details=[e for e in runs[4]['workflow']['observations'] if e['state']=='observed' and e['role']=='details'][-1]
path=Path(prep['backendData'])/'draft-recoveries'/runs[4]['id']/details['frame']
with Image.open(io.BytesIO(path.read_bytes())) as image:image.convert('RGB').save(HERE/'review-final-details.png')
report=dict(passed=True,checks=checks,productSourceCommit='e066acccc6651a0f1b3212cdc50238845177e0db',
    nativeSha256=prep['nativeSha256'],kernelSha256=prep['kernelSha256'],backendSourceHash=prep['backendSourceHash'],
    inspections={str(i):dict(id=v['id'],state=v['state'],actions=len(v['workflow']['actions']),commands=len(v['workflow']['commands']),cleanup=v['cleanup'],nativeAssertions=len(load(HERE/f'native-inspection-{i}/checks.json'))) for i,v in runs.items()},
    retainedFrames=frames,successfulInspections=3,intentionallyStoppedInspections=1,
    nativeAssertions=sum(len(load(HERE/f'native-inspection-{i}/checks.json')) for i in runs)+len(load(HERE/'native-result-recovery/checks.json')),
    originalSourceFilesChecked=len(copied['sha256']),sourceCreationUnchanged=True,protectedFiles=25,
    appRestartEvidence='Operator replied ready after instruction to swipe Instagram away and relaunch; exact profile rechecked. No independent iOS process telemetry. Product keeps appRestartVerified false.',
    backendRestart='Graceful restart after terminal inspections; active-process-death coverage remains offline.',
    replyLoss='Controlled client receive failure after real successful backend response, not a claim of TCP packet loss.',
    finalPhoneScreen='carousel_details',finalGeneration=phone['generation'],initialStoppedStateRestored=True,
    publishing=False,messaging=False,desktopControl=False,FkaChanged=False,C241Input=False,installedReleaseChanged=False,
    scope='Same retained three-slide Instagram creation on C24C/@xs.halle.xo, not recurring execution or general unattended acceptance.')
(HERE/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(dict(passed=True,checks=len(checks),inspections=3,stopped=1,retainedFrames=len(frames),nativeAssertions=report['nativeAssertions'],sourceFiles=report['originalSourceFilesChecked'],generation=phone['generation'])))
