"""Collect retained acceptance evidence. No sockets or phone commands."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

record=Path(__file__).resolve().parent
root=record.parents[1]
attempt=int(sys.argv[1])
value=json.loads((record/f'live-attempt-{attempt}/result.json').read_bytes())['run']
folder=root/'output/candidate-runs/farm-new-draft-20261019/backend/draft-creations'
checks=[]
def check(name,passed):
    checks.append(dict(name=name,passed=bool(passed)))
    if not passed:raise AssertionError(name)
def sha(raw):return hashlib.sha256(raw).hexdigest()
workflow=value['workflow']
check('Terminal new draft verified',value['terminal'] and value['state']=='verified'
    and value['savedDraftVerified'] and workflow['createdDraftVerified'])
check('Exact designated account',workflow['account']=='xs.halle.xo')
check('Independent verifier accepted',workflow['verification']['savedDraftVerified']
    and workflow['verification']['source']=='candidate_phone_workflow')
check('Confirmed lease and evidence cleanup',workflow['cleanup']=='confirmed' and workflow['evidenceExport']=='confirmed')
check('No uncertain semantic action',all(a['state']=='answered' for a in workflow['actions']))
check('No uncertain command',all(c['state'] in ('answered','not_sent') for c in workflow['commands']))
check('Media listener stopped',workflow['mediaDelivery']['stopped'])
check('Copy/Paste caption path',workflow['captionMethod']=='verified_safari_copy_and_instagram_paste')
check('Draft-only result',not any(value[k] for k in ('publishing','messaging','desktopControl','automaticResume')))
chain=[];key=value['id']
with sqlite3.connect(folder/'runs.db') as db:
    while key:
        check('Acyclic explicit request history',key not in [r['id'] for r in chain])
        request,package,digest=db.execute('SELECT request,package,package_hash FROM runs WHERE id=?',(key,)).fetchone()
        request=json.loads(request);w=json.loads((folder/key/'record.json').read_bytes())
        check('Immutable source package '+key[:8],sha(package)==digest==value['packageSha256'])
        check('Prior command outcomes known '+key[:8],all(c['state'] in ('answered','not_sent') for c in w['commands']))
        check('Prior cleanup confirmed '+key[:8],w['cleanup']=='confirmed' and w['evidenceExport']=='confirmed')
        chain.append(dict(id=key,record=w,request=request))
        key=request.get('continue_imported_from')
photo_saves=[c['purpose'] for r in chain for c in r['record']['commands'] if c.get('state')=='answered' and c['purpose'].startswith('save-photo-')]
check('Exactly three Photos saves across the whole history',sorted(photo_saves)==['save-photo-1','save-photo-2','save-photo-3'])
images=[]
for row in chain:
    for entry in row['record']['observations']:
        if entry['state']!='observed':continue
        raw=(folder/row['id']/entry['frame']).read_bytes()
        check('Retained frame '+entry['observationId'],sha(raw)==entry['observation']['reviewFrameSha256'])
        check('C24C capture '+entry['observationId'],entry['observation']['resolvedDeviceId']=='86:1D:4A:04:2F:F6')
        images.append(dict(runId=row['id'],observationId=entry['observationId'],sha256=sha(raw)))
controls=workflow['verification']['actions']
check('Both verifier Save actions answered',sum(a['kind']=='save_draft' and a['state']=='answered' for a in controls)==2)
check('All three slides checked in both verifier passes',all(any(e['role']=='editor' and e['index']==n and e.get('state')=='observed'
    for e in workflow['verification']['observations']) for n in (1,2,3)))
details=[e for e in workflow['verification']['observations'] if e['role']=='details' and e.get('state')=='observed']
check('Exact caption in both verifier passes',len(details)>=2 and all(e.get('screenCheck',{}).get('status')=='exact_visible_lines' for e in details))
driver=json.loads((record/f'live-attempt-{attempt}/checks.json').read_bytes())
check('Every native driver assertion passed',all(c['pass'] for c in driver))
report=dict(accepted=True,attempt=attempt,runId=value['id'],packageSha256=value['packageSha256'],
    checks=checks,history=[dict(id=r['id'],request=r['request']) for r in reversed(chain)],
    photosSaves=len(photo_saves),images=images,nativeAssertions=len(driver),semanticActions=len(workflow['actions']),
    meaning='New saved-revision media, exact caption and three-slide order verified through draft creation and independent reopen. Scoped to C24C and the designated Instagram account; no publication or app-restart persistence claim.')
(record/f'acceptance-attempt-{attempt}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(dict(accepted=True,checks=len(checks),images=len(images),nativeAssertions=len(driver),history=len(chain))))
