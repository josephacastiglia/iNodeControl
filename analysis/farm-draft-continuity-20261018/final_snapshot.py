import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];RUN=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from imouse_social_automation import IMouseKernel
k=IMouseKernel(); record=dict(phoneInput=False)
try:
    record['status']=k.kernel_status();record['input']=k.input_status()
    before=json.loads((RUN/'read-only-preflight.json').read_text(encoding='utf-8'))
    initial={r['deviceid']:r for r in before['status']['receivers']}
    record['receiverProcessesUnchanged']=all(initial[r['deviceid']]['receiver_pid']==r['receiver_pid'] for r in record['status']['receivers'])
    record['otherPhoneGenerationsUnchanged']=all(record['input'][i]['generation']==v['generation']
        for i,v in before['endInput'].items() if i != before['preflight']['resolved_id'])
    record['c24cOwnedAtEnd']=record['input'][before['preflight']['resolved_id']]['owned']
except Exception as error: record['error']=str(error)
record['audit']=k.audit_log
assert all(row['fun']=='/input/status' for row in k.audit_log)
(RUN/'final-rack-readonly.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps({key:record.get(key) for key in ('phoneInput','receiverProcessesUnchanged','otherPhoneGenerationsUnchanged','c24cOwnedAtEnd','error')}))
