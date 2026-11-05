"""The Home screen in icon-edit mode ('jiggle' mode), recognized before any Home-screen input.

A press held past the kernel's long-press promotion (250 ms) on the Home screen enters this mode (A12 14:29,
A13 14:37, 5 Nov: a Search-pill click from the parked pointer). There a later tap on an icon's '-' badge
starts removing an app, so no farm tool taps anything while it shows: the start screen may send one Home
(iOS leaves edit mode on Home) and stops; a run stops with no input.

iOS shows 'Edit' at the top left and 'Done' at the top right in this mode (iOS 17-18), and a '-' badge on
each icon's top-left corner; any one of the two labels at its place, or several badges, is enough.
"""
import re

TOP = (10, 125)            # Edit/Done replace the status bar (A13 5 Nov: OCR y 27-28) or sit just under it.
MINUS = re.compile(r'^[-−–—]$')


def _rows(text):
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        yield (line.get('text', '').strip(), min(w['x'] for w in words), min(w['y'] for w in words),
               max(w['x'] + w['width'] for w in words))


def edit_mode(text, width=500):
    """Why this frame looks like Home's edit mode, or None (also for anything that is not an OCR result)."""
    if not isinstance(text, dict): return None
    rows = list(_rows(text))
    edit = any(t.casefold() == 'edit' and x < width * .3 and TOP[0] <= y <= TOP[1] for t, x, y, _ in rows)
    done = any(t.casefold() == 'done' and right > width * .7 and TOP[0] <= y <= TOP[1] for t, x, y, right in rows)
    badges = sum(1 for line in text.get('lines', []) for w in line.get('words') or []
                 if MINUS.match(str(w.get('text', '')).strip()) and w.get('y', 0) > 60)   # Below the status bar.
    if edit and done: return "'Edit' and 'Done' at the top"
    if (edit or done) and badges >= 1: return "'Edit' or 'Done' at the top and '-' badges"
    if badges >= 3: return f"{badges} '-' badges on the icons"
    return None
