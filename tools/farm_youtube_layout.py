"""Recognizers for the YouTube Short draft route, as observed on C24C. No input.

Positions come from retained 17 October C24C frames (500x1080; another frame size is
refused, so a phone of another model needs its own evidence), the transferred
MP4 Short (supervised steps 131-151). That run met YouTube's later layout: a
four-item navigation bar with an unlabelled +, and a picker headed "Create from
gallery". Earlier the same day (photo Short, steps 46-66) YouTube showed a
labelled five-item bar and another picker; those frames are negative controls
here, so an older or newer layout stops the run. The channel is whichever one
YouTube shows on Add details; it is read there and must not change. Video
checks compare frames decoded from the immutable package under fixed crops; a
match is visual evidence, not byte identity or proof that YouTube kept a draft.
Unknown or ambiguous screens stop.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image

from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import require, exact
from farm_screen_layout import pixels, words_at, line_at
from farm_reel_layout import UNIQUE_MARGIN, POINTER, band_words, no_overlay, rows_between, reel_paste_menu
from farm_tiktok_layout import media_match

# A 26-character title was read exactly on Add details and on one drafts-list
# line (17 Oct steps 65 and 147); a 32-character one ran into the title field's
# edge and lost its first letter to OCR (steps 145 and 149). Keep a margin.
CAPTION_LIMIT = 24
HANDLE = re.compile(r'@([A-Za-z0-9_.-]{1,50})')
TOAST = ({'draft saved'}, (25, 920, 220, 960))


def caption_supported(caption):
    """One short title line of printable ASCII; nothing is ever truncated or wrapped by the farm."""
    return (isinstance(caption, str) and 0 < len(caption) <= CAPTION_LIMIT and caption == caption.strip()
            and all(32 <= ord(c) <= 126 for c in caption) and '  ' not in caption)


def _reference(name):
    row = json.loads(Path(__file__).with_name('farm_youtube_controls.json').read_text(encoding='utf-8'))[name]
    raw = base64.b64decode(row['png'], validate=True)
    require(hashlib.sha256(raw).hexdigest() == row['sha256'], 'YouTube control reference is damaged.')
    with Image.open(io.BytesIO(raw)) as reference: return row['box'], np.asarray(reference.convert('RGB')).astype(float)


def control(frame, name, *, offset=(0, 0), ignore=()):
    """Fixed control template; same thresholds as the Reel and TikTok controls.

    The comparison mode is fixed per template: 'pixels' (opaque controls),
    'glyph' (dark icon shapes on the translucent navigation bar, whose tint
    follows the feed behind it) or 'disk' (the round selection badge, without
    the tile corners round it). ignore: frame rectangles left out (the parked
    pointer); a template mostly hidden by them is refused.
    """
    box, reference = _reference(name)
    mode = MODES[name]
    left, top, right, bottom = box; dx, dy = offset
    left, top, right, bottom = left+dx, top+dy, right+dx, bottom+dy
    require(0 <= left and right <= 500 and 0 <= top and bottom <= 1080, 'YouTube control is outside the frame.')
    observed = pixels(frame, exact=True)[top:bottom, left:right].astype(float)
    valid = np.ones(observed.shape[:2], dtype=bool)
    if mode == 'disk':
        yy, xx = np.ogrid[:observed.shape[0], :observed.shape[1]]
        cy, cx = (observed.shape[0]-1)/2, (observed.shape[1]-1)/2
        valid &= (yy-cy)**2 + (xx-cx)**2 <= 13**2
    for a, b, c, d in ignore:
        valid[max(0, b-top):max(0, d-top), max(0, a-left):max(0, c-left)] = False
    require(valid.mean() >= (.4 if mode == 'disk' else .6), 'YouTube control is hidden: '+name)
    if mode == 'glyph':
        shape, seen = reference.max(axis=2) < 110, observed.max(axis=2) < 110
        require(shape.sum() >= 20 and (shape != seen)[valid].mean() < .03, 'YouTube control changed: '+name)
    else:
        delta = np.abs(observed-reference)/255
        require(delta[valid].mean() < .02 and (delta[valid].max(axis=1) > 35/255).mean() < .04, 'YouTube control changed: '+name)
    return left, top, right, bottom


SAVE_LABEL = (64, 984, 178, 1006)   # The Save draft label inside its pill.


MODES = {'yt_home_logo': 'pixels', 'yt_home_actions': 'glyph', 'yt_nav_home': 'glyph', 'yt_nav_create': 'glyph',
         'yt_camera_record': 'pixels', 'yt_badge_one': 'disk', 'yt_picker_next': 'pixels', 'yt_trim_done': 'pixels',
         'yt_editor_next': 'pixels', 'yt_details_save': 'pixels', 'yt_details_upload': 'pixels', 'yt_details_back': 'pixels',
         'yt_drafts_header': 'pixels'}


def present(frame, name, **kwargs):
    try: control(frame, name, **kwargs); return True
    except InspectionStopped: return False


def white_fraction(image, box, level=230):
    left, top, right, bottom = box
    return float((image[top:bottom, left:right].min(axis=2) > level).mean())


def chrome_only(text, role):
    """Feed posts and gallery media are content, never controls: guards read only the app chrome there."""
    band = {'yt_home': (110, 980), 'yt_picker': (295, 1045), 'yt_picker_selected': (295, 866)}.get(role)
    if band is None: return text
    return {**text, 'lines': [r for r in text.get('lines', []) if not r.get('words')
                              or not band[0] <= min(w['y'] for w in r['words']) < band[1]]}


# ---- Home feed and camera ---------------------------------------------------------------

LABELLED_NAV = (('home', (25, 1012, 80, 1040)), ('shorts', (120, 1012, 180, 1040)), ('subscriptions', (300, 1012, 395, 1040)))


def labelled_create(frame):
    """The labelled five-item bar's + (slot 16, 22 Oct): a light grey disk centred at (250, 1011)
    with a dark plus; returns its centre or None."""
    image = pixels(frame, exact=True).astype(int)
    # Each 2 px stroke counts where any pixel across its width is dark.
    vertical = float((image[1003:1020, 246:255].min(axis=2).min(axis=1) < 90).mean())
    horizontal = float((image[1008:1015, 241:260].min(axis=2).min(axis=0) < 90).mean())
    disk = image[996:1027, 232:268]
    # The translucent bar tints the disk with the feed behind it (teal, red 194-200, run 73, 27 Oct).
    grey = float(((disk.min(axis=2) > 170) & (disk.mean(axis=2) > 200) & (disk.max(axis=2) < 246)).mean())
    return (250, 1011) if vertical > .8 and horizontal > .8 and grey > .4 else None


def yt_home(frame, text, *, saved=False):
    """Home feed with either observed bar: four unlabelled items (Home, Shorts, +, You; C24C, 17 Oct)
    or five labelled ones (Home, Shorts, +, Subscriptions, You; slot 16, 22 Oct). Feed content is
    arbitrary and never a target. saved: the home shown right after Save draft, where slot 16's
    'Draft saved' toast slides down over the + (23 Oct); no input follows there, so the + may be hidden."""
    require(words_at(text, 'youtube', (50, 65, 140, 105)), 'The YouTube home header is not recognized.')
    for name in ('yt_home_logo', 'yt_home_actions'): control(frame, name)
    if all(words_at(text, label, box) for label, box in LABELLED_NAV):
        target = labelled_create(frame)
        require(target or saved, 'The YouTube create button is not where it was observed.')
        layout = 'labelled'
    else:
        for name in ('yt_nav_home', 'yt_nav_create'): control(frame, name)
        # The unlabelled layout shows no tab labels; any other mix is neither observed bar.
        require(not any(words_at(text, label, (0, 1005, 500, 1045)) for label in ('home', 'shorts', 'subscriptions', 'you')),
                'This YouTube navigation bar is not the observed layout.')
        target, layout = (311, 1020), 'unlabelled'
    no_overlay(chrome_only(text, 'yt_home'))
    return dict(createTarget=target, navLayout=layout, toastSeen=bool(line_at(text, 'draft saved', TOAST[1])))


def enlarged_label(frame, label, box):
    """A small white label the full-frame OCR missed over a bright camera preview ('Add' over a lamp,
    slot 16, 26 Oct), read again enlarged; it must still lie inside its box."""
    left, top, right, bottom = box
    band = (max(0, left-10), top-8, min(500, right+10), bottom+8)
    for scale in (4, 3):   # 'Title' (run 67) is read only at 3, 'Add' (run 66) at 4.
        if any(t.casefold() == label and left <= x0 and x1 <= right and top <= y0 and y1 <= bottom
               for t, x0, y0, x1, y1 in band_words(frame, band, scale)): return True
    return False


RECORD_CORE = (236, 831, 264, 859)   # The record button's centre: red, or white with the effects row.


def yt_camera(frame, text):
    """The Short camera opened by +. Only Add (gallery) and Drafts are ever targets; record, Live and Post never."""
    for label, box in (('video', (135, 978, 200, 1008)), ('short', (218, 978, 282, 1008)), ('live', (300, 978, 352, 1008)),
                       ('post', (370, 978, 425, 1008)), ('add', (25, 878, 65, 900))):
        require(words_at(text, label, box) or enlarged_label(frame, label, box), 'The YouTube camera is not recognized: ' + label)
    require(line_at(text, 'add sound', (215, 110, 320, 140)), 'The YouTube camera is not recognized: add sound')
    image = pixels(frame, exact=True)
    # The record button is red, or white with the effects row beside it (after Start over, slot 16, 26 Oct).
    if not present(frame, 'yt_camera_record'):
        require(white_fraction(image, RECORD_CORE) >= .95, 'YouTube control changed: yt_camera_record')
    no_overlay(text)
    def tab(left, right):   # Background behind a mode label, its bright letters left out.
        part = image[970:1012, left:right].reshape(-1, 3)
        part = part[part.max(axis=1) < 120]
        return float(part.mean()) if len(part) else 255.
    others = [tab(132, 202), tab(300, 352), tab(368, 428)]
    require(tab(214, 286) - max(others) >= 25, 'The YouTube camera is not in Short mode.')
    drafts = words_at(text, 'drafts', (428, 878, 482, 900))
    return dict(addTarget=(46, 847), draftsTarget=(455, 846) if drafts else None)


def yt_draft_prompt(text):
    """YouTube's own 'Continue your draft video?' dialog over the Short camera, met after a cold start
    (slot 16, 23-26 Oct): 'Starting over will save the draft and start a new Short.' Start over is the
    target, at the centre of its OCR label; a tap 33 px above it, on the dialog body, did nothing, and
    the centre closed the dialog (26 Oct). Continue (reopening the unfinished draft) is never a target."""
    require(line_at(text, 'continue your draft video?', (90, 465, 415, 515)), 'No YouTube draft prompt is shown.')
    require(line_at(text, 'continue', (300, 590, 420, 640)), 'The draft prompt\'s Continue button is not recognized.')
    start = line_at(text, 'start over', (185, 590, 320, 640))
    require(start, 'The draft prompt\'s Start over button is not recognized.')
    left, top, right, bottom = start[0]
    return dict(target=((left + right) // 2, (top + bottom) // 2))


# ---- Gallery picker ------------------------------------------------------------------------

COLUMNS = ((0, 164), (168, 333), (336, 500))
ROW_TOP, ROW_PITCH, ROW_HEIGHT = 298, 295, 291


def _picker_header(frame, text, role):
    """Either observed gallery: 'Create from gallery' over 'Recents' (C24C, 17 Oct), or 'Recents' alone
    at the top left with Create video right below it (slot 16, 22 Oct), which moves the same grid up
    86 px. Returns the frame's pixels and that vertical offset."""
    if line_at(text, 'create from gallery', (8, 250, 220, 285)) and words_at(text, 'recents', (375, 250, 460, 280)):
        require(line_at(text, 'create video', (190, 190, 310, 220)), 'The YouTube picker header is not recognized.')
        dy, gutters = 0, ((164, 168), (333, 336))
    else:
        require(any(line['text'].strip().casefold().startswith('recents') and line.get('words')
                    and 15 <= min(w['x'] for w in line['words']) <= 40 and 65 <= min(w['y'] for w in line['words']) <= 95
                    for line in text.get('lines', [])),
                'The YouTube gallery picker is not recognized.')
        # Create video alone in the middle (22 Oct), or beside a Drafts button on the left (slot 16, 26 Oct,
        # when the Short camera no longer shows Drafts); the grid below is the same.
        require(line_at(text, 'create video', (190, 160, 310, 195)) or gallery_drafts(text),
                'The YouTube picker header is not recognized.')
        # This gallery draws the first column one pixel wider (to x 164) in its second row.
        dy, gutters = -86, ((165, 168), (333, 336))
    no_overlay(chrome_only(text, role))
    image = pixels(frame, exact=True)
    for x0, x1 in gutters:
        require((image[300+dy:860+dy, x0:x1].max(axis=2) < 40).mean() > .95, 'YouTube picker grid geometry changed.')
    require((image[589+dy:593+dy, 5:495].max(axis=2) < 40).mean() > .95, 'YouTube picker grid geometry changed.')
    return image, dy


def gallery_drafts(text):
    """The gallery's Drafts button (left) beside Create video (right), slot 16, 26 Oct: Drafts' centre or None."""
    drafts = words_at(text, 'drafts', (90, 160, 170, 195))
    if not drafts or not line_at(text, 'create video', (300, 160, 440, 195)): return None
    return 128, 177


def yt_gallery(frame, text):
    """The gallery opened from the Short camera's Add, used by the read-only verifier only to reach Drafts
    (slot 16, 26 Oct). Media and Create video are never targets here; its X returns to the camera."""
    _picker_header(frame, text, 'yt_picker')
    target = gallery_drafts(text)
    require(target, 'The YouTube gallery shows no Drafts button.')
    return dict(draftsTarget=target, closeTarget=GALLERY_CLOSE)


GALLERY_CLOSE = (465, 87)


def _tiles(bottom, dy=0):
    """Complete tiles above the given bottom edge; never scroll to find more."""
    for row in range(3):
        top = ROW_TOP + dy + row*ROW_PITCH
        if top + ROW_HEIGHT > bottom: break
        for left, right in COLUMNS: yield (left, top, right, top+ROW_HEIGHT)


def circle(tile):
    left, top, right, bottom = tile
    return right-23, top+22


def badge(frame, tile):
    """The numbered selection disk at this tile's circle (template taken at circle (141, 320))."""
    x, y = circle(tile)
    return present(frame, 'yt_badge_one', offset=(x-141, y-320), ignore=(POINTER,))


def border(image, tile):
    """The white frame YouTube draws round a selected tile. Supplementary: a white picture has white edges too."""
    left, top, right, bottom = tile
    sides = ((left+1, top+5, left+3, bottom-5), (right-3, top+5, right-1, bottom-5))
    # The top edge sits one pixel lower in slot 16's shifted gallery (y 214-215 for a tile top of 212, 22 Oct).
    tops = [(left+5, top+shift, right-5, top+shift+2) for shift in (1, 2)]
    return all(white_fraction(image, box, 200) > .9 for box in sides) and max(white_fraction(image, box, 200) for box in tops) > .9


def _tile_match(frame, tile, reference, image):
    left, top, right, bottom = tile
    return media_match(frame, (left+2, top+2, right-2, bottom-2), reference, 'fill', image=image,
                       ignore=((right-52, bottom-40, right, bottom), (right-45, top, right, top+45)))


def _veiled_match(frame, tile, reference, image):
    """Slot 16's gallery draws the selected tile under a dark veil (white read as about 180, 22 Oct).
    The veil's gain comes from the tile's brightest picture pixels (badge and duration corners left out);
    only a plausible veil is undone, and only inside the tile, before the same match."""
    left, top, right, bottom = tile
    bright = float(np.percentile(image[top+50:bottom-45, left+5:right-5].max(axis=2), 98))
    gain = 255/max(bright, 1)
    if not 1.2 <= gain <= 1.7: return dict(matched=False, status='no_veil', veilGain=round(gain, 3))
    lifted = image.copy()
    lifted[top:bottom, left:right] = np.clip(image[top:bottom, left:right].astype(float)*gain, 0, 255).astype(image.dtype)
    return dict(_tile_match(frame, tile, reference, lifted), veilGain=round(gain, 3))


def _duration(text, tile):
    left, top, right, bottom = tile
    return [w['text'] for line in text.get('lines', []) for w in line.get('words', [])
            if re.fullmatch(r'\d:\d\d', str(w.get('text', ''))) and right-60 <= w['x'] and w['x']+w['width'] <= right
            and bottom-34 <= w['y'] and w['y']+w['height'] <= bottom]


def yt_picker(frame, text, reference):
    """Unselected gallery: the one complete tile showing the package video, nothing selected yet."""
    image, dy = _picker_header(frame, text, 'yt_picker')
    require(not words_at(text, 'next', (330, 975, 410, 1015)) and not present(frame, 'yt_picker_next'),
            'The YouTube picker already offers Next; review the selection.')
    tiles = list(_tiles(1040, dy))
    require(len(tiles) == 6, 'YouTube picker grid geometry changed.')
    require(not any(badge(frame, t) for t in tiles), 'A YouTube picker item already shows a selection.')
    scored = [(t, _tile_match(frame, t, reference, image)) for t in tiles]
    matched = [(t, v) for t, v in scored if v['matched']]
    require(len(matched) == 1, 'The package video is absent or ambiguous in the YouTube picker; nothing is selected.')
    tile, best = matched[0]
    others = sorted(v['mean'] for t, v in scored if t != tile and v['mean'] is not None)
    require(not others or others[0]-best['mean'] >= UNIQUE_MARGIN, 'Another picker item looks too similar to the package video.')
    label = _duration(text, tile)
    if label: require(len(label) == 1 and label[0] == reference.duration, 'The picker duration differs from the package video.')
    return dict(tile=list(tile), target=circle(tile), match=best, nearestOther=others[0] if others else None,
                durationRead=label[0] if label else None)


def yt_picker_selected(frame, text, reference, tile):
    """Exactly one selection, number 1 on the tile chosen from the unselected frame, one tray item and Next."""
    image, dy = _picker_header(frame, text, 'yt_picker_selected')
    tile = tuple(tile)
    complete = list(_tiles(866, dy))
    require(tile in complete, 'The chosen YouTube picker item is no longer fully visible.')
    require(badge(frame, tile) and border(image, tile), 'The chosen video is not visibly selected as number 1.')
    require(not any(badge(frame, t) for t in complete if t != tile), 'Another YouTube picker item is selected.')
    match = _tile_match(frame, tile, reference, image)
    if not match['matched']: match = _veiled_match(frame, tile, reference, image)
    require(match['matched'], 'The selected YouTube picker item shows different media.')
    # The tray holds exactly one small thumbnail; it is too dark to compare, so only its count is read.
    require((image[884:942, 16:74].max(axis=2) > 12).mean() > .9, 'The YouTube selection tray is empty.')
    require((image[878:950, 84:490].max(axis=2) < 12).mean() > .97, 'The YouTube selection tray holds more than one item.')
    exact(text, 'Next', (335, 980, 400, 1012)); control(frame, 'yt_picker_next')
    label = _duration(text, (16, 884, 74, 942))
    return dict(tile=list(tile), tileMatch=match, trayDurationRead=label[0] if label else None, target=(367, 997))


# ---- Trim review and editor -------------------------------------------------------------------

def seconds_label(seconds):
    return f'{seconds:.1f}s'


def whole_video(image):
    """The white selection frame spans the whole strip, handles at both ends: nothing is trimmed."""
    edges = [max(white_fraction(image, (40, y, 460, y+1), 200) for y in band) for band in (range(882, 894), range(951, 964))]
    handles = all(white_fraction(image, box, 200) > .95 for box in ((24, 892, 28, 955), (472, 892, 476, 955)))
    return min(edges) > .95 and handles


def yt_trim(frame, text, reference):
    """Trim review after Next: the package video, untrimmed, with Done."""
    require(line_at(text, 'drag to adjust video', (8, 990, 170, 1022)), 'The YouTube trim review is not recognized.')
    exact(text, 'Done', (420, 990, 480, 1020)); control(frame, 'yt_trim_done')
    no_overlay(text)
    image = pixels(frame, exact=True)
    require(whole_video(image), 'The YouTube trim selection does not cover the whole package video; nothing is trimmed.')
    media = media_match(frame, (50, 154, 450, 868), reference, 'fill', image=image)
    require(media['matched'], 'The YouTube trim review shows different media.')
    label = [w['text'] for line in text.get('lines', []) for w in line.get('words', [])
             if re.fullmatch(r'\d+\.\ds', str(w.get('text', ''))) and 200 <= w['x'] and w['x']+w['width'] <= 300
             and 905 <= w['y'] and w['y']+w['height'] <= 940]
    if label: require(label == [seconds_label(reference.seconds)], 'The YouTube trim length differs from the package video.')
    return dict(media=media, wholeVideo=True, lengthRead=label[0] if label else None, target=(449, 1005))


EDITOR_TOOLS = (('text', (355, 350, 412, 382)), ('effects', (340, 410, 415, 440)), ('filters', (340, 470, 415, 500)),
                ('stickers', (330, 530, 415, 562)), ('captions', (325, 590, 415, 622)), ('voiceover', (310, 650, 410, 682)))


def yt_editor(frame, text, reference):
    """Editor with the package video playing. Edit and Add sound are never targets."""
    require(line_at(text, 'add sound', (215, 85, 320, 115)), 'The YouTube editor is not recognized.')
    exact(text, 'Next', (340, 990, 400, 1020)); control(frame, 'yt_editor_next')
    require(words_at(text, 'edit', (120, 990, 170, 1020)), 'The YouTube editor buttons are not recognized.')
    no_overlay(text)
    media = media_match(frame, (0, 71, 500, 958), reference, 'fill',
                        ignore=((0, 71, 500, 135), (320, 330, 500, 700), (150, 920, 350, 965)))
    require(media['matched'], 'The YouTube editor shows different media.')
    # The tool labels fade a few seconds after the editor opens (17 Oct steps 141-142); they are recorded only.
    tools = [name for name, box in EDITOR_TOOLS if words_at(text, name, box)]
    return dict(media=media, toolLabelsRead=tools, target=(368, 1006))


# ---- Add details -----------------------------------------------------------------------------

TITLE_BAND = (125, 146, 495, 190)
DETAILS_BUTTONS = (({'save draft'}, (80, 980, 180, 1012)),)


class CaretVisible(InspectionStopped):
    """The title field's caret is drawn; a later frame may show the text without it. No input follows."""


class Processing(CaretVisible):
    """The reopened editor's 'Processing' overlay after Next (slot 16, 23 Oct): Add details follows by
    itself, so a later frame is awaited the same way, read-only."""


def caret_visible(image):
    """A thin dark vertical bar taller than any title glyph (about 24 px against 16).

    The caret fades rather than blinking off: mid-fade it is grey, above the dark level, yet still
    clips the last letter for OCR ('tes€', run 68, slot 16, 26 Oct). So an unbroken grey run of 20 px
    in one column counts too; the grey 'Title' label above the text is separated from it by a gap."""
    left, top, right, bottom = TITLE_BAND
    band = image[top:bottom, left:right].max(axis=2)
    if ((band < 120).sum(axis=0) >= 20).any(): return True
    run = best = np.zeros(band.shape[1], dtype=int)
    for row in band < 200:
        run = np.where(row, run + 1, 0); best = np.maximum(best, run)
    return bool((best >= 20).any())


def handle(text):
    """The one channel handle under the channel name; personal content is never read elsewhere."""
    found = [m.group(1) for line in text.get('lines', []) if line.get('words')
             and 65 <= min(w['x'] for w in line['words']) <= 90 and 330 <= min(w['y'] for w in line['words']) <= 480
             for m in [HANDLE.fullmatch(' '.join(str(line.get('text', '')).split()))] if m]
    require(len(found) == 1, 'The YouTube channel on Add details is not uniquely readable.')
    return found[0]


def yt_details(frame, text, reference, caption=None, *, state):
    """Add details. state: 'blank' placeholder, 'focused' empty field, or 'titled' with the exact caption.

    Upload Short publishes and is never a target; Save draft is.
    """
    if line_at(text, 'processing', (170, 540, 330, 585)): raise Processing('YouTube is still processing the draft; capture again without input.')
    no_overlay(text, DETAILS_BUTTONS)
    require(words_at(text, 'details', (90, 70, 195, 102)), 'YouTube Add details is not recognized.')
    exact(text, 'Save draft', (80, 980, 180, 1012)); exact(text, 'Upload Short', (305, 980, 435, 1012))
    # Slot 16 draws the 'Save draft' label one size larger than the template (22 Oct); the pill is still
    # compared and the label is read exactly above.
    control(frame, 'yt_details_save', ignore=(SAVE_LABEL,)); control(frame, 'yt_details_upload'); control(frame, 'yt_details_back')
    require(words_at(text, 'visibility', (55, 395, 130, 510)) and line_at(text, 'select audience', (55, 530, 220, 600)),
            'The YouTube details fields are not recognized.')
    channel = handle(text)
    image = pixels(frame, exact=True)
    cover = media_match(frame, (15, 125, 119, 282), reference, 'card', image=image, ignore=((15, 125, 62, 168), (60, 245, 119, 282)))
    require(cover['matched'], 'The YouTube details cover shows different media.')
    left, top, right, bottom = TITLE_BAND
    # Full-frame OCR can drop the small 'Title' label while the caret blinks beside the pasted title
    # (run 67, slot 16, 26 Oct); the label alone is read again, enlarged.
    labelled = bool(words_at(text, 'title', (125, 130, 175, 155))) or (state != 'blank' and enlarged_label(frame, 'title', (125, 130, 175, 155)))
    rows = rows_between(text, 150 if labelled else top, bottom, left, right)
    if state == 'blank':
        if not labelled and rows != ['Caption your Short']:
            # Full-frame OCR clipped the grey placeholder ('Caption y', slot 16, 23 Oct); the field
            # alone is read again, enlarged, and must hold exactly the placeholder.
            rows = [' '.join(w[0] for w in sorted(band_words(frame, TITLE_BAND, 3), key=lambda w: (round(w[2]/12), w[1])))]
        require(not labelled and rows == ['Caption your Short'], 'The YouTube title is not empty.')
    else:
        require(labelled, 'The YouTube title field is not focused.')
        if state == 'focused':
            # The caret proves focus here; OCR may misread it as a letter, so that frame is captured again.
            if rows and caret_visible(image): raise CaretVisible('The title caret may be read as text; capture again without input.')
            require(not rows, 'The YouTube title field is not empty.')
        else:
            if caret_visible(image): raise CaretVisible('The title caret is drawn; capture again without input.')
            bounds = [(min(w['x'] for w in line['words']), max(w['x']+w['width'] for w in line['words']))
                      for line in text.get('lines', []) if line.get('words') and line['text'] in rows]
            require(rows == [caption] and len(bounds) == 1 and bounds[0][0] >= 128 and bounds[0][1] <= 470,
                    'The visible YouTube title is missing, different or does not fit the field.')
    return dict(channel=channel, cover=cover, state=state, captionExact=state == 'titled',
                titleTarget=(256, 161), pressTarget=(220, 165), saveTarget=(130, 996))


def yt_paste_menu(frame, text):
    """The system Paste callout over the focused title; same rule as the Reel caption."""
    return reel_paste_menu(frame, text, press_y=165)


# ---- Drafts list -----------------------------------------------------------------------------

THUMB = (15, 153)
DRAFT_TOP, DRAFT_PITCH, DRAFT_HEIGHT = 190, 224, 206   # Fixed rows; only those fully on screen are read.
WHEN = re.compile(r'(\d+ (second|minute|hour|day|week|month|year)s? ago|just now|[A-Z][a-z]{2} \d{1,2}, \d{4})')


def title_lines(lines, caption):
    """The visible title equals the caption on one line, or wrapped once at a hyphen or a space."""
    if lines == [caption]: return True
    if len(lines) != 2: return False
    first, second = lines
    return (first.endswith('-') and first + second == caption) or first + ' ' + second == caption


def drafts_notice(text):
    """The notice under the Drafts header, two lines. OCR can clip their first letters ('moving the
    YouTube app ...', 's device.', run 70, slot 16, 26 Oct): each line must end with its words."""
    def ends(tail, box, longest):
        left, top, right, bottom = box
        return sum(1 for line in text.get('lines', []) if line.get('words')
                   and left <= min(w['x'] for w in line['words']) and max(w['x']+w['width'] for w in line['words']) <= right
                   and top <= min(w['y'] for w in line['words']) and max(w['y']+w['height'] for w in line['words']) <= bottom
                   and ' '.join(line['text'].casefold().split()).endswith(tail)
                   and len(' '.join(line['text'].split())) <= longest) == 1
    return (ends('the youtube app will delete all draft videos created on', (10, 125, 470, 156), 64)
            and ends('device.', (10, 145, 110, 170), 12))


def yt_drafts(frame, text, reference, caption):
    """Drafts on this device: the one row whose full title equals the caption and whose thumbnail is the package video."""
    require(drafts_notice(text), 'The YouTube drafts list is not recognized.')
    control(frame, 'yt_drafts_header')
    no_overlay(text)
    image = pixels(frame, exact=True)
    rows = []
    for top in range(DRAFT_TOP, 1035-DRAFT_HEIGHT, DRAFT_PITCH):
        bottom = top + DRAFT_HEIGHT
        # An empty slot is plain background; light test media still differs from it.
        if (image[top+4:bottom-4, THUMB[0]+4:THUMB[1]-4].min(axis=2) < 235).mean() < .05: continue
        require((image[top-16:top-3, THUMB[0]:THUMB[1]].min(axis=2) > 235).mean() > .97, 'YouTube drafts list geometry changed.')
        # Only words in the title column: OCR can join the thumbnail's own 'TEST' to the title line
        # ('TEST Fresh short test', run 70, slot 16, 26 Oct).
        columns = [[w for w in r['words'] if w['x'] >= 155] for r in text.get('lines', []) if r.get('words')]
        lines = sorted((min(w['y'] for w in ws), ' '.join(w['text'] for w in ws)) for ws in columns if ws
                       and 160 <= min(w['x'] for w in ws) <= 180 and top <= min(w['y'] for w in ws) < top+110)
        when = [i for i, (_, value) in enumerate(lines) if WHEN.fullmatch(value)]
        titles = [value for _, value in (lines[:when[0]] if when else lines)]
        match = media_match(frame, (THUMB[0], top, THUMB[1], bottom), reference, 'card', image=image,
                            ignore=((THUMB[1]-55, bottom-36, THUMB[1], bottom),))
        rows.append(dict(top=top, bottom=bottom, title=titles, when=lines[when[0]][1] if when else None, match=match))
    require(rows, 'No YouTube drafts are recognized.')
    exact_rows = [r for r in rows if title_lines(r['title'], caption)]
    if len(exact_rows) > 1:   # Same title from an earlier test: the package video's thumbnail decides, as on X (23 Oct).
        exact_rows = [r for r in exact_rows if r['match']['matched']]
    require(len(exact_rows) == 1, 'The exact draft title is absent or ambiguous in YouTube drafts.')
    row = exact_rows[0]
    require(row['match']['matched'], 'The YouTube draft with this title does not show the package video.')
    return dict(row=row, rows=len(rows), target=(228, row['top']+74))
