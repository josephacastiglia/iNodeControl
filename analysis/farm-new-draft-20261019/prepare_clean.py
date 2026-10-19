"""Prepare one distinct local acceptance carousel through product APIs. No phone input."""
import base64
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import uuid
import sys

from PIL import Image,ImageDraw,ImageFont

record=Path(__file__).resolve().parent
final='--final' in sys.argv
prefix='final-clean' if final else 'clean'
intent=record/(prefix+'-preparation.intent.json')
if intent.exists():raise RuntimeError('The clean request already exists; recover its saved ID instead of creating another.')
prep=json.loads((record/'preparation.json').read_bytes())
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def request(path,value=None):
    req=urllib.request.Request('http://127.0.0.1:9915'+path,
        data=None if value is None else json.dumps(value).encode('utf-8'),
        headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:9915'})
    with opener.open(req,timeout=10) as response:return json.load(response)
health=request('/health')
assert health['sourceHash']==prep['backendSourceHash'] and health['draftCreation']['enabled']
assert json.loads((record/'live-attempt-13/result.json').read_bytes())['run']['savedDraftVerified']
if final:assert json.loads((record/'caption-recovery/result.json').read_bytes())['accepted']
draft_id=str(uuid.uuid4())
intent.write_text(json.dumps(dict(draftId=draft_id,phoneInput=False),indent=2),encoding='utf-8')
title='Fresh carousel final check' if final else 'Fresh carousel acceptance'
draft=request('/api/farm/drafts',dict(id=draft_id,title=title))['draft']
large=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',180)
heading=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',45)
body=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',35)
colors=('#8a2c8e','#9d6818','#226090') if final else ('#07508f','#b01d79','#097950')
for number,color in enumerate(colors,1):
    image=Image.new('RGB',(1080,1350),color);draw=ImageDraw.Draw(image)
    draw.rectangle((50,50,1030,1300),outline='white',width=5)
    draw.text((85,140),'FINAL DRAFT CHECK' if final else 'FRESH DRAFT CHECK',font=heading,fill='white')
    draw.text((85,300),str(number),font=large,fill='white')
    if final:
        for block in range(number):draw.rectangle((85+block*240,535,265+block*240,590),fill='white')
    draw.text((85,630),'SLIDE %d OF 3'%number,font=heading,fill='white')
    draw.text((85,790),'DRAFT ONLY',font=heading,fill='white')
    draw.text((85,880),'DO NOT PUBLISH',font=body,fill='white')
    draw.text((85,1130),'Acceptance | October 19',font=body,fill='white')
    output=io.BytesIO();image.save(output,'PNG')
    draft=request('/api/farm/drafts/'+draft_id+'/import',dict(revision=draft['revision'],name='fresh-check-%d.png'%number,
        content=base64.b64encode(output.getvalue()).decode('ascii')))['draft']
caption='Fresh content acceptance\nThree slides in order\nDraft only'
draft=request('/api/farm/drafts/'+draft_id+'/save',dict(revision=draft['revision'],title=title,caption=caption,slide_ids=draft['slideIds']))['draft']
export=request('/api/farm/drafts/'+draft_id+'/export',dict(revision=draft['revision']))
package=base64.b64decode(export['content'],validate=True)
(record/(prefix+'-carousel.zip')).write_bytes(package)
(record/(prefix+'-draft.json')).write_text(json.dumps(draft,indent=2),encoding='utf-8')
prep.update(draftId=draft_id,revision=draft['revision'],caption=caption,packageSha256=hashlib.sha256(package).hexdigest(),
    packageFile=str(record/(prefix+'-carousel.zip')),draftTitle=title)
if final:prep['nativeDataDirectory']=str(record/'final-clean-native-data')
(record/(prefix+'-preparation.json')).write_text(json.dumps(prep,indent=2),encoding='utf-8')
(record/'preparation.json').write_text(json.dumps(prep,indent=2),encoding='utf-8')
print(json.dumps(dict(prepared=True,draftId=draft_id,revision=draft['revision'],phoneInput=False)))
