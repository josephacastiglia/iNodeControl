"""Recognizers for the TikTok photo (tt_photo) draft route on phone A20 (board C214, iPhone XR). No input.

Positions come from A20 calibration frames of 4 Nov 2026 (500x1080): the Safari slide pages of the
shared image transfer page and their image menu, TikTok's upload picker with numbered photo
selection, the photo editor (slideshow with a suggested sound), the photo details screen, its
expanded description editor and the Paste callout. Image checks compare frames with the immutable
package slides (farm_image.ImageReference); a match is visual evidence, not byte identity or proof
that TikTok persisted a draft. Unknown or ambiguous screens stop.

TikTok attaches a suggested sound to a photo post by itself. It is recorded and kept: no
recognizer here ever returns a target on the sound pill.
"""
import re

import numpy as np

from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import require, exact
from farm_screen_layout import pixels, words_at, line_at
from farm_reel_layout import UNIQUE_MARGIN, no_overlay, rows_between, band_words, reel_paste_menu
import farm_tiktok_layout as tt
from farm_tiktok_layout import media_match, red_fraction, caption_supported, CaretVisible, caret_visible  # noqa: F401

TITLE = 'TikTok photo draft'                          # farm_image.PAGES['tt_photo']['title']
COPIED = 'Caption copied. Verify the pasted text in TikTok.'
PAGE_BOX = (10, 65, 490, 940)                         # Safari content above its address bar.
TILE_MATCH = .10       # Highest mean for a picker/tray tile chosen by ranking (package slides .058-.096, 4 Nov).
TILE_MARGIN = .05      # Every other tile must be this much further (other media .23 or more, 4 Nov).


def _bounds(words):
    return (min(w['x'] for w in words), min(w['y'] for w in words),
            max(w['x']+w['width'] for w in words), max(w['y']+w['height'] for w in words))


def centre(box):
    left, top, right, bottom = box
    return round((left+right)/2), round((top+bottom)/2)


def _line(text, pattern, box):
    """Unique line whose casefolded text fully matches pattern, inside box: (text, bounds)."""
    left, top, right, bottom = box
    found = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        b = _bounds(words)
        if left <= b[0] and top <= b[1] and b[2] <= right and b[3] <= bottom and re.fullmatch(pattern, ' '.join(line['text'].casefold().split())):
            found.append((line['text'], b))
    return found[0] if len(found) == 1 else None


# ---- Safari transfer page (farm_media_transfer, image draft layout) -------------------------------

def transfer_index(text, download, count):
    """Index page as loaded: title, package name, Open slide 1..N, then Copy caption, top to bottom."""
    order = [exact(text, TITLE, PAGE_BOX)[1], exact(text, 'Package ' + download, PAGE_BOX)[1]]
    order += [exact(text, f'Open slide {n} of {count}', PAGE_BOX)[1] for n in range(1, count+1)]
    copy = exact(text, 'Copy caption', PAGE_BOX)
    order.append(copy[1])
    require(order == sorted(order), 'The photo transfer page layout changed.')
    return dict(copyTarget=centre(copy), openTarget=centre(exact(text, f'Open slide 1 of {count}', PAGE_BOX)))


def transfer_copied(text, count):
    """After Copy caption Safari scrolls the page; the confirmation and Open slide 1 must both show."""
    require(COPIED in ' '.join(rows_between(text, 65, 940)), 'The transfer page did not confirm copying. No paste is permitted.')
    first = exact(text, f'Open slide 1 of {count}', PAGE_BOX)
    copy = exact(text, 'Copy caption', PAGE_BOX)
    require(first[1] < copy[1], 'The photo transfer page layout changed.')
    return dict(copied=True, openTarget=centre(first))


def canvas_box(image, area=(0, 65, 500, 940)):
    """The slide's black-margined 9:16 canvas on a light page: (left, top, right, bottom)."""
    left, top, right, bottom = area
    dark = image[top:bottom, left:right].max(axis=2) < 40
    rows = np.where(dark.mean(axis=1) > .5)[0]
    require(len(rows) >= 40, 'The slide image is not visible.')
    first, last = top + int(rows[0]), top + int(rows[-1])
    # Columns of the top margin (a few rows in, clear of the menu preview's rounded corners); the
    # mirrored frame has a 1 px dark border at both edges, so the longest dark run is the canvas.
    flags = dark[rows[0]+6:rows[0]+26].mean(axis=0) > .9
    runs, start = [], None
    for x, value in enumerate(list(flags) + [False]):
        if value and start is None: start = x
        if not value and start is not None: runs.append((start, x-1)); start = None
    require(runs, 'The slide image is not visible.')
    a, b = max(runs, key=lambda r: r[1]-r[0])
    require(b-a >= 100, 'The slide image is not visible.')
    x0, x1 = left + a, left + b
    width, height = x1-x0+1, last-first+1
    require(abs(width/height - 9/16) < .02, 'The slide image is not shown whole.')
    return x0, first, x1+1, last+1


def slide_image(frame, image, reference, number):
    """The shown canvas is package slide `number` (1-based), better than every other slide."""
    box = canvas_box(image)
    match = media_match(frame, box, reference, 'fill', image=image)
    require(match['matched'] and match['index'] == number-1, f'The page does not show package slide {number}.')
    return box, match


def selection_handles(image, box=(10, 120, 490, 245)):
    """Blue text-selection handles (a long press that selected page text instead of the image)."""
    left, top, right, bottom = box
    part = image[top:bottom, left:right].astype(int)
    blue = (part[..., 2] > 200) & (part[..., 0] < 60) & (part[..., 1] > 90) & (part[..., 1] < 160)
    return int(blue.sum())


def transfer_slide(frame, text, number, count, reference):
    """Slide page N of M with package slide N whole; nothing selected; the next control below it."""
    exact(text, f'Slide {number} of {count}', (10, 65, 490, 140))
    image = pixels(frame, exact=True)
    require(selection_handles(image) < 20, 'Page text is selected on the slide page; no input is sent.')
    box, match = slide_image(frame, image, reference, number)
    label = 'Back to caption' if number == count else 'Next slide'
    nxt = _line(text, re.escape(label.casefold()) + r'( ?[→>-]+)?', (30, box[3], 470, 940))
    require(nxt is not None, 'The slide page navigation is not recognized.')
    return dict(canvas=list(box), match=match, holdTarget=centre(box), nextTarget=centre(nxt[1]), last=number == count)


def save_menu(frame, text, number, reference):
    """Safari's image menu over slide N: Share..., Save to Photos, Copy, top to bottom, under the preview."""
    image = pixels(frame, exact=True)
    box, match = slide_image(frame, image, reference, number)
    save = exact(text, 'Save to Photos', (90, box[3], 410, 1040))
    copy = exact(text, 'Copy', (90, box[3], 410, 1040))
    share = _line(text, r'share(\.\.\.|…)?', (90, box[3], 410, 1040))
    require(share is not None and share[1][1] < save[1] < copy[1], 'The image menu is not recognized; nothing is saved.')
    require(abs(save[0]-copy[0]) < 8 and abs(save[0]-share[1][0]) < 8, 'The image menu is not recognized; nothing is saved.')
    return dict(preview=list(box), match=match, target=centre(save))


# ---- Spotlight -----------------------------------------------------------------------------------

TOP_HIT_LABELS = (10, 195, 490, 232)


def app_target(text, name, frame):
    """farm_creation_layout.app_target, plus an enlarged read of the Top Hit label row: full-frame OCR
    missed the Top Hit 'TikTok' label on A20 twice (4 Nov). The name must be read there exactly once,
    leftmost (the app itself; shortcuts such as Search, Inbox, Create follow it)."""
    from farm_creation_layout import app_target as shared
    try: return shared(text, name, frame)
    except InspectionStopped as stop:
        labels = {r['text'].casefold() for r in text.get('lines', []) if r.get('words')}
        if 'top hit' not in labels or frame is None: raise
        words = sorted(band_words(frame, TOP_HIT_LABELS, 3), key=lambda w: w[1])
        found = [w for w in words if w[0].casefold() == name.casefold()]
        if len(found) != 1 or words[0] is not found[0]: raise stop
        _, x0, y0, x1, y1 = found[0]
        return round((x0+x1)/2), round((y0+y1)/2)


# ---- TikTok profile (A20 reads) -------------------------------------------------------------------

def profile(frame, text, account):
    """The exact signed-in profile. OCR on A20 drops 'Likes' and reads 'Drafts: 4' as '-Drafts:' (4 Nov);
    tt.tiktok_profile reads those bands again, enlarged. One @handle only, the authorized one."""
    handles = [w['text'] for line in text.get('lines', []) for w in line.get('words', [])
               if str(w.get('text', '')).startswith('@') and w['y'] < 380]
    require(len(handles) == 1 and handles[0].casefold() == '@' + account.casefold(),
            'The TikTok profile does not show exactly the authorized account.')
    return tt.tiktok_profile(frame, text, account)


# ---- Upload picker: numbered photo selection ------------------------------------------------------

COLUMNS = tt.COLUMNS
PITCH = tt.PITCH
TRAY = [(18 + 90*i, 882, 90 + 90*i, 956) for i in range(10)]   # Selection tray thumbnails, in order.
NEXT_BOX = (300, 990, 440, 1025)


def photo_grid(image):
    """Tile rows between pure white gutters. The package slides' light backgrounds (247,247,243) join
    a gutter under the shared rule (4 Nov); gutters and the bar below the grid are white (min >= 250)."""
    white = (image[tt.GRID_TOP:1000].min(axis=2) >= 250).mean(axis=1) > .9
    runs, start = [], None
    for y, value in enumerate(white):
        if value and start is None: start = y
        if not value and start is not None: runs.append((tt.GRID_TOP+start, tt.GRID_TOP+y)); start = None
    if start is not None: runs.append((tt.GRID_TOP+start, 1000))
    thick = [a for a, b in runs if b-a >= 10]
    require(thick, 'TikTok picker grid geometry changed.')
    bottom = thick[0]
    lines = [(a, b) for a, b in runs if a < bottom and b-a <= 6]
    require(lines and all(abs(b[0]-a[0]-PITCH) <= 1 for a, b in zip(lines, lines[1:])), 'TikTok picker grid geometry changed.')
    require(abs(bottom - lines[-1][1] - (PITCH-4)) <= 3, 'TikTok picker grid geometry changed.')
    starts = [lines[0][0]-(PITCH-4)] + [b for a, b in lines]
    ends = [a for a, b in lines] + [bottom]
    rows = [dict(top=t, bottom=b, complete=t >= tt.GRID_TOP and b-t >= 158) for t, b in zip(starts, ends)]
    for row in rows:
        if not row['complete']: continue
        for x in (166, 332):
            require((image[row['top']+5:row['bottom']-5, x].min(axis=1) > 225).mean() > .9, 'TikTok picker grid geometry changed.')
    return rows, bottom


def tiles(image, rows):
    for row in rows:
        if not row['complete']: continue
        for left, right in COLUMNS:
            yield (left, row['top'], right, row['bottom'])


def tile_score(frame, image, tile, reference):
    left, top, right, bottom = tile
    return media_match(frame, (left+2, top+2, right-2, bottom-2), reference, 'square', image=image,
                       ignore=((right-46, top, right, top+46), (right-60, bottom-26, right, bottom)))


def rank(frame, image, boxes, reference, slide, scorer):
    """The one box that shows `slide` (0-based): lowest mean against that slide, at most TILE_MATCH,
    TILE_MARGIN clear of every other box, and closer to that slide than to any other package slide."""
    one = reference.slide(slide)
    scored = []
    for box in boxes:
        match = scorer(frame, image, box, one)
        if match['mean'] is not None: scored.append((match['mean'], box, match))
    require(scored, 'No picker item shows enough detail to compare.')
    scored.sort(key=lambda s: s[0])
    best = scored[0]
    require(best[0] <= TILE_MATCH, f'Package slide {slide+1} is absent; nothing is selected.')
    require(len(scored) == 1 or scored[1][0]-best[0] >= TILE_MARGIN, f'Package slide {slide+1} is ambiguous; nothing is selected.')
    every = scorer(frame, image, best[1], reference)
    require(every['index'] == slide, f'The chosen item looks more like another package slide than slide {slide+1}.')
    return best[1], dict(mean=best[0], nearestOther=scored[1][0] if len(scored) > 1 else None, model='square', byteIdentityVerified=False)


def tray_score(frame, image, box, reference):
    left, top, right, bottom = box
    return media_match(frame, box, reference, 'square', image=image, ignore=((right-24, top-2, right+2, top+22),))


def photo_picker(frame, text, reference, selected):
    """Upload picker with `selected` package slides already chosen (in order). Returns the circle of
    the next slide's tile, or Next once every slide is chosen. Only package slides are ever chosen."""
    tt._picker_header(frame, text)
    image = pixels(frame, exact=True)
    rows, _ = photo_grid(image)
    every = list(tiles(image, rows))
    badges = [t for t in every if tt.badge(image, t)]
    require(len(badges) == selected, 'The TikTok picker shows a different selection; review the picker.')
    count = reference.count
    if selected == 0:
        require(line_at(text, 'select multiple', (40, 990, 200, 1025)), 'TikTok multiple selection is not shown.')
        require(red_fraction(image, (17, 996, 28, 1016)) > .5, 'TikTok multiple selection is not enabled.')
        tt.control(frame, 'tt_next_disabled')
        tray = []
    else:
        require(line_at(text, 'use layout', (40, 832, 150, 868)) and words_at(text, 'autocut', (95, 990, 195, 1025)),
                'The TikTok selection tray is not recognized.')
        label = 'next' if selected == 1 else f'next ({selected})'
        require(line_at(text, label, NEXT_BOX) and red_fraction(image, (262, 984, 478, 1028)) > .6,
                'The TikTok Next button does not show this selection.')
        # The tray shows exactly the chosen slides, in order; the slot after them is empty.
        tray = []
        for index in range(selected):
            box, match = rank(frame, image, TRAY[:selected], reference, index, tray_score)
            require(box == TRAY[index], f'The selection tray does not show slide {index+1} in place {index+1}.')
            tray.append(match)
        if selected < len(TRAY):
            left, top, right, bottom = TRAY[selected]
            require((image[top+4:bottom-4, left+4:right-4].min(axis=2) > 235).mean() > .97, 'The selection tray holds more items.')
    if selected == count:
        return dict(selected=selected, tray=tray, target=centre(NEXT_BOX), done=True)
    free = [t for t in every if not tt.badge(image, t)]
    tile, match = rank(frame, image, free, reference, selected, tile_score)
    return dict(selected=selected, tray=tray, tile=list(tile), match=match, target=tt.circle(tile), done=False)


# ---- Photo editor ---------------------------------------------------------------------------------

EDITOR_IGNORE = ((0, 65, 500, 140), (425, 140, 500, 560), (160, 840, 340, 900))
STRIP = (20, 900, 420, 962)   # The strip slides sideways with the shown slide (Collage at x 50 or 105, 4 Nov).


def photo_editor(frame, text, reference):
    """The photo editor: a slideshow of the package slides and the sound TikTok attached by itself.
    Story publishes and is never a target; the sound pill is read, never touched."""
    require(line_at(text, 'your story', (90, 990, 210, 1025)) or line_at(text, 'story 24h', (90, 990, 210, 1025)),
            'The TikTok photo editor is not recognized.')
    tt.control(frame, 'tt_editor_next')
    require(words_at(text, 'collage', STRIP), 'The TikTok photo strip is not recognized.')
    no_overlay(text)
    media = media_match(frame, (0, 72, 500, 961), reference, 'fill', ignore=EDITOR_IGNORE)
    require(media['matched'], 'The TikTok editor shows different media.')
    pill = rows_between(text, 95, 135, 140, 360)
    if pill == ['Add sound']: sound, label = 'none', None
    elif pill: sound, label = 'attached', re.sub(r'\s+[x×]$', '', pill[0], flags=re.IGNORECASE)
    else: sound, label = 'unread', None
    return dict(media=media, slideShown=media['index']+1, sound=sound, soundLabel=label, nextTarget=(367, 1006))


# ---- Photo details and its description editor -----------------------------------------------------

COVERS = ((21, 148), (159, 286), (297, 424))          # Collapsed details: Cover, 2, 3 cards at y 121-248.
SMALL = ((21, 81), (87, 147), (153, 213))             # Expanded editor's small strip at y 121-181.
PLACEHOLDER = ('writing a long description can help get 3x more', 'views on average.')
COUNTER = (15, 410, 130, 440)
DESCRIPTION_BOX = (15, 250, 480, 410)                 # Expanded description text (caret region).


def _strip(frame, image, reference, columns, top, bottom):
    found = []
    for index in range(reference.count):
        if index >= len(columns): break
        left, right = columns[index]
        match = media_match(frame, (left, top, right, bottom), reference, 'square', image=image,
                            ignore=((left, top, left+(right-left)//2, top+(bottom-top)//5),))
        require(match['index'] == index and match['mean'] is not None and match['mean'] <= TILE_MATCH,
                f'The cover strip does not show slide {index+1} in place {index+1}.')
        found.append(dict(mean=match['mean']))
    return found


def _placeholder(lines):
    joined = [' '.join(l.casefold().split()) for l in lines]
    # OCR drops the caret-covered first letter ('riting a long...') and capitalizes 'views' (4 Nov).
    return (len(joined) == 2 and re.fullmatch(r'.{0,3}iting a long description can help get 3x more', joined[0])
            and joined[1] == PLACEHOLDER[1])


def photo_details(frame, text, reference, caption=None):
    """Collapsed photo details: Preview, the three covers in order, title placeholder, the description
    (placeholder when caption is None, else exactly caption), Location, Drafts and Post. Post is never a target."""
    no_overlay(text)
    require(words_at(text, 'preview', (400, 65, 490, 100)), 'The TikTok photo details are not recognized.')
    require(line_at(text, 'add a catchy title', (20, 265, 260, 300)), 'The TikTok title field is not recognized.')
    require(words_at(text, 'location', (15, 600, 140, 645)), 'TikTok details field missing: location')
    require(words_at(text, 'drafts', (105, 985, 190, 1022)), 'The TikTok Drafts button is not recognized.')
    tt.control(frame, 'tt_details_drafts'); tt.control(frame, 'tt_back')
    image = pixels(frame, exact=True)
    require(red_fraction(image, (262, 984, 478, 1028)) > .6, 'The TikTok Post button is not where it was observed.')
    covers = _strip(frame, image, reference, COVERS, 121, 248)
    lines = rows_between(text, 315, 530, 15, 480)
    if caption is None: require(_placeholder(lines), 'The new TikTok description is not empty.')
    else: require(lines == [caption], 'The visible TikTok description is missing, different or wrapped.')
    return dict(covers=covers, captionExact=caption is not None, descriptionTarget=(200, 345), draftsTarget=(130, 1005))


def description_editor(frame, text, reference, caption=None):
    """The expanded description editor: small strip, title, description, counter. Blank (caption None):
    placeholder and 0/4000. Pasted: the counter equals the caption length; the text may be clipped by
    the caret here, so the exact text is required on the collapsed details before Drafts."""
    no_overlay(text)
    require(line_at(text, 'add a catchy title', (20, 195, 260, 230)), 'The TikTok description editor is not recognized.')
    require(not words_at(text, 'preview', (400, 65, 490, 100)), 'The TikTok description editor is not open.')
    require(words_at(text, 'drafts', (105, 985, 190, 1022)), 'The TikTok Drafts button is not recognized.')
    tt.control(frame, 'tt_back')
    image = pixels(frame, exact=True)
    require(red_fraction(image, (262, 984, 478, 1028)) > .6, 'The TikTok Post button is not where it was observed.')
    strip = _strip(frame, image, reference, SMALL, 121, 181)
    counter = _line(text, r'\d{1,4}/4000', COUNTER)
    require(counter is not None, 'The description counter is not readable.')
    length = int(counter[0].split('/')[0])
    lines = rows_between(text, 245, 410, 15, 480)
    if caption is None:
        require(length == 0 and _placeholder(lines), 'The new TikTok description is not empty.')
    else:
        require(length == len(caption), 'The pasted description length differs from the caption.')
        require(len(lines) == 1, 'The pasted description is not one line.')
    return dict(strip=strip, length=length, pressTarget=(80, 266), collapseTarget=(27, 84))


def paste_menu(frame, text):
    """The system Paste callout over the empty description (Paste, AutoFill)."""
    return reel_paste_menu(frame, text, press_y=266)


# ---- Drafts ----------------------------------------------------------------------------------------

def photo_drafts(frame, text, reference):
    """Drafts grid: exactly one tile whose cover shows package slide 1; its sound label is read.
    Same grid as tt.tiktok_drafts; a photo tile also carries a multi-photo glyph at its top right."""
    no_overlay(text, (tt.TOAST,))
    require(words_at(text, 'select', (410, 68, 490, 100)), 'The TikTok drafts list is not recognized.')
    tt.control(frame, 'tt_back')
    require(line_at(text, 'only you can see your drafts. uninstalling tiktok will', (50, 965, 450, 1000))
            and line_at(text, 'discard all drafts.', (175, 985, 325, 1015)), 'The TikTok drafts list is not recognized.')
    header = [r['text'] for r in text.get('lines', []) if r.get('words') and min(w['x'] for w in r['words']) < 40
              and 125 <= min(w['y'] for w in r['words']) <= 165]
    found = [re.match(r'(\d+) drafts?\b', ' '.join(h.casefold().split())) for h in header]
    count = int(found[0].group(1)) if len(found) == 1 and found[0] else None
    image = pixels(frame, exact=True)
    chips = any(r['text'].casefold().startswith('sort by') and 175 <= min(w['y'] for w in r['words']) <= 210
                for r in text.get('lines', []) if r.get('words'))
    shift = 0 if chips else tt.DRAFT_SHIFTS[1]
    boxes = []
    for top, bottom in ((t + shift, b + shift) for t, b in tt.DRAFT_ROWS):
        for left, right in tt.DRAFT_COLUMNS:
            if (image[top+10:bottom-10, left+10:right-10].min(axis=2) > 235).mean() > .97: continue
            boxes.append((left, top, right, bottom))
    require(boxes, 'No TikTok drafts are recognized.')
    def cover(frame, image, box, ref):
        left, top, right, bottom = box
        return media_match(frame, (left+2, top+2, right-2, bottom-2), ref, 'portrait', image=image,
                           ignore=((left, top, left+62, top+62), (right-40, top, right, top+40), (left, bottom-55, right, bottom)))
    tile, match = _rank_cover(frame, image, boxes, reference, cover)
    left, top, right, bottom = tile
    label = rows_between(text, bottom-50, bottom, left, right)
    return dict(count=count, tile=list(tile), match=match, tiles=len(boxes), soundLabel=label[0] if label else None,
                toastSeen=bool(line_at(text, 'draft saved', tt.TOAST[1])), target=centre(tile))


def _rank_cover(frame, image, boxes, reference, scorer):
    """Covers show slide 1 only; ranking compares with slide 1 alone."""
    first = reference.slide(0)
    scored = sorted(((m['mean'], b, m) for b in boxes for m in [scorer(frame, image, b, first)] if m['mean'] is not None),
                    key=lambda s: s[0])
    require(scored and scored[0][0] <= TILE_MATCH, 'The package photo draft is absent from TikTok drafts.')
    require(len(scored) == 1 or scored[1][0]-scored[0][0] >= TILE_MARGIN, 'Another TikTok draft looks too similar.')
    return scored[0][1], dict(mean=scored[0][0], nearestOther=scored[1][0] if len(scored) > 1 else None, model='portrait',
                              byteIdentityVerified=False)
