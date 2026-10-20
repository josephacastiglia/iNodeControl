"""Recognizers for the observed C24C X draft route. No input.

Positions come from retained 17 October C24C frames (500x1080, supervised steps
28-45 and 114-130). The account is whichever X account is signed in: it is
read from the side menu at the start of each run and must not change. Video
checks compare frames decoded from the immutable package under fixed centre
crops; a match is visual evidence, not byte identity or proof that X persisted a
draft. Unknown or ambiguous screens stop.
"""
import re

import numpy as np

from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import require, exact
from farm_screen_layout import pixels, words_at, line_at
from farm_reel_layout import UNIQUE_MARGIN, no_overlay, rows_between, reel_paste_menu
from farm_tiktok_layout import media_match

CAPTION_LIMIT = 32          # One drafts-list line at the observed width; nothing truncated.
HANDLE = re.compile(r'@([A-Za-z0-9_]{1,15})')
CARD = (70, 172, 358, 690)  # Composer media card: the whole 9:16 frame.
CARD_IGNORE = ((316, 178, 352, 214), (70, 640, 358, 690), (196, 595, 470, 640))   # remove x, duration/720p row, sensitive-media tip
POST = (395, 62, 482, 106)
REMOVE = (316, 178, 352, 214)
TIPS = ({'your drafts are here', 'choose who can reply to your post.', 'add your location', 'mark your media as sensitive',
         'ark your media as sensitive'}, (0, 60, 500, 1040))


def caption_supported(caption):
    """One visible drafts-list line of printable ASCII; nothing is ever truncated or wrapped."""
    return (isinstance(caption, str) and 0 < len(caption) <= CAPTION_LIMIT and caption == caption.strip()
            and all(32 <= ord(c) <= 126 for c in caption) and '  ' not in caption)


def blue_fraction(image, box):
    left, top, right, bottom = box
    part = image[top:bottom, left:right].astype(int)
    return float(((part[..., 2] > 200) & (part[..., 0] < 90) & (part[..., 1] > 90) & (part[..., 1] < 175)).mean())


# ---- Feed and account menu ------------------------------------------------------------

def x_feed(frame, text):
    """Home timeline. Feed content is arbitrary and never a target; only the avatar and compose button are."""
    require(words_at(text, 'following', (195, 120, 320, 160)) and line_at(text, 'for you', (30, 120, 130, 160)),
            'The X timeline header is not recognized.')
    image = pixels(frame, exact=True)
    require(blue_fraction(image, (428, 909, 480, 961)) > .5, 'The X compose button is not where it was observed.')
    no_overlay({**text, 'lines': [r for r in text.get('lines', []) if not r.get('words')
                                  or not 160 <= min(w['y'] for w in r['words']) < 980]})
    return dict(menuTarget=(45, 85), composeTarget=(454, 935))


def x_menu(frame, text):
    """Side menu: exactly one signed-in handle under the display name."""
    for label, box in (('profile', (90, 262, 190, 300)), ('communities', (90, 455, 265, 495)),
                       ('download grok', (85, 775, 240, 810)), ('settings and privacy', (85, 828, 280, 866))):
        require(line_at(text, label, box), 'The X account menu is not recognized: ' + label)
    handles = [m.group(1) for line in text.get('lines', []) if line.get('words')
               and min(w['y'] for w in line['words']) < 200 and min(w['x'] for w in line['words']) < 120
               for m in HANDLE.finditer(line.get('text', ''))]
    require(len(handles) == 1, 'The signed-in X account is not uniquely readable.')
    return dict(handle=handles[0], closeTarget=(447, 83))


# ---- Composer --------------------------------------------------------------------------

COMPOSER_CANCEL = ({'cancel'}, (18, 68, 100, 100))


def _composer(frame, text):
    no_overlay(text, (TIPS, COMPOSER_CANCEL))
    exact(text, 'Cancel', (18, 68, 100, 100))
    require(line_at(text, 'everyone can reply', (40, 930, 205, 966)), 'The X composer is not recognized.')
    return pixels(frame, exact=True)


def x_composer_empty(frame, text):
    """An empty composer; the Drafts link exists only once drafts exist."""
    _composer(frame, text)
    rows = [r for r in rows_between(text, 115, 165, 55, 330) if ' '.join(r.casefold().split()) not in TIPS[0]]
    require(len(rows) == 1 and rows[0].casefold().startswith("what's happen"), 'The X composer is not empty.')
    drafts = words_at(text, 'drafts', (310, 70, 380, 98))
    return dict(draftsTarget=(344, 85) if drafts else None, textTarget=(160, 140), pressTarget=(160, 140))


def x_composer_text(frame, text):
    """Pasted text, enabled Post (never a target) and no media yet."""
    image = _composer(frame, text)
    require(words_at(text, 'post', (410, 70, 470, 98)), 'The X composer Post control is not where it was observed.')
    rows = rows_between(text, 115, 165, 55, 490)
    require(rows and not rows[0].casefold().startswith("what's happen"), 'The pasted text is not visible in the X composer.')
    require((image[CARD[1]:CARD[3], CARD[0]:CARD[2]].min(axis=2) > 235).mean() > .9, 'The X composer already holds media.')
    return dict(galleryTarget=(26, 1009), cancelTarget=(57, 85))


def x_composer_media(frame, text, reference, *, reopened=False):
    """Text and the package video's card; a reopened card may be blank until Play."""
    image = _composer(frame, text)
    require(words_at(text, 'post', (410, 70, 470, 98)), 'The X composer Post control is not where it was observed.')
    require(words_at(text, 'people', (120, 700, 190, 730)), 'The X media card is not recognized.')
    rows = rows_between(text, 115, 165, 55, 490)
    require(rows and not rows[0].casefold().startswith("what's happen"), 'The X composer has no text.')
    card = image[CARD[1]:CARD[3], CARD[0]:CARD[2]].astype(float)
    median = np.median(card.reshape(-1, 3), axis=0)
    # A reopened card stays one light grey with a play button until Play (17 Oct steps 125-126).
    blank = bool((np.abs(card-median).max(axis=2) < 12).mean() > .93 and median.min() > 180 and median.max()-median.min() < 30)
    if reopened and blank:
        return dict(blank=True, playTarget=(214, 432), cancelTarget=(57, 85))
    media = media_match(frame, CARD, reference, 'fill', image=image, ignore=CARD_IGNORE)
    require(media['matched'], 'The X media card shows different media.')
    return dict(blank=False, media=media, cancelTarget=(57, 85))


def x_paste_menu(frame, text):
    return reel_paste_menu(frame, text, press_y=140)


def x_save_sheet(text):
    """Cancel's sheet: Save to drafts (the target), Discard (never), Keep editing."""
    bounds = exact(text, 'Save to drafts', (170, 450, 330, 495))
    exact(text, 'Discard', (200, 520, 300, 560)); exact(text, 'Keep editing', (180, 588, 325, 630))
    return dict(target=(round((bounds[0]+bounds[2])/2), round((bounds[1]+bounds[3])/2)))


# ---- System photo picker ------------------------------------------------------------------

PICKER_TOP, PICKER_PITCH = 201, 167
PICKER_COLUMNS = ((0, 166), (167, 333), (334, 500))


class Loading(InspectionStopped):
    """The system picker is still loading; a later read-only capture may show the grid."""


def _picker_header(text):
    for label, box in (('Cancel', (18, 88, 100, 120)), ('Photos', (160, 88, 235, 120)), ('Collections', (250, 88, 355, 120)),
                       ('Add', (425, 88, 485, 120))):
        exact(text, label, box)
    require(words_at(text, 'search', (40, 140, 140, 180)) or line_at(text, 'q search your library...', (25, 140, 300, 180)),
            'The photo picker search field is not recognized.')


def _picker_tiles(image):
    tiles = []
    for row in range(4):
        top = PICKER_TOP + row*PICKER_PITCH
        bottom = top + PICKER_PITCH - 1
        require((image[bottom, 5:495].min(axis=1) > 225).mean() > .9 if row < 3 else True, 'Photo picker grid geometry changed.')
        for left, right in PICKER_COLUMNS: tiles.append((left, top, right, bottom))
    for x in (166, 333):
        require((image[210:860, x].min(axis=1) > 225).mean() > .9, 'Photo picker grid geometry changed.')
    return tiles


def _badge(image, tile):
    left, top, right, bottom = tile
    return blue_fraction(image, (right-30, bottom-31, right-8, bottom-9)) > .5


def _tile(frame, tile, reference, image):
    left, top, right, bottom = tile
    return media_match(frame, (left+2, top+2, right-2, bottom-2), reference, 'square', image=image,
                       ignore=((right-58, bottom-34, right, bottom),))


def x_picker(frame, text, reference):
    """Unselected system picker: the one tile showing the package video, nothing selected."""
    if line_at(text, 'loading...', (150, 560, 350, 660)) and exact(text, 'Cancel', (18, 88, 100, 120)):
        raise Loading('The photo picker is still loading.')
    _picker_header(text)
    require(line_at(text, 'select items', (190, 990, 335, 1025)), 'The photo picker selection bar is not recognized.')
    image = pixels(frame, exact=True)
    require(blue_fraction(image, (437, 96, 474, 111)) < .05, 'Add is already enabled; review the picker.')
    tiles = _picker_tiles(image)
    require(not any(_badge(image, t) for t in tiles), 'A picker item already shows a selection; review the picker.')
    scored = [(t, _tile(frame, t, reference, image)) for t in tiles]
    matched = [(t, v) for t, v in scored if v['matched']]
    require(len(matched) == 1, 'The package video is absent or ambiguous in the photo picker; nothing is selected.')
    tile, best = matched[0]
    others = sorted(v['mean'] for t, v in scored if t != tile and v['mean'] is not None)
    require(not others or others[0]-best['mean'] >= UNIQUE_MARGIN, 'Another picker item looks too similar to the package video.')
    left, top, right, bottom = tile
    return dict(tile=list(tile), target=((left+right)//2, (top+bottom)//2), match=best, nearestOther=others[0] if others else None)


def x_picker_selected(frame, text, reference, tile):
    """Exactly one badge, on the tile chosen from the unselected frame, and Add enabled.

    The picker does not scroll on selection and draws the selected tile dimmed,
    so identity comes from that decision; the dimmed tile's match is recorded only.
    """
    _picker_header(text)
    require(line_at(text, 'show selected (1)', (165, 985, 355, 1020)), 'Exactly one picker item must be selected.')
    image = pixels(frame, exact=True)
    tiles = _picker_tiles(image)
    selected = [t for t in tiles if _badge(image, t)]
    require(len(selected) == 1 and list(selected[0]) == list(tile), 'Exactly the chosen picker item must be selected.')
    return dict(tile=list(selected[0]), tileMatch=_tile(frame, selected[0], reference, image), target=(456, 103))


# ---- Drafts --------------------------------------------------------------------------------

def x_drafts(frame, text, reference, caption):
    """Drafts sheet: the one row with the exact text and the package video's thumbnail."""
    for label, box in (('Cancel', (18, 82, 100, 115)), ('Drafts', (210, 82, 290, 115)), ('Scheduled', (315, 138, 415, 170))):
        exact(text, label, box)
    no_overlay(text, (({'cancel'}, (18, 82, 100, 115)),))
    image = pixels(frame, exact=True)
    rows = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        x, y = min(w['x'] for w in words), min(w['y'] for w in words)
        if not (10 <= x <= 40 and 190 <= y <= 950): continue
        thumb = (405, y-3, 476, y+68)
        has_thumb = float(np.std(image[thumb[1]:thumb[3], thumb[0]:thumb[2]].astype(float)/255)) > .05
        match = media_match(frame, thumb, reference, 'square', image=image) if has_thumb else None
        rows.append(dict(text=line['text'], y=y, thumbnail=has_thumb, match=match))
    require(rows, 'No X drafts are recognized.')
    exact_rows = [r for r in rows if r['text'] == caption]
    require(len(exact_rows) == 1, 'The exact draft text is absent or ambiguous in X drafts.')
    row = exact_rows[0]
    require(row['match'] and row['match']['matched'], 'The X draft with this text does not show the package video.')
    return dict(row=row, rows=len(rows), target=(182, row['y']+10))
