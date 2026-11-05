"""Recognizers for the observed C24C Instagram Reel draft route. No input.

Positions come from retained 17 October C24C frames (500x1080) and the 19
October Create sheet. Video checks compare frames decoded from the immutable
package; a match is visual evidence, not byte identity, app authenticity or
proof that Instagram persisted a draft. Unknown or ambiguous screens stop.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile

import numpy as np
from PIL import Image

from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import require, exact, control
from farm_screen_layout import pixels, words_at, line_at, overlay_present, create_menu_controls
from farm_video import probe_video, run_media

FILL = (45, 80)        # Every 9:16 rendering: screens, picker tiles and thumbnails.
SQUARE = (48, 48)      # Reels drafts list: square centre crop.
SAMPLE_FPS = 5
MATCH_MEAN, MATCH_BLOCK = .06, .16
UNIQUE_MARGIN = .03
POINTER = (420, 270, 500, 330)   # Fresh-frame challenge parks the pointer here.
PICKER_COLUMNS = ((0, 166), (167, 333), (334, 500))
PICKER_ROWS = ((259, 553), (554, 848))   # Only fully visible rows; never scroll to search.
CAPTION_LIMIT = 40


PILL_CONTROLS = {'next_pill'}


def reference_rgb(raw):
    with Image.open(io.BytesIO(raw)) as reference: return reference.convert('RGB')


def reel_control(frame, name, exclude_columns=(), dy=0):
    """Fixed control template; same thresholds as the carousel controls. dy moves it down for a sheet whose rows
    were located by OCR (A12's Create sheet, 5 Nov); 0 everywhere else."""
    row = json.loads(Path(__file__).with_name('farm_reel_controls.json').read_text(encoding='utf-8'))[name]
    raw = base64.b64decode(row['png'], validate=True)
    require(hashlib.sha256(raw).hexdigest() == row['sha256'], 'Reel control reference is damaged.')
    left, top, right, bottom = row['box']
    top, bottom = top + dy, bottom + dy
    require(0 <= top and bottom <= 1080, 'Reel control is outside the frame.')
    image = pixels(frame, exact=True)
    with Image.open(io.BytesIO(raw)) as reference:
        delta = np.abs(image[top:bottom, left:right].astype(float)-np.asarray(reference.convert('RGB')).astype(float))/255
    valid = np.ones(delta.shape[:2], dtype=bool)
    if name in PILL_CONTROLS:
        # Only the pill: the picker draws a blurred copy of the photos behind its rounded corners
        # (22 Oct, slot 18), so those corner pixels follow the library, not the control.
        pill = np.asarray(reference_rgb(raw))[..., 2] > 180
        valid = pill & np.roll(pill, 1, 0) & np.roll(pill, -1, 0) & np.roll(pill, 1, 1) & np.roll(pill, -1, 1)
    for a, b in exclude_columns: valid[:, a-left:b-left] = False
    require(delta[valid].mean() < .02 and (delta[valid].max(axis=1) > 35/255).mean() < .04, 'Reel control changed: '+name)
    return [left, top, right, bottom]


def present(frame, name):
    try: reel_control(frame, name); return True
    except InspectionStopped: return False


def caption_supported(caption):
    """One visible line on details and Preview; nothing is ever truncated."""
    return (isinstance(caption, str) and 0 < len(caption) <= CAPTION_LIMIT and caption == caption.strip()
            and all(32 <= ord(c) <= 126 for c in caption) and '  ' not in caption)


def duration_label(seconds):
    whole = int(round(seconds))
    return f'{whole//60}:{whole%60:02d}'


class VideoReference:
    """Frames decoded once from the immutable package video, before any lease."""
    def __init__(self, raw):
        if not isinstance(raw, bytes) or not raw: raise ValueError('A package video is required.')
        with tempfile.TemporaryDirectory(prefix='farm-reel-reference-') as directory:
            path = Path(directory) / 'reel.mp4'; path.write_bytes(raw)
            info = probe_video(path)
            data = run_media('ffmpeg', ['-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-i', str(path),
                                        '-vf', f'fps={SAMPLE_FPS},scale=360:640:flags=lanczos', '-f', 'rawvideo',
                                        '-pix_fmt', 'rgb24', '-'], timeout=60)
        size = 360*640*3
        if not data or len(data) % size: raise ValueError('Package video frames could not be decoded completely.')
        frames = np.frombuffer(data, dtype=np.uint8).reshape(-1, 640, 360, 3)
        if not 2 <= len(frames) <= 240: raise ValueError('Package video must provide 2 to 240 sampled frames.')
        self.sha256, self.seconds, self.count = hashlib.sha256(raw).hexdigest(), info['seconds'], len(frames)
        self.duration = duration_label(info['seconds'])
        self.fill = [np.asarray(Image.fromarray(f).resize(FILL, Image.Resampling.LANCZOS), dtype=float)/255 for f in frames]
        self.square = [np.asarray(Image.fromarray(f[140:500]).resize(SQUARE, Image.Resampling.LANCZOS), dtype=float)/255 for f in frames]


def video_match(frame, box, reference, *, square=False, ignore=(), image=None):
    """Best sampled frame inside a fixed box; no fitted colour, scale or position."""
    image = pixels(frame, exact=True) if image is None else image
    left, top, right, bottom = box
    size = SQUARE if square else FILL
    observed = np.asarray(Image.fromarray(image[top:bottom, left:right]).resize(size, Image.Resampling.LANCZOS), dtype=float)/255
    mask = np.ones(observed.shape[:2], dtype=bool)
    mask[:2] = mask[-2:] = False; mask[:, :2] = mask[:, -2:] = False
    sx, sy = size[0]/(right-left), size[1]/(bottom-top)
    for a, b, c, d in tuple(ignore) + (POINTER,):
        x0, y0 = max(0, int((a-left)*sx)), max(0, int((b-top)*sy))
        x1, y1 = min(size[0], int(np.ceil((c-left)*sx))), min(size[1], int(np.ceil((d-top)*sy)))
        if x0 < x1 and y0 < y1: mask[y0:y1, x0:x1] = False
    if mask.mean() < .5 or np.mean(np.std(observed[mask], axis=0)) < .03:
        return dict(status='insufficient_detail', matched=False, index=None, mean=None)
    best = None
    for index, target in enumerate(reference.square if square else reference.fill):
        difference = np.abs(observed-target).mean(axis=2)
        blocks = [float(difference[ys][:, xs][mask[ys][:, xs]].mean())
                  for ys in np.array_split(np.arange(size[1]), 4) for xs in np.array_split(np.arange(size[0]), 4)
                  if mask[ys][:, xs].any()]
        score = (float(difference[mask].mean()), max(blocks), index)
        if best is None or score[0] < best[0]: best = score
    mean, worst, index = best
    matched = mean <= MATCH_MEAN and worst <= MATCH_BLOCK
    return dict(status='visual_match' if matched else 'different', matched=matched, index=index, mean=mean,
                worstBlock=worst, byteIdentityVerified=False)


def without(text, allowed):
    """Drop recognized fixed controls before the generic interruption check."""
    def keep(row):
        words = row.get('words') or []
        if not words: return True
        box = (min(w['x'] for w in words), min(w['y'] for w in words),
               max(w['x']+w['width'] for w in words), max(w['y']+w['height'] for w in words))
        label = ' '.join(str(row.get('text', '')).casefold().split())
        return not any(label in names and a <= box[0] and b <= box[1] and box[2] <= c and box[3] <= d
                       for names, (a, b, c, d) in allowed)
    return {**text, 'lines': [row for row in text.get('lines', []) if keep(row)]}


def no_overlay(text, allowed=()):
    require(not overlay_present(without(text, allowed)), 'An unexpected dialog interrupts the Reel route.')


def rows_between(text, top, bottom, left=0, right=500):
    rows = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        x, y = min(w['x'] for w in words), min(w['y'] for w in words)
        if top <= y < bottom and left <= x < right: rows.append((y, x, line['text']))
    return [row[2] for row in sorted(rows)]


# Regions allowed to move between two fresh frames of an otherwise settled screen.
# Video areas play; a fading toast or card preview is not an action target.
MOVING = {
    'reel_editor': ((0, 56, 500, 890),),
    'quicklook': ((0, 96, 500, 985),),
    'quicklook_controls': ((0, 110, 500, 985),),
    'reel_details_blank': ((160, 136, 340, 456),),
    'reel_details': ((160, 136, 340, 456),),
    'reels_drafts': ((0, 940, 500, 1040),),
    'link_menu': ((40, 80, 460, 745),),
}


def reel_compare(role):
    """Settling rule for one Reel screen: protected pixels must stay put.

    A change inside the protected area asks for another fresh capture (sheets and
    selection badges animate); the shared waiter bounds that to four captures.
    """
    def compare(first, first_text, second, second_text):
        a, b = pixels(first, exact=True).astype(float), pixels(second, exact=True).astype(float)
        difference = np.abs(a-b)/255
        mask = np.ones((1080, 500), dtype=bool); mask[:65] = False
        for left, top, right, bottom in MOVING.get(role, ()) + (POINTER,): mask[top:bottom, left:right] = False
        mean = float(difference[mask].mean()); changed = float((difference.max(axis=2) > 35/255)[mask].mean())
        if mean <= .002 and changed <= .005:
            return dict(state='ready', mean=mean, changed=changed, automaticInputAllowed=False)
        return dict(state='wait', mean=mean, changed=changed, automaticInputAllowed=False,
                    reason='Protected screen content is still changing; capture again without input.')
    return compare


# ---- Instagram ----------------------------------------------------------------

CREATE_ROWS = ('reel', 'edits', 'post', 'story', 'highlights', 'live', 'fundraiser')
CREATE_OPTIONAL = ('live',)
REEL_ICON_Y = 576   # reel_row_icon's centre on A18's sheet.


def create_rows(frame, text):
    """A Create sheet located by its own text (A12, 5 Nov: no Instants row, 'Create' at y 569): a centred
    'Create' header, then every row label once, in order, evenly spaced, on a light, empty sheet. {label: box} or None.
    A18's sheet (Instants between Story and Highlights) never fits the even spacing and keeps its positioned rule."""
    if (text.get('width'), text.get('height')) != (500, 1080) or overlay_present(text): return None
    def box(line):
        words = line['words']
        return (min(w['x'] for w in words), min(w['y'] for w in words),
                max(w['x']+w['width'] for w in words), max(w['y']+w['height'] for w in words))
    rows = [(' '.join(l['text'].casefold().split()), box(l)) for l in text.get('lines', []) if l.get('words')]
    header = [b for t, b in rows if t == 'create' and 190 <= b[0] and b[2] <= 310]
    if len(header) != 1: return None
    top = header[0][1]
    found = {}
    for label in CREATE_ROWS:
        hits = [b for t, b in rows if t == label and 55 <= b[0] <= 90 and top < b[1] < 1000]
        if label in CREATE_OPTIONAL and not hits: continue   # A19 (5 Nov) has no Live row; the spacing below still holds.
        if len(hits) != 1: return None
        found[label] = hits[0]
    ys = [found[label][1] for label in CREATE_ROWS if label in found]
    if not 35 <= ys[0] - top <= 70 or not all(44 <= b - a <= 62 for a, b in zip(ys, ys[1:])): return None
    image = pixels(frame, exact=True)
    for left, upper, right, lower in ((180, ys[0] - 10, 400, ys[-1] + 30), (30, ys[-1] + 45, 470, min(ys[-1] + 95, 1040))):
        if (image[upper:lower, left:right].min(axis=2) > 225).mean() < .97: return None
    return found


def _icon_at(frame, dy):
    try: reel_control(frame, 'reel_row_icon', dy=dy); return True
    except InspectionStopped: return False


def reel_create(frame, text):
    """The observed Create sheet; OCR often omits 'Reel', so its icon is required too."""
    if not create_menu_controls(frame, text):
        rows = create_rows(frame, text)
        if rows:
            # The Reel row read by OCR is the target; its icon must sit beside it.
            x0, y0, x1, y1 = rows['reel']
            centre = (round((x0 + x1) / 2), round((y0 + y1) / 2))
            # OCR's line box can sit a pixel off the glyphs; the icon is searched within 2 px of the row's centre.
            if not any(_icon_at(frame, centre[1] - REEL_ICON_Y + d) for d in (0, -1, 1, -2, 2)):
                raise InspectionStopped('Reel control changed: reel_row_icon')
            return dict(target=centre, labelRead=True, method='ocr_rows_sheet_and_reel_icon')
    if not create_menu_controls(frame, text) and line_at(text, 'edit profile', (40, 395, 220, 440)):
        # The profile still shows after '+' (slot 18, 25 Oct): the sheet may slide up a moment later,
        # so a later frame is read again without input.
        raise SheetPending('The Instagram Create sheet has not opened yet; capture again without input.')
    require(create_menu_controls(frame, text), 'The Instagram Create sheet is not recognized.')
    reel_control(frame, 'reel_row_icon')
    label = words_at(text, 'reel', (60, 555, 140, 600))
    return dict(target=(105, 576), labelRead=bool(label), method='positioned_sheet_and_reel_icon')


PICKER_PILL = ({'cancel', 'o1 cancel', '01 cancel', 'o cancel', 'select', '01 select'}, (370, 200, 485, 245))


def _picker_frame(frame, text):
    no_overlay(text, (PICKER_PILL,))
    exact(text, 'New reel', (190, 70, 310, 112))
    require(words_at(text, 'recents', (12, 205, 130, 245)), 'The Reel Recents grid is not visible.')
    require(words_at(text, 'templates', (40, 140, 270, 175)), 'The Reel picker toolbar is not recognized.')
    reel_control(frame, 'picker_close')
    image = pixels(frame, exact=True)
    # Black gutters fix the three-column grid; a sheet over the grid fails here.
    for x in (166, 333):
        require((image[262:550, x].max(axis=1) < 40).mean() > .9, 'Reel picker grid geometry changed.')
    require((image[248:258, :].max(axis=2) < 40).mean() > .9, 'Reel picker grid geometry changed.')
    chip = words_at(text, 'drafts', (20, 135, 140, 175))
    count = None
    if chip:
        # The count is supplementary evidence; an unreadable digit stays unknown.
        rows = [line['text'] for line in text.get('lines', []) if line.get('words') and 'drafts' in line['text'].casefold()
                and min(w['y'] for w in line['words']) < 180]
        found = re.findall(r'(\d+)\s*$', rows[0]) if len(rows) == 1 else []
        count = int(found[0]) if found else None
    return image, (list(chip[0]) if chip else None), count


def circle(cell):
    (row, column) = cell
    return PICKER_COLUMNS[column][1]-22, PICKER_ROWS[row][0]+21


def white_disk(image, cell):
    """Fraction of the selection circle that is white; an empty ring is gray."""
    x, y = circle(cell)
    disk = image[y-11:y+12, x-11:x+12].astype(int)
    yy, xx = np.ogrid[-11:12, -11:12]
    return float((disk.min(axis=2) > 200)[xx*xx+yy*yy <= 10*10].mean())


def selected_disk(image, cell):
    """A selected item's circle: white with its dark selection number in the middle. An empty ring
    over a white thumbnail is just as white but has nothing dark inside (slot 18, 21 Oct)."""
    x, y = circle(cell)
    centre = image[y-6:y+7, x-6:x+7].astype(int)
    return white_disk(image, cell) >= .3 and float((centre.max(axis=2) < 110).mean()) > .04


def numbered_one(image, cell):
    """A settled white disk carrying the numeral 1, at this cell's circle."""
    row = json.loads(Path(__file__).with_name('farm_reel_controls.json').read_text(encoding='utf-8'))['selection_one']
    raw = base64.b64decode(row['png'], validate=True)
    require(hashlib.sha256(raw).hexdigest() == row['sha256'], 'Reel control reference is damaged.')
    x, y = circle(cell); dx, dy = x-311, y-280
    left, top, right, bottom = row['box']
    with Image.open(io.BytesIO(raw)) as reference:
        delta = np.abs(image[top+dy:bottom+dy, left+dx:right+dx].astype(float)-np.asarray(reference.convert('RGB')).astype(float))/255
    return bool(delta.mean() < .02 and (delta.max(axis=2) > 35/255).mean() < .04)


NEAR_MATCH_MEAN = .09   # Slot 18's Recents thumbnail of the package video scored .061/.176 (21 Oct).


def tile_colours_match(image, box, reference):
    """A thumbnail that only narrowly misses the frame match (Instagram crops it slightly differently)
    still counts when all six test-media tiles carry the package's own colour code."""
    left, top, right, bottom = box
    observed = np.asarray(Image.fromarray(image[top:bottom, left:right]).resize(FILL, Image.Resampling.LANCZOS), dtype=float)/255
    worst = float(np.abs(tile_chroma(observed) - tile_chroma(reference.fill[0])).max())
    return dict(matched=worst <= TILE_CHROMA, status='tile_colour_match' if worst <= TILE_CHROMA else 'different', worstTile=worst)


def reel_picker(frame, text, reference):
    """Locate the one Recents tile that shows the package video."""
    image, chip, count = _picker_frame(frame, text)
    tiles = []
    for r, (top, bottom) in enumerate(PICKER_ROWS):
        for c, (left, right) in enumerate(PICKER_COLUMNS):
            if (r, c) == (0, 0): continue  # Camera shortcut, never media.
            result = video_match(frame, (left+2, top+2, right-2, bottom-2), reference, image=image,
                ignore=((right-46, top, right, top+46), (right-92, bottom-42, right, bottom)))
            if not result['matched'] and result['mean'] is not None and result['mean'] <= NEAR_MATCH_MEAN:
                result = dict(result, **tile_colours_match(image, (left+2, top+2, right-2, bottom-2), reference))
            tiles.append(((r, c), result))
    matched = [(cell, value) for cell, value in tiles if value['matched']]
    require(len(matched) == 1, 'The package video is absent or ambiguous in Recents; nothing is selected.')
    cell, best = matched[0]
    others = sorted(v['mean'] for c, v in tiles if c != cell and v['mean'] is not None)
    require(not others or others[0]-best['mean'] >= UNIQUE_MARGIN, 'Another Recents item looks too similar to the package video.')
    require(not any(selected_disk(image, (r, c)) for r in range(len(PICKER_ROWS)) for c in range(3) if (r, c) != (0, 0)),
            'A Recents item already shows a selection; review the picker.')
    left, right = PICKER_COLUMNS[cell[1]]; top, bottom = PICKER_ROWS[cell[0]]
    label = [w for line in text.get('lines', []) for w in line.get('words', [])
             if re.fullmatch(r'\d:\d\d', str(w.get('text', ''))) and right-95 <= w['x'] and w['x']+w['width'] <= right
             and bottom-45 <= w['y'] and w['y']+w['height'] <= bottom]
    if label: require(len(label) == 1 and label[0]['text'] == reference.duration, 'The tile duration differs from the package video.')
    return dict(cell=list(cell), target=circle(cell), match=best, nearestOther=others[0] if others else None,
                durationRead=label[0]['text'] if label else None, draftsChip=chip, draftsCount=count)


def reel_selected(frame, text, reference, cell):
    """Exactly the chosen tile numbered 1, its thumbnail in the tray, and Next."""
    image, _, _ = _picker_frame(frame, text)
    cell = tuple(cell)
    require(numbered_one(image, cell), 'The chosen video is not visibly selected as number 1.')
    require(not any(selected_disk(image, (r, c)) for r in range(len(PICKER_ROWS)) for c in range(3) if (r, c) not in ((0, 0), cell)),
            'Another Recents item is selected or unreadable.')
    # Each word on its own: OCR may join the button's icon to the label ('t-g First draft', 22 Oct).
    found = all(words_at(text, word, (290, 975, 395, 1012)) for word in ('first', 'draft'))
    if not found:   # Full-frame OCR can miss the white pill over a dark tray (A18, 5 Nov 16:54); that band alone, enlarged.
        found = {'first', 'draft'} <= {w[0].casefold() for w in band_words(frame, (280, 970, 400, 1016))}
    require(found, 'Exact visible label missing: First draft')
    reel_control(frame, 'next_pill')
    # The tray thumbnail carries a remove X at its top-right; it is never tapped.
    tray = video_match(frame, (16, 963, 51, 1025), reference, image=image, ignore=((38, 958, 55, 978),))
    if not tray['matched'] and tray['mean'] is not None and tray['mean'] <= NEAR_MATCH_MEAN:
        # The 35 px thumbnail shifts by a pixel between renders (.067 on 22 Oct, slot 18); its six
        # tiles still carry this package's colour code (.04; other test videos .57 or more).
        tray = dict(tray, **tile_colours_match(image, (16, 963, 51, 1025), reference))
    require(tray['matched'], 'The selection tray does not show the package video.')
    return dict(cell=list(cell), tray=tray, target=(444, 993))


EDITOR_TOOLBAR = (('audio', (45, 902, 108, 942)), ('voice', (222, 902, 282, 942)),
                  ('captions', (298, 902, 380, 942)), ('overlay', (390, 902, 465, 942)))
TOOLBAR_BAND, TOOLBAR_SCALE = (30, 905, 475, 940), 4


def band_words(frame, band, scale=4):
    """OCR of one band alone, enlarged with stronger contrast, for small light text that full-frame
    OCR misses. Words in frame coordinates: (text, left, top, right, bottom)."""
    from PIL import ImageOps
    from farm_observations import WindowsOcr
    left, top, right, bottom = band
    with Image.open(io.BytesIO(frame)) as image:
        crop = ImageOps.autocontrast(image.convert('L').crop(band).resize(
            ((right-left)*scale, (bottom-top)*scale), Image.Resampling.LANCZOS))
    out = io.BytesIO(); crop.convert('RGB').save(out, 'BMP')
    return [(str(w['text']), left + w['x']/scale, top + w['y']/scale, left + (w['x']+w['width'])/scale, top + (w['y']+w['height'])/scale)
            for line in WindowsOcr().read(out.getvalue()).get('lines', []) for w in line.get('words', [])]


def toolbar_words(frame):
    """The editor toolbar's label row alone, enlarged: (word, left, right)."""
    return [(t.casefold(), x0, x1) for t, x0, _, x1, _ in band_words(frame, TOOLBAR_BAND, TOOLBAR_SCALE)]


def reel_editor(frame, text, reference):
    no_overlay(text)
    exact(text, 'Edit video', (25, 975, 125, 1008))
    toolbar = [words_at(text, name, box) for name, box in EDITOR_TOOLBAR]
    if sum(bool(t) for t in toolbar) < 3:
        # Full-frame OCR can miss the small light labels over a light video (22 Oct, slot 18).
        enlarged = toolbar_words(frame)
        toolbar = [[w for w in enlarged if w[0] == name and box[0] <= w[1] and w[2] <= box[2]] for name, box in EDITOR_TOOLBAR]
    require(sum(bool(t) for t in toolbar) >= 3, 'The Reel editor toolbar is not recognized.')
    require(words_at(text, 'next', (405, 975, 470, 1008)) or present(frame, 'next_pill'), 'The editor Next control is not verified.')
    media = video_match(frame, (0, 56, 500, 945), reference, ignore=((0, 56, 80, 120), (0, 880, 500, 945)))
    require(media['matched'], 'The Reel editor shows different media.')
    return dict(media=media, target=(444, 993))


COVER_NEAR_MEAN = .18


DETAILS_BUTTONS = (({'save draft'}, (80, 980, 190, 1012)), ({'cancel'}, (12, 62, 90, 96)))


def details_rows(text):
    """The settings rows under the cover: location, then audio ('Original audio') 40-80 px below.
    The list grew on 22 Oct (slot 18: a 'Tag products' row), moving location and audio 58 px down
    (location y 749 -> 807); either position is accepted, location above audio. On 4 Nov (slot 18)
    an 'Add link' row ('Try Meta One') appeared between them and pushed audio under the button bar,
    where OCR does not read it: then the 'Add link' row, in audio's old place, stands in for it.
    Recognition only; that row is never tapped."""
    location = words_at(text, 'location', (60, 735, 190, 835))
    require(location, 'Reel details field missing: location')
    below = words_at(text, 'original', (330, 790, 480, 895)) or words_at(text, 'link', (60, 790, 190, 895))
    require(below, 'Reel details field missing: original')
    require(40 <= below[0][1] - location[0][1] <= 80, 'The Reel details rows are out of order.')
    return 'audio' if words_at(text, 'original', (330, 790, 480, 895)) else 'link'


def reel_details(frame, text, reference, caption=None, *, reopened=False):
    """Fresh or reopened details. caption=None requires the empty placeholder."""
    no_overlay(text, DETAILS_BUTTONS)
    exact(text, 'New reel', (190, 62, 310, 100))
    require(words_at(text, 'preview', (185, 150, 268, 188)) and line_at(text, 'edit cover', (182, 405, 292, 445)),
            'The Reel cover card is not recognized.')
    for name, box in (('poll', (180, 605, 235, 640)), ('prompt', (245, 605, 350, 640))):
        require(words_at(text, name, box), 'Reel details field missing: ' + name)
    details_rows(text)
    exact(text, 'Save draft', (80, 980, 190, 1012))
    require(words_at(text, 'share', (335, 980, 405, 1012)), 'Reel details buttons are not recognized.')
    if reopened:
        require(words_at(text, 'cancel', (12, 62, 90, 96)) and words_at(text, 'edit', (430, 62, 490, 96)),
                'The reopened draft header is not recognized.')
    else:
        reel_control(frame, 'details_back')
    lines = rows_between(text, 470, 530, 10, 490)
    if caption is None:
        # OCR may drop a dot of the placeholder's ellipsis ('Add a caption..', slot 18, 25 Oct).
        require(len(lines) == 1 and re.fullmatch(r'Add a caption(\.{2,3}|…)', lines[0]), 'The new Reel caption is not empty.')
    else:
        require(lines == [caption], 'The visible Reel caption is missing, different or wrapped.')
    cover = video_match(frame, (160, 136, 340, 456), reference, ignore=((182, 148, 270, 190), (180, 402, 295, 448)))
    if not cover['matched'] and cover['mean'] is not None and cover['mean'] <= COVER_NEAR_MEAN:
        # The card now darkens the cover's lower part (22 Oct, slot 18: mean .134); its six tiles
        # keep this package's colour code (.03; earlier test videos .42 or more, mean .21 or more).
        cover = dict(cover, **tile_colours_match(pixels(frame, exact=True), (160, 136, 340, 456), reference))
    require(cover['matched'], 'The Reel cover shows different media.')
    return dict(captionExact=caption is not None, cover=cover, reopened=reopened,
                captionTarget=(80, 505), saveTarget=(130, 996), previewTarget=(225, 172))


def reel_caption(frame, text, *, blank):
    """Top caption sheet over details. OK only closes it; it never saves."""
    exact(text, 'Caption', (200, 62, 300, 100))
    control(frame, 'ok')
    for name, box in (('hashtags', (25, 240, 145, 278)), ('poll', (178, 240, 238, 278)), ('prompt', (265, 240, 350, 278))):
        require(words_at(text, name, box), 'The Reel caption sheet is not recognized.')
    empty = present(frame, 'caption_placeholder')
    if blank: require(empty, 'The Reel caption field is not empty and focused.')
    else: require(not empty and rows_between(text, 115, 235, 10, 490), 'The pasted caption is not visible in the editor.')
    return dict(blank=blank, captionExact=False, requiresExactDetailsBeforeSave=True, pressTarget=(80, 142), okTarget=(461, 84))


def reel_paste_menu(frame, text, press_y=142):
    rows = [(w['x'], w['y'], w['x']+w['width'], w['y']+w['height'], str(w.get('text', '')).casefold())
            for line in text.get('lines', []) for w in line.get('words', [])
            if press_y-120 <= w['y'] <= press_y+120]
    paste = [r for r in rows if r[4] == 'paste']
    autofill = [r for r in rows if r[4] == 'autofill']
    require(len(paste) == 1 and len(autofill) == 1 and abs(paste[0][1]-autofill[0][1]) < 10 and paste[0][2] < autofill[0][0],
            'The Paste menu is not uniquely recognized; no caption is entered.')
    p = paste[0]
    return dict(target=(round((p[0]+p[2])/2), round((p[1]+p[3])/2)), bounds=list(p[:4]))


def reel_saved_picker(frame, text):
    """After Save draft Instagram returned to the Reel picker with a Drafts chip."""
    _, chip, count = _picker_frame(frame, text)
    require(chip, 'Instagram did not return to the Reel picker with a Drafts control.')
    return dict(draftsChip=chip, draftsCount=count, chipTarget=(round((chip[0]+chip[2])/2), round((chip[1]+chip[3])/2)),
                closeTarget=(42, 98))


TOAST = ({'if you uninstall the instagram app, all your', 'drafts will be lost.', 'ok', '0k'}, (60, 940, 480, 1030))


def reels_drafts(frame, text, reference):
    """The one Reels drafts row whose thumbnail shows the package video."""
    no_overlay(text, (TOAST,))
    exact(text, 'Reels drafts', (180, 62, 320, 100))
    reel_control(frame, 'drafts_close')
    image = pixels(frame, exact=True)
    rows = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words or not line['text'].casefold().startswith('edited '): continue
        x, y = min(w['x'] for w in words), min(w['y'] for w in words)
        if not (120 <= x <= 260 and 150 <= y <= 900): continue
        duration = next((r['text'].split()[0] for r in text.get('lines', []) if r.get('words')
                         and 120 <= min(w['x'] for w in r['words']) <= 260 and y+12 <= min(w['y'] for w in r['words']) <= y+40), None)
        match = video_match(frame, (20, y-40, 112, y+52), reference, square=True, image=image)
        rows.append(dict(editedY=y, edited=line['text'], duration=duration, match=match))
    require(rows, 'No Reels draft rows are recognized.')
    matched = [r for r in rows if r['match']['matched']]
    require(len(matched) == 1, 'The package video is absent or ambiguous in Reels drafts.')
    row = matched[0]
    others = sorted(r['match']['mean'] for r in rows if r is not row and r['match']['mean'] is not None)
    require(not others or others[0]-row['match']['mean'] >= UNIQUE_MARGIN, 'Another Reels draft looks too similar.')
    if row['duration'] and re.fullmatch(r'\d:\d\d', row['duration']):
        require(row['duration'] == reference.duration, 'The Reels draft duration differs from the package video.')
    return dict(row=row, rows=len(rows), target=(66, row['editedY']+6))


PREVIEW_WASHED = .8                 # Header band brightness (0..1); .85 on 22 Oct.
PREVIEW_OWNER_BAND = (60, 862, 340, 896)


def preview_playback(frame, reference):
    """The draft Preview's video. Pixels only."""
    media = video_match(frame, (0, 44, 500, 933), reference, ignore=((0, 44, 500, 112), (420, 560, 500, 900), (0, 820, 500, 933)))
    if not media['matched'] and media['mean'] is not None and media['mean'] <= COVER_NEAR_MEAN:
        # Framed slightly differently on 22 Oct (mean .12); the six tiles keep this package's colours (.04).
        media = dict(media, **tile_colours_match(pixels(frame, exact=True), (0, 44, 500, 933), reference))
    return media


def preview_compare(reference):
    """A newer Preview frame is the same screen when its button bar is unchanged and it still plays
    the package video; the video itself never holds still."""
    def compare(first, first_text, second, second_text):
        a, b = pixels(first, exact=True).astype(float), pixels(second, exact=True).astype(float)
        bar = float(np.abs(a[960:1030] - b[960:1030]).mean() / 255)
        media = preview_playback(second, reference)
        if bar <= .01 and media['matched']:
            return dict(state='ready', identity='package_video', bar=bar, automaticInputAllowed=False)
        return dict(state='wait', bar=bar, reason='The Preview changed or plays other media; capture again without input.',
                    automaticInputAllowed=False)
    return compare


def reel_preview(frame, text, reference, account, caption):
    """Draft Preview: account, caption and playing package media. Sample counts are not metrics."""
    no_overlay(text, DETAILS_BUTTONS)
    # The white title and back arrow vanish over a light video (22 Oct, slot 18: this test media's
    # white top); then the account, caption, buttons and media below decide alone.
    washed = float(pixels(frame, exact=True)[60:110, 150:350].mean()) / 255 > PREVIEW_WASHED
    if not washed:
        require(words_at(text, 'preview', (180, 62, 300, 100)), 'The Reel Preview is not recognized.')
        reel_control(frame, 'preview_back')
    owner = words_at(text, account.casefold(), (35, 870, 335, 935))
    # A handle OCR read cleanly that is unlike this account (the name row or the audio line) stops;
    # a garbled read of this account ('alle.xu', 22 Oct) is settled by the enlarged read below.
    from difflib import SequenceMatcher
    handles = []   # The first handle-like word of each line starting in the name row or the audio line.
    for line in text.get('lines', []):
        words = [w for w in line.get('words', []) if 35 <= w['x'] and w['x']+w['width'] <= 335]
        if not words or not 866 <= min(w['y'] for w in words) <= 910: continue
        first = next((w['text'] for w in words if re.fullmatch(r'[A-Za-z0-9._]{3,30}', str(w.get('text', '')))
                      and re.search(r'[a-z]', w['text'].casefold())), None)
        if first: handles.append(first)
    others = [h for h in handles if h.casefold() != account.casefold()
              and SequenceMatcher(None, h.casefold(), account.casefold()).ratio() < .5]
    require(owner or not others, 'Preview does not show the exact account.')
    if not owner:   # The light account name over the video's lower part is read enlarged.
        owner = [(round(x0), round(y0), round(x1), round(y1)) for t, x0, y0, x1, y1 in band_words(frame, PREVIEW_OWNER_BAND)
                 if t.casefold() == account.casefold() and x1 <= 335]
        require(len(owner) == 1, 'Preview does not show the exact account.')
    below = [row for row in rows_between(text, owner[0][3]+2, 950, 10, 440)]
    if below[:1] and 'original aud' in below[0].casefold():
        below = below[1:]   # The audio line ('<account> · Original audio') now sits above the caption (22 Oct).
    require(below[:1] == [caption], 'Preview caption is missing or different.')
    exact(text, 'Save draft', (80, 980, 190, 1012))
    require(words_at(text, 'share', (335, 980, 405, 1012)), 'Preview buttons are not recognized.')
    media = preview_playback(frame, reference)
    require(media['matched'], 'Preview plays different media.')
    return dict(media=media, accountVerified=True, saveTarget=(130, 996), metrics=None)


# ---- Safari transfer --------------------------------------------------------------

def reel_transfer_page(text, download):
    """The package page, top to bottom: title, file name, Download video, Copy caption."""
    order = []
    for label in ('Reel draft', 'File ' + download, 'Download video', 'Copy caption'):
        bounds = exact(text, label, (10, 80, 490, 940))
        order.append(bounds[1])
    require(order == sorted(order), 'The transfer page layout changed.')
    found = exact(text, 'Download video', (10, 80, 490, 940)); copy = exact(text, 'Copy caption', (10, 80, 490, 940))
    return dict(downloadTarget=(round((found[0]+found[2])/2), round((found[1]+found[3])/2)),
                copyTarget=(round((copy[0]+copy[2])/2), round((copy[1]+copy[3])/2)))


# OCR reads these alike in the address field's small type; a match folds them together.
_ADDRESS_FOLD = str.maketrans({'0': 'o', '1': 'l', 'i': 'l', '|': 'l', '5': 's', '8': 'b', '-': '_'})


def _address_fold(value): return value.casefold().translate(_ADDRESS_FOLD)


def typed_transfer_address(text, url):
    """Safari's address field, still being edited, shows this transfer's address before Enter.

    4 Nov (slot 18, 22:33): after the address was typed, Enter loaded an address the transfer server
    did not know (one 404, no page request) and Safari stayed on the previous transfer page, so no
    download could start. The field (left of its mic and clear buttons) shows the end of what was
    typed; that end must be the end of this transfer's own address. A previous transfer's address
    differs in its random path, so its end never matches. Recognition only."""
    rows = [line for line in text.get('lines', []) if line.get('words')
            and all(25 <= w['x'] and w['x'] + w['width'] <= 395 and 925 <= w['y'] and w['y'] + w['height'] <= 985 for w in line['words'])]
    require(len(rows) == 1, 'The Safari address field is not readable.')
    shown = ''.join(w['text'] for w in rows[0]['words'])
    expected = re.sub(r'^https?://', '', url)
    # A19 (5 Nov, also seen on A18): the final '/' beside the caret reads as 'l', and when the field is scrolled its
    # first visible glyph is cut by the field's edge ('9' read '3'). Transfer paths never contain l, I or 1.
    if len(shown) >= 2 and shown[-1] in 'l|I1': shown = shown[:-1] + '/'
    if len(shown.rstrip('/')) < len(expected.rstrip('/')): shown = shown[1:]
    require(len(shown.rstrip('/')) >= 24, 'The Safari address field shows too little of the address.')
    require(_address_fold(expected.rstrip('/')).endswith(_address_fold(shown.rstrip('/'))),
            'The Safari address field does not show this transfer address. Enter was not pressed.')
    return dict(addressTyped=True, shownChars=len(shown))


def caption_copied(text):
    # The phone wraps the confirmation ("... text in" / "Instagram."); the exact sentence may span rows.
    require('Caption copied. Verify the pasted text in Instagram.' in ' '.join(rows_between(text, 80, 1000)),
            'The transfer page did not confirm copying. No paste is permitted.')
    return dict(copied=True)


# The rows were identical on 17 and 20 Oct, but iOS placed the menu column about 85 px further
# right on 20 Oct (labels at x 139 instead of about 60). Only the rows are fixed; the labels
# must share one left edge, and the target is the exact label's own centre.
# Private Browsing has one row fewer between 'Open in New Tab' and 'Download Linked File' (slot 20,
# 22 Oct: Download at y 879 instead of 925), so the lower two rows may sit one row higher.
LINK_MENU = (('Open', (40, 765, 360, 800)), ('Open in New Tab', (40, 818, 360, 853)),
             ('Download Linked File', (40, 870, 360, 956)), ('Add to Reading List', (40, 923, 360, 1012)))


def link_menu(text):
    found = [exact(text, label, box) for label, box in LINK_MENU]
    lefts, tops = [b[0] for b in found], [b[1] for b in found]
    require(max(lefts) - min(lefts) <= 12, 'The Safari link menu items are not one column.')
    require(tops == sorted(tops) and 40 <= tops[3] - tops[2] <= 66, 'The Safari link menu rows are out of order.')
    require(line_at(text, 'hide preview', (355, 90, 480, 122)), 'The Safari link preview is not recognized.')
    bounds = found[2]
    return dict(target=(round((bounds[0]+bounds[2])/2), round((bounds[1]+bounds[3])/2)))


def leftover_link_menu(text):
    """An earlier run's link menu (touch and hold on the download link), left open over Safari
    (slot 20, 22 Oct). A tap on the dimmed background beside the menu, below the preview card,
    only dismisses it."""
    link_menu(text)
    return dict(leftoverLinkMenu=True, closeTarget=(50, 760))


def download_badge(frame):
    """Safari's downloads icon: filled while a download is shown (17 Oct) or outlined after it (20 Oct)."""
    try: reel_control(frame, 'safari_download')
    except InspectionStopped:
        try: reel_control(frame, 'safari_download_outline')
        except InspectionStopped:
            # Private Browsing's dark bar draws it as a white filled glyph (slot 20, 22 Oct: .28 of
            # its box bright; the same bar without a download .0).
            image = pixels(frame, exact=True).astype(int)
            dark = float(image[935:978, 150:350].mean()) < 110
            box = image[940:971, 76:107]
            bright = float((box.min(axis=2) > 215).mean())
            # While the file is still arriving the glyph is a blue progress ring (.12 of its box blue;
            # 22 Oct). The Downloads list later still requires the complete file size.
            ring = float(((box[..., 2] > 200) & (box[..., 0] < 90) & (box[..., 1] > 90)).mean())
            require(dark and (.2 <= bright <= .5 or .06 <= ring <= .4), 'Reel control changed: safari_download_outline')
    return dict(target=(91, 955))


PROMO = ({'not now', 'turn on'}, (90, 745, 410, 790))


def page_menu(text):
    no_overlay(text, (PROMO,))
    bounds = exact(text, 'Downloads', (40, 905, 170, 950))
    return dict(target=(round((bounds[0]+bounds[2])/2), round((bounds[1]+bounds[3])/2)))


def size_label(byte_count):
    return f'{round(byte_count/1000)} KB' if byte_count < 999_500 else f'{byte_count/1_000_000:.1f} MB'


def download_rows(text, left=85, top=560, bottom=1000):
    """OCR lines in the downloads list merged into visual rows: OCR sometimes splits one file name
    into fragments (21 Oct, slot 18: 'mouse' + '-cpfypm'). Returns (x0, y0, x1, y1, joined text)."""
    items = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        box = (min(w['x'] for w in words), min(w['y'] for w in words),
               max(w['x']+w['width'] for w in words), max(w['y']+w['height'] for w in words))
        if box[0] >= left and top <= box[1] <= bottom: items.append((*box, line['text']))
    rows = []
    for item in sorted(items, key=lambda i: (i[1]+i[3]) / 2):
        centre = (item[1]+item[3]) / 2
        row = next((r for r in rows if abs(r[0]-centre) <= 9), None)
        if row is None: rows.append([centre, [item]])
        else: row[1].append(item)
    return [(min(i[0] for i in items), min(i[1] for i in items), max(i[2] for i in items), max(i[3] for i in items),
             ''.join(i[4].replace(' ', '') for i in sorted(items))) for _, items in rows]


def code_similarity(name, code):
    """How closely an OCR'd download name's code (after 'imouse-<route>-') reads as `code`, 0..1."""
    import difflib
    tail = re.sub(r'^i?mouse(reel|tt|x|yt)?', '', re.sub(r'[^a-z]', '', name.casefold()))
    return difflib.SequenceMatcher(None, tail, code).ratio()


def downloads_list(text, download, byte_count, frame=None):
    exact(text, 'Downloads', (185, 512, 315, 548)); exact(text, 'Done', (18, 512, 90, 548)); exact(text, 'Clear', (415, 512, 490, 548))
    # The name's last part is this package's own six-letter code (no look-alike letters), so the
    # row is the one and only row ending in it, even when OCR splits or clips the rest of the name.
    code = download.rsplit('-', 1)[-1]
    # OCR can also drop the dash and the 'reel' part ('mouse' + 'htxkyd', 22 Oct, slot 18).
    names = [row[:4] for row in download_rows(text) if row[4] == download or row[4].endswith('-' + code)
             or (row[4].endswith(code) and re.match(r'i?mouse', row[4]))]
    exact_read = len(names) == 1 and len([row for row in download_rows(text) if code in row[4]]) == 1
    if not exact_read and not names:
        # OCR can mangle the code itself ('imouse-reel-eareef' read 'mouse' + '— a reef', slot 18, 25 Oct).
        # Then only the newest row may stand in for it: its code reads closer than .8 to this package's
        # and every other row's code reads at most .5. The preview header and media are checked next.
        scored = [(code_similarity(row[4], code), row) for row in download_rows(text) if not re.fullmatch(r'\d+KB|\d+(\.\d)?MB', row[4])]
        close = [row for score, row in scored if score >= .8]
        exact_read = (len(close) == 1 and close[0] is scored[0][1] and all(score <= .5 for score, row in scored[1:]))
        names = [close[0][:4]] if exact_read else []
    require(exact_read, 'The package download is absent or ambiguous.')
    x0, y0, x1, y1 = names[0]
    sizes = rows_between(text, y1+4, y1+30, 85, 400)
    if not sizes and frame is not None:
        # Full-frame OCR can miss the small grey size line ('31 KB', 23 Oct, slot 17); that row's name
        # and size are then read alone, enlarged (the size line by itself read as nothing). A misread
        # there still has to equal the expected label.
        words = [w for w in band_words(frame, (85, y0-4, 400, y1+42)) if y1 <= w[2] < y1+36]
        sizes = [' '.join(w[0] for w in sorted(words, key=lambda w: w[1]))] if words else []
    require(sizes[:1] == [size_label(byte_count)], 'The download is incomplete or has a different size.')
    return dict(target=(round((x0+x1)/2), round((y0+y1)/2)), size=sizes[0])


def player_overlay(text):
    """iOS's playback overlay over a previewed video: its two '10' skip buttons. While it shows,
    the whole video is dimmed (21 Oct, slot 18), so the picture cannot be compared yet."""
    tens = [min(w['x'] for w in line['words']) for line in text.get('lines', []) if line.get('words') and line['text'] == '10'
            and all(500 <= w['y'] <= 580 for w in line['words'])]
    return len(tens) == 2 and min(tens) < 200 < 300 < max(tens)


def tile_chroma(fill):
    """Colour proportions of the six test-media tiles (farm_reel_test_media layout), sampled at each
    tile's top-left corner, clear of the player's centre buttons. Even dimming keeps them."""
    height, width = fill.shape[:2]; rows = []
    for n in range(6):
        left, top = 60 + (n % 2)*310, 300 + (n // 2)*230
        x0, x1 = round((left+25)/720*width), round((left+95)/720*width)
        y0, y1 = round((top+25)/1280*height), round((top+85)/1280*height)
        colour = fill[y0:y1, x0:x1].reshape(-1, 3).mean(axis=0)
        rows.append(colour / max(float(colour.sum()), 1e-6))
    return np.array(rows)


def dimmed_video_match(frame, reference):
    """The package video under the player's dimming overlay: every tile's colour proportions must
    match the package's own first frame. Proportions are not fitted; dimming only scales them."""
    image = pixels(frame, exact=True)
    observed = np.asarray(Image.fromarray(image[96:985, 0:500]).resize(FILL, Image.Resampling.LANCZOS), dtype=float)/255
    # Undo the overlay's dimming as measured on the plain background between title and tiles; the
    # same per-channel factor applies to every tile (one physical overlay, not a fit per tile).
    height, width = observed.shape[:2]
    band = (slice(round(225/1280*height), round(290/1280*height)), slice(round(60/720*width), round(660/720*width)))
    scale = reference.fill[0][band].reshape(-1, 3).mean(axis=0) / np.maximum(observed[band].reshape(-1, 3).mean(axis=0), 1e-6)
    worst = float(np.abs(tile_chroma(np.clip(observed*scale, 0, 1)) - tile_chroma(reference.fill[0])).max())
    bright = float(observed.mean())
    matched = worst <= TILE_CHROMA and .25 <= bright
    return dict(status='tile_colour_match' if matched else 'different', matched=matched, worstTile=worst, brightness=bright,
                byteIdentityVerified=False)


TILE_CHROMA = .06   # Same video 0.037 under the overlay (21 Oct); closest palette pair (blue, sky) differs by 0.078.


def preview_media(frame, reference):
    """The package video in the preview, plain or under the player's dimming overlay. Pixels only."""
    media = video_match(frame, (0, 96, 500, 985), reference, ignore=((0, 880, 500, 985),))
    if not media['matched']: media = dimmed_video_match(frame, reference)
    require(media['matched'], 'The previewed download is not the package video.')
    return media


def quicklook(frame, text, download, reference):
    """Files preview of the downloaded package video. Controls may be hidden.

    The player's overlay dims the whole video and stays while it is paused at its end (21 Oct,
    slot 18), so a picture that does not match plainly is matched by its six tiles' colour
    proportions instead, which dimming keeps. The reviewed header name is required whenever the
    toolbar shows."""
    media = preview_media(frame, reference)
    controls = bool(present(frame, 'quicklook_share'))
    if controls:
        # OCR can split the name at its dash ('imouse-x- kxcyem', slot 17, 23 Oct): the header line is
        # compared with its spaces removed.
        named = words_at(text, download, (120, 65, 380, 110)) or any(
            l['text'].replace(' ', '') == download and 120 <= min(w['x'] for w in l['words'])
            and max(w['x']+w['width'] for w in l['words']) <= 380 and 65 <= min(w['y'] for w in l['words']) <= 110
            for l in text.get('lines', []) if l.get('words'))
        require(named and words_at(text, 'done', (410, 65, 490, 105)), 'The preview header does not show this download.')
    return dict(media=media, controls=controls, overlay=player_overlay(text), shareTarget=(40, 1012), doneTarget=(450, 85),
                revealTarget=(250, 300))


# Any earlier transfer's download name, from every draft route (as tiktok's leftover preview).
LEFTOVER_NAME = r'imouse-((reel|tt|x|yt)-[acdefhkmnprtuvwxy]{6}|draft)'


def header_names(text, pattern):
    """Download names in a preview header, each line's words joined: OCR can split one name
    ('imouse-x-' + 'hctunh', slot 17, 22 Oct)."""
    names = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        joined = ''.join(str(w.get('text', '')) for w in words)
        if (re.fullmatch(pattern, joined) and 120 <= min(w['x'] for w in words) and max(w['x']+w['width'] for w in words) <= 380
                and 65 <= min(w['y'] for w in words) and max(w['y']+w['height'] for w in words) <= 110):
            names.append(joined)
    return names


def leftover_preview(frame, text):
    """A Files preview of an earlier transfer, left open in Safari. Done only closes it."""
    names = header_names(text, LEFTOVER_NAME)
    require(len(names) == 1 and words_at(text, 'done', (410, 65, 490, 105)) and present(frame, 'quicklook_share'),
            'Safari opened on an unrecognized screen; no input is sent.')
    return dict(leftoverPreview=True, name=names[0], doneTarget=(450, 85))


SHARE_ROWS = (('Copy', (40, 755, 120, 795)), ('Save Video', (40, 828, 175, 863)), ('Add Tags', (40, 890, 150, 928)),
              ('Save to Files', (40, 950, 185, 985)), ('Add to Shared Album', (40, 1012, 265, 1046)))


SHARE_SWAP = {'Add Tags': (950, 985), 'Save to Files': (890, 928)}   # Each row's top and bottom when the two swap places.
SHARE_HEADER_TOP = 521      # The file name's top in the sheet header, as on 21-22 Oct.
SHARE_SHIFT = (-10, 60)     # iOS also settled the whole sheet 35 px lower (22 Oct, slot 18).


def share_header(text, name_pattern):
    """The sheet header's file name and the sheet's vertical shift from the usual position."""
    found = [(w['text'], round(w['y'] - SHARE_HEADER_TOP)) for line in text.get('lines', []) for w in line.get('words', [])
             if re.fullmatch(name_pattern, str(w.get('text', ''))) and 60 <= w['x'] and w['x']+w['width'] <= 320
             and SHARE_HEADER_TOP + SHARE_SHIFT[0] - 9 <= w['y'] and w['y']+w['height'] <= SHARE_HEADER_TOP + SHARE_SHIFT[1] + 24]
    return found[0] if len(found) == 1 else (None, None)


def share_rows(text, shift, frame=None):
    """The sheet's actions, moved with the sheet, or further down by a 'Send Copy' row under the
    header (slot 17, 22 Oct: Copy at y 795 with the header unmoved). The rows' own shift is taken
    from 'Copy', within the same bounds. A row pushed under the home indicator is not read."""
    copy = [w for line in text.get('lines', []) if line.get('text', '').strip().casefold() == 'copy' for w in line.get('words', [])
            if 40 <= w['x'] <= 70 and 755 + SHARE_SHIFT[0] - 10 <= w['y'] <= 755 + SHARE_SHIFT[1] + 10]
    if len(copy) == 1: shift = max(SHARE_SHIFT[0], min(SHARE_SHIFT[1], copy[0]['y'] - 765))
    rows = {}
    for label, (left, top, right, bottom) in SHARE_ROWS:
        if bottom + shift > 1046: continue
        box = (left, top + shift, right, bottom + shift)
        if label == 'Save Video' and frame is not None and not line_at(text, 'save video', box):
            rows[label] = enlarged_row(frame, label, box)   # Full-frame OCR read 'Save V o' (slot 17, 23 Oct).
        elif label in ('Copy', 'Save Video'): rows[label] = exact(text, label, box)   # Save Video is the target.
        else:
            # OCR can clip a neighbour's first letter into its icon ('ave to Files', slot 17, 22 Oct).
            try: rows[label] = exact(text, label, box)
            except InspectionStopped:
                # A19 (5 Nov) lists Save to Files before Add Tags: either of the two may hold the other's row.
                other = SHARE_SWAP.get(label)
                if other and other[1] + shift <= 1046:
                    try: rows[label] = exact(text, label, (left, other[0] + shift, max(right, 190), other[1] + shift))
                    except InspectionStopped: pass
    require(len(rows) >= 3, 'The share sheet actions are not recognized.')
    return rows


def leftover_share_sheet(text):
    """An earlier transfer's share sheet, left open over its preview (22 Oct, slot 18, after a stop
    on this sheet). Its close button only dismisses the sheet; the preview behind is closed next."""
    name, shift = share_header(text, LEFTOVER_NAME)
    require(name is not None, 'Safari opened on an unrecognized screen; no input is sent.')
    share_rows(text, shift)
    return dict(leftoverShareSheet=True, name=name, closeTarget=(460, 531 + shift))


def enlarged_row(frame, label, box):
    """One sheet row read again alone, enlarged: its words must be exactly the label, inside the row's
    box horizontally. Returns the row's bounds (the words' extent at the box's height)."""
    left, top, right, bottom = box
    words = band_words(frame, (30, top-10, 330, bottom+10), 3)
    require(' '.join(w[0] for w in sorted(words, key=lambda w: w[1])) == label
            and all(left <= w[1] and w[3] <= right for w in words), 'Exact visible label missing: ' + label)
    return (round(min(w[1] for w in words)), top+5, round(max(w[3] for w in words)), bottom-5)


class SheetPending(InspectionStopped):
    """The preview still shows its own header after Share was answered (slot 17, 23 Oct): the sheet
    slides up a moment later, so a later frame is read again without input."""


def share_sheet(text, download, frame=None):
    name, shift = share_header(text, re.escape(download))
    if name is None and line_at(text, download, (60, 60, 330, 110)) and line_at(text, 'done', (410, 60, 490, 110)):
        raise SheetPending('The share sheet has not opened yet; capture again without input.')
    require(name is not None, 'The share sheet is not for this download.')
    bounds = share_rows(text, shift, frame)['Save Video']
    return dict(target=(round((bounds[0]+bounds[2])/2), round((bounds[1]+bounds[3])/2)), shift=shift)
