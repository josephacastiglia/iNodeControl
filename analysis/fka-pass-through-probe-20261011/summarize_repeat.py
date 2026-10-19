"""Summarize recorded trials; visible results are explicitly manual transcriptions."""
import hashlib
import json
from pathlib import Path

record=Path(__file__).resolve().parent
repo=record.parents[1]
live=record/'live-repeat-20261011'
out=live/'RESULTS.json'
assert not out.exists(), 'Refusing to replace the result record'
phone='86:1D:4A:04:2F:F6'
provenance=json.loads((record/'provenance.json').read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
assert all(sha(repo/name)==digest for name,digest in provenance['source_sha256'].items())
assert all(sha(record/'build'/name)==digest for name,digest in provenance['build_sha256'].items())
trials=[]
for label,condition,visible in (
 ('r1-baseline','FKA On baseline','Hithere'),
 ('r1-after-shortcut','after one shortcut','Hi there'),
 ('r1-restored-baseline','physical FKA reset; shared middle baseline','Hithere'),
 ('r2-after-shortcut','after one shortcut','Hi there'),
 ('r2-restored-baseline','physical FKA reset','Hithere'),
):
    rows=[json.loads(line) for line in (live/label/'requests.jsonl').read_text(encoding='utf-8').splitlines()]
    sends=[r for r in rows if r.get('fun')=='/key/sendkey' and 'key' in r.get('data',{})]
    assert len(sends)==1 and sends[0]['data']['key']=='Hi there' and sends[0]['data']['id']==phone and sends[0]['response']['code']==0
    assert rows[-1]['capture_finished'] and not rows[-1]['capture_errors']
    waits=[r['wait_from_measurement_ms'] for r in rows if 'wait_from_measurement_ms' in r]
    assert 30000<=waits[-1]<31000
    assert (live/label/'after.png').exists()
    trials.append({'label':label,'condition':condition,'sent':'Hi there','visible':visible,'visible_evidence':'manual visual transcription of '+label+'/after.png','exact':visible=='Hi there','text_wait_ms':waits[-1],'text_request_elapsed_ms':sends[0]['elapsed_ms'],'no_retry':True})
all_requests=[]
for path in live.glob('*/requests.jsonl'):
    for line in path.read_text(encoding='utf-8').splitlines():
        row=json.loads(line)
        if row.get('fun'):
            assert row['data']['id']==phone, 'Unexpected test target'
            all_requests.append({'file':path.relative_to(live).as_posix(),'fun':row['fun'],'target':row['data']['id']})
text100='Hi there. '*9+'Hi there!?'
assert len(text100)==100
console=[]
for label,sent,visible,verdict in (
 ('console-short-button','Hi there','Hi there','passed once after shortcut in same field'),
 ('console-100-button',text100,text100.replace('Hi there','Hithere',1),'failed after app navigation without another shortcut'),
 ('console-direct-100-button',text100,text100,'passed once after shortcut in same field'),
 ('console-append-button',' Next.',text100,'unverified: no visible append or completion entry'),
):
    click=json.loads((live/label/'ui-click.json').read_text(encoding='utf-8'))
    assert click['text']==sent
    assert (live/label/'after.png').exists()
    states=[json.loads(line) for line in (live/label/'states.jsonl').read_text(encoding='utf-8').splitlines()]
    assert all(len(r['input']['phones'])==1 and r['input']['phones'][0]['id']==phone for r in states)
    console.append({'label':label,'sent':sent,'attempted_characters':len(sent),'visible_note_text':visible,'visible_evidence':'manual visual transcription of '+label+'/after.png','verdict':verdict,'mouse_click':click,'active_observed':any(r['input']['phones'][0]['active'] for r in states),'retry':False})
result={'API_unique_fields':trials,'shared_control':'r1-restored-baseline counted once, serves R1-C and R2-A','console_attempts':console,'mode_acknowledgement':'No named mode confirmed; operator reported yellow highlight only','test_API_requests':all_requests,'source_and_build_hashes_unchanged':True,'C241_test_input':'None; absent from test configuration and requests','typing_acceptance':'Open: persistence failed and append is unverified','restoration_record':'restoration-verified.json (verify separately before sealing)'}
out.write_text(json.dumps(result,indent=2),encoding='utf-8')
print('Five unique API fields and four button attempts recorded; source/build hashes unchanged.')
print('API timing:',[(t['label'],t['text_wait_ms'],t['text_request_elapsed_ms']) for t in trials])
print('Console active observed:',[(t['label'],t['active_observed']) for t in console])
