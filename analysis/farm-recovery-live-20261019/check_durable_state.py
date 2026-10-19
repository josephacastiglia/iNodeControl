"""Inspect retained results across a backend restart; never sends a phone command."""
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from farm_live_verification import ReadOnlyKernel, idle

phase=sys.argv[1]
if phase not in ('before','after'):raise ValueError('Choose before or after.')
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def call(path,body=None):
    if not path.startswith('/api/farm/draft-recoveries') and path!='/health':raise ValueError('Inspection routes only.')
    request=Request('http://127.0.0.1:9915'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=8) as reply:return json.load(reply)
prep=load(HERE/'preparation.json')
health=call('/health')
assert health['sourceHash']==prep['backendSourceHash'] and health['draftRecovery']['storeId']==prep['recoveryStoreId']
kernel=ReadOnlyKernel('http://127.0.0.1:9916/api')
status=kernel.kernel_status();state=kernel.input_status()[prep['expectedDeviceId']]
assert idle(state)
history=call('/api/farm/draft-recoveries?draft_id='+prep['draftId'])['runs']
values={row['id']:call('/api/farm/draft-recoveries/'+row['id'])['run'] for row in history}
assert values and all(v['terminal'] and v['cleanup']=='confirmed' for v in values.values())
records={key:sha((Path(prep['backendData'])/'draft-recoveries'/key/'record.json').read_bytes()) for key in values}
source=sha((Path(prep['backendData'])/'draft-creations'/prep['creationId']/'record.json').read_bytes())
assert source==prep['sourceProof']['creationRecordSha256']
record=dict(phase=phase,runs={key:dict(state=v['state'],jobStatus=v['jobStatus'],savedDraftVerified=v['savedDraftVerified'],commands=len(v['workflow']['commands']),recordSha256=records[key]) for key,v in values.items()},
    generation=state['generation'],kernelPid=status['process']['pid'],receiverPid=status['receivers'][0]['receiver_pid'],receiverRestarts=status['receivers'][0]['receiver_restarts'],
    sourceRecordSha256=source,phoneInput=False,desktopControl=False)
if phase=='after':
    before=load(HERE/'durable-before.json')
    assert all(record[k]==before[k] for k in ('runs','generation','kernelPid','receiverPid','receiverRestarts','sourceRecordSha256'))
    # This is an intentional idempotency check of the SAME retained request,
    # never a fresh request or automatic retry after an unknown phone action.
    original=load(HERE/'native-inspection-2/result.json')['run']
    duplicate=call('/api/farm/draft-recoveries',original['request'])['run']
    assert duplicate==values[original['id']]
    assert all(sha((Path(prep['backendData'])/'draft-recoveries'/key/'record.json').read_bytes())==digest for key,digest in records.items())
    after=kernel.input_status()[prep['expectedDeviceId']]
    assert idle(after) and after['generation']==state['generation']
    record.update(unchanged=True,duplicateRequestRetrieved=True,newAdmission=False)
(HERE/f'durable-{phase}.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(dict(phase=phase,runs=len(values),generation=state['generation'],unchanged=record.get('unchanged'),phoneInput=False)))
