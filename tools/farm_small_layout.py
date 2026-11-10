"""4.7-inch phone layouts (iPhone 6s/7/8/SE 2nd gen) for the Marketing Farm. Recognition only, no input.

Calibrated on rack B slot 5 (board CD51, iPhone 6s) from live frames, 4 Nov 2026. These phones run
an iOS whose Home screen has page dots and no Search pill: Spotlight opens with a downward swipe and
its search field sits at the top with Cancel, unlike the XR rack's bottom field (farm_creation_layout).

Coordinates are mirror-frame pixels (500x1080). The phone's screen is letterboxed in it from y 95 to
985 (375x667 points at 1.333 px per point).
"""
from __future__ import annotations

import re

from farm_owned_capture import InspectionStopped

SCREEN = (0, 95, 500, 985)
STATUS_BAR = (0, 95, 500, 120)
# Home screen grid: icon centres. Labels sit 50 px below an icon's centre (OCR line top).
COLUMNS = (76, 192, 308, 424)
ROWS = (175, 292, 410, 527, 644, 761)
LABEL_DROP = 50
DOCK_Y = 923
PAGE_DOTS = (220, 835, 280, 852)
# Gestures. A slower page swipe counts as a long press on these phones (icons wiggle, 30 Oct);
# 100 ms turns the page cleanly (4 Nov). Spotlight: a short downward swipe in the grid area.
PAGE_LEFT = dict(x1=430, y1=560, x2=70, y2=560, duration=100)
SPOTLIGHT_SWIPE = dict(x1=250, y1=330, x2=250, y2=620, duration=100)
SPOTLIGHT_CANCEL = (454, 151)
SPOTLIGHT_FIELD = (10, 125, 405, 178)

PAGE_ONE = {'facetime', 'calendar', 'camera', 'mail', 'notes', 'clock', 'app store', 'maps', 'health',
            'utilities', 'phone', 'safari', 'messages'}
# Page 2 on B5: the social apps. OCR reads 'X' as 'x' and can drop a leading letter ('Tube').
PAGE_TWO = {'instagram', 'tiktok', 'x', 'youtube', 'threads', 'bluesky', 'clapper', 'likee'}


def small_screen(frame):
    """A 4.7-inch phone's frame: the screen letterboxed in 500x1080 with pure-black bands above y 95 and
    below y 985 (B5, 4 Nov). No XR frame matched (176 archived A-rack frames, 5 Nov): their status bar
    and wallpaper reach the frame's top."""
    import io
    import numpy as np
    from PIL import Image
    if not isinstance(frame, bytes): return False
    try:
        with Image.open(io.BytesIO(frame)) as image:
            if image.size != (500, 1080): return False
            a = np.asarray(image.convert('RGB'))
    except Exception:
        return False
    return int(a[:SCREEN[1]].max()) == 0 and int(a[SCREEN[3] + 1:].max()) == 0 and int(a[SCREEN[1]:SCREEN[1] + 25].max()) > 0


def require(condition, message):
    if not condition: raise InspectionStopped(message)


def rows(text):
    out = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        left = min(w['x'] for w in words); top = min(w['y'] for w in words)
        right = max(w['x'] + w['width'] for w in words); bottom = max(w['y'] + w['height'] for w in words)
        out.append(dict(text=' '.join(line.get('text', '').split()), fold=' '.join(line.get('text', '').casefold().split()),
                        box=(left, top, right, bottom)))
    return out


def _inside(box, area):
    return area[0] <= box[0] and area[1] <= box[1] and box[2] <= area[2] and box[3] <= area[3]


def _nearest(value, options, tolerance):
    best = min(options, key=lambda o: abs(o - value))
    return best if abs(best - value) <= tolerance else None


def grid_labels(text):
    """Home-screen labels that sit on the icon grid: {folded label: (column x, icon y)}."""
    found = {}
    for r in rows(text):
        left, top, right, bottom = r['box']
        x = _nearest((left + right) / 2, COLUMNS, 30)
        y = _nearest(top - LABEL_DROP, ROWS, 18)
        if x is None or y is None or bottom - top > 24: continue
        found[r['fold']] = (x, y)
    return found


def _label_matches(fold, name):
    name = name.casefold()
    if fold == name: return True
    # A dropped leading letter (YouTube -> 'Tube', Safari -> 'afari'), never shorter than 4 letters.
    return len(name) > 4 and len(fold) >= 4 and name.endswith(fold)


LABEL_BAND = (40, 75)     # A label row's band below its icon centre, read alone and enlarged.


def enlarged_labels(frame, reader=None):
    """Grid labels read row by row, enlarged with stronger contrast: whole-frame OCR misses white labels
    over the light wallpaper (B5, 4 Nov: 3 of 8 page-2 labels). Returns OCR-shaped text."""
    if reader is None:
        from farm_reel_layout import band_words as reader
    lines = []
    for y in ROWS[:4]:
        cells = {}
        for word, left, top, right, bottom in reader(frame, (0, y + LABEL_BAND[0], 500, y + LABEL_BAND[1]), 3):
            x = _nearest((left + right) / 2, COLUMNS, 58)
            if x is not None: cells.setdefault(x, []).append((left, word, top, right, bottom))
        for x, words in cells.items():
            words.sort()
            lines.append(dict(text=' '.join(w[1] for w in words), words=[
                dict(text=w[1], x=round(w[0]), y=round(w[2]), width=round(w[3] - w[0]), height=round(w[4] - w[2])) for w in words]))
    return dict(lines=lines)


def home_page(text, frame=None, reader=None):
    """1 or 2 for the recognized Home screen page, else InspectionStopped. With the frame, the
    enlarged per-row label read is added to the full-frame text."""
    labels = grid_labels(text)
    if frame is not None: labels.update(grid_labels(enlarged_labels(frame, reader)))
    folds = set(labels)
    one = sum(any(_label_matches(f, n) for f in folds) for n in PAGE_ONE)
    two = sum(any(_label_matches(f, n) for f in folds) for n in PAGE_TWO)
    require(not any(_inside(r['box'], SPOTLIGHT_FIELD) and r['fold'].endswith('search') for r in rows(text)),
            'Spotlight is open, not the Home screen.')
    if one >= 6 and two == 0: return 1
    if two >= 5 and one == 0: return 2
    raise InspectionStopped('The 4.7-inch Home screen is not recognized.')


def app_icon(text, name, frame=None, reader=None):
    """Centre of `name`'s icon on the recognized Home page; exactly one matching grid label."""
    home_page(text, frame, reader)
    labels = grid_labels(text)
    if frame is not None: labels.update(grid_labels(enlarged_labels(frame, reader)))
    hits = {point for fold, point in labels.items() if _label_matches(fold, name)}
    require(len(hits) == 1, f'Home screen label for {name} is missing or ambiguous.')
    return hits.pop()


SPOTLIGHT_NOTICE = ('you can search the web', 'suggestions as you type')


def spotlight(text):
    """The open Spotlight: 'Search' field at the top, Cancel at its right. Stops on the first-use
    Siri & Search notice (Continue only): it is not in the prompt policy, so the operator answers it."""
    found = rows(text)
    require(any(r['fold'].endswith('search') and _inside(r['box'], SPOTLIGHT_FIELD) for r in found),
            'The 4.7-inch Spotlight field is not recognized.')
    require(any(r['fold'] == 'cancel' and _inside(r['box'], (405, 125, 500, 178)) for r in found),
            'Spotlight Cancel is not recognized.')
    joined = ' '.join(r['fold'] for r in found)
    if all(part in joined for part in SPOTLIGHT_NOTICE) and any(r['fold'] == 'continue' for r in found):
        return dict(state='first_use_notice', answer=None,
                    stop='Spotlight shows its first-use Siri & Search notice (Continue only); '
                         'it is not in the prompt policy. The operator answers it once on this phone.')
    return dict(state='ready')


def control_center(text):
    """Control Center (4 Nov frame on B5): its Focus tile with Now Playing or the battery percentage.
    Never send Home over it: on 4 Nov a Home there opened Settings."""
    folds = {r['fold'] for r in rows(text)}
    return 'focus' in folds and ('not playing' in folds or any(f.endswith('%') for f in folds))


def empty_spotlight(text):
    """The open 4.7-inch Spotlight with an empty field: its placeholder 'Search' alone in the field."""
    state = spotlight(text)
    require(state['state'] == 'ready', state.get('stop', 'Spotlight is not ready.'))
    inside = [r for r in rows(text) if _inside(r['box'], SPOTLIGHT_FIELD)]
    require(len(inside) == 1 and re.fullmatch(r'(q\s*)?[a-z]?earch', inside[0]['fold']) is not None,
            'The 4.7-inch Spotlight field is not empty.')
    return True


def spotlight_clear(frame):
    raise InspectionStopped('The 4.7-inch Spotlight clear button is not calibrated yet.')


def app_target(text, name, frame):
    """A 4.7-inch phone's tap point for `name`: its Home screen icon."""
    return app_icon(text, name, frame)
