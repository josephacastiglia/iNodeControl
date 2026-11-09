"""Closes one app from the iOS app switcher on a window's phone: a stuck screen no tap can leave.

YouTube on slot 16 stayed on its reopened draft's 'Processing' overlay for over half an hour and
ignored its back arrow (23 Oct). Closing the app leaves the saved draft in YouTube's Drafts; nothing
is saved, discarded or posted. Steps: App Switcher (Fn+Up); a fresh frame must show the app's own
name once in the card label row (the app last used is the front card, at the right); one swipe up
on that card; a fresh frame must no longer show that name, and the card's own pixels must be gone from the
switcher (card_gone); Home. A name or header word that is simply not read again proves nothing: closing is
reported only on that positive evidence, otherwise the run stops as not proven. One lease, released at the end.

The farm's creation transport allows only Home, Enter, Escape and bounded text, so the switcher key
and the swipe go to the kernel directly under the same lease, as auto_connect.py sends ControlBar.

  python close_app.py --config windows/youtube-slot16/creation-config.json --folder windows/youtube-slot16/close-1 --app YouTube
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from farm_carousel_inspection import InspectionStopped  # noqa: E402
from farm_draft_runs import phone_of  # noqa: E402
from farm_start_screen import StartScreen  # noqa: E402
from identify_phone import post  # noqa: E402

BASE = 'http://127.0.0.1:9916/api'
SWIPES = 3   # Swipes on one unchanged card before stopping.

LABELS = (95, 160)   # The switcher's card labels (icon and app name) sit in this band (slot 16, 23 Oct).
# OCR cannot read a one-letter label ('X', slot 17, 23 Oct); the card then shows the app's own header
# words, left edge within the card: the timeline's 'For you', or an open composer's 'Cancel'.
# (words, lowest left x, top band) per app; the card is drawn at about 3/4 scale from x 276, y 155.
CARD_WORDS = {'X': (('for you', 280, (200, 300)), ('cancel', 280, (195, 235))),
              # TikTok's card sits centred or pushed to the right edge with its name cut off (slot 20, 24 Oct);
              # its profile's 'Following' counter label marks it.
              'TikTok': (('following', 80, (280, 345)),),
              # Instagram's profile card shows its note bubble 'Make this space yours' (slot 18, 25 Oct).
              # An open Reel editor as the front card, its name cut off at the right edge (A12, 5 Nov): 'Edit video'.
              'Instagram': (('make this', 80, (225, 300)), ('edit video', 280, (820, 870)))}


# A swiped card is gone when its pre-swipe pixels are found nowhere in the switcher at any horizontal offset
# (cards slide sideways). Calibrated 5 Nov on every retained close: real closes scored .229-.438, swipes that
# left the card untouched .001-.004, including A20's 4 Nov check 4, which was reported closed only because
# TikTok's 'Following' was not read again.
CARD_ROWS = (220, 700)
CARD_PRESENT, CARD_GONE = .05, .15


def card_gone(before, after, left, width=200):
    """'gone', 'present' or 'unclear', with the best match (mean grey difference) and its horizontal offset."""
    import io
    import numpy as np
    from PIL import Image
    def grey(raw):
        with Image.open(io.BytesIO(raw)) as image: return np.asarray(image.convert('L')).astype(float) / 255
    b, a = grey(before), grey(after)
    if b.shape != a.shape: return dict(verdict='unclear', score=None, offset=None)
    top, bottom = CARD_ROWS
    x0 = max(0, int(left)); x1 = min(b.shape[1], x0 + width)
    if x1 - x0 < 40: return dict(verdict='unclear', score=None, offset=None)
    crop = b[top:bottom, x0:x1]
    best = None
    for dx in range(-b.shape[1], b.shape[1] + 1, 4):
        c0, c1 = max(0, x0 + dx), min(b.shape[1], x1 + dx)
        if c1 - c0 < max(40, (x1 - x0) // 2): continue   # A thin edge sliver could match plain background.
        score = float(np.abs(a[top:bottom, c0:c1] - crop[:, c0 - x0 - dx:c1 - x0 - dx]).mean())
        if best is None or score < best[0]: best = (score, dx)
    verdict = 'present' if best[0] < CARD_PRESENT else 'gone' if best[0] > CARD_GONE else 'unclear'
    return dict(verdict=verdict, score=round(best[0], 4), offset=best[1])


def status_bar(text):
    """A full-screen app shows the clock at the top left; the switcher has no status bar."""
    import re
    return any(re.fullmatch(r'\d{1,2}\W?\W?\d\d', l['text'].strip()) and min(w['y'] for w in l['words']) < 45
               and min(w['x'] for w in l['words']) < 110 for l in text.get('lines', []) if l.get('words'))


def named(label, app):
    """The card label is the app's name; OCR may clip its first letter ('ikTok', slot 20, 24 Oct) or read
    the icon as a short token before it ('-r YouTube', slot 16, 26 Oct)."""
    words = label.split()
    if len(words) > 1 and all(len(w) <= 2 for w in words[:-1]): label = words[-1]
    return label == app or (len(app) >= 5 and label == app[1:])


def card_by_content(text, app):
    """Left x of the app's card found by its own header words (only for apps listed in CARD_WORDS)."""
    found = []
    for words, left, (top, bottom) in CARD_WORDS.get(app, ()):
        found += [min(w['x'] for w in line['words']) - 45 for line in text.get('lines', []) if line.get('words')
                  and line['text'].strip().casefold().startswith(words) and min(w['x'] for w in line['words']) >= left
                  and top <= min(w['y'] for w in line['words']) <= bottom]
    return sorted(found)[-1:]   # The rightmost: the front card is the app last used.


def labels(text):
    """(name, left x) of each card label in the label band."""
    return [(line['text'].strip(), min(w['x'] for w in line['words'])) for line in text.get('lines', [])
            if line.get('words') and LABELS[0] <= min(w['y'] for w in line['words']) <= LABELS[1]]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True); p.add_argument('--folder', required=True); p.add_argument('--app', required=True)
    a = p.parse_args()
    print(json.dumps(close(json.loads(Path(a.config).read_text(encoding='utf-8')), a.folder, a.app)))


def close(config, folder, app, purpose='close-stuck-app'):
    """Closes `app` from the switcher on the config's phone; returns dict(state=closed|stopped, ...)."""
    a = argparse.Namespace(app=app)
    out = {}
    s = StartScreen(folder, phone=phone_of(config))
    s.record.update(purpose=purpose, app=a.app)
    s.tokens = s.kernel.acquire([s.phone.board], 30000)
    def raw(fun, purpose, **data):
        item = dict(fun=fun, purpose=purpose, data=data, state='outcome_unknown', direct=True)
        s.record['commands'].append(item); s.record['phoneInput'] = True; s.save()
        got = post(BASE, fun, dict(id=s.phone.device_id, token=s.tokens[s.phone.board], **data))
        item['state'] = 'answered' if got.get('code') == 0 else 'failed'; s.save()
        if got.get('code') != 0: raise InspectionStopped(f'{purpose}: {got}')
    try:
        raw('/key/sendkey', 'open-app-switcher', fn_key='AppSwitch')
        s.pause(1.5)
        raw_frame, text, _, _ = s.fresh('switcher')
        if not any(named(name, a.app) for name, _ in labels(text)) and not card_by_content(text, a.app):
            if status_bar(text):
                # The switcher key was ignored and the app is still full screen with its status bar
                # (slot 16, 25 Oct): the key, which only opens the switcher, is sent once more.
                raw('/key/sendkey', 'open-app-switcher-again', fn_key='AppSwitch')
            s.pause(1.0)   # The switcher can still be sliding in (slot 20, 24 Oct); read once more.
            raw_frame, text, _, _ = s.fresh('switcher-again')
        found = [x for name, x in labels(text) if named(name, a.app)]
        s.record['labels'] = [name for name, _ in labels(text)]
        if not found:
            found = card_by_content(text, a.app); s.record['foundBy'] = 'card content' if found else None
        if len(found) != 1: raise InspectionStopped(f'{a.app} is not one switcher card ({s.record["labels"]}); nothing was swiped.')
        # On slot 16 (26 Oct) about half the swipes left the switcher frame unchanged, the card untouched,
        # with or without a pointer reset first (switcher_probe.py swipe-1..4). An unchanged card is swiped
        # again, at most SWIPES times, each on the app's own card found again in a fresh frame.
        evidence = s.record.setdefault('cardEvidence', [])
        for attempt in range(1, SWIPES + 1):
            x = max(60, min(440, found[0] + 45))   # The card's middle, right of its icon and name.
            before, left = raw_frame, found[0]
            s.command('/mouse/reset', 'reset-before-swipe')
            raw('/mouse/swipe', 'close-' + a.app.casefold(), x1=x, y1=650, x2=x, y2=120, duration=250)
            s.pause(1.5)
            raw_frame, text, _, _ = s.fresh(f'after-swipe-{attempt}')
            s.record['after'] = [name for name, _ in labels(text)]
            found = [x for name, x in labels(text) if named(name, a.app)] or card_by_content(text, a.app)
            pixels = card_gone(before, raw_frame, left)
            evidence.append(dict(attempt=attempt, read=bool(found), **pixels)); s.save()
            if len(found) > 1: raise InspectionStopped(f'{a.app} is not one switcher card after a swipe; no further input.')
            if found: continue   # Its name or header is still read: the card is there.
            if pixels['verdict'] == 'gone': break
            if pixels['verdict'] == 'present':
                # Not read again, but its pixels are still in the switcher (A20, 4 Nov check 4): swipe it again there.
                found = [left + pixels['offset']]; continue
            raise InspectionStopped(f'Closing {a.app} is not proven: its card is not read and only partly matches '
                                    f"(score {pixels['score']}); no further input.")
        else:
            raise InspectionStopped(f'{a.app} is still a switcher card after {SWIPES} swipes; no further input.')
        s.record['swipes'] = attempt
        s.command('/key/sendkey', 'home-after-close', fn_key='Home')
        s.record['state'] = 'closed'
        out = dict(state='closed', after=s.record['after'])
    except InspectionStopped as stop:
        s.record['state'] = 'stopped'; out = dict(state='stopped', error=str(stop))
        if any(c['purpose'] == 'open-app-switcher' for c in s.record['commands']):
            s.command('/key/sendkey', 'home-leaves-switcher', fn_key='Home')   # Leaves the switcher; closes nothing.
    finally:
        s.kernel.release(s.tokens); s.save()
    return out


if __name__ == '__main__':
    main()
