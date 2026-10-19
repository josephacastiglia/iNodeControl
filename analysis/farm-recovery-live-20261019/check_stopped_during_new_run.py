"""Read a stopped request while a different live inspection owns the worker."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

HERE=Path(__file__).resolve().parent
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
prep=load(HERE/'preparation.json')
old=load(HERE/'native-inspection-3/result.json')['run']['id']
bookmark=load(Path(prep['runDirectory'])/'native-live-4-data/farm-pending-draft-inspection.json')
current=bookmark['Id']
assert old!=current
def get(key):
    with urlopen('http://127.0.0.1:9915/api/farm/draft-recoveries/'+key,timeout=5) as reply:return json.load(reply)['run']
active=get(current)
assert not active['terminal'], 'No active worker was observed; do not claim overlap coverage.'
path=Path(prep['backendData'])/'draft-recoveries'/old/'record.json'
before=hashlib.sha256(path.read_bytes()).hexdigest()
reads=[get(old) for _ in range(3)]
assert all(v['terminal'] and v['jobStatus']=='cancelled' and not v['savedDraftVerified'] for v in reads)
assert hashlib.sha256(path.read_bytes()).hexdigest()==before
report=dict(passed=True,stoppedId=old,currentId=current,currentWasRunning=True,reads=len(reads),stoppedRecordSha256=before,
    stoppedRecordUnchanged=True,phoneInput=False,desktopControl=False)
(HERE/'stopped-during-new-run.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
