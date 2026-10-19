"""Historical images only. No API or phone input; raw evidence remains private."""
import hashlib, io, json, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; RUN=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from farm_observations import WindowsOcr,classify
from farm_draft_media import media_comparison
PRIOR=ROOT/'analysis/farm-phone-transfer-20261017'
with zipfile.ZipFile(PRIOR/'test-carousel.zip') as z:
    manifest=json.loads(z.read('manifest.json')); assets=[z.read(row['file']) for row in manifest['assets']]
assert all(hashlib.sha256(a).hexdigest()==row['sha256'] for a,row in zip(assets,manifest['assets']))
results=[]
for step,layout,index in [('47-open-drafts-library','draft_library_candidate',1),
                          ('48-reopen-saved-draft','carousel_editor',1),
                          ('49-reopened-third-slide','carousel_editor',3),
                          ('54-final-drafts-library','draft_library_candidate',1)]:
    raw=(PRIOR/step/'after.png').read_bytes(); text=WindowsOcr().read(raw)
    (RUN/(step+'-ocr.json')).write_text(json.dumps(text),encoding='utf-8')
    screen=classify(text,dict(platform='instagram',account='test.account',caption=''))
    if layout=='carousel_editor': assert screen['layout']==layout,screen
    media=media_comparison(raw,assets,layout)
    assert media['matchedIndex']==index,media
    if layout=='carousel_editor': assert media['position']==dict(status='visible_position',index=index,count=3)
    results.append(dict(step=step,screen=screen['screen'],frameSha256=hashlib.sha256(raw).hexdigest(),media=media))
(RUN/'historical-replay.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps([dict(step=r['step'],screen=r['screen'],matched=r['media']['matchedIndex'],position=r['media'].get('position')) for r in results]))
print('Historical component comparisons only. Slide 2 full-size view, full account history and paired frame metadata are absent.')
