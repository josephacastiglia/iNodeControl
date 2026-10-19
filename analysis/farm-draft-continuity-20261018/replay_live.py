"""Evaluate the captured C24C run offline; never manufacture freshness or account continuity."""
import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];RUN=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from farm_observations import WindowsOcr,classify
from farm_draft_media import media_comparison
from farm_draft_verification import caption_comparison
with zipfile.ZipFile(ROOT/'analysis/farm-phone-transfer-20261017/test-carousel.zip') as z:
    manifest=json.loads(z.read('manifest.json'));assets=[z.read(row['file']) for row in manifest['assets']]
assert all(hashlib.sha256(a).hexdigest()==row['sha256'] for a,row in zip(assets,manifest['assets']))
results=[]
steps=[('04-account-before','after',None),('07-draft-library','after','draft_library_candidate'),
       ('09-slide-two','before','carousel_editor'),('09-slide-two','after','carousel_editor'),('10-slide-three','after','carousel_editor'),
       ('11-caption-details','after','carousel_details')]
for step,phase,layout in steps:
    raw=(RUN/step/(phase+'.png')).read_bytes();text=WindowsOcr().read(raw)
    (RUN/(step+'-'+phase+'-ocr.json')).write_text(json.dumps(text),encoding='utf-8')
    result=classify(text,dict(platform='instagram',account='xs.halle.xo',caption=manifest['caption']))
    media=media_comparison(raw,assets,layout)
    if layout in ('carousel_editor','carousel_details'): assert result['layout']==layout,result
    caption=caption_comparison(text,manifest['caption']) if layout=='carousel_details' else None
    results.append(dict(step=step,phase=phase,frameSha256=hashlib.sha256(raw).hexdigest(),screen=result['screen'],account=result['accountStatus'],media=media,caption=caption))
assert results[0]['account']=='exact_text_match'
assert results[1]['media']['matchedIndex']==1
assert results[1]['media']['libraryCell']==dict(row=1,column=2)
for i,row in enumerate(results[2:5],1):
    assert row['media']['matchedIndex']==i,row
    assert row['media']['position']==dict(status='visible_position',index=i,count=3)
assert results[5]['caption']['status']=='exact_visible_lines'
record=dict(results=results,allReopenedSlidesMatched=True,fullCaptionMatched=True,
            accountAfterCaptured=False,pairedFrameMetadata=False,savedDraftVerified=False,automaticInputAllowed=False,
            reason='Another controller acquired C24C before account-after. No input sent after the ownership preflight refused step 12.')
(RUN/'live-comparisons.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps({key:value for key,value in record.items() if key!='results'}))
