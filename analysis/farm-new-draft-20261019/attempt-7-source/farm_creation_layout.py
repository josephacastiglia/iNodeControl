"""Recognizers for importing a saved carousel. No input or guessed OCR repair."""
import io
import base64
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image
from farm_carousel_inspection import InspectionStopped
from farm_screen_layout import pixels, words_at, line_at, overlay_present


def require(value, reason):
    if not value: raise InspectionStopped(reason)
    return value


def exact(text, label, box):
    return require(line_at(text, label.casefold(), box), 'Exact visible label missing: ' + label)[0]


def control(frame,name):
    row=json.loads(Path(__file__).with_name('farm_creation_controls.json').read_text(encoding='utf-8'))[name]
    raw=base64.b64decode(row['png'],validate=True)
    require(hashlib.sha256(raw).hexdigest()==row['sha256'], 'Creation control reference is damaged.')
    left,top,right,bottom=row['box'];image=pixels(frame,exact=True)
    with Image.open(io.BytesIO(raw)) as reference:
        delta=np.abs(image[top:bottom,left:right].astype(float)-np.asarray(reference.convert('RGB')).astype(float))/255
    valid=np.ones(delta.shape[:2],dtype=bool)
    if name=='empty_ios_search':valid[:,32:40]=False  # Fixed blinking caret; all label/magnifier pixels remain checked.
    require(delta[valid].mean()<.02 and (delta[valid].max(axis=1)>35/255).mean()<.04,'Creation control changed: '+name)
    return row['box']


def source_match(frame, raw, box, *, square=False, badge=False, prepared=None):
    """Fixed fit/crop models. Never fit colours to the observed image."""
    image = prepared['image'] if prepared is not None else pixels(frame, exact=True)
    left, top, right, bottom = box
    size = (100, 100 if square else 125)
    observed = np.asarray(Image.fromarray(image).crop(box).resize(size), dtype=float)/255
    expected=prepared['sources'].get(id(raw)) if prepared is not None else None
    if expected is None:
        with Image.open(io.BytesIO(raw)) as source:
            source = source.convert('RGB')
            if square:
                side = min(source.size); x=(source.width-side)//2; y=(source.height-side)//2
                source = source.crop((x,y,x+side,y+side))
            expected = np.asarray(source.resize(size), dtype=float)/255
        if prepared is not None: prepared['sources'][id(raw)]=expected
    mask = np.ones(observed.shape[:2], dtype=bool)
    mask[:5] = mask[-5:] = False; mask[:, :5] = mask[:, -5:] = False
    if badge: mask[:30, 70:] = False
    models=[expected]
    if badge: models.append(expected*.5)  # Observed selected thumbnail shade.
    delta=min((np.abs(observed-model).mean(axis=2) for model in models),key=lambda d:d[mask].mean())
    blocks = [float(delta[y:y+25,x:x+25][mask[y:y+25,x:x+25]].mean())
              for y in range(0,size[1],25) for x in range(0,100,25) if mask[y:y+25,x:x+25].any()]
    return dict(mean=float(delta[mask].mean()), worst=max(blocks),
                matched=bool(delta[mask].mean() <= .045 and max(blocks) <= .12))


def picker_grid(frame, text, assets, selected=()):
    checked={**text,'lines':[r for r in text.get('lines',[]) if not (selected and
        r.get('text','').casefold() in ('cancel','o cancel') and r.get('words')
        and 620<min(w['y'] for w in r['words'])<670)]}
    require(not overlay_present(checked), 'An overlay interrupts the media picker.')
    exact(text, 'New post', (180,65,320,110)); exact(text, 'Next', (420,65,495,110))
    require(words_at(text,'recents',(12,620,120,670)), 'Recents picker is not visible.')
    if selected: require(words_at(text,'cancel',(365,620,490,670)), 'Selection mode changed.')
    else: control(frame,'select')
    matches = {}
    prepared=dict(image=pixels(frame,exact=True),sources={})
    for number, raw in enumerate(assets,1):
        found=[]
        # Only fully visible cells; never scroll blindly to find missing assets.
        for row in range(3):
            for column in range(4):
                box=(column*125,677+row*125,column*125+125,802+row*125)
                if source_match(frame,raw,box,square=True,badge=True,prepared=prepared)['matched']:
                    found.append((row,column))
        require(len(found)==1, 'Slide %d is absent or duplicated in Recents.' % number)
        matches[number] = found[0]
    require(len(set(matches.values())) == len(assets), 'Two slides resolve to the same thumbnail.')
    return matches


def selected_badges(frame, text, cells, expected):
    """Match the three observed selection glyphs; unreadable numbers stop input."""
    image = pixels(frame, exact=True)
    references=json.loads(Path(__file__).with_name('farm_creation_badges.json').read_text(encoding='utf-8'))
    badges={}
    for key,row in references.items():
        raw=base64.b64decode(row['png'],validate=True)
        require(hashlib.sha256(raw).hexdigest()==row['sha256'], 'Selection glyph reference is damaged.')
        with Image.open(io.BytesIO(raw)) as reference: badges[int(key)]=np.asarray(reference.convert('RGB')).max(axis=2)<100
    actual = {}
    for asset, (row,col) in cells.items():
        x,y=col*125+102,677+row*125+23
        disk=image[y-10:y+11,x-10:x+11].astype(int)
        light=disk.min(axis=2)>140
        if light.mean() < .5: continue
        glyph=image[y-9:y+10,x-9:x+10].max(axis=2)<100
        scores=sorted((float((glyph!=reference).mean()),number) for number,reference in badges.items())
        require(scores[0][0]<.045 and scores[1][0]-scores[0][0]>.02, 'Selection number is unreadable or ambiguous.')
        actual[asset] = scores[0][1]
    require(actual == {asset:i+1 for i,asset in enumerate(expected)}, 'Selected slide order/count differs from the saved revision.')
    return actual


def caption_editor(text, caption=None, frame=None):
    exact(text,'Caption',(180,65,320,112))
    if frame is not None: control(frame,'ok')
    else: exact(text,'OK',(425,65,495,112))
    exact(text,'Poll',(20,580,160,680)); exact(text,'Prompt',(120,580,300,680))
    if caption is not None:
        rows=[]
        for line in text.get('lines',[]):
            words=line.get('words',[])
            if words and 480 < min(w['y'] for w in words) < 610:
                rows.append((min(w['y'] for w in words),min(w['x'] for w in words),line['text']))
        require('\n'.join(r[2] for r in sorted(rows))==caption, 'Pasted caption is missing, truncated or different.')
    return True


def home(text):
    names={'facetime','calendar','camera','app store','mail','notes','reminders','clock',
           'news','tv','podcasts','maps','health','wallet','safari','music','settings','photos',
           'instagram','tiktok','youtube','bluesky','gmail','zoho mail','expo go','proton vpn'}
    labels={r['text'].casefold() for r in text.get('lines',[]) if r.get('words')
            and 135<min(w['y'] for w in r['words'])<850}
    require(words_at(text,'search',(160,850,350,940)) and len(labels & names)>=6, 'The iOS Home screen is not recognized.')
    return True


def empty_search(text,frame=None):
    require(line_at(text,'siri suggestions',(10,65,320,125)), 'The empty iOS app search is not recognized.')
    if frame is None:require(words_at(text,'search',(40,930,475,1045)), 'The app search field is not empty and focused.')
    else:control(frame,'empty_ios_search')
    return True


def test_video_preview(text):
    exact(text,'imouse-draft',(150,65,350,110))
    exact(text,'Done',(405,65,495,110))
    exact(text,'Open in VLC',(100,990,310,1040))
    exact(text,'END OF TEST VIDEO',(30,270,470,350))
    return dict(readOnlyPreview=True,accountVerified=False)


def restored_app_search(text):
    exact(text,'Top Hit',(10,65,180,125))
    for name in ('Safari','Instagram'):
        try:return dict(app=name,target=app_target(text,name))
        except InspectionStopped:pass
    raise InspectionStopped('Only the known Safari/Instagram app-search result can be dismissed.')


def app_target(text, name):
    rows=[r for r in text.get('lines',[]) if r.get('words')]
    labels={r['text'].casefold() for r in rows}
    try: home(text);home_screen=True
    except InspectionStopped: home_screen=False
    suggestions='siri suggestions' in labels
    top_hit='top hit' in labels
    require(home_screen or suggestions or top_hit, 'No recognized Home or app search results.')
    bounds=exact(text,name,(10,130,490,850 if home_screen else 260))
    x=(bounds[0]+bounds[2])/2
    return round(x),round(bounds[1]-42)
