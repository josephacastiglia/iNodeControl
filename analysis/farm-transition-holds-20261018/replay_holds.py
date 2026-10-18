"""Offline replay of the five holds; never imports or calls a phone transport.

Windows OCR re-reads checksum-verified archived frames. A virtual observer/clock
exercises the read-only settler; historical frames are NOT fresh phone evidence.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from farm_observations import WindowsOcr
from farm_transitions import wait_for_transition

CASES = {
    '04-create-sheet': ('create',None,['04-post-picker/fresh.png','05-open-post-picker/fresh.png']),
    '05-picker-indicator': ('picker',None,['05-open-post-picker/after-first.png','05-open-post-picker/after.png',
                                         '06-open-drafts/before.png','07-drafts-from-settled-picker/fresh.png']),
    '06-new-picker-pair': ('picker',None,['06-open-drafts/before.png','07-drafts-from-settled-picker/fresh.png']),
    '08-editor-suggestion': ('editor',1,['08-open-test-draft/after-first.png','08-open-test-draft/after.png','09-inspect-second-slide/fresh.png']),
    '11-exact-next': ('editor',3,['11-caption-details/fresh.png','12-caption-with-label-crop/fresh.png']),
}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,default=ROOT.parent/'iMouseXP-2.0-evidence-archive/20261018-farm-live-layout')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=False)
    inventory=json.loads((args.archive/'SHA256SUMS.json').read_text(encoding='utf-8-sig'))
    hashes={row['path']:row['sha256'] for row in inventory['files']}
    def read(relative):
        raw=(args.archive/relative).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=hashes[relative]: raise ValueError('Archived input checksum mismatch: '+relative)
        return raw
    with zipfile.ZipFile(io.BytesIO(read('inputs/test-carousel.zip'))) as package:
        manifest=json.loads(package.read('manifest.json')); assets=[package.read(a['file']) for a in manifest['assets']]
    ocr=WindowsOcr(); cache={}; output=[]
    for name,(stage,index,paths) in CASES.items():
        events=[]; observations={}; tick=[0.]; count=[0]
        def capture():
            path=paths[count[0]]; raw=read('run/'+path)
            if path not in cache: cache[path]=ocr.read(raw)
            text=copy.deepcopy(cache[path]); count[0]+=1; tick[0]+=.1
            digest=hashlib.sha256(raw).hexdigest(); key=str(uuid.uuid4())
            value=dict(id=key,state='observed',freshness='recent',stable=True,inputSettled=True,
                expected=dict(device_id='C24C',platform='instagram',account='fixture.account',caption=''),
                source='simulation',observerSession='offline-replay',resolvedDeviceId='C24C',receiverPid=1,inputGeneration=1,
                ownershipEvidence=dict(runId=name,source='owned_capture_guard',generation=1,authenticatedBeforeAndAfter=True),
                frameEvidence=dict(pairedMetadata=True,session='offline-replay',sequence=count[0]),
                frameSha256=digest,reviewFrameSha256=digest,evidenceRecordSha256=digest,text=text)
            observations[key]=(value,raw); return value,raw
        def pause(seconds): tick[0]+=seconds
        try:
            _,_,decision=wait_for_transition(stage,capture,lambda:None,lambda key:observations[key],
                assets=assets,index=index,require_next=name=='11-exact-next',journal=events.append,
                monotonic=lambda:tick[0],pause=pause)
            result=dict(case=name,status='replay_passed',decision=decision)
        except Exception as error:
            result=dict(case=name,status='held',error=str(error))
        output.append({**result,'captures':count[0],'events':events,'inputs':paths})
    record=dict(source='retained_fixture_replay',freshPhoneAcceptance=False,clock='virtual',
                phoneInput=False,archive=str(args.archive),cases=output)
    (args.output/'results.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    (args.output/'ocr.json').write_text(json.dumps(cache,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([dict(case=r['case'],status=r['status'],captures=r['captures'],error=r.get('error')) for r in output]))
    return 0 if all(r['status']=='replay_passed' for r in output) else 2


if __name__=='__main__': raise SystemExit(main())
