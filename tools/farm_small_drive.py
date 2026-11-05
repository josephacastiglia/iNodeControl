"""One supervised step on the Small phone lane's 4.7-inch phone (B5), then a fresh frame and its text.

Every call: one lease on that phone only, one action (or none), a pause, a frame, release. The frame and
its OCR are saved under output/small-phone/<run>/ (never committed); the printed text is for the
operator's lane chat only. Navigation only: the guard below refuses keys other than Home and refuses
typing; taps are refused near labels that publish, sign in, follow, message or change settings.

  python tools/farm_small_drive.py <run> <label> [--tap x,y] [--key Home] [--swipe x1,y1,x2,y2,ms] [--wait s]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from identify_phone import acquire, post, request  # noqa: E402

BASE = 'http://127.0.0.1:9916/api'
BOARD = 'CD51'
ROOT = HERE.parent / 'output' / 'small-phone'
KEYS = ('Home',)
# The only text this driver types: an app name into Spotlight.
APP_NAMES = ('Instagram', 'TikTok', 'X', 'YouTube')
# Labels a navigation tap must not land on (case-folded whole words or phrases of an OCR line).
REFUSED = ('post', 'share', 'publish', 'send', 'reply', 'follow', 'like', 'message', 'log in', 'login',
           'sign in', 'sign up', 'create account', 'continue with', 'review account', 'agree', 'accept',
           'delete', 'remove', 'subscribe', 'repost', 'allow', "don't allow", 'save', 'upload')
NEAR = 28


def refused_near(lines, x, y, allowed=()):
    """Return the refused label a tap at (x, y) would land on, or None."""
    for line in lines:
        text = line.get('text', '').strip().casefold()
        box = line_box(line)
        if not box or not text: continue
        left, top, width, height = box
        inside = left - NEAR <= x <= left + width + NEAR and top - NEAR <= y <= top + height + NEAR
        if not inside or text in allowed: continue
        words = text.replace('·', ' ').split()
        for label in REFUSED:
            if (' ' in label and label in text) or label in words: return text
    return None


def line_box(line):
    """(left, top, width, height) of an OCR line from its words, or None."""
    words = line.get('words') or []
    if not words: return None
    left = min(w['x'] for w in words); top = min(w['y'] for w in words)
    right = max(w['x'] + w['width'] for w in words); bottom = max(w['y'] + w['height'] for w in words)
    return left, top, right - left, bottom - top


def control_center(lines):
    """Control Center on the 4.7-inch phone (4 Nov frame): its Focus and Now Playing tiles."""
    return 'focus' in lines and ('not playing' in lines or any(l.endswith('%') for l in lines))


def device_id():
    rows = request(BASE, 'GET', '/device/get', timeout=8)['list']
    hits = [d for d in rows if str(d.get('pid', '')).upper() == BOARD]
    if len(hits) != 1: raise SystemExit(f'expected one {BOARD}, found {len(hits)}')
    if hits[0].get('video_state') != 'mirroring': raise SystemExit(f'{BOARD} is not mirroring; stop and report.')
    return hits[0]['deviceid']


def frame(i):
    raw = urllib.request.urlopen(f'{BASE}/pic/screenshot?id={i}', timeout=8).read()
    return raw


def ocr(raw):
    from farm_observations import WindowsOcr
    return WindowsOcr().read(raw)


def last_text(folder):
    texts = sorted(folder.glob('*.json'))
    texts = [t for t in texts if t.name != 'steps.json']
    return json.loads(texts[-1].read_text(encoding='utf-8')).get('lines', []) if texts else []


def main():
    p = argparse.ArgumentParser()
    p.add_argument('run'); p.add_argument('label')
    p.add_argument('--tap'); p.add_argument('--key'); p.add_argument('--swipe'); p.add_argument('--type', help='an app name for Spotlight')
    p.add_argument('--allow', default='', help='| separated OCR lines this tap may land on (navigation labels)')
    p.add_argument('--wait', type=float, default=2.0)
    a = p.parse_args()
    folder = ROOT / a.run; folder.mkdir(parents=True, exist_ok=True)
    steps_path = folder / 'steps.json'
    steps = json.loads(steps_path.read_text(encoding='utf-8')) if steps_path.exists() else []
    if a.key and a.key not in KEYS: raise SystemExit(f'key {a.key!r} refused; navigation keys only: {KEYS}')
    if a.key == 'Home':
        lines = [l.get('text', '').strip().casefold() for l in last_text(folder)]
        if not lines: raise SystemExit('Home refused: look first (no frame in this run yet).')
        if control_center(lines): raise SystemExit('Home refused: Control Center is open (Home there opened Settings, 4 Nov).')
    if a.type and a.type not in APP_NAMES: raise SystemExit(f'typing {a.type!r} refused; app names only: {APP_NAMES}')
    if a.tap:
        x, y = (int(v) for v in a.tap.split(','))
        allowed = tuple(s.strip().casefold() for s in a.allow.split('|') if s.strip())
        hit = refused_near(last_text(folder), x, y, allowed)
        if hit: raise SystemExit(f'tap refused: ({x}, {y}) is near {hit!r}')
    i = device_id()
    step = dict(label=a.label, tap=a.tap, key=a.key, swipe=a.swipe, type=a.type, at=time.strftime('%Y-%m-%dT%H:%M:%S'))
    if a.tap or a.key or a.swipe or a.type:
        t = acquire(BASE, i)
        def send(fun, **data):
            post(BASE, '/input/renew', dict(id=i, token=t))
            got = post(BASE, fun, dict(id=i, token=t, **data))
            if got.get('code') != 0: raise RuntimeError(f'{fun}: {got}')
        try:
            if a.key: send('/key/sendkey', fn_key=a.key)
            if a.tap:
                send('/mouse/reset'); time.sleep(.3)
                send('/mouse/move', x=x, y=y); time.sleep(1.2)   # 6s pointers settle slowly.
                send('/mouse/click', x=x, y=y, button=1); time.sleep(.3)
                send('/mouse/move', x=480, y=300)
            if a.type: send('/key/sendkey', key=a.type)
            if a.swipe:
                x1, y1, x2, y2, ms = (int(v) for v in a.swipe.split(','))
                send('/mouse/reset'); time.sleep(.3)
                send('/mouse/swipe', x1=x1, y1=y1, x2=x2, y2=y2, duration=ms)
        finally:
            got = post(BASE, '/input/release', dict(id=i, token=t))
            step['released'] = got.get('code') == 0
    time.sleep(a.wait)
    raw = frame(i)
    name = f'{len(steps) + 1:02d}-{a.label}'
    (folder / f'{name}.bmp').write_bytes(raw)
    text = ocr(raw)
    (folder / f'{name}.json').write_text(json.dumps(text), encoding='utf-8')
    step.update(frame=f'{name}.bmp', sha256=hashlib.sha256(raw).hexdigest())
    steps.append(step); steps_path.write_text(json.dumps(steps, indent=1), encoding='utf-8')
    for line in text.get('lines', []):
        b = line_box(line) or ('?', '?', 0, 0)
        print(f"{b[0]:>4},{b[1]:>4} {b[2]:>3}x{b[3]:<3} {line.get('text', '')}")
    print(f'[{name}]')


if __name__ == '__main__':
    main()
