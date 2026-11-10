"""Recognizers for the X image draft route (x_image: one 1080x1350 image). No input.

The transfer page is the shared farm_media_transfer image page (carousel layout, one slide):
index 'X image draft' / 'Package <name>' / 'Open slide 1 of 1' / 'Copy caption'; the slide page
'Slide 1 of 1' with the image, touch and hold -> Safari's menu -> 'Save to Photos'; 'Back to
caption' returns to the index. In X the image is added through the same system photo picker as
the video route (farm_x_layout.x_picker with the image's square crop) and the composer then shows
it whole on a 4:5 card. Positions come from retained 17 Oct C24C frames (Safari carousel transfer
steps 11-25, X image route steps 33-45) and are re-checked on A17 before any run is trusted.

Images are compared with fixed crop models of the package image (farm_image.ImageReference plus
'whole', the full 4:5 image); a match is visual evidence, never byte identity. Every image box is
found by a bounded search over the positions the layout allows, so a paragraph that wraps onto one
line more or less does not move the decision off the image. Unknown or ambiguous screens stop.
"""
import numpy as np

from farm_owned_capture import InspectionStopped
from farm_creation_layout import require, exact
from farm_image import IMAGE_MODELS, ImageReference
from farm_reel_layout import rows_between
from farm_screen_layout import pixels, words_at, line_at
from farm_tiktok_layout import media_match
import farm_x_layout as xl

WHOLE = ('cover', (48, 60))   # The whole 4:5 package image (a cover crop of the same aspect keeps all of it).


class XImageReference(ImageReference):
    """The package image under the shared crop models plus 'whole'. `seconds` is None: no video."""
    seconds = None

    def __init__(self, images, models=None):
        super().__init__(images, {**IMAGE_MODELS, 'whole': WHOLE} if models is None else models)


def centre(bounds):
    return round((bounds[0]+bounds[2])/2), round((bounds[1]+bounds[3])/2)


def find_image(frame, reference, *, left, width, tops, height, model='whole', ignore=(), image=None, lefts=None):
    """Best match of the package image over boxes of a fixed size at the allowed positions.

    Returns the best match with its box; `matched` follows the shared media_match thresholds."""
    image = pixels(frame, exact=True) if image is None else image
    lefts, tops = list(lefts if lefts is not None else (left,)), list(tops)
    best, tried = None, set()
    def score(x, top):
        nonlocal best
        if (x, top) in tried or x+width > 500 or top+height > 1080: return
        tried.add((x, top))
        found = media_match(frame, (x, top, x+width, top+height), reference, model, image=image, ignore=ignore)
        if found['mean'] is not None and (best is None or found['mean'] < best['mean']):
            best = dict(found, box=[x, top, x+width, top+height])
    # Coarse pass over every fourth allowed top at the middle left, then every allowed position near the best.
    # A matching image scores far below any other offset (17 Oct frames: .01 on it, over .05 a few px off).
    middle = lefts[len(lefts)//2]
    for top in tops[::4]: score(middle, top)
    if best is not None:
        near = [t for t in tops if abs(t-best['box'][1]) <= 8]
        for x in lefts:
            for top in near: score(x, top)
    return best or dict(status='insufficient_detail', matched=False, index=None, mean=None, model=model, box=None)


# ---- Transfer page (Safari) -----------------------------------------------------------------

PAGE_TITLE = 'X image draft'
PAGE = (10, 65, 490, 935)   # Above Safari's bottom address bar.


def transfer_index(text, package, title=PAGE_TITLE):
    """The package index, top to bottom: title, package name, 'Open slide 1 of 1', 'Copy caption'."""
    rows = []
    for label in (title, 'Package ' + package, 'Open slide 1 of 1', 'Copy caption'):
        rows.append(exact(text, label, PAGE))
    require([r[1] for r in rows] == sorted(r[1] for r in rows), 'The X image transfer page layout changed.')
    require(not line_at(text, 'open slide 2 of 2', PAGE), 'The transfer page offers more than one image.')
    return dict(openTarget=centre(rows[2]), copyTarget=centre(rows[3]))


def caption_copied(text, package):
    """The index after Copy caption. Focusing the caption box scrolls the page by about 54 px (slot 17, 4 Nov),
    so the title may be gone: the package name, then Copy caption, then the confirmation."""
    rows = [exact(text, label, PAGE) for label in ('Package ' + package, 'Copy caption')]
    require(rows[0][1] < rows[1][1], 'The X image transfer page layout changed.')
    # The confirmation can wrap onto a second row (C24C, 20 Oct); the exact sentence may span rows.
    require('Caption copied. Verify the pasted text in X.' in ' '.join(rows_between(text, 80, 1000)),
            'The transfer page did not confirm copying. No paste is permitted.')
    return dict(copied=True, copyTarget=centre(rows[1]))


def copy_selection(text, package):
    """The index with Safari's text-selection menu over 'Copy caption' instead of the confirmation: the click was
    taken as a hold and selected the button's word (A17, 4 Nov, prep 13). The menu row (Copy, Look Up) sits just
    above the button. The target is blank page right of the button, which only dismisses the selection; the menu's
    own Copy is never a target."""
    rows = [exact(text, label, PAGE) for label in ('Package ' + package, 'Copy caption')]
    require(rows[0][1] < rows[1][1], 'The X image transfer page layout changed.')
    require('caption copied.' not in ' '.join(rows_between(text, 80, 1000)).casefold(), 'The caption was copied.')
    button = rows[1]
    menu = [exact(text, label, (10, button[1]-90, 490, button[1]-5)) for label in ('Copy', 'Look Up')]
    require(menu[0][0] < menu[1][0], "Safari's text-selection menu is not recognized.")
    return dict(dismissTarget=(430, round((button[1]+button[3])/2)), copyTarget=centre(button))


# The slide is as wide as the page content (23-477 on C24C, 17 Oct step 12) and 4:5 tall; its top
# follows the instruction paragraph, which wraps differently with the app's name.
SLIDE_LEFT, SLIDE_WIDTH = 23, 454
SLIDE_HEIGHT = round(SLIDE_WIDTH*1350/1080)
SLIDE_TOPS = range(150, 331, 2)


def transfer_slide(frame, text, reference):
    """'Slide 1 of 1' with the package image and 'Back to caption' below it."""
    heading = exact(text, 'Slide 1 of 1', (10, 65, 490, 140))
    back = exact(text, 'Back to caption', (30, 300, 470, 1000))
    found = find_image(frame, reference, left=SLIDE_LEFT, width=SLIDE_WIDTH, height=SLIDE_HEIGHT, lefts=(21, 23, 25),
                       tops=[t for t in SLIDE_TOPS if heading[3] < t and t+SLIDE_HEIGHT < back[1]])
    require(found['matched'], 'The transfer page does not show the package image.')
    left, top, right, bottom = found['box']
    return dict(image=found, holdTarget=((left+right)//2, (top+bottom)//2), backTarget=centre(back))


# Safari's image menu (C24C, 17 Oct step 15): the lifted image, then Share..., Save to Photos, Copy,
# Copy Subject, Show Text, Look Up. Only 'Save to Photos' is ever a target.
PREVIEW_LEFT, PREVIEW_WIDTH = 25, 450
PREVIEW_HEIGHT = round(PREVIEW_WIDTH*1350/1080)
PREVIEW_TOPS = range(70, 251, 2)
MENU = (95, 560, 410, 1040)


def save_menu(frame, text, reference):
    """The image's context menu: the package image lifted above it and 'Save to Photos' under 'Share'."""
    save = exact(text, 'Save to Photos', MENU)
    copy = exact(text, 'Copy', MENU)
    require(copy[1] > save[3], 'The image menu order changed; nothing is chosen.')
    share = [r for r in text.get('lines', []) if r.get('words') and r['text'].casefold().startswith('share')]
    for row in share:
        top = min(w['y'] for w in row['words']); bottom = max(w['y']+w['height'] for w in row['words'])
        require(bottom+12 <= save[1] or top >= save[3]+12, 'Share is too close to Save to Photos.')
    found = find_image(frame, reference, left=PREVIEW_LEFT, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT,
                       lefts=(21, 25, 29), tops=[t for t in PREVIEW_TOPS if t+PREVIEW_HEIGHT < save[1]])
    require(found['matched'], 'The image menu belongs to a different image.')
    return dict(preview=found, target=centre(save))


# ---- X composer with the image --------------------------------------------------------------

# 17 Oct step 38 (C24C): the whole image on a rounded 4:5 card under the text row, its remove
# control top right and Video / +ALT / edit buttons along its bottom edge.
CARD_LEFT, CARD_TOP, CARD_WIDTH = 66, 170, 420
CARD_HEIGHT = round(CARD_WIDTH*1350/1080)
# Slot 17 (4 Nov) adds an Edit button left of Video and first-use callouts above the buttons: 'Make Video with
# Grok' (x 262-472) and 'Describe this image for those who are blind or low vision' (x 40-492, y 573-640).
CARD_IGNORE = ((436, 174, 482, 218), (40, 570, 495, 700))   # remove x; callouts, Edit, Video, +ALT
REMOVE = (436, 174, 482, 218)
CARD_BUTTONS = (200, 590, 482, 700)


def composer_image(frame, text, reference):
    """Pasted text, Post (never a target) and the package image on the composer card."""
    image = xl._composer(frame, text)
    require(words_at(text, 'post', (410, 70, 470, 98)), 'The X composer Post control is not where it was observed.')
    require(words_at(text, 'people', (95, 695, 200, 735)), 'The X media card is not recognized.')
    rows = xl.composer_rows(text)
    require(rows and not rows[0].casefold().startswith("what's happen"), 'The X composer has no text.')
    found = find_image(frame, reference, left=CARD_LEFT, width=CARD_WIDTH, height=CARD_HEIGHT, image=image,
                       lefts=range(CARD_LEFT-6, CARD_LEFT+7, 3), tops=range(CARD_TOP-8, CARD_TOP+9, 2), ignore=CARD_IGNORE)
    require(found['matched'], 'The X media card shows different media.')
    return dict(media=found, cancelTarget=(57, 85))
