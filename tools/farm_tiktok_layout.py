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
                              no_overlay, rows_between, duration_label, reel_paste_menu, present as reel_present, band_words)
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


BADGE_CONTROLS = {'tt_badge_one'}
GLYPH_CONTROLS = {'tt_sound_remove', 'tt_sound_note'}


def control(frame, name, *, offset=(0, 0)):
    """Fixed control template; same thresholds as the Reel and carousel controls."""
    row = json.loads(Path(__file__).with_name('farm_tiktok_controls.json').read_text(encoding='utf-8'))[name]
    raw = base64.b64decode(row['png'], validate=True)
    require(hashlib.sha256(raw).hexdigest() == row['sha256'], 'TikTok control reference is damaged.')
    left, top, right, bottom = row['box']; dx, dy = offset
    require(0 <= left+dx and right+dx <= 500 and 0 <= top+dy and bottom+dy <= 1080, 'TikTok control is outside the frame.')
    image = pixels(frame, exact=True)
    with Image.open(io.BytesIO(raw)) as reference:
        expected = np.asarray(reference.convert('RGB')).astype(float)
    delta = np.abs(image[top+dy:bottom+dy, left+dx:right+dx].astype(float)-expected)/255
    if name in GLYPH_CONTROLS:
        # White glyphs on the sound pill, whose grey follows the video under it (slot 20, 22 Oct):
        # the glyph must be bright in place and stand out from the pill around it.
        glyph = expected.min(axis=2) > 200
        current = image[top+dy:bottom+dy, left+dx:right+dx].astype(float)
        bright = float((current.min(axis=2)[glyph] > 200).mean())
        contrast = float(current.mean(axis=2)[glyph].mean() - current.mean(axis=2)[~glyph].mean())
        require(bright > .85 and contrast > 40, 'TikTok control changed: '+name)
        return left+dx, top+dy, right+dx, bottom+dy
    if name in BADGE_CONTROLS:
        # Only the badge itself (red disk, white numeral): the tile picture around it differs per video
        # (slot 20, 22 Oct: corners .20 changed, the badge .002). The numeral is checked on its own too.
        numeral = expected.min(axis=2) > 230
        require((delta[numeral].max(axis=1) > 35/255).mean() < .1, 'TikTok control changed: '+name)
        # The disk's anti-aliased rim blends with the tile behind it (.07 changed on 22 Oct); two
        # pixels in from the rim the red is solid.
        disk = (expected[..., 0] > 180) & (expected[..., 1] < 90)
        for _ in range(2):
            disk = disk & np.roll(disk, 1, 0) & np.roll(disk, -1, 0) & np.roll(disk, 1, 1) & np.roll(disk, -1, 1)
        delta = delta[disk | numeral][:, None, :]
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
    # Slot 20 draws it a lighter pink ((254, 142, 171), 25 Oct) than C24C did.
    pink = (part[..., 0] > 200) & (part[..., 1] < 165) & (part[..., 2] < 200) & (part[..., 0]-part[..., 1] > 80)
    return bool((pink.sum(axis=0) >= 12).any())


# ---- TikTok feed, profile and camera ----------------------------------------------

NAV = (('home', (25, 1012, 80, 1040)), ('friends', (118, 1012, 182, 1040)), ('inbox', (322, 1012, 378, 1040)),
       ('profile', (420, 1012, 480, 1040)))


FEED_HEADER = (90, 62, 360, 108)
FEED_TABS = {'following', 'shop', 'community', 'explore', 'friends'}   # The feed's own header tabs.


def tiktok_feed(frame, text):
    """For You feed (TikTok's landing screen after Drafts). Content and captions are arbitrary; never a target."""
    for name, box in NAV: require(words_at(text, name, box), 'The TikTok navigation bar is not recognized.')
    if not words_at(text, 'following', (150, 60, 300, 110)):
        # A video's own title can cover the light header (slot 20, 22 Oct); the header row is read
        # again alone, enlarged, and 'Following' must sit in the same place.
        # Over a bright photo even the enlarged read can lose 'Following' while it still reads another of
        # the feed's own tabs ('Shop', slot 20, 25 Oct); any of them in the header row marks the feed.
        words = [re.sub(r'[^a-z ]', '', t.casefold()) for t, x0, _, x1, _ in band_words(frame, FEED_HEADER)]
        # A video's own caption box can cover the whole header (A20 after a cold start, 4 Nov: no tab read even
        # enlarged). The four nav labels (required above) and TikTok's Create button on the dark feed nav bar then
        # mark the feed.
        require(any(w in FEED_TABS for w in words) or feed_create_button(frame), 'The TikTok feed header is not recognized.')
    # Feed captions and comments sit in this band; a dialog elsewhere still stops.
    no_overlay({**text, 'lines': [r for r in text.get('lines', []) if not r.get('words')
                                  or not 780 <= min(w['y'] for w in r['words']) < 1000]})
    return dict(toastSeen=bool(line_at(text, 'draft saved', (190, 135, 310, 170))), profileTarget=(450, 1005))


def feed_create_button(frame):
    """TikTok's Create button on the feed's dark nav bar: a white tile with cyan and pink edges (A20, 4 Nov: nav
    dark .85, tile white .42, cyan .044, pink .035; the light profile nav is dark .07)."""
    try: image = pixels(frame, exact=True).astype(int)
    except (OSError, ValueError, InspectionStopped): return False   # An unreadable frame is never the feed.
    tile = image[990:1030, 215:285]
    white = (tile.min(axis=2) > 230).mean()
    cyan = ((tile[..., 0] < 120) & (tile[..., 1] > 180) & (tile[..., 2] > 180)).mean()
    pink = ((tile[..., 0] > 200) & (tile[..., 1] < 110) & (tile[..., 2] > 90)).mean()
    dark = (image[985:1045].max(axis=2) < 40).mean()
    return bool(dark > .7 and .3 < white < .55 and cyan > .02 and pink > .02)


def tiktok_profile(frame, text, account):
    """The exact signed-in TikTok profile; the Drafts tile count is supplementary evidence."""
    no_overlay(text)
    require(words_at(text, '@' + account.casefold(), (10, 165, 300, 200)), 'The TikTok profile does not show the exact account.')
    def counters(found):
        return (found('following', (10, 228, 100, 258)) and found('likes', (195, 228, 270, 258))
                and (found('follower', (105, 228, 195, 258)) or found('followers', (105, 228, 205, 258))))
    if not counters(lambda label, box: words_at(text, label, box)):
        # Full-frame OCR drops 'Likes' on slot 20 (4 Nov); the counter labels are read again alone, enlarged.
        band = [(t.casefold(), x0, y0, x1, y1) for t, x0, y0, x1, y1 in band_words(frame, (10, 205, 300, 262), 3)]
        def enlarged(label, box):
            return sum(1 for t, x0, y0, x1, y1 in band if t == label and box[0] <= x0 and x1 <= box[2]
                       and box[1] <= y0 and y1 <= box[3]) == 1
        require(counters(enlarged), 'The TikTok profile counters are not recognized.')
    require(words_at(text, 'profile', NAV[3][1]), 'The TikTok navigation bar is not recognized.')
    control(frame, 'tt_nav_create')
    rows = [r['text'] for r in text.get('lines', []) if r.get('words') and min(w['x'] for w in r['words']) < 40
            and 365 <= min(w['y'] for w in r['words']) <= 400]
    if not rows:
        # White 'Drafts: 1' over a white-topped test video is missed by full-frame OCR (slot 20, 24 Oct);
        # the label band alone is read again, enlarged.
        words = band_words(frame, (0, 360, 170, 400), 3)
        rows = [' '.join(w[0] for w in sorted(words, key=lambda w: w[1]))] if words else []
    # The enlarged read can lead with a stray mark ('-Drafts: 4', slot 20, 4 Nov).
    found = [re.fullmatch(r'[^a-z0-9]?drafts:\s*(\d+)', ' '.join(r.casefold().split())) for r in rows]
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
    # A last row of white-backed test videos beside an empty white cell has full-width bright
    # rows inside it (slot 20, 22 Oct: y 858, 911); only lines a row's pitch apart are gutters.
    # The white-backed test videos also draw 1 px white rows a pitch apart inside their thumbnails
    # (slot 20, 24 Oct: y 210, 378, 545 against real gutters at 321, 489, 655). Every chain of runs a
    # pitch apart is built and the one made of the thickest lines wins; real gutters are 2-5 px.
    candidates = [(a, b) for a, b in runs if a < bottom]
    chains = []
    for i, first in enumerate(candidates):
        chain = [first]
        for run in candidates[i+1:]:
            if abs(run[0] - chain[-1][0] - PITCH) <= 1: chain.append(run)
        chains.append(chain)
    lines = max(chains, key=lambda c: (sum(b-a for a, b in c), len(c)), default=[])
    # A gutter above white-topped thumbnails reads up to 5 px (slot 20, 22 Oct); real gutters are 2-3.
    require(lines and all(b-a <= 6 for a, b in lines)
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


NEAR_TILE_MEAN = .09


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
        if complete:
            match = _tile_match(frame, tile, reference, image)
            if not match['matched'] and match['mean'] is not None and match['mean'] <= NEAR_TILE_MEAN:
                # A narrow miss (.060 on 22 Oct, others .22 or more) is decided by the tiles' colours.
                left, top, right, bottom = tile
                match = dict(match, **tile_colours(image, (left+2, top+2, right-2, bottom-2), reference))
            tiles.append((tile, match))
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


def tray_colours(image, reference):
    """The tray thumbnail squeezes the six test-media tiles into a square (slot 20, 22 Oct: strict
    mean .091). Each uncovered tile's colour proportions must match this package's: .037 for it,
    .23 or more for every earlier test video. The remove x and the duration cover tiles 2 and 6."""
    return tile_colours(image, (18, 882, 90, 956), reference)


def tile_colours(image, box, reference, model='square'):
    """Square-crop thumbnail (tray or picker tile), or a 3:4 drafts cover with model='portrait': the
    uncovered test-media tiles' colour proportions."""
    left, top, right, bottom = box
    size, targets = reference.models[model]
    observed = np.asarray(Image.fromarray(image[top:bottom, left:right]).resize(size, Image.Resampling.LANCZOS), dtype=float)/255
    def grid3x2(rgb):
        h, w = rgb.shape[:2]; rows = []
        for r in range(3):
            for c in range(2):
                cy, cx = int(h*(r*2+1)/6), int(w*(c*2+1)/4)
                block = rgb[cy-h//12:cy+h//12, cx-w//8:cx+w//8].reshape(-1, 3).mean(axis=0)
                rows.append(block/max(float(block.sum()), 1e-6))
        return np.array(rows)
    worst = float(np.abs(grid3x2(observed) - grid3x2(targets[0])).max(axis=1)[[0, 2, 3, 4]].max())
    return dict(matched=worst <= .06, status='tile_colour_match' if worst <= .06 else 'different', worstTile=worst)


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
    require(badge_one(frame, x, y), 'TikTok control changed: tt_badge_one')
    # A selected tile is drawn zoomed and dimmed, so its match is recorded only.
    # The tray shows exactly what is selected: one thumbnail, the package video.
    tray = media_match(frame, (18, 882, 90, 956), reference, 'square', image=image, ignore=((66, 880, 92, 904), (40, 936, 92, 958)))
    if not tray['matched'] and tray['mean'] is not None and tray['mean'] <= .15:
        tray = dict(tray, **tray_colours(image, reference))
    require(tray['matched'], 'The selection tray does not show the package video.')
    require((image[884:954, 100:240].min(axis=2) > 235).mean() > .97, 'The selection tray holds more than one item.')
    return dict(tile=list(tile), tileMatch=_tile_match(frame, tile, reference, image), tray=tray, target=(367, 1006))


def badge_one(frame, x, y):
    """The numbered badge at a tile's circle. Template taken at circle (478, 678); the middle column's
    badge can sit a pixel right of the circle its tile edges give (slot 20, 23 Oct), so the template
    may move one pixel either way."""
    return any(present(frame, 'tt_badge_one', offset=(x-478+dx, y-678+dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1))


# ---- Editor and details --------------------------------------------------------------

EDITOR_IGNORE = ((0, 65, 500, 95), (0, 90, 70, 140), (150, 90, 360, 140), (425, 90, 500, 660), (185, 880, 315, 925))


def tiktok_editor(frame, text, reference):
    """Editor with the package video. Your Story publishes and is never a target; reports the sound control."""
    # The Story button reads 'Your Story' or, newer, 'Story 24h' (slot 20, 22 Oct); either way it is never a target.
    require(line_at(text, 'your story', (90, 990, 210, 1025)) or line_at(text, 'story 24h', (90, 990, 210, 1025)),
            'The TikTok editor is not recognized.')
    control(frame, 'tt_editor_next')
    # The white back arrow cannot be seen over a white video (slot 20, 22 Oct); it is checked only
    # where the video under it is dark enough to show it.
    if float(pixels(frame, exact=True)[98:132, 22:50].mean()) < 200: control(frame, 'tt_editor_back')
    no_overlay(text)
    media = media_match(frame, (0, 71, 500, 960), reference, 'fill', ignore=EDITOR_IGNORE)
    require(media['matched'], 'The TikTok editor shows different media.')
    pill = rows_between(text, 95, 135, 140, 360)
    if pill == ['Add sound'] and present(frame, 'tt_sound_note'):
        sound, label = 'none', None
    elif (remove := sound_remove(frame)) is not None and pill and not any('sound' in row.casefold() for row in pill):
        sound, label = 'attached', re.sub(r'\s+[x×]$', '', pill[0], flags=re.IGNORECASE)   # OCR joins the pill's x.
    elif words_at(text, 'sound', (240, 95, 330, 130)) and not present(frame, 'tt_sound_note') and not present(frame, 'tt_sound_remove'):
        sound, label = 'loading', None
    else:
        raise InspectionStopped('The TikTok sound control is not recognized.')
    return dict(media=media, sound=sound, soundLabel=label, nextTarget=(367, 1006),
                removeTarget=(339 + (remove if sound == 'attached' else 0), 115))


def sound_remove(frame):
    """Horizontal offset of the sound pill's x from its template spot, or None. The centred pill is as
    wide as the sound's name, so a short name ('Bounce', slot 20, 23 Oct) moves the x left by 31 px.
    The x must be found at exactly one place (a run of neighbouring offsets) along the pill row."""
    hits = [dx for dx in range(-150, 61) if present(frame, 'tt_sound_remove', offset=(dx, 0))]
    if not hits or hits[-1] - hits[0] > 2: return None
    return hits[len(hits)//2]


DETAILS_CANCEL = ({'cancel'}, (415, 65, 495, 105))


def tiktok_details(frame, text, reference, caption=None, *, reopened=False):
    """New or reopened details. caption=None requires the empty placeholder; Post is never a target."""
    no_overlay(text, (DETAILS_CANCEL,) if reopened else ())
    # A white video washes out 'Preview' and slot 20's parked pointer lands on 'Edit cover' ('dit1Cover',
    # 23 Oct); either label read, or the pointer-clipped one, marks the card. Its media is matched below.
    # ('ditlCov' when the video's progress bar shows through the pill, 23 Oct; 'dit1CovÅr' and
    # '•EditlCovcr', 25 Oct: slot 20's parked pointer rests on this label.)
    edit = [r for r in rows_between(text, 280, 310, 370, 460) if re.search(r'dit.{0,2}c[o0]v', r.casefold())]
    require(words_at(text, 'preview', (350, 125, 425, 155)) or line_at(text, 'edit cover', (370, 280, 460, 310)) or edit,
            'The TikTok cover card is not recognized.')
    require(words_at(text, 'hashtags', (40, 340, 140, 372)) and words_at(text, 'mention', (160, 340, 250, 372)),
            'The TikTok description tools are not recognized.')
    require(words_at(text, 'location', (40, 422, 140, 458)), 'TikTok details field missing: location')
    detail_rows(text)
    require(words_at(text, 'drafts', (105, 985, 190, 1022)), 'The TikTok Drafts button is not recognized.')
    control(frame, 'tt_details_drafts'); control(frame, 'tt_back')
    image = pixels(frame, exact=True)
    require(red_fraction(image, (262, 984, 478, 1028)) > .6, 'The TikTok Post button is not where it was observed.')
    header = (words_at(text, 'back', (35, 68, 95, 100)), words_at(text, 'cancel', (415, 68, 490, 100)))
    if reopened: require(all(header), 'The reopened TikTok draft header is not recognized.')
    else: require(not any(header), 'These are not new TikTok draft details.')
    # Only a pasted description can be clipped by the caret. Before the paste, slot 20's caret rests at the
    # empty field's start without blinking off (25 Oct); the placeholder rule below already allows it.
    if caption is not None and caret_visible(image): raise CaretVisible('The text caret covers the description; capture again without input.')
    lines = rows_between(text, 120, 330, 15, 340)
    if caption is None:
        # The pink caret can sit on the placeholder's 'A' ('hcld description...', 'VAdd description...',
        # slot 20, 25 Oct); only the placeholder's own words count, never a pasted caption.
        require(len(lines) == 1 and (lines[0] == 'Add description...' or re.fullmatch(r'.{0,4}d description\.{2,3}', lines[0])),
                'The new TikTok description is not empty.')
    else: require(lines == [caption], 'The visible TikTok description is missing, different or wrapped.')
    cover = media_match(frame, (345, 122, 475, 313), reference, 'card', image=image,
                        ignore=((345, 122, 425, 152), (345, 278, 475, 313)))
    if not cover['matched']:   # Slot 20 draws the card larger: (345, 120)-(480, 318) (23 Oct).
        cover = dict(media_match(frame, (345, 120, 480, 318), reference, 'card', image=image,
                                 ignore=((345, 120, 430, 152), (345, 278, 480, 318))), card='large')
    require(cover['matched'], 'The TikTok cover shows different media.')
    return dict(captionExact=caption is not None, cover=cover, reopened=reopened,
                captionTarget=(155, 139), pressTarget=(80, 140), draftsTarget=(130, 1005))


DETAIL_ROWS = (('everyone can view this post', (50, 598, 300, 628)), ('more options', (50, 660, 175, 690)),
               ('share to', (50, 724, 135, 750)))
DETAIL_SHIFTS = (0, -54)   # Slot 20 draws these rows 54 px higher under its location chips (23 Oct).


def detail_rows(text):
    """The three rows under Location, all at one of the observed heights. OCR may join a row's icon
    to its label as a leading 'O' ('O More options', from x 20)."""
    lines = [(re.sub(r'^[o0]\s+', '', ' '.join(l['text'].casefold().split())), min(w['x'] for w in l['words']),
              min(w['y'] for w in l['words'])) for l in text.get('lines', []) if l.get('words')]
    for shift in DETAIL_SHIFTS:
        if all(any(t == label and 15 <= x <= box[2] and box[1]+shift-6 <= y <= box[3]+shift for t, x, y in lines)
               for label, box in DETAIL_ROWS):
            return shift
    raise InspectionStopped('TikTok details rows are not where they were observed.')


def tiktok_paste_menu(frame, text):
    """The system Paste callout over the empty description; same rule as the Reel caption."""
    return reel_paste_menu(frame, text, press_y=140)


# ---- Drafts --------------------------------------------------------------------------

DRAFT_COLUMNS = ((0, 163), (169, 331), (337, 500))
DRAFT_ROWS = ((238, 453), (459, 674), (680, 895))
DRAFT_SHIFTS = (0, -50)
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
    # A 'Sort by' chip row (C24C, 17 Oct, two or more drafts) puts the grid at y 238; without it the grid
    # starts 50 px higher (slot 20, one draft, 24 Oct), and the first tile's top edge must sit there.
    chips = any(r['text'].casefold().startswith('sort by') and 175 <= min(w['y'] for w in r['words']) <= 205
                for r in text.get('lines', []) if r.get('words'))
    shift = 0
    if not chips:
        content = np.where((image[170:470, 10:150].min(axis=2) < 240).mean(axis=1) > .5)[0]
        first = 170 + int(content[0]) if len(content) else None
        require(first is not None and abs(first - (DRAFT_ROWS[0][0] + DRAFT_SHIFTS[1])) <= 4, 'TikTok drafts grid geometry changed.')
        shift = DRAFT_SHIFTS[1]
    tiles = []
    for top, bottom in ((t + shift, b + shift) for t, b in DRAFT_ROWS):
        for left, right in DRAFT_COLUMNS:
            if (image[top+10:bottom-10, left+10:right-10].min(axis=2) > 235).mean() > .97: continue   # empty slot
            for a, b in ((left-6, left), (right, right+6)):
                if 0 <= a and b <= 500:
                    require((image[top+5:bottom-5, a:b].min(axis=2) > 235).mean() > .97, 'TikTok drafts grid geometry changed.')
            # (Slot 20's tiles end up to 2 px lower, 24 Oct.)
            require((image[bottom+2:bottom+5, left+5:right-5].min(axis=2) > 235).mean() > .97, 'TikTok drafts grid geometry changed.')
            # C24C's cover sits 2 px inside its tile; slot 20's fills it edge to edge, a pixel lower, whether
            # or not the 'Sort by' row is shown (24-25 Oct). Both crops are compared; the closer one counts.
            ignore = ((left, top, left+62, top+62), (left, bottom-55, right, bottom+2))
            match = min((media_match(frame, cover, reference, 'portrait', image=image, ignore=ignore)
                         for cover in ((left+2, top+2, right-2, bottom-2), (left+2, top, right-1, bottom+1))),
                        key=lambda m: (not m['matched'], m['mean'] if m['mean'] is not None else 9))
            if not match['matched'] and match['mean'] is not None and match['mean'] <= .1:
                # A narrow miss on slot 20's rounded, shaded cover (.068, 24 Oct) is decided by its colour blocks.
                match = dict(match, **tile_colours(image, (left+2, top+2, right-2, bottom-2), reference, 'portrait'))
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
    # The phone wraps the confirmation onto a second row (C24C, 20 Oct); the exact sentence may span rows.
    require(f'Caption copied. Verify the pasted text in {app}.' in ' '.join(rows_between(text, 80, 1000)),
            'The transfer page did not confirm copying. No paste is permitted.')
    return dict(copied=True)


def leftover_preview(frame, text):
    """A Files preview of an earlier package download, left open in Safari. Done only closes it."""
    from farm_reel_layout import LEFTOVER_NAME, header_names
    names = header_names(text, LEFTOVER_NAME)
    require(len(names) == 1 and words_at(text, 'done', (410, 65, 490, 105)) and reel_present(frame, 'quicklook_share'),
            'Safari opened on an unrecognized screen; no input is sent.')
    return dict(leftoverPreview=True, name=names[0], doneTarget=(450, 85))
