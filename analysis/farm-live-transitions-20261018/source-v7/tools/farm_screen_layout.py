"""Evidence for the observed 500x1080 Instagram layouts. Never sends input.

Motion inside a preview is not permission to ignore the surrounding controls.
These patterns do not establish app authenticity, account identity or persistence.
"""
import hashlib
import io
import math

import numpy as np
from PIL import Image


NEXT_BOX = (396, 980, 478, 1032)
# Keep the label separate from the adjacent arrow. The full button is still
# required for editor geometry; OCR must return the exact word from this crop.
NEXT_LABEL_BOX = (404, 987, 447, 1026)
NEXT_LABEL_SCALE = 3
NEXT_CROP_SIZE = (129, 117)


def next_crop(frame):
    """A fixed control crop; never crop or repair account/caption text."""
    image = Image.fromarray(pixels(frame, exact=True))
    crop = image.crop(NEXT_LABEL_BOX).resize(NEXT_CROP_SIZE, Image.Resampling.LANCZOS)
    stream = io.BytesIO(); crop.save(stream, 'PNG')
    return stream.getvalue(), hashlib.sha256(image.tobytes()).hexdigest()


def next_label(frame, text):
    if words_at(text, 'next', (400, 982, 468, 1027)):
        return dict(method='whole_frame_exact_word', label='Next')
    detail = text.get('controlOcr', {}).get('next')
    if not isinstance(detail, dict):
        return None
    crop, source_pixels = next_crop(frame)
    if (detail.get('sourceFrameSha256') != text.get('frameSha256')
            or detail.get('sourcePixelsSha256') != source_pixels
            or detail.get('bounds') != list(NEXT_LABEL_BOX) or detail.get('scale') != NEXT_LABEL_SCALE
            or (detail.get('width'), detail.get('height')) != NEXT_CROP_SIZE
            or detail.get('imageSha256') != hashlib.sha256(crop).hexdigest()
            or not words_at(detail, 'next', (0, 0, *NEXT_CROP_SIZE))):
        return None
    return dict(method='same_frame_crop_exact_word', label='Next', imageSha256=detail['imageSha256'])


def pixels(frame, *, exact=False):
    if not isinstance(frame, bytes) or not 0 < len(frame) <= 16 * 1024 * 1024:
        raise ValueError('Invalid layout frame.')
    with Image.open(io.BytesIO(frame)) as image:
        width, height = image.size
        if (not 100 <= width <= 4096 or not 100 <= height <= 4096
                or abs(width / height - 500 / 1080) > .01 or exact and image.size != (500, 1080)):
            raise ValueError('Unsupported layout dimensions.')
        return np.asarray(image.convert('RGB').resize((500, 1080), Image.Resampling.LANCZOS))


def words_at(text, label, box):
    """Unique exact OCR word, independently located even in a combined line."""
    left, top, right, bottom = box
    found = []
    for line in text.get('lines', []):
        for word in line.get('words', []):
            values = [word.get(k) for k in ('x', 'y', 'width', 'height')]
            if not all(type(v) in (int, float) and math.isfinite(v) for v in values):
                return []
            x, y, w, h = values
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x+w > text['width'] or y+h > text['height']:
                return []
            if str(word.get('text', '')).casefold() == label and left <= x and top <= y and x+w <= right and y+h <= bottom:
                found.append((x, y, x+w, y+h))
    return found if len(found) == 1 else []


def line_at(text, label, box):
    left, top, right, bottom = box
    found = []
    for line in text.get('lines', []):
        words = line.get('words', [])
        if line.get('text', '').casefold() != label or not words:
            continue
        bounds = (min(w['x'] for w in words), min(w['y'] for w in words),
                  max(w['x']+w['width'] for w in words), max(w['y']+w['height'] for w in words))
        if left <= bounds[0] and top <= bounds[1] and bounds[2] <= right and bounds[3] <= bottom:
            found.append(bounds)
    return found if len(found) == 1 else []


def overlay_present(text):
    # Interruptions win over the app underneath, including labels in the preview.
    lines = [' '.join(str(row.get('text', '')).casefold().replace('’', "'").split()) for row in text.get('lines', [])]
    exact = {'allow', "don't allow", 'cancel', 'discard', 'save draft', 'continue', 'not now', 'try again'}
    return any(row in exact or 'edits will be discarded' in row or 'would like to' in row for row in lines)


def create_menu_controls(frame, text):
    """Observed Create sheet, not the profile visible behind it or a publish button."""
    if (text.get('width'), text.get('height')) != (500, 1080) or overlay_present(text):
        return None
    boxes = {'create': (205, 505, 290, 540), 'edits': (60, 612, 130, 650),
             'post': (60, 665, 130, 700), 'story': (60, 720, 140, 755),
             'instants': (60, 770, 155, 810), 'highlights': (60, 825, 175, 865),
             'live': (60, 880, 140, 920), 'fundraiser': (60, 930, 180, 970)}
    if not all(words_at(text, label, box) for label, box in boxes.items()):
        return None
    try: image = pixels(frame, exact=True)
    except ValueError: return None
    # Empty sheet margin and the separated rows must be light; a text list alone
    # or a modal over the profile cannot establish this navigation target.
    for left, top, right, bottom in ((180, 550, 400, 970), (30, 1000, 470, 1040)):
        if (image[top:bottom, left:right].min(axis=2) > 225).mean() < .97:
            return None
    return dict(method='create_sheet_positioned_controls', postBounds=list(words_at(text, 'post', boxes['post'])[0]),
                automaticInputAllowed=False)


def carousel_position(frame):
    """Read page dots, not numbers printed on the content."""
    strip = pixels(frame)[835:844, 185:315].astype(float)
    brightness = strip.mean(axis=2)
    columns = (brightness > 40).sum(axis=0) >= 3
    runs, start = [], None
    for x, present in enumerate(list(columns) + [False]):
        if present and start is None: start = x
        if not present and start is not None:
            runs.append((start, x)); start = None
    if not 2 <= len(runs) <= 10 or any(not 4 <= b-a <= 10 for a, b in runs):
        return dict(status='unreadable', index=None, count=None)
    centres = [(a+b)/2 for a, b in runs]
    if abs((centres[0]+centres[-1])/2 - 65) > 3 or any(not 9 <= b-a <= 14 for a, b in zip(centres, centres[1:])):
        return dict(status='unreadable', index=None, count=None)
    levels = [float(np.percentile(brightness[:, a:b], 70)) for a, b in runs]
    active = [i for i, v in enumerate(levels) if v >= 180]
    if len(active) != 1 or any(v > 130 for i, v in enumerate(levels) if i not in active):
        return dict(status='ambiguous', index=None, count=None)
    return dict(status='visible_position', index=active[0]+1, count=len(runs))


def editor_controls(frame, text):
    """Corroborate a carousel editor without guessing missing Next/audio letters."""
    if (text.get('width'), text.get('height')) != (500, 1080) or overlay_present(text):
        return None
    boxes = {'audio': (25, 907, 90, 940), 'overlay': (172, 907, 242, 940),
             'filter': (257, 907, 323, 940), 'edit': (335, 907, 395, 940), 'ratio': (410, 907, 475, 940)}
    if not all(words_at(text, label, box) for label, box in boxes.items()):
        return None
    try:
        image = pixels(frame, exact=True)
        position = carousel_position(frame)
    except ValueError:
        return None
    # A blue rounded button with light glyphs in the observed Next location.
    # Its presence corroborates the layout, not the semantic meaning of a tap.
    button = image[980:1032, 396:478].astype(int)
    blue = (button[:, :, 2] > 180) & (button[:, :, 2]-button[:, :, 0] > 70) & (button[:, :, 1] < 160)
    light = button.min(axis=2) > 175
    surround = image[970:1042, 386:488]
    border = np.ones(surround.shape[:2], dtype=bool); border[10:62, 10:92] = False
    if not (.55 < blue.mean() < .95 and .005 < light.mean() < .20
            and (surround[border].max(axis=1) < 70).mean() > .9
            and position['status'] == 'visible_position'):
        return None
    label = next_label(frame, text)
    return dict(method='toolbar_button_and_page_dots', position=position, nextLabel=label,
                textRepaired=False, actionTargetVerified=label is not None, automaticInputAllowed=False)


def picker_controls(frame, text):
    """Fixed portrait post picker; no caller-selected ignored regions."""
    if (text.get('width'), text.get('height')) != (500, 1080) or overlay_present(text):
        return None
    if (not line_at(text, 'new post', (185, 66, 310, 107))
            or not words_at(text, 'next', (420, 66, 490, 107))
            or not words_at(text, 'recents', (12, 620, 115, 666))
            or not words_at(text, 'drafts', (125, 620, 215, 666))
            or not words_at(text, 'select', (410, 620, 485, 666))):
        return None
    try: image = pixels(frame, exact=True)
    except ValueError: return None
    # Solid header/separator backgrounds prevent accepting partially opened drawers.
    for box in ((70, 65, 180, 108), (0, 612, 500, 620), (0, 666, 500, 677)):
        left, top, right, bottom = box
        if (image[top:bottom, left:right].max(axis=2) < 70).mean() < .95:
            return None
    return dict(method='post_picker_controls', previewBounds=[0, 112, 500, 612],
                automaticInputAllowed=False)


def picker_stability(before, before_text, after, after_text):
    """Compare app chrome/grid; motion tolerance is confined to the preview.

    Pure visual evidence: freshness and ownership must be checked by the workflow.
    The result does not authorize a click or prove there is no unseen overlay.
    """
    result = dict(controlsStable=False, previewChanged=False, automaticInputAllowed=False,
                  beforeSha256=hashlib.sha256(before).hexdigest(), afterSha256=hashlib.sha256(after).hexdigest())
    if not picker_controls(before, before_text) or not picker_controls(after, after_text):
        return {**result, 'reason': 'Both frames must independently show the supported unobstructed picker controls.'}
    first, second = pixels(before, exact=True), pixels(after, exact=True)
    difference = np.abs(first.astype(float)-second.astype(float)) / 255
    result['previewChanged'] = bool(difference[112:612].mean() > .002)
    # Protect everything except the status bar and this one validated preview.
    protected = np.ones((1080, 500), dtype=bool)
    protected[:65] = False; protected[112:612] = False
    # The home indicator stays protected, as do library thumbnails and all actions.
    changed = difference.max(axis=2) > 35/255
    worst = 0.0
    for y in range(65, 1080, 25):
        for x in range(0, 500, 25):
            valid = protected[y:y+25, x:x+25]
            if valid.any(): worst = max(worst, float(difference[y:y+25, x:x+25][valid].mean()))
    mean, fraction = float(difference[protected].mean()), float(changed[protected].mean())
    control_boxes=((16,65,64,108),(420,66,490,107),(12,620,115,666),
                   (125,620,215,666),(410,620,485,666))
    control_changed=max(int(changed[top:bottom,left:right].sum()) for left,top,right,bottom in control_boxes)
    stable = mean <= .002 and fraction <= .005 and worst <= .025 and control_changed < 4
    return {**result, 'controlsStable': stable, 'protectedMeanError': mean,
            'protectedChangedFraction': fraction, 'worstProtectedBlock': worst,
            'mostChangedControlPixels': control_changed,
            'ignoredRegions': [[0, 0, 500, 65], [0, 112, 500, 612]],
            'reason': 'Picker controls/grid agree; preview motion was excluded.' if stable else 'Controls or library pixels changed; inspect again.'}
