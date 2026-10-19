"""Offline rehearsal of the preserved three-slide test package; no network imports."""
import base64,hashlib,json,sys,time,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; RUN=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from farm_drafts import CarouselDrafts
from farm_draft_rehearsal import DraftRehearsals,SCENARIOS
from farm_test_network import allowed_ports
root=RUN/(sys.argv[1] if len(sys.argv)>1 else 'exercise'); root.mkdir(exist_ok=False)
drafts=CarouselDrafts(root/'drafts.db',root/'stage'); draft=drafts.create(str(uuid.uuid4()))
package=ROOT/'analysis/farm-phone-transfer-20261017/test-carousel.zip'
with zipfile.ZipFile(package) as files:
    manifest=json.loads(files.read('manifest.json'))
    for asset in manifest['assets']:
        draft=drafts.import_image(draft['id'],draft['revision'],asset['file'],base64.b64encode(files.read(asset['file'])).decode())
caption='iMouse carousel draft test.\nThree numbered slides in order: 1, 2, 3.\nDRAFT ONLY - do not publish.'
draft=drafts.save(draft['id'],draft['revision'],'Offline three-slide recovery',caption,draft['slideIds'])
store=DraftRehearsals(root/'rehearsals.db',drafts); results=[]
for scenario in SCENARIOS:
    start=time.monotonic(); result=store.run(dict(id=str(uuid.uuid4()),draft_id=draft['id'],revision=draft['revision'],scenario=scenario))
    (root/(scenario+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    expected='simulation_passed' if scenario=='normal' else 'review_required'
    assert result['state']==expected,(scenario,result['reason'])
    reasons={'save_reply_lost':'TimeoutError','reopen_reply_lost':'TimeoutError','permission_prompt':'dialog','account_changed':'Account boundary','stale_frame':'fresh','wrong_slide':'Full-size slide','wrong_caption':'caption','duplicate_cover':'ambiguous'}
    if scenario!='normal': assert reasons[scenario] in result['reason'],(scenario,result['reason'])
    assert result['cleanup']=='confirmed' and not result['savedDraftVerified']
    results.append(dict(scenario=scenario,state=result['state'],reason=result['reason'],seconds=round(time.monotonic()-start,3),
        captures=len(result['evidenceManifest']),actions=len(result['actions']),cleanup=result['cleanup']))
    if scenario in ('normal','save_reply_lost'):
        for obs,digest in result['evidenceManifest'].items():
            role=result['captureRoles'][obs]
            if role in ('save_prompt','library','reopened_caption'):
                (root/(scenario+'-'+role+'.png')).write_bytes(store.frame(result['id'],obs))
output=dict(sourcePackageSha256=hashlib.sha256(package.read_bytes()).hexdigest(),source='simulation',phoneCommands=0,results=results)
(root/'scenario-results.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
print(json.dumps(output))
