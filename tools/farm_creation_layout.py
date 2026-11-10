"""Recognizers for importing a saved carousel. No input or guessed OCR repair."""
import io
import base64
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image
from farm_owned_capture import InspectionStopped
from farm_screen_layout import pixels, words_at, line_at, overlay_present


def require(value, reason):
    if not value: raise InspectionStopped(reason)
    return value


def exact(text, label, box):
    return require(line_at(text, label.casefold(), box), 'Exact visible label missing: ' + label)[0]


def _line_box(text, predicate):
    rows = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if words and predicate(line['text']):
            rows.append((min(w['x'] for w in words), min(w['y'] for w in words),
                         max(w['x'] + w['width'] for w in words), max(w['y'] + w['height'] for w in words)))
    return rows


def _inside(boxes, area):
    return [b for b in boxes if area[0] <= b[0] and b[2] <= area[2] and area[1] <= b[1] and b[3] <= area[3]]


def safari_start_page(text):
    """Safari with no tab open (its Start Page). Its address field is empty, so the transfer URL
    can be typed after focusing it; the toolbar's share icon is disabled, so the chrome
    templates do not apply. Observed on C24C, 21 Oct."""
    require(_inside(_line_box(text, lambda t: t == 'Favorites'), (40, 100, 200, 160)), 'Safari Start Page heading is absent.')
    require(len(_inside(_line_box(text, lambda t: t.startswith('Search or enter')), (90, 935, 400, 975))) == 1
            and _inside(_line_box(text, lambda t: t in ('Q', 'q')), (40, 935, 80, 975)), 'Safari Start Page search field is absent.')
    return dict(browser='safari', startPage=True)


def safari_address_empty(text):
    """The Start Page's address field after it was focused: still empty (iOS shows the placeholder
    only for an empty field) and moved left over the magnifier, which focus removes. Typing
    cannot overwrite anything. The small close button is not required: OCR misses it at times."""
    # OCR can read the blinking caret as one character before the placeholder ('(Search or enter...',
    # slot 16, 22 Oct).
    require(len(_inside(_line_box(text, lambda t: re.match(r'^[(|\[Il]?\s*Search or enter', t) is not None),
                        (25, 930, 330, 975))) == 1
            and not _inside(_line_box(text, lambda t: t in ('Q', 'q')), (40, 935, 80, 975)),
            'Safari address field is not focused and empty.')
    return dict(addressSelected=True, addressEmpty=True)


def leftover_downloads(text):
    """Safari reopened with its Downloads sheet still open (an earlier run stopped there). Done only
    closes the sheet; no download is opened, cleared or replayed."""
    exact(text, 'Downloads', (185, 512, 315, 548)); exact(text, 'Done', (18, 512, 90, 548)); exact(text, 'Clear', (415, 512, 490, 548))
    return dict(browser='safari', leftoverDownloads=True, doneTarget=(51, 530))


def leftover_player(frame, text=None):
    """Safari reopened into iOS's full-screen video player of an earlier download, its toolbar hidden:
    a black bar above a bright picture, and below it either a black bar or, with the playback
    overlay up, its scrubber; the overlay's two '10' skip buttons then show (21-22 Oct, slot 18).
    Done closes it once the toolbar is shown."""
    image = pixels(frame, exact=True)
    dark = lambda rows: float((image[rows].max(axis=2) < 25).mean())
    tens = [line for line in (text or {}).get('lines', []) if line.get('words') and line['text'] == '10'
            and all(500 <= w['y'] <= 580 for w in line['words'])]
    # When OCR misses the '10' labels, the overlay's white play glyph at the centre shows it (22 Oct);
    # the scrubber and home indicator then lighten the bottom bar a little.
    glyph = float((image[525:580, 230:280].min(axis=2) > 235).mean())
    overlay = len(tens) >= 1 or (glyph > .15 and dark(slice(990, 1080)) > .85)
    require(dark(slice(0, 90)) > .97 and dark(slice(100, 980)) < .5 and (dark(slice(990, 1080)) > .97 or overlay),
            'Safari did not reopen into the full-screen player.')
    return dict(browser='safari', leftoverPlayer=True, revealTarget=(420, 130), doneTarget=(450, 85))


def safari_blank(text):
    """Safari with no tab open, its empty address field either unfocused or already focused (Safari
    restores focus). Either way the next step only focuses the empty field."""
    try: return safari_start_page(text)
    except InspectionStopped: pass
    require(_inside(_line_box(text, lambda t: t == 'Favorites'), (40, 100, 200, 160)), 'Safari Start Page heading is absent.')
    return dict(safari_address_empty(text), browser='safari', startPage=True)


# Templates accepted for one control. instagram_logo: the current wordmark (A18) or the older script one (A12, 5 Nov).
CONTROL_VARIANTS={'instagram_logo':('instagram_logo','instagram_logo_script')}


def control(frame,name):
    """The control's box when its template (or an accepted variant) matches; otherwise stops naming the control."""
    if not _matches(frame,name):
        for variant in CONTROL_VARIANTS.get(name,())[1:]:
            if _matches(frame,variant):return _control(frame,variant)
    return _control(frame,name)


def _matches(frame,name):
    try:_control(frame,name);return True
    except InspectionStopped:return False


def _control(frame,name):
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
    models=[(expected,1.0)]
    if badge:
        # Instagram dims previously selected cells and washes the currently
        # previewed cell with white. Fixed observed overlays, never fitted to
        # arbitrary colours. Full-size media checks do not permit either one.
        models.extend(((expected*.5,.5), (expected*.4+.6,.4), (expected*.2+.6,.2)))
    # An overlay suppresses differences between unrelated images too. Tighten
    # its residual budget with its fixed contrast gain; do not let a washed-out
    # wrong slide pass the ordinary full-contrast tolerance.
    delta,gain=min(((np.abs(observed-model).mean(axis=2)/gain**.5,gain) for model,gain in models),
                   key=lambda pair:pair[0][mask].mean())
    blocks = [float(delta[y:y+25,x:x+25][mask[y:y+25,x:x+25]].mean())
              for y in range(0,size[1],25) for x in range(0,100,25) if mask[y:y+25,x:x+25].any()]
    return dict(mean=float(delta[mask].mean()), worst=max(blocks),overlayGain=gain,
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
    yy,xx=np.ogrid[:19,:19]
    numeral_area=(xx-9)**2+(yy-9)**2<=8.5**2
    for key,row in references.items():
        raw=base64.b64decode(row['png'],validate=True)
        require(hashlib.sha256(raw).hexdigest()==row['sha256'], 'Selection glyph reference is damaged.')
        with Image.open(io.BytesIO(raw)) as reference: badges[int(key)]=(np.asarray(reference.convert('RGB')).max(axis=2)<100)&numeral_area
    actual = {}
    for asset, (row,col) in cells.items():
        x,y=col*125+102,677+row*125+23
        disk=image[y-10:y+11,x-10:x+11].astype(int)
        light=disk.min(axis=2)>140
        if light.mean() < .5: continue
        glyph=(image[y-9:y+10,x-9:x+10].max(axis=2)<100)&numeral_area
        # An empty selection ring can be pale over a bright source image.
        # It has no numeral. Missing digits on an expected selection still fail
        # the exact final mapping; any visible unreadable digit fails below.
        if not glyph.any(): continue
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


HOME_SEARCH_BOX=(205,879,296,920)


def small_screen(frame):
    """A 4.7-inch phone (rack B: iPhone 6s/7/8/SE), told by its letterboxed frame; see farm_small_layout."""
    from farm_small_layout import small_screen as small
    return frame is not None and small(frame)


def home_search(frame,text):
    """The Home screen Search pill. Its translucent fill takes the wallpaper's tint (C24C, 20 Oct:
    5.4% changed pixels after a restart), so the exact OCR word inside the pill box also proves it."""
    require(not small_screen(frame),'A 4.7-inch Home screen has no Search pill: Spotlight opens with a downward swipe.')
    try: return control(frame,'home_search')
    except InspectionStopped: pass
    if words_at(text,'search',HOME_SEARCH_BOX): return list(HOME_SEARCH_BOX)
    # On a light wallpaper the pill's light label is read neither by the template nor by full-frame
    # OCR (slot 18, 21 Oct): read the pill alone, enlarged with stronger contrast.
    require(pill_word(frame)=='search','The Home screen Search pill is not recognized.')
    return list(HOME_SEARCH_BOX)


def pill_word(frame):
    from PIL import ImageOps
    from farm_observations import WindowsOcr
    left,top,right,bottom=HOME_SEARCH_BOX
    with Image.open(io.BytesIO(frame)) as image:
        crop=ImageOps.autocontrast(image.convert('L').crop((left-10,top-8,right+10,bottom+4)).resize(((right-left+20)*3,(bottom-top+12)*3),Image.Resampling.LANCZOS))
    out=io.BytesIO(); crop.convert('RGB').save(out,'BMP')
    words=[w['text'].casefold() for line in WindowsOcr().read(out.getvalue()).get('lines',[]) for w in line.get('words',[])]
    return 'search' if words[-1:]==['search'] else (words[-1] if words else '')


def home(text,frame=None):
    if small_screen(frame):
        from farm_small_layout import home_page
        home_page(text,frame)   # Page dots and its icon grid, labels read enlarged row by row.
        return True
    if frame is not None:
        home_search(frame,text)
        grid=[]
        for row in text.get('lines',[]):
            words=row.get('words',[])
            if words:
                y=min(w['y'] for w in words)
                if any(abs(y-line)<18 for line in (171,298,425,552,679,806)):grid.append(row)
        require(len(grid)>=4,'The iOS Home icon grid is not recognized.')
        return True
    names={'facetime','calendar','camera','app store','mail','notes','reminders','clock',
           'news','tv','podcasts','maps','health','wallet','safari','music','settings','photos',
           'instagram','tiktok','youtube','bluesky','gmail','zoho mail','expo go','proton vpn'}
    labels={r['text'].casefold() for r in text.get('lines',[]) if r.get('words')
            and 135<min(w['y'] for w in r['words'])<850}
    require(words_at(text,'search',(160,850,350,940)) and len(labels & names)>=6, 'The iOS Home screen is not recognized.')
    return True


def empty_search(text,frame=None):
    if small_screen(frame):
        from farm_small_layout import empty_spotlight
        return empty_spotlight(text)
    require(line_at(text,'siri suggestions',(10,65,320,125)), 'The empty iOS app search is not recognized.')
    if frame is None:require(words_at(text,'search',(40,930,475,1045)), 'The app search field is not empty and focused.')
    else:
        try:control(frame,'empty_ios_search')
        except InspectionStopped:
            # The field is translucent, so the template follows the wallpaper (slots 17 and 20, 22 Oct);
            # then the grey placeholder alone, read at the field's start, shows it is empty.
            placeholder=[r for r in text.get('lines',[]) if r.get('words') and re.fullmatch(r'(q\s*)?[a-z]?earch',' '.join(r['text'].casefold().split()))
                         and 35<=min(w['x'] for w in r['words'])<=80 and 975<=min(w['y'] for w in r['words'])<=1010]
            require(len(placeholder)==1,'The app search field is not empty and focused.')
    return True


def test_video_preview(text):
    exact(text,'imouse-draft',(150,65,350,110))
    exact(text,'Done',(405,65,495,110))
    exact(text,'Open in VLC',(100,990,310,1040))
    exact(text,'END OF TEST VIDEO',(30,270,470,350))
    return dict(readOnlyPreview=True,accountVerified=False)


def search_clear(frame):
    """The app search field's clear button. Its template follows the wallpaper through the
    translucent field (slot 17, 22 Oct); the white glyph alone is then measured in place
    (.35 of its box bright; an empty field .0)."""
    if small_screen(frame):
        from farm_small_layout import spotlight_clear
        return spotlight_clear(frame)
    try: return control(frame,'search_clear')
    except InspectionStopped:
        image=pixels(frame,exact=True)
        bright=float((image[988:1022,430:462].min(axis=2)>215).mean())
        if .2<=bright<=.6: return [430,988,462,1022]
        # A tinted wallpaper tints the glyph too (A14, 5 Nov: teal, a cyan glyph; .06 white). Then the glyph is
        # measured against the empty field beside it: pixels 40 luminance above the field's median. 5 Nov frames:
        # .39-.41 with the button (A11, A12, A14, A15), .00 empty fields, .20-.21 an alert dimming the Home screen.
        lum=image[...,:3].astype(float)@np.array([.299,.587,.114])
        lifted=float((lum[988:1022,430:462]>np.median(lum[990:1020,300:420])+40).mean())
        require(.30<=lifted<=.55,'Creation control changed: search_clear')
        return [430,988,462,1022]


# Queries iOS restores in the app search that a run may clear (recognized only; nothing is opened). YouTube and
# TikTok joined on 5 Nov: on phones without their icon on Home pages 1-2 (A14) they open from the app search, so
# the next search shows their query again (youtube-slot14 attempt 1 stopped there).
RESTORED_QUERIES=('Safari','Instagram','YouTube','TikTok')


def restored_app_search(text):
    exact(text,'Top Hit',(10,65,180,125))
    for name in RESTORED_QUERIES:
        try:return dict(app=name,target=app_target(text,name))
        except InspectionStopped:pass
    raise InspectionStopped('Only the known Safari/Instagram/YouTube/TikTok app-search result can be dismissed.')   # X image matches this prefix.


SUGGESTION_LABELS=(10,200,490,236)   # The Siri Suggestions app label row in the empty app search.
TOP_HIT_LABELS=(10,195,490,232)      # The Spotlight Top Hit label row (the app, then its shortcuts).


def app_target(text, name,frame=None):
    if small_screen(frame):
        from farm_small_layout import app_target as small_target
        return small_target(text,name,frame)
    rows=[r for r in text.get('lines',[]) if r.get('words')]
    labels={r['text'].casefold() for r in rows}
    try: home(text,frame);home_screen=True
    except InspectionStopped: home_screen=False
    suggestions='siri suggestions' in labels
    top_hit='top hit' in labels
    require(home_screen or suggestions or top_hit, 'No recognized Home or app search results.')
    try: bounds=exact(text,name,(10,130,490,850 if home_screen else 260))
    except InspectionStopped:
        if not ((suggestions or top_hit) and not home_screen and frame is not None): raise
        from farm_reel_layout import band_words
        if suggestions:
            # Full-frame OCR can miss a Siri Suggestions label (slot 20, 22 Oct: 'TikTok'); the label row
            # alone is read again, enlarged, and the name must be read exactly once.
            found=[(x0,y0,x1,y1) for t,x0,y0,x1,y1 in band_words(frame,SUGGESTION_LABELS) if t.casefold()==name.casefold()]
            require(len(found)==1,'Exact visible label missing: '+name)
        else:
            # Full-frame OCR missed the Spotlight Top Hit label twice (A20, 4 Nov: 'TikTok'); the label row
            # alone is read again, enlarged. The name must be read there exactly once and leftmost: the app
            # itself, before its shortcuts (Search, Inbox, Create).
            words=sorted(band_words(frame,TOP_HIT_LABELS,3),key=lambda w:w[1])
            found=[(x0,y0,x1,y1) for t,x0,y0,x1,y1 in words if t.casefold()==name.casefold()]
            require(len(found)==1 and words[0][0].casefold()==name.casefold(),'Exact visible label missing: '+name)
        bounds=tuple(round(v) for v in found[0])
    x=(bounds[0]+bounds[2])/2
    return round(x),round((bounds[1]+bounds[3])/2 if top_hit and not home_screen else bounds[1]-42)
