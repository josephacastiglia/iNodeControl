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
from farm_reel_layout import POINTER, UNIQUE_MARGIN, band_words, no_overlay, rows_between, reel_paste_menu
from farm_tiktok_layout import media_match, tile_colours

CAPTION_LIMIT = 32          # One drafts-list line at the observed width; nothing truncated.
HANDLE = re.compile(r'@([A-Za-z0-9_]{1,15})')
CARD = (70, 172, 358, 690)  # Composer media card: the whole 9:16 frame.
CARD_IGNORE = ((316, 178, 352, 214), (70, 640, 358, 690), (196, 595, 470, 640))   # remove x, duration/720p row, sensitive-media tip
# After X's Edit Video step the card is drawn larger, with a play button and an edit button (slot 17, 23 Oct).
EDITED_CARD = (66, 170, 362, 697)
EDITED_IGNORE = ((316, 178, 352, 214), (66, 640, 362, 697), (196, 595, 470, 640), (174, 392, 256, 474))   # ... and play button
POST = (395, 62, 482, 106)
REMOVE = (316, 178, 352, 214)
TIPS = ({'your drafts are here', 'choose who can reply to your post.', 'add your location', 'mark your media as sensitive',
         'ark your media as sensitive', 'find awesome gifs'}, (0, 60, 500, 1040))   # GIFs: slot 17's new account, 22 Oct.


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
    # A newer account's header adds tabs ('For you v | Following | Add + | Crypto', slot 17, 22 Oct),
    # moving 'Following' left to x 154.
    # OCR can also clip it and join the chevron before it ('v Followin' from x 108, slot 17, 23 Oct).
    # The parked pointer can cover its end ('Followi', A17, 4 Nov): 'followi' is the shortest form accepted.
    following = words_at(text, 'following', (140, 120, 320, 160)) or any(
        re.search(r'(^|\s)followi?n?g?$', ' '.join(r['text'].casefold().split())) and r['text'].casefold().split()[-1].startswith('followi')
        and 100 <= min(w['x'] for w in r['words']) and max(w['x']+w['width'] for w in r['words']) <= 320
        and 120 <= min(w['y'] for w in r['words']) <= 160 for r in text.get('lines', []) if r.get('words'))
    require(following and line_at(text, 'for you', (30, 120, 130, 160)), 'The X timeline header is not recognized.')
    image = pixels(frame, exact=True)
    require(blue_fraction(image, (428, 909, 480, 961)) > .5, 'The X compose button is not where it was observed.')
    no_overlay({**text, 'lines': [r for r in text.get('lines', []) if not r.get('words')
                                  or not 160 <= min(w['y'] for w in r['words']) < 980]})
    return dict(menuTarget=(45, 85), composeTarget=(454, 935))


def x_menu(frame, text):
    """Side menu: exactly one signed-in handle under the display name."""
    # Since 4 Nov evening X adds 'Money' (with 'Claim bonus') and 'History' rows on slot 17; every row
    # from Communities down then sits 58-63 px lower. That layout is used only when both new rows are read
    # in their own place; otherwise the earlier boxes apply unchanged.
    shift = 62 if (line_at(text, 'money', (90, 385, 200, 432)) and line_at(text, 'history', (90, 448, 200, 495))) else 0
    for label, box in (('profile', (90, 262, 190, 300)), ('communities', (90, 455 + shift, 265, 495 + shift)),
                       ('settings and privacy', (85, 828 + shift, 280, 866 + shift))):
        require(line_at(text, label, box), 'The X account menu is not recognized: ' + label)
    # The Grok row reads 'Try Grok Bot' on slot 17's newer account (22 Oct).
    require(line_at(text, 'download grok', (85, 775 + shift, 240, 810 + shift)) or line_at(text, 'try grok bot', (85, 775 + shift, 240, 815 + shift)),
            'The X account menu is not recognized: grok')
    handles = [m.group(1) for line in text.get('lines', []) if line.get('words')
               and min(w['y'] for w in line['words']) < 200 and min(w['x'] for w in line['words']) < 120
               for m in HANDLE.finditer(line.get('text', ''))]
    require(len(handles) == 1, 'The signed-in X account is not uniquely readable.')
    return dict(handle=handles[0], closeTarget=(447, 83))


# ---- Composer --------------------------------------------------------------------------

# X draws Cancel from x 13 on slot 17 since 4 Nov (26 on C24C, 17 Oct; 18+ on slot 17, 22-25 Oct).
COMPOSER_CANCEL = ({'cancel'}, (8, 68, 100, 100))


def _composer(frame, text):
    no_overlay(text, (TIPS, COMPOSER_CANCEL))
    exact(text, 'Cancel', COMPOSER_CANCEL[1])
    # A tip callout can cover the end of the row ('Everyone can' under 'Find awesome GIFs', 22 Oct).
    tip = any(' '.join(r['text'].casefold().split()) in TIPS[0] for r in text.get('lines', []) if r.get('words')
              and min(w['y'] for w in r['words']) > 900)
    # OCR can also join the globe icon ('O Everyone can', from x 22).
    reply = [re.sub(r'^[o0]\s+', '', ' '.join(r['text'].casefold().split())) for r in text.get('lines', []) if r.get('words')
             and 15 <= min(w['x'] for w in r['words']) and max(w['x']+w['width'] for w in r['words']) <= 205
             and 930 <= min(w['y'] for w in r['words']) and max(w['y']+w['height'] for w in r['words']) <= 966]
    require('everyone can reply' in reply or (tip and 'everyone can' in reply), 'The X composer is not recognized.')
    return pixels(frame, exact=True)


def composer_rows(text, right=490):
    """The composer's first text row. OCR can join the avatar to it as a leading 'O' and start
    the line at x 25 ('O What's happening?', slot 17, 22 Oct); only such a joined line loses it."""
    rows = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        x, y = min(w['x'] for w in words), min(w['y'] for w in words)
        if not (115 <= y < 165 and 15 <= x < right): continue
        value = line['text']
        if x < 55:
            joined = re.match(r'^[o0]\s+(.*)$', value, flags=re.IGNORECASE)
            if not joined: continue
            value = joined.group(1)
        rows.append((y, x, value))
    return [row[2] for row in sorted(rows)]


def x_composer_empty(frame, text):
    """An empty composer; the Drafts link exists only once drafts exist."""
    _composer(frame, text)
    rows = [r for r in composer_rows(text, 330) if ' '.join(r.casefold().split()) not in TIPS[0]]
    if not rows:
        # The 'Your drafts are here' tip can hide the placeholder from full-frame OCR (slot 17, 23 Oct);
        # the field alone is read again, enlarged, and must still read as the placeholder.
        rows = [' '.join(w[0] for w in sorted(band_words(frame, (60, 115, 250, 160), 3), key=lambda w: w[1]))]
    require(len(rows) == 1 and rows[0].casefold().startswith("what's happen"), 'The X composer is not empty.')
    drafts = words_at(text, 'drafts', (310, 70, 380, 98))
    return dict(draftsTarget=(344, 85) if drafts else None, textTarget=(160, 140), pressTarget=(160, 140))


def x_composer_text(frame, text):
    """Pasted text, enabled Post (never a target) and no media yet."""
    image = _composer(frame, text)
    require(words_at(text, 'post', (410, 70, 470, 98)), 'The X composer Post control is not where it was observed.')
    rows = composer_rows(text)
    require(rows and not rows[0].casefold().startswith("what's happen"), 'The pasted text is not visible in the X composer.')
    require((image[CARD[1]:CARD[3], CARD[0]:CARD[2]].min(axis=2) > 235).mean() > .9, 'The X composer already holds media.')
    return dict(galleryTarget=(26, 1009), cancelTarget=(57, 85))


def x_composer_media(frame, text, reference, *, reopened=False):
    """Text and the package video's card; a reopened card may be blank until Play."""
    image = _composer(frame, text)
    require(words_at(text, 'post', (410, 70, 470, 98)), 'The X composer Post control is not where it was observed.')
    require(words_at(text, 'people', (120, 700, 190, 730)), 'The X media card is not recognized.')
    rows = composer_rows(text)
    require(rows and not rows[0].casefold().startswith("what's happen"), 'The X composer has no text.')
    card = image[CARD[1]:CARD[3], CARD[0]:CARD[2]].astype(float)
    median = np.median(card.reshape(-1, 3), axis=0)
    # A reopened card stays one light grey with a play button until Play (17 Oct steps 125-126).
    blank = bool((np.abs(card-median).max(axis=2) < 12).mean() > .93 and median.min() > 180 and median.max()-median.min() < 30)
    if reopened and blank:
        return dict(blank=True, playTarget=(214, 432), cancelTarget=(57, 85))
    media = media_match(frame, CARD, reference, 'fill', image=image, ignore=CARD_IGNORE)
    if not media['matched']:
        media = dict(media_match(frame, EDITED_CARD, reference, 'fill', image=image, ignore=EDITED_IGNORE), card='edited')
    require(media['matched'], 'The X media card shows different media.')
    # The edited card reopens paused on its first frame under a play button (slot 17, 23 Oct).
    paused = bool(reopened and media.get('card') == 'edited' and play_button(image))
    return dict(blank=False, paused=paused, media=media, cancelTarget=(57, 85), playTarget=(214, 432))


def play_button(image):
    """The white play triangle on its dark disc at the card's centre. The test video's white gutter
    crosses the same box, about 120 white pixels; the triangle alone adds over 200."""
    triangle = int((image[418:448, 204:232].min(axis=2) > 235).sum())
    ring = np.concatenate([image[400:412, 190:240].reshape(-1, 3), image[455:466, 190:240].reshape(-1, 3)]).astype(float)
    return triangle > 250 and float(ring.mean()) < 170


def x_paste_menu(frame, text):
    return reel_paste_menu(frame, text, press_y=140)


def x_save_sheet(text):
    """Cancel's sheet: Save to drafts (the target) above Discard (never); 'Keep editing' below them in the
    17-25 Oct layout. Slot 17's X shows only the two rows since 4 Nov, Save to drafts at y 498, Discard at 565."""
    bounds = exact(text, 'Save to drafts', (160, 440, 340, 530))
    discard = exact(text, 'Discard', (190, 505, 310, 600))
    require(discard[1] - bounds[3] >= 25, 'Save to drafts is too close to Discard.')
    keep = line_at(text, 'keep editing', (170, 570, 335, 650))
    require(not keep or keep[0][1] > discard[3], 'The X save sheet rows are out of order.')
    return dict(target=(round((bounds[0]+bounds[2])/2), round((bounds[1]+bounds[3])/2)), discard=list(discard),
                layout='three_rows' if keep else 'two_rows')


EDITOR_TIPS = ({'text gives your video context', "say what it's about in a few words", "sa what it's about in a few words"},
               (0, 860, 500, 960))   # First-use callout over the video (slot 17's new account, 22 Oct).
EDITOR_SAVE = (395, 1010, 460, 1045)   # Saves the edit to Photos; never a target.


def x_video_editor(frame, text):
    """X's Edit Video screen after Add (slot 17, 22 Oct): Next continues to the composer, Save is never pressed."""
    no_overlay(text, (EDITOR_TIPS,))
    exact(text, 'Edit Video', (190, 72, 310, 102))
    bounds = exact(text, 'Next', (410, 72, 475, 102))
    for label, box in (('Trim', (45, 1012, 100, 1045)), ('Cover', (220, 1012, 285, 1045)), ('Save', EDITOR_SAVE)):
        exact(text, label, box)
    return dict(nextTarget=(round((bounds[0]+bounds[2])/2), round((bounds[1]+bounds[3])/2)))


def x_editor_playing(frame, text, reference):
    """A reopened draft's play button opens Edit Video, where the video plays (slot 17, 23 Oct):
    the package video in the editor's frame; Next returns to the composer, Save is never pressed."""
    found = x_video_editor(frame, text)
    media = media_match(frame, (64, 135, 436, 797), reference, 'fill', ignore=(EDITOR_TIPS[1],))
    require(media['matched'], 'The X editor shows different media.')
    return dict(found, blank=False, editor=True, media=media)


# ---- System photo picker ------------------------------------------------------------------

PICKER_TOP, PICKER_PITCH = 201, 167
PICKER_COLUMNS = ((0, 166), (167, 333), (334, 500))


class Loading(InspectionStopped):
    """The system picker is still loading; a later read-only capture may show the grid."""


def _picker_header(text):
    for label, box in (('Cancel', (8, 88, 100, 120)), ('Photos', (160, 88, 235, 120)), ('Collections', (250, 88, 355, 120)),
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
    """The picker's numbered selection badge: iOS system blue (about (9, 123, 250)) over most of its box.
    The farm's own test images carry sky-blue (14, 165, 233) and dark-blue (21, 101, 192) blocks, and a sky-blue
    block in a tile's corner passed the wider X-blue test (A17, 4 Nov, prep 5); neither reaches B 240 with G 145 or less."""
    left, top, right, bottom = tile
    part = image[bottom-31:bottom-9, right-30:right-8].astype(int)
    system_blue = (part[..., 2] >= 240) & (part[..., 0] <= 60) & (part[..., 1] >= 90) & (part[..., 1] <= 145)
    return float(system_blue.mean()) > .5


def _tile(frame, tile, reference, image):
    left, top, right, bottom = tile
    return media_match(frame, (left+2, top+2, right-2, bottom-2), reference, 'square', image=image,
                       ignore=((right-58, bottom-34, right, bottom),))


def x_picker(frame, text, reference):
    """Unselected system picker: the one tile showing the package video, nothing selected."""
    if line_at(text, 'loading...', (150, 560, 350, 660)) and exact(text, 'Cancel', (8, 88, 100, 120)):
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

def drafts_loading(image):
    """An empty Drafts sheet with only its spinner in the middle (slot 17, 23 Oct): a later read-only
    capture may show the rows."""
    dark = image.min(axis=2) < 200
    left, top, right, bottom = POINTER   # The parked pointer.
    dark[top:bottom, left:right] = False
    spinner = int(dark[585:635, 225:275].sum())
    return bool(spinner >= 15 and int(dark[190:950, 20:480].sum()) - spinner <= 40)


def x_drafts(frame, text, reference, caption):
    """Drafts sheet: the one row with the exact text and the package video's thumbnail."""
    for label, box in (('Cancel', (8, 82, 100, 115)), ('Drafts', (210, 82, 290, 115)), ('Scheduled', (315, 138, 415, 186))):
        exact(text, label, box)
    no_overlay(text, (({'cancel'}, (8, 82, 100, 115)),))   # Cancel from x 13 as in the composer (4 Nov).
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
        if match and not match['matched'] and match['mean'] is not None and match['mean'] <= .15:
            # The rounded thumbnail narrowly misses pixel for pixel (slot 17, 23 Oct: .14); its six colour
            # blocks decide, as for the TikTok tray (other test videos differ by .4 or more).
            match = dict(match, **tile_colours(image, (408, y-1, 473, y+72), reference))
        rows.append(dict(text=line['text'], y=y, thumbnail=has_thumb, match=match))
    if not rows and drafts_loading(image): raise Loading('The X drafts list is still loading.')
    require(rows, 'No X drafts are recognized.')
    exact_rows = [r for r in rows if r['text'] == caption]
    if len(exact_rows) > 1:
        # An older draft with the same text but no video (slot 17, 23 Oct) is told apart by the package
        # video's thumbnail: exactly one such row shows it, and no other row with that text does.
        exact_rows = [r for r in exact_rows if r['match'] and r['match']['matched']]
    require(len(exact_rows) == 1, 'The exact draft text is absent or ambiguous in X drafts.')
    row = exact_rows[0]
    # A just re-saved draft lists its row before its thumbnail (slot 17, 23 Oct); a later capture shows it.
    if not row['thumbnail']: raise Loading('The X draft thumbnail is still loading.')
    require(row['match'] and row['match']['matched'], 'The X draft with this text does not show the package video.')
    return dict(row=row, rows=len(rows), target=(182, row['y']+10))
