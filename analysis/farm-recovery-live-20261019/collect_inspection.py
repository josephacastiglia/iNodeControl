"""Local acceptance records only; does not connect to or control the phone."""
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
attempt=int(sys.argv[1]); checks=[]
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def check(name,passed):
    checks.append(dict(name=name,passed=bool(passed)))
    if not passed:raise AssertionError(name)
prep=load(HERE/'preparation.json')
value=load(HERE/f'native-inspection-{attempt}/result.json')['run']
workflow=value['workflow'];folder=Path(prep['backendData'])/'draft-recoveries'/value['id']
check('Terminal live saved-draft observation',value['terminal'] and value['state']=='verified' and value['savedDraftVerified']
    and workflow['source']=='candidate_phone_workflow' and workflow['mode']=='inspect_saved_draft')
check('Confirmed cleanup/evidence export',workflow['cleanup']=='confirmed' and workflow['evidenceExport']=='confirmed')
expected=['inspect-open-create','inspect-choose-post','inspect-open-library','inspect-open-draft','inspect-slide-2','inspect-slide-3','inspect-details']
check('Exactly seven answered inspection actions',[a['label'] for a in workflow['actions']]==expected and all(a['state']=='answered' for a in workflow['actions']))
check('No Save/import/typing command',all(c['fun'] in ('/mouse/move','/mouse/reset','/mouse/click','/mouse/swipe')
    and c['state']=='answered' and c['purpose'] in expected+['initial_pointer_reset','fresh_frame_challenge','park_after_answered_action'] for c in workflow['commands']))
check('Fixed source/revision/package binding',value['request']['creation_id']==prep['creationId']
    and value['request']['creation_record_sha256']==prep['sourceProof']['creationRecordSha256']
    and value['packageSha256']==prep['packageSha256'] and value['request']['revision']==prep['revision'])
check('Original creation bytes unchanged',sha((Path(prep['backendData'])/'draft-creations'/prep['creationId']/'record.json').read_bytes())==prep['sourceProof']['creationRecordSha256'])
images=[]
for entry in workflow['observations']:
    if entry['state']!='observed':continue
    frame=(folder/entry['frame']).read_bytes()
    check('Retained frame '+entry['observationId'],sha(frame)==entry['observation']['reviewFrameSha256'])
    check('C24C-only frame '+entry['observationId'],entry['observation']['resolvedDeviceId']==prep['expectedDeviceId'])
    images.append(dict(id=entry['observationId'],role=entry['role'],sha256=sha(frame)))
check('All three full-size slides checked',all(any(e['role']=='editor' and e.get('index')==index and e.get('state')=='observed' for e in workflow['observations']) for index in (1,2,3)))
details=[e for e in workflow['observations'] if e['role']=='details' and e.get('state')=='observed']
check('Exact visible full caption',details and all(e['screenCheck']['status']=='exact_visible_lines' for e in details))
check('No changed scope or restart claim',value['inspectionOnly'] and not value['originalOutcomeChanged'] and not value['appRestartVerified']
    and not any(value[k] for k in ('publishing','messaging','desktopControl','automaticResume')))
driver=load(HERE/f'native-inspection-{attempt}/checks.json')
check('Every native driver assertion passed',all(c['pass'] for c in driver))
report=dict(accepted=True,attempt=attempt,id=value['id'],checks=checks,retainedFrames=images,
    semanticActions=len(workflow['actions']),nativeAssertions=len(driver),finalScreen=workflow['finalScreen'],
    appRestartVerified=False,sourceCreationUnchanged=True,publishing=False,messaging=False,desktopControl=False,
    meaning='A unique matching saved carousel was inspected with no Save/import/typing; original outcome unchanged. No app-restart claim.')
(HERE/f'acceptance-{attempt}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(dict(accepted=True,id=value['id'],checks=len(checks),retainedFrames=len(images),nativeAssertions=len(driver))))
