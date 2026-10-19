"""Check a deliberately stopped inspection from local evidence, without sockets."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
prep=load(HERE/'preparation.json')
value=load(HERE/'native-inspection-3/result.json')['run']
workflow=value['workflow']
events=load(HERE/'native-inspection-3/http-events.json')
checks=[]
def check(name,passed):
    checks.append(dict(name=name,passed=bool(passed)))
    if not passed:raise AssertionError(name)
check('Terminal cancellation is not verification',value['terminal'] and value['jobStatus']=='cancelled' and value['state']=='review_required' and not value['savedDraftVerified'])
check('Confirmed release and evidence export',workflow['cleanup']=='confirmed' and workflow['evidenceExport']=='confirmed')
check('Stopped after first action instead of finishing',workflow['actions'][0]['label']=='inspect-open-create' and workflow['actions'][0]['state']=='answered' and len(workflow['actions'])<7)
check('One admission and one store-bound cancellation',sum(e['method']=='POST' and e['path']=='/api/farm/draft-recoveries' for e in events)==1 and sum(e['method']=='POST' and e['path'].endswith('/cancel') for e in events)==1)
check('No Save import typing or unknown command',all(c['fun'] in ('/mouse/reset','/mouse/move','/mouse/click','/mouse/swipe') and c['state'] in ('answered','not_sent') for c in workflow['commands']))
check('No changed original outcome or automatic resume',not value['originalOutcomeChanged'] and not value['automaticResume'] and value['inspectionOnly'] and not value['appRestartVerified'])
source=Path(prep['backendData'])/'draft-creations'/prep['creationId']/'record.json'
check('Original creation bytes unchanged',hashlib.sha256(source.read_bytes()).hexdigest()==prep['sourceProof']['creationRecordSha256'])
driver=load(HERE/'native-inspection-3/checks.json')
check('All native Stop assertions pass',all(c['pass'] for c in driver))
report=dict(accepted=True,expectedCancellation=True,id=value['id'],checks=checks,actions=workflow['actions'],commands=len(workflow['commands']),nativeAssertions=len(driver),finalScreen='interrupted_create_flow',
    cleanup=workflow['cleanup'],automaticReplay=False,originalOutcomeChanged=False,publishing=False,messaging=False,desktopControl=False)
(HERE/'acceptance-3.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(dict(accepted=True,id=value['id'],checks=len(checks),actions=len(workflow['actions']),nativeAssertions=len(driver),cleanup=workflow['cleanup'])))
