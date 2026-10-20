"""Recognizers for the observed C24C TikTok video draft route. No input.

Positions come from retained 17 October C24C frames (500x1080, supervised
steps 94-113). Video checks compare frames decoded from the immutable package;
a match is visual evidence, not byte identity, app authenticity or proof that
TikTok persisted a draft. Unknown or ambiguous screens stop.
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
from farm_creation_layout import require, exact
from farm_screen_layout import pixels, words_at, line_at
from farm_reel_layout import (MATCH_MEAN, MATCH_BLOCK, UNIQUE_MARGIN, POINTER, SAMPLE_FPS, FILL, SQUARE,
                              no_overlay, rows_between, duration_label, reel_paste_menu, present as reel_present)
from farm_video import probe_video, run_media

# Centre crops observed on 17 Oct: picker tiles and tray (square), profile and
# drafts tiles (3:4), the details cover card, and the full 9:16 editor canvas.
MODELS = {'fill': (640, FILL), 'square': (360, SQUARE), 'portrait': (480, (45, 60)), 'card': (528, (45, 66))}
CAPTION_LIMIT = 24          # One unwrapped line beside the details cover card.
RED = (254, 44, 85)         # TikTok accent: selection badge, enabled Next, caret.


def caption_supported(caption):
    """One visible description line; nothing is ever truncated or wrapped."""
    return (isinstance(caption, str) and 0 < len(caption) <= CAPTION_LIMIT and caption == caption.strip()
            and all(32 <= ord(c) <= 126 for c in caption) and '  ' not in caption)


def clock_label(seconds):
    whole = int(round(seconds))
    return f'{whole//60:02d}:{whole%60:02d}'


class TikTokReference:
    """Frames decoded once from the immutable package video, before any lease."""
    def __init__(self, raw):
        if not isinstance(raw, bytes) or not raw: raise ValueError('A package video is required.')
        with tempfile.TemporaryDirectory(prefix='farm-tiktok-reference-') as directory:
            path = Path(directory) / 'video.mp4'; path.write_bytes(raw)
            info = probe_video(path)
            data = run_media('ffmpeg', ['-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-i', str(path),
                                        '-vf', f'fps={SAMPLE_FPS},scale=360:640:flags=lanczos', '-f', 'rawvideo',
                                        '-pix_fmt', 'rgb24', '-'], timeout=60)
        size = 360*640*3
        if not data or len(data) % size: raise ValueError('Package video frames could not be decoded completely.')
        frames = np.frombuffer(data, dtype=np.uint8).reshape(-1, 640, 360, 3)
        if not 2 <= len(frames) <= 240: raise ValueError('Package video must provide 2 to 240 sampled frames.')
        self.sha256, self.seconds, self.count = hashlib.sha256(raw).hexdigest(), info['seconds'], len(frames)
        self.duration, self.clock = duration_label(info['seconds']), clock_label(info['seconds'])
        self.models = {}
        for name, (height, shape) in MODELS.items():
            top = (640-height)//2
            self.models[name] = (shape, [np.asarray(Image.fromarray(f[top:top+height]).resize(shape, Image.Resampling.LANCZOS),
                                                    dtype=float)/255 for f in frames])
        # The shared Safari/Files recognizers read these two directly.
        self.fill, self.square = self.models['fill'][1], self.models['square'][1]


def media_match(frame, box, reference, model, *, ignore=(), image=None):
    """Best sampled frame inside a fixed box under one fixed crop model."""
    image = pixels(frame, exact=True) if image is None else image
    size, targets = reference.models[model]
    left, top, right, bottom = box
    observed = np.asarray(Image.fromarray(image[top:bottom, left:right]).resize(size, Image.Resampling.LANCZOS), dtype=float)/255
    mask = np.ones(observed.shape[:2], dtype=bool)
    mask[:2] = mask[-2:] = False; mask[:, :2] = mask[:, -2:] = False
    sx, sy = size[0]/(right-left), size[1]/(bottom-top)
    for a, b, c, d in tuple(ignore) + (POINTER,):
        x0, y0 = max(0, int((a-left)*sx)), max(0, int((b-top)*sy))
        x1, y1 = min(size[0], int(np.ceil((c-left)*sx))), min(size[1], int(np.ceil((d-top)*sy)))
        if x0 < x1 and y0 < y1: mask[y0:y1, x0:x1] = False
    if mask.mean() < .5 or np.mean(np.std(observed[mask], axis=0)) < .03:
        return dict(status='insufficient_detail', matched=False, index=None, mean=None, model=model)
    best = None
    for index, target in enumerate(targets):
        difference = np.abs(observed-target).mean(axis=2)
        blocks = [float(difference[ys][:, xs][mask[ys][:, xs]].mean())
                  for ys in np.array_split(np.arange(size[1]), 4) for xs in np.array_split(np.arange(size[0]), 4)
                  if mask[ys][:, xs].any()]
        score = (float(difference[mask].mean()), max(blocks), index)
        if best is None or score[0] < best[0]: best = score
    mean, worst, index = best
    matched = mean <= MATCH_MEAN and worst <= MATCH_BLOCK
    return dict(status='visual_match' if matched else 'different', matched=matched, index=index, mean=mean,
                worstBlock=worst, model=model, byteIdentityVerified=False)


def control(frame, name, *, offset=(0, 0)):
    """Fixed control template; same thresholds as the Reel and carousel controls."""
    row = json.loads(Path(__file__).with_name('farm_tiktok_controls.json').read_text(encoding='utf-8'))[name]
    raw = base64.b64decode(row['png'], validate=True)
    require(hashlib.sha256(raw).hexdigest() == row['sha256'], 'TikTok control reference is damaged.')
    left, top, right, bottom = row['box']; dx, dy = offset
    require(0 <= left+dx and right+dx <= 500 and 0 <= top+dy and bottom+dy <= 1080, 'TikTok control is outside the frame.')
    image = pixels(frame, exact=True)
    with Image.open(io.BytesIO(raw)) as reference:
        delta = np.abs(image[top+dy:bottom+dy, left+dx:right+dx].astype(float)-np.asarray(reference.convert('RGB')).astype(float))/255
    require(delta.mean() < .02 and (delta.max(axis=2) > 35/255).mean() < .04, 'TikTok control changed: '+name)
    return left+dx, top+dy, right+dx, bottom+dy


def present(frame, name, offset=(0, 0)):
    try: control(frame, name, offset=offset); return True
    except InspectionStopped: return False


def red_fraction(image, box):
    left, top, right, bottom = box
    part = image[top:bottom, left:right].astype(int)
    return float(((part[..., 0] > 220) & (part[..., 1] < 90) & (part[..., 2] < 130)).mean())


class CaretVisible(InspectionStopped):
    """The blinking caret covers description text; a later frame may show it. No input follows."""


def caret_visible(image, box=(15, 120, 340, 330)):
    """TikTok's pink caret: a thin vertical run of accent pixels in the description area."""
    left, top, right, bottom = box
    part = image[top:bottom, left:right].astype(int)
    pink = (part[..., 0] > 200) & (part[..., 1] < 140) & (part[..., 2] < 175) & (part[..., 0]-part[..., 1] > 90)
    return bool((pink.sum(axis=0) >= 12).any())


# ---- TikTok feed, profile and camera ----------------------------------------------

NAV = (('home', (25, 1012, 80, 1040)), ('friends', (118, 1012, 182, 1040)), ('inbox', (322, 1012, 378, 1040)),
       ('profile', (420, 1012, 480, 1040)))


def tiktok_feed(frame, text):
    """For You feed (TikTok's landing screen after Drafts). Content and captions are arbitrary; never a target."""
    for name, box in NAV: require(words_at(text, name, box), 'The TikTok navigation bar is not recognized.')
    require(words_at(text, 'following', (150, 60, 300, 110)), 'The TikTok feed header is not recognized.')
    # Feed captions and comments sit in this band; a dialog elsewhere still stops.
    no_overlay({**text, 'lines': [r for r in text.get('lines', []) if not r.get('words')
                                  or not 780 <= min(w['y'] for w in r['words']) < 1000]})
    return dict(toastSeen=bool(line_at(text, 'draft saved', (190, 135, 310, 170))), profileTarget=(450, 1005))


def tiktok_profile(frame, text, account):
    """The exact signed-in TikTok profile; the Drafts tile count is supplementary evidence."""
    no_overlay(text)
    require(words_at(text, '@' + account.casefold(), (10, 165, 300, 200)), 'The TikTok profile does not show the exact account.')
    require(words_at(text, 'following', (10, 228, 100, 258)) and words_at(text, 'likes', (195, 228, 270, 258))
            and (words_at(text, 'follower', (105, 228, 195, 258)) or words_at(text, 'followers', (105, 228, 205, 258))),
            'The TikTok profile counters are not recognized.')
    require(words_at(text, 'profile', NAV[3][1]), 'The TikTok navigation bar is not recognized.')
    control(frame, 'tt_nav_create')
    rows = [r['text'] for r in text.get('lines', []) if r.get('words') and min(w['x'] for w in r['words']) < 40
            and 365 <= min(w['y'] for w in r['words']) <= 400]
    found = [re.fullmatch(r'drafts:\s*(\d+)', ' '.join(r.casefold().split())) for r in rows]
    count = int(found[0].group(1)) if len(found) == 1 and found[0] else None
    # TikTok sometimes lands here after Drafts with the same toast as on the feed (17 Oct photo route).
    return dict(account=account, draftsCount=count, draftsTarget=(79, 478) if count is not None else None,
                createTarget=(250, 1009), toastSeen=bool(line_at(text, 'draft saved', (190, 135, 310, 170))))


def tiktok_camera(frame, text):
    """Camera opened by +. Only the bottom-left gallery button is ever a target; LIVE is never near it."""
    for name, box in (('camera', (195, 985, 305, 1015)), ('live', (405, 985, 475, 1015)), ('sound', (240, 95, 330, 130))):
        require(words_at(text, name, box), 'The TikTok camera is not recognized.')
    no_overlay(text)
    return dict(galleryTarget=(40, 1000))


# ---- Upload picker -------------------------------------------------------------------

GRID_TOP = 169                          # Below the All/Videos/Photos tabs.
COLUMNS = ((0, 166), (167, 332), (334, 500))
PITCH = 167


def gutters(image, top, bottom):
    bright = (image[top:bottom].min(axis=2) > 225).mean(axis=1) > .9
    runs, start = [], None
    for y, value in enumerate(bright):
        if value and start is None: start = y
        if not value and start is not None: runs.append((top+start, top+y)); start = None
    if start is not None: runs.append((top+start, bottom))
    return runs


def grid(image):
    """Tile rows between white gutters, down to the bottom bar or selection tray."""
    runs = gutters(image, GRID_TOP, 1000)
    thick = [a for a, b in runs if b-a >= 10]
    require(thick, 'TikTok picker grid geometry changed.')
    bottom = thick[0]
    lines = [(a, b) for a, b in runs if a < bottom]
    require(lines and all(b-a <= 3 for a, b in lines)
            and all(abs(b[0]-a[0]-PITCH) <= 1 for a, b in zip(lines, lines[1:])), 'TikTok picker grid geometry changed.')
    starts = [lines[0][0]-(PITCH-2)] + [b for a, b in lines]
    ends = [a for a, b in lines] + [bottom]
    rows = [dict(top=t, bottom=b, complete=t >= GRID_TOP and b-t >= 158) for t, b in zip(starts, ends)]
    for row in rows:
        if not row['complete']: continue
        for x in (166, 332):
            require((image[row['top']+5:row['bottom']-5, x].min(axis=1) > 225).mean() > .9, 'TikTok picker grid geometry changed.')
    return rows, bottom


def circle(tile):
    left, top, right, bottom = tile
    return right-22, top+21


def badge(image, tile):
    x, y = circle(tile)
    return red_fraction(image, (x-9, y-9, x+10, y+10)) > .5


def _tiles(image, rows):
    """(tile, complete) for every row whose selection circle is visible."""
    for row in rows:
        for left, right in COLUMNS:
            tile = (left, row['top'], right, row['bottom'])
            if circle(tile)[1]-12 >= GRID_TOP and circle(tile)[1]+12 <= row['bottom']:
                yield tile, row['complete']


def _picker_header(frame, text):
    require(words_at(text, 'recents', (190, 75, 320, 105)), 'The TikTok upload picker is not recognized.')
    for name, box in (('all', (35, 130, 85, 165)), ('videos', (95, 130, 180, 165)), ('photos', (180, 130, 265, 165))):
        require(words_at(text, name, box), 'The TikTok picker tabs are not recognized.')
    control(frame, 'tt_picker_close')
    no_overlay(text)


def _tile_match(frame, tile, reference, image):
    left, top, right, bottom = tile
    return media_match(frame, (left+2, top+2, right-2, bottom-2), reference, 'square', image=image,
                       ignore=((right-46, top, right, top+46), (right-60, bottom-26, right, bottom)))


def tiktok_picker(frame, text, reference):
    """Unselected upload picker: locate the one complete tile that shows the package video."""
    _picker_header(frame, text)
    require(line_at(text, 'select multiple', (40, 990, 200, 1025)), 'TikTok multiple selection is not shown.')
    image = pixels(frame, exact=True)
    require(red_fraction(image, (17, 996, 28, 1016)) > .5, 'TikTok multiple selection is not enabled.')
    control(frame, 'tt_next_disabled')
    rows, _ = grid(image)
    tiles = []
    for tile, complete in _tiles(image, rows):
        require(not badge(image, tile), 'A TikTok picker item already shows a selection; review the picker.')
        if complete: tiles.append((tile, _tile_match(frame, tile, reference, image)))
    matched = [(t, v) for t, v in tiles if v['matched']]
    require(len(matched) == 1, 'The package video is absent or ambiguous in the TikTok picker; nothing is selected.')
    tile, best = matched[0]
    others = sorted(v['mean'] for t, v in tiles if t != tile and v['mean'] is not None)
    require(not others or others[0]-best['mean'] >= UNIQUE_MARGIN, 'Another picker item looks too similar to the package video.')
    left, top, right, bottom = tile
    label = [w for line in text.get('lines', []) for w in line.get('words', [])
             if re.fullmatch(r'\d\d:\d\d', str(w.get('text', ''))) and right-60 <= w['x'] and w['x']+w['width'] <= right
             and bottom-28 <= w['y'] and w['y']+w['height'] <= bottom]
    if label: require(len(label) == 1 and label[0]['text'] == reference.clock, 'The picker duration differs from the package video.')
    return dict(tile=list(tile), target=circle(tile), match=best, nearestOther=others[0] if others else None,
                durationRead=label[0]['text'] if label else None)


def tiktok_selected(frame, text, reference):
    """Exactly one tile numbered 1 shows the package video, its thumbnail is in the tray and Next is enabled."""
    _picker_header(frame, text)
    require(line_at(text, 'use layout', (40, 832, 150, 868)) and words_at(text, 'autocut', (95, 990, 195, 1025)),
            'The TikTok selection tray is not recognized.')
    control(frame, 'tt_picker_next')
    image = pixels(frame, exact=True)
    rows, _ = grid(image)
    selected = [(tile, complete) for tile, complete in _tiles(image, rows) if badge(image, tile)]
    require(len(selected) == 1 and selected[0][1], 'Exactly one complete TikTok picker item must be selected.')
    tile = selected[0][0]
    x, y = circle(tile)
    control(frame, 'tt_badge_one', offset=(x-478, y-678))   # Template taken at circle (478, 678).
    # A selected tile is drawn zoomed and dimmed, so its match is recorded only.
    # The tray shows exactly what is selected: one thumbnail, the package video.
    tray = media_match(frame, (18, 882, 90, 956), reference, 'square', image=image, ignore=((66, 880, 92, 904), (40, 936, 92, 958)))
    require(tray['matched'], 'The selection tray does not show the package video.')
    require((image[884:954, 100:240].min(axis=2) > 235).mean() > .97, 'The selection tray holds more than one item.')
    return dict(tile=list(tile), tileMatch=_tile_match(frame, tile, reference, image), tray=tray, target=(367, 1006))


# ---- Editor and details --------------------------------------------------------------

EDITOR_IGNORE = ((0, 65, 500, 95), (0, 90, 70, 140), (150, 90, 360, 140), (425, 90, 500, 660), (185, 880, 315, 925))


def tiktok_editor(frame, text, reference):
    """Editor with the package video. Your Story publishes and is never a target; reports the sound control."""
    require(line_at(text, 'your story', (90, 990, 210, 1025)), 'The TikTok editor is not recognized.')
    control(frame, 'tt_editor_next'); control(frame, 'tt_editor_back')
    no_overlay(text)
    media = media_match(frame, (0, 71, 500, 960), reference, 'fill', ignore=EDITOR_IGNORE)
    require(media['matched'], 'The TikTok editor shows different media.')
    pill = rows_between(text, 95, 135, 140, 360)
    if pill == ['Add sound'] and present(frame, 'tt_sound_note'):
        sound, label = 'none', None
    elif present(frame, 'tt_sound_remove') and pill and not any('sound' in row.casefold() for row in pill):
        sound, label = 'attached', pill[0]
    elif words_at(text, 'sound', (240, 95, 330, 130)) and not present(frame, 'tt_sound_note') and not present(frame, 'tt_sound_remove'):
        sound, label = 'loading', None
    else:
        raise InspectionStopped('The TikTok sound control is not recognized.')
    return dict(media=media, sound=sound, soundLabel=label, nextTarget=(367, 1006), removeTarget=(339, 115))


DETAILS_CANCEL = ({'cancel'}, (415, 65, 495, 105))


def tiktok_details(frame, text, reference, caption=None, *, reopened=False):
    """New or reopened details. caption=None requires the empty placeholder; Post is never a target."""
    no_overlay(text, (DETAILS_CANCEL,) if reopened else ())
    require(words_at(text, 'preview', (350, 125, 425, 155)) and line_at(text, 'edit cover', (370, 280, 460, 310)),
            'The TikTok cover card is not recognized.')
    require(words_at(text, 'hashtags', (40, 340, 140, 372)) and words_at(text, 'mention', (160, 340, 250, 372)),
            'The TikTok description tools are not recognized.')
    require(words_at(text, 'location', (40, 422, 140, 458)), 'TikTok details field missing: location')
    for label, box in (('everyone can view this post', (50, 598, 300, 628)), ('more options', (50, 660, 175, 690)),
                       ('share to', (50, 724, 135, 750))):
        exact(text, label, box)
    require(words_at(text, 'drafts', (105, 985, 190, 1022)), 'The TikTok Drafts button is not recognized.')
    control(frame, 'tt_details_drafts'); control(frame, 'tt_back')
    image = pixels(frame, exact=True)
    require(red_fraction(image, (262, 984, 478, 1028)) > .6, 'The TikTok Post button is not where it was observed.')
    header = (words_at(text, 'back', (35, 68, 95, 100)), words_at(text, 'cancel', (415, 68, 490, 100)))
    if reopened: require(all(header), 'The reopened TikTok draft header is not recognized.')
    else: require(not any(header), 'These are not new TikTok draft details.')
    if caret_visible(image): raise CaretVisible('The text caret covers the description; capture again without input.')
    lines = rows_between(text, 120, 330, 15, 340)
    if caption is None: require(lines == ['Add description...'], 'The new TikTok description is not empty.')
    else: require(lines == [caption], 'The visible TikTok description is missing, different or wrapped.')
    cover = media_match(frame, (345, 122, 475, 313), reference, 'card', image=image,
                        ignore=((345, 122, 425, 152), (345, 278, 475, 313)))
    require(cover['matched'], 'The TikTok cover shows different media.')
    return dict(captionExact=caption is not None, cover=cover, reopened=reopened,
                captionTarget=(155, 139), pressTarget=(80, 140), draftsTarget=(130, 1005))


def tiktok_paste_menu(frame, text):
    """The system Paste callout over the empty description; same rule as the Reel caption."""
    return reel_paste_menu(frame, text, press_y=140)


# ---- Drafts --------------------------------------------------------------------------

DRAFT_COLUMNS = ((0, 163), (169, 331), (337, 500))
DRAFT_ROWS = ((238, 453), (459, 674), (680, 895))
TOAST = ({'draft saved'}, (190, 135, 310, 170))


def tiktok_drafts(frame, text, reference):
    """Drafts list: the one tile whose cover shows the package video, and any sound label on it."""
    no_overlay(text, (TOAST,))
    require(words_at(text, 'select', (410, 68, 490, 100)), 'The TikTok drafts list is not recognized.')
    control(frame, 'tt_back')
    require(line_at(text, 'only you can see your drafts. uninstalling tiktok will', (50, 965, 450, 1000))
            and line_at(text, 'discard all drafts.', (175, 985, 325, 1015)), 'The TikTok drafts list is not recognized.')
    header = [r['text'] for r in text.get('lines', []) if r.get('words') and min(w['x'] for w in r['words']) < 40
              and 125 <= min(w['y'] for w in r['words']) <= 165]
    found = [re.match(r'(\d+) drafts?\b', ' '.join(h.casefold().split())) for h in header]
    count = int(found[0].group(1)) if len(found) == 1 and found[0] else None
    image = pixels(frame, exact=True)
    tiles = []
    for top, bottom in DRAFT_ROWS:
        for left, right in DRAFT_COLUMNS:
            if (image[top+10:bottom-10, left+10:right-10].min(axis=2) > 235).mean() > .97: continue   # empty slot
            for a, b in ((left-6, left), (right, right+6)):
                if 0 <= a and b <= 500:
                    require((image[top+5:bottom-5, a:b].min(axis=2) > 235).mean() > .97, 'TikTok drafts grid geometry changed.')
            require((image[bottom:bottom+6, left+5:right-5].min(axis=2) > 235).mean() > .97, 'TikTok drafts grid geometry changed.')
            match = media_match(frame, (left+2, top+2, right-2, bottom-2), reference, 'portrait', image=image,
                                ignore=((left, top, left+62, top+62), (left, bottom-55, right, bottom)))
            label = rows_between(text, bottom-50, bottom, left, right)
            tiles.append(dict(tile=[left, top, right, bottom], match=match, soundLabel=label[0] if label else None))
    require(tiles, 'No TikTok drafts are recognized.')
    matched = [t for t in tiles if t['match']['matched']]
    require(len(matched) == 1, 'The package video is absent or ambiguous in TikTok drafts.')
    tile = matched[0]
    others = sorted(t['match']['mean'] for t in tiles if t is not tile and t['match']['mean'] is not None)
    require(not others or others[0]-tile['match']['mean'] >= UNIQUE_MARGIN, 'Another TikTok draft looks too similar.')
    left, top, right, bottom = tile['tile']
    return dict(count=count, tile=tile, tiles=len(tiles), toastSeen=bool(line_at(text, 'draft saved', TOAST[1])),
                target=((left+right)//2, (top+bottom)//2))


# ---- Safari transfer page (TikTok package) -------------------------------------------------

def transfer_page(text, download, title='TikTok draft'):
    """The package page, top to bottom: title, file name, Download video, Copy caption."""
    order = []
    for label in (title, 'File ' + download, 'Download video', 'Copy caption'):
        order.append(exact(text, label, (10, 80, 490, 940))[1])
    require(order == sorted(order), 'The transfer page layout changed.')
    found = exact(text, 'Download video', (10, 80, 490, 940)); copy = exact(text, 'Copy caption', (10, 80, 490, 940))
    return dict(downloadTarget=(round((found[0]+found[2])/2), round((found[1]+found[3])/2)),
                copyTarget=(round((copy[0]+copy[2])/2), round((copy[1]+copy[3])/2)))


def caption_copied(text, app='TikTok'):
    require(f'Caption copied. Verify the pasted text in {app}.' in rows_between(text, 80, 1000),
            'The transfer page did not confirm copying. No paste is permitted.')
    return dict(copied=True)


def leftover_preview(frame, text):
    """A Files preview of an earlier package download, left open in Safari. Done only closes it."""
    names = [w['text'] for line in text.get('lines', []) for w in line.get('words', [])
             if re.fullmatch(r'imouse-((reel|tt|x)-[acdefhkmnprtuvwxy]{6}|draft)', str(w.get('text', '')))
             and 150 <= w['x'] and w['x']+w['width'] <= 360 and 65 <= w['y'] and w['y']+w['height'] <= 110]
    require(len(names) == 1 and words_at(text, 'done', (410, 65, 490, 105)) and reel_present(frame, 'quicklook_share'),
            'Safari opened on an unrecognized screen; no input is sent.')
    return dict(leftoverPreview=True, name=names[0], doneTarget=(450, 85))
