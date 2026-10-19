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


def reel_control(frame, name, exclude_columns=()):
    """Fixed control template; same thresholds as the carousel controls."""
    row = json.loads(Path(__file__).with_name('farm_reel_controls.json').read_text(encoding='utf-8'))[name]
    raw = base64.b64decode(row['png'], validate=True)
    require(hashlib.sha256(raw).hexdigest() == row['sha256'], 'Reel control reference is damaged.')
    left, top, right, bottom = row['box']
    image = pixels(frame, exact=True)
    with Image.open(io.BytesIO(raw)) as reference:
        delta = np.abs(image[top:bottom, left:right].astype(float)-np.asarray(reference.convert('RGB')).astype(float))/255
    valid = np.ones(delta.shape[:2], dtype=bool)
    for a, b in exclude_columns: valid[:, a-left:b-left] = False
    require(delta[valid].mean() < .02 and (delta[valid].max(axis=1) > 35/255).mean() < .04, 'Reel control changed: '+name)
    return row['box']


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

def reel_create(frame, text):
    """The observed Create sheet; OCR often omits 'Reel', so its icon is required too."""
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


def reel_picker(frame, text, reference):
    """Locate the one Recents tile that shows the package video."""
    image, chip, count = _picker_frame(frame, text)
    tiles = []
    for r, (top, bottom) in enumerate(PICKER_ROWS):
        for c, (left, right) in enumerate(PICKER_COLUMNS):
            if (r, c) == (0, 0): continue  # Camera shortcut, never media.
            result = video_match(frame, (left+2, top+2, right-2, bottom-2), reference, image=image,
                ignore=((right-46, top, right, top+46), (right-92, bottom-42, right, bottom)))
            tiles.append(((r, c), result))
    matched = [(cell, value) for cell, value in tiles if value['matched']]
    require(len(matched) == 1, 'The package video is absent or ambiguous in Recents; nothing is selected.')
    cell, best = matched[0]
    others = sorted(v['mean'] for c, v in tiles if c != cell and v['mean'] is not None)
    require(not others or others[0]-best['mean'] >= UNIQUE_MARGIN, 'Another Recents item looks too similar to the package video.')
    require(all(white_disk(image, (r, c)) < .3 for r in range(len(PICKER_ROWS)) for c in range(3) if (r, c) != (0, 0)),
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
    require(all(white_disk(image, (r, c)) < .3 for r in range(len(PICKER_ROWS)) for c in range(3) if (r, c) not in ((0, 0), cell)),
            'Another Recents item is selected or unreadable.')
    exact(text, 'First draft', (290, 975, 395, 1012))
    reel_control(frame, 'next_pill')
    # The tray thumbnail carries a remove X at its top-right; it is never tapped.
    tray = video_match(frame, (16, 963, 51, 1025), reference, image=image, ignore=((38, 958, 55, 978),))
    require(tray['matched'], 'The selection tray does not show the package video.')
    return dict(cell=list(cell), tray=tray, target=(444, 993))


def reel_editor(frame, text, reference):
    no_overlay(text)
    exact(text, 'Edit video', (25, 975, 125, 1008))
    toolbar = [words_at(text, name, box) for name, box in (('audio', (45, 902, 108, 942)), ('voice', (222, 902, 282, 942)),
                                                           ('captions', (298, 902, 380, 942)), ('overlay', (390, 902, 465, 942)))]
    require(sum(bool(t) for t in toolbar) >= 3, 'The Reel editor toolbar is not recognized.')
    require(words_at(text, 'next', (405, 975, 470, 1008)) or present(frame, 'next_pill'), 'The editor Next control is not verified.')
    media = video_match(frame, (0, 56, 500, 945), reference, ignore=((0, 56, 80, 120), (0, 880, 500, 945)))
    require(media['matched'], 'The Reel editor shows different media.')
    return dict(media=media, target=(444, 993))


DETAILS_BUTTONS = (({'save draft'}, (80, 980, 190, 1012)), ({'cancel'}, (12, 62, 90, 96)))


def reel_details(frame, text, reference, caption=None, *, reopened=False):
    """Fresh or reopened details. caption=None requires the empty placeholder."""
    no_overlay(text, DETAILS_BUTTONS)
    exact(text, 'New reel', (190, 62, 310, 100))
    require(words_at(text, 'preview', (185, 150, 268, 188)) and line_at(text, 'edit cover', (182, 405, 292, 445)),
            'The Reel cover card is not recognized.')
    for name, box in (('poll', (180, 605, 235, 640)), ('prompt', (245, 605, 350, 640)),
                      ('location', (60, 735, 190, 770)), ('original', (330, 790, 480, 825))):
        require(words_at(text, name, box), 'Reel details field missing: ' + name)
    exact(text, 'Save draft', (80, 980, 190, 1012))
    require(words_at(text, 'share', (335, 980, 405, 1012)), 'Reel details buttons are not recognized.')
    if reopened:
        require(words_at(text, 'cancel', (12, 62, 90, 96)) and words_at(text, 'edit', (430, 62, 490, 96)),
                'The reopened draft header is not recognized.')
    else:
        reel_control(frame, 'details_back')
    lines = rows_between(text, 470, 530, 10, 490)
    if caption is None:
        require(lines == ['Add a caption...'], 'The new Reel caption is not empty.')
    else:
        require(lines == [caption], 'The visible Reel caption is missing, different or wrapped.')
    cover = video_match(frame, (160, 136, 340, 456), reference, ignore=((182, 148, 270, 190), (180, 402, 295, 448)))
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


def reel_preview(frame, text, reference, account, caption):
    """Draft Preview: account, caption and playing package media. Sample counts are not metrics."""
    no_overlay(text, DETAILS_BUTTONS)
    require(words_at(text, 'preview', (180, 62, 300, 100)), 'The Reel Preview is not recognized.')
    reel_control(frame, 'preview_back')
    owner = words_at(text, account.casefold(), (35, 870, 335, 935))
    require(owner, 'Preview does not show the exact account.')
    below = [row for row in rows_between(text, owner[0][3]+2, 950, 10, 440)]
    require(below[:1] == [caption], 'Preview caption is missing or different.')
    exact(text, 'Save draft', (80, 980, 190, 1012))
    require(words_at(text, 'share', (335, 980, 405, 1012)), 'Preview buttons are not recognized.')
    media = video_match(frame, (0, 44, 500, 933), reference, ignore=((0, 44, 500, 112), (420, 560, 500, 900), (0, 820, 500, 933)))
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


def caption_copied(text):
    require('Caption copied. Verify the pasted text in Instagram.' in rows_between(text, 80, 1000),
            'The transfer page did not confirm copying. No paste is permitted.')
    return dict(copied=True)


LINK_MENU = (('Open', (55, 765, 140, 800)), ('Open in New Tab', (55, 818, 245, 853)),
             ('Download Linked File', (55, 925, 275, 956)), ('Add to Reading List', (55, 978, 255, 1012)))


def link_menu(text):
    for label, box in LINK_MENU: exact(text, label, box)
    require(line_at(text, 'hide preview', (355, 90, 480, 122)), 'The Safari link preview is not recognized.')
    bounds = exact(text, 'Download Linked File', (55, 925, 275, 956))
    return dict(target=(round((bounds[0]+bounds[2])/2), round((bounds[1]+bounds[3])/2)))


def download_badge(frame):
    reel_control(frame, 'safari_download')
    return dict(target=(91, 955))


PROMO = ({'not now', 'turn on'}, (90, 745, 410, 790))


def page_menu(text):
    no_overlay(text, (PROMO,))
    bounds = exact(text, 'Downloads', (40, 905, 170, 950))
    return dict(target=(round((bounds[0]+bounds[2])/2), round((bounds[1]+bounds[3])/2)))


def size_label(byte_count):
    return f'{round(byte_count/1000)} KB' if byte_count < 999_500 else f'{byte_count/1_000_000:.1f} MB'


def downloads_list(text, download, byte_count):
    exact(text, 'Downloads', (185, 512, 315, 548)); exact(text, 'Done', (18, 512, 90, 548)); exact(text, 'Clear', (415, 512, 490, 548))
    names = [(min(w['x'] for w in line['words']), min(w['y'] for w in line['words']),
              max(w['x']+w['width'] for w in line['words']), max(w['y']+w['height'] for w in line['words']))
             for line in text.get('lines', []) if line.get('words') and line['text'] == download]
    require(len(names) == 1 and 85 <= names[0][0] and 560 <= names[0][1] <= 1000, 'The package download is absent or ambiguous.')
    x0, y0, x1, y1 = names[0]
    sizes = rows_between(text, y1+4, y1+30, 85, 400)
    require(sizes[:1] == [size_label(byte_count)], 'The download is incomplete or has a different size.')
    return dict(target=(round((x0+x1)/2), round((y0+y1)/2)), size=sizes[0])


def quicklook(frame, text, download, reference):
    """Files preview of the downloaded package video. Controls may be hidden."""
    media = video_match(frame, (0, 96, 500, 985), reference, ignore=((0, 880, 500, 985),))
    require(media['matched'], 'The previewed download is not the package video.')
    controls = present(frame, 'quicklook_share')
    if controls:
        require(words_at(text, download, (150, 65, 360, 110)) and words_at(text, 'done', (410, 65, 490, 105)),
                'The preview header does not show this download.')
    return dict(media=media, controls=controls, shareTarget=(40, 1012), doneTarget=(450, 85), revealTarget=(250, 300))


def leftover_preview(frame, text):
    """A Files preview of an earlier transfer, left open in Safari. Done only closes it."""
    names = [w['text'] for line in text.get('lines', []) for w in line.get('words', [])
             if re.fullmatch(r'imouse-(reel-[acdefhkmnprtuvwxy]{6}|draft)', str(w.get('text', '')))
             and 150 <= w['x'] and w['x']+w['width'] <= 360 and 65 <= w['y'] and w['y']+w['height'] <= 110]
    require(len(names) == 1 and words_at(text, 'done', (410, 65, 490, 105)) and present(frame, 'quicklook_share'),
            'Safari opened on an unrecognized screen; no input is sent.')
    return dict(leftoverPreview=True, name=names[0], doneTarget=(450, 85))


SHARE_ROWS = (('Copy', (40, 755, 120, 795)), ('Save Video', (40, 828, 175, 863)), ('Add Tags', (40, 890, 150, 928)),
              ('Save to Files', (40, 950, 185, 985)), ('Add to Shared Album', (40, 1012, 265, 1046)))


def share_sheet(text, download):
    require(words_at(text, download, (60, 512, 320, 545)), 'The share sheet is not for this download.')
    for label, box in SHARE_ROWS: exact(text, label, box)
    bounds = exact(text, 'Save Video', (40, 828, 175, 863))
    return dict(target=(round((bounds[0]+bounds[2])/2), round((bounds[1]+bounds[3])/2)))
