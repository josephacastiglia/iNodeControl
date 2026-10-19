"""Pixel comparisons for explicitly recognized carousel layouts; never input coordinates."""
import io

import numpy as np
from PIL import Image
from farm_observations import image_size
from farm_screen_layout import carousel_position


def media_comparison(frame, assets, layout):
    if layout == 'draft_library_candidate':
        # A fixed four-column library: scan its seven fully visible rows, not arbitrary crops.
        # Multiple identical covers remain ambiguous even if their captions might differ.
        candidates=[]; matches=[]
        for row in range(7):
            for column in range(4):
                box=(column*125,111+row*125,column*125+124,235+row*125)
                result=_compare(frame,assets,layout,box)
                if result['status']=='insufficient_detail': continue
                result['libraryCell']=dict(row=row+1,column=column+1)
                candidates.append(result)
                if result['matchedIndex']==1: matches.append(result)
        if len(matches)==1:
            return {**matches[0],'candidateCells':len(candidates),'matchingCovers':1}
        return dict(status='ambiguous_library' if matches else 'no_matching_cover',matchedIndex=None,
                    matchingCovers=len(matches),candidateCells=len(candidates),fullImageVisible=False,byteIdentityVerified=False)
    return _compare(frame,assets,layout)


def _compare(frame, assets, layout, library_bounds=None):
    bounds = {'carousel_details': (20,126,260,426), 'carousel_editor': (0,164,500,789),
              'draft_library_candidate': library_bounds or (0,111,124,235)}
    if layout not in bounds: return dict(status='unsupported_layout', matchedIndex=None)
    width, height = image_size(frame)
    if abs(width/height - 500/1080) > .01: return dict(status='unsupported_geometry', matchedIndex=None)
    library = layout == 'draft_library_candidate'
    size = (100,100) if library else (100,125)
    with Image.open(io.BytesIO(frame)) as image:
        box = tuple(round(v*(width/500 if i%2 == 0 else height/1080)) for i,v in enumerate(bounds[layout]))
        observed = np.asarray(image.convert('RGB').crop(box).resize(size, Image.Resampling.LANCZOS), dtype=float)/255
    mask = np.ones(observed.shape[:2], dtype=bool)
    mask[:4] = mask[-4:] = False; mask[:, :4] = mask[:, -4:] = False
    if library:
        # The lower-left stack badge is UI, not source content. All other interior pixels count.
        mask[72:94, 4:26] = False
    if layout == 'carousel_editor': mask[:12, 89:] = False  # Fixed top-right remove-slide icon.
    if np.mean(np.std(observed[mask], axis=0)) < .04:
        return dict(status='insufficient_detail', matchedIndex=None)
    # Two fixed rendering models, no fitted colour/contrast or arbitrary crop search.
    shade = 1 - .70*(np.maximum(0, np.linspace(0,1,size[1])-.30)/.70)**2
    models = [('plain', np.ones(size[1]))]
    if library: models.append(('library_lower_gradient', shade))
    scores = []
    for index, raw in enumerate(assets, 1):
        with Image.open(io.BytesIO(raw)) as source:
            source = source.convert('RGB')
            if library:
                side = min(source.size); x=(source.width-side)//2; y=(source.height-side)//2
                source=source.crop((x,y,x+side,y+side))
            target=np.asarray(source.resize(size, Image.Resampling.LANCZOS), dtype=float)/255
        candidates=[]
        for name, alpha in models:
            difference=np.abs(observed-target*alpha[:,None,None]).mean(axis=2)
            blocks=[]
            for ys in np.array_split(np.arange(size[1]),5):
                for xs in np.array_split(np.arange(size[0]),4):
                    valid=mask[np.ix_(ys,xs)]
                    if valid.any(): blocks.append(float(difference[np.ix_(ys,xs)][valid].mean()))
            candidates.append(dict(index=index, meanError=float(difference[mask].mean()), worstBlock=max(blocks), rendering=name))
        scores.append(min(candidates, key=lambda row: row['meanError']))
    ordered=sorted(scores,key=lambda row:row['meanError'])
    best=ordered[0]; margin=ordered[1]['meanError']-best['meanError'] if len(ordered)>1 else 0
    accepted=best['meanError']<=.045 and best['worstBlock']<=.12 and margin>=.025
    result=dict(status='visual_match' if accepted else 'ambiguous_or_different', matchedIndex=best['index'] if accepted else None,
                scores=scores, margin=margin, byteIdentityVerified=False, fullImageVisible=not library)
    if layout == 'carousel_editor': result['position']=carousel_position(frame)
    return result
