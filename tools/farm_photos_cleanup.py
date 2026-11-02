"""Photos cleanup for the farm phones (LANES.md: Photos cleanup lane, tracker priority 2).

Every creation run saves its package video to the phone's Photos before the app picks it, and nothing
removes it afterwards. This finds those videos and nothing else: each tile of Photos' Select grid is
compared with every package video the farm has made (the creation runs' stored packages), and only a
tile that clearly matches a package video is a farm video. Account content, and anything that is
neither a clear match nor clearly different, is never selected.

  plan  Read-only: Select, one frame of the whole library, Cancel. Writes plan.json and prints its id.
  move  Only with the operator's OK for that plan id, given in the chat: the library is read again and
        must match the plan exactly; the planned tiles are selected, Photos' own count and every badge
        are checked, then 'Delete N Videos', which moves them to Recently Deleted (recoverable for 30
        days). Recently Deleted is never opened or emptied: permanent deletion is the operator's.

  python tools/farm_photos_cleanup.py plan --board F215
  python tools/farm_photos_cleanup.py move --board F215 --plan <id>

Measured on phone 16 (an XR on iOS 18, 1 Nov 2026): in Select mode the 38-item library fits one frame
as a 5-column grid, 100 px a cell, ending at y 908 above the toolbar; a selected tile shows a blue
check at its bottom-right corner and the toolbar reads '1 Video Selected'.
"""
import argparse
import glob
import hashlib
import io
import json
import re
import sqlite3
import sys
import threading
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from farm_paths import MAIN  # noqa: E402
from farm_reel_layout import MATCH_BLOCK, MATCH_MEAN, VideoReference, video_match  # noqa: E402

BASE = 'http://127.0.0.1:9916/api'
OUTPUT = MAIN / 'output' / 'photos-cleanup'
COLUMNS, PITCH = 5, 100
VISIBLE = (100, 970)        # Below the 'Library' title and item count, above the toolbar (phone 16).
# A tile is 'other' only when no package comes near; between the two it is 'unsure' and left alone.
OTHER_MEAN = 2 * MATCH_MEAN
# Header pills and the toolbar trash on phone 16. OCR misses the white-on-grey pills ('Select' not
# read, 'Cancel' read as 'ance'), so they are tapped at fixed points and each mode is confirmed by the
# header title and the toolbar text, which read reliably.
SELECT, CANCEL, TRASH = (387, 82), (428, 82), (406, 1012)


class Stopped(Exception):
    """Nothing further is sent; the reason says what was seen."""


def require(condition, message):
    if not condition: raise Stopped(message)


# ---- Package videos -----------------------------------------------------------------------------

class Squares:
    """The square centre crops video_match compares with (VideoReference.square), cached by video hash."""
    def __init__(self, sha256, square):
        self.sha256, self.square = sha256, list(square)


def package_videos(root=MAIN):
    """Every distinct package video stored by a creation run: {sha256: video bytes}."""
    found = {}
    for db in sorted(glob.glob(str(Path(root) / 'output' / 'candidate-runs' / '*' / 'backend' / '*-creations' / 'runs.db'))):
        con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        try: rows = con.execute('SELECT package FROM runs WHERE package IS NOT NULL').fetchall()
        except sqlite3.Error: rows = []
        finally: con.close()
        for (package,) in rows:
            with zipfile.ZipFile(io.BytesIO(package)) as archive:
                if 'video.mp4' not in archive.namelist(): continue   # Carousel packages hold images.
                video = archive.read('video.mp4')
            found.setdefault(hashlib.sha256(video).hexdigest(), video)
    return found


def references(root=MAIN, cache=OUTPUT / 'reference-cache'):
    cache.mkdir(parents=True, exist_ok=True)
    result = {}
    for sha, video in package_videos(root).items():
        path = cache / f'{sha}.npy'
        if not path.is_file(): np.save(path, np.stack(VideoReference(video).square))
        result[sha] = Squares(sha, np.load(path))
    return result


# ---- One frame of the Select grid ---------------------------------------------------------------

def light(image):
    return image.min(axis=2) > 225


def grid_cells(image):
    """Cell boxes (row, column, box) of the Select grid, top row first, from its light separators.
    The grid sits where Photos left it scrolled (rows from y 108 or from 168 on phone 16, 1 Nov), so the
    separators are found as the 100 px pattern of full-width light lines, and only rows wholly between
    the header and the toolbar are cells."""
    rows = light(image)[:, 5:495].mean(axis=1) > .97
    lines_at = lambda offset: [y for y in range(offset, VISIBLE[1] + 1, PITCH) if y >= VISIBLE[0]]
    offset = max(range(PITCH), key=lambda o: (sum(rows[y] for y in lines_at(o)), -o))
    separators = lines_at(offset)
    hits = [y for y in separators if rows[y]]
    require(len(hits) >= 3, 'The Photos grid has no visible rows.')
    # Inner separators must all be light; only the edges may meet the header gradient or the toolbar.
    first, last = separators.index(hits[0]), separators.index(hits[-1])
    require(all(rows[y] for y in separators[first:last + 1]), 'The Photos grid rows are not 100 px apart.')
    cells = []
    for index, (top, bottom) in enumerate(zip(separators, separators[1:])):
        for column in range(COLUMNS):
            # The whole cell up to the next separator: a 1 to 2 px inset doubled the match difference (.038 to .06+).
            cells.append(dict(row=index, column=column, box=(PITCH * column + 1, top + 1, PITCH * (column + 1), bottom)))
    return cells


def occupied(image, box):
    """Empty cells are plain background or the header's smooth gradient (spread along a row 1-4, a tile about 46)."""
    left, top, right, bottom = box
    return float(image[top:bottom, left:right].astype(int).std(axis=1).mean()) > 15


def classify(image, cells, refs):
    """Each occupied cell: 'farm' (one package clearly matches), 'other' (none comes near) or 'unsure'."""
    tiles = []
    for cell in cells:
        if not occupied(image, cell['box']): continue
        box = left, top, right, bottom = cell['box']
        # Photos darkens each video's bottom edge under its duration label (or the selection check); with that
        # strip compared, clear matches (mean .04) failed on their worst block (.17-.19 against .16).
        ignore = ((left, bottom - 30, right, bottom),)
        scores = sorted((m['mean'], m['worstBlock'], m['matched'], sha) for sha, ref in refs.items()
                        for m in [video_match(None, box, ref, square=True, ignore=ignore, image=image)] if m['mean'] is not None)
        best = scores[0] if scores else None
        status = ('farm' if best and best[2] else 'other' if best is None or best[0] > OTHER_MEAN else 'unsure')
        tiles.append(dict(cell, status=status, package=best[3] if best and status == 'farm' else None,
                          mean=round(best[0], 4) if best else None, worstBlock=round(best[1], 4) if best else None,
                          nearest=round(scores[1][0], 4) if len(scores) > 1 else None,
                          alsoMatches=[s[3] for s in scores[1:] if s[2]] if status == 'farm' else []))
    return tiles


def lines(text):
    for line in text.get('lines', []):
        words = line.get('words') or []
        if words:
            yield (line['text'].strip(), min(w['x'] for w in words), min(w['y'] for w in words),
                   max(w['x'] + w['width'] for w in words), max(w['y'] + w['height'] for w in words))


def find(text, pattern, band):
    """The first OCR line fully matching pattern inside band (left, top, right, bottom): (match, centre)."""
    a, b, c, d = band
    for words, x0, y0, x1, y1 in lines(text):
        found = re.fullmatch(pattern, words)
        if found and a <= x0 and b <= y0 and x1 <= c and y1 <= d: return found, ((x0 + x1) // 2, (y0 + y1) // 2)
    return None, None


def item_count(text):
    found, _ = find(text, r'\W*(\d+) Items?', (0, 95, 250, 140))
    return int(found.group(1)) if found else None


def selected_count(text):
    """Select mode's toolbar: 'Select Items' (0), '1 Video Selected', '18 Videos Selected'; None otherwise."""
    if find(text, r'Select Items', (100, 985, 400, 1030))[0]: return 0
    found, _ = find(text, r'(\d+) Videos? Selected', (60, 985, 440, 1030))
    return int(found.group(1)) if found else None


def delete_target(text, count):
    """The confirmation sheet's red button, worded for exactly count videos."""
    _, centre = find(text, rf'Delete {count} Video{"" if count == 1 else "s"}', (0, 500, 500, 1080))
    return centre


def badge(image, box):
    """The selection check: a blue disk about 16 px across, 4-20 px in from the tile's bottom-right corner,
    with light space to its right. A farm video's own blue block there has the duration label's dark
    shading beside it instead (phone 16, 1 Nov)."""
    left, top, right, bottom = box
    disk = image[bottom - 22:bottom - 6, right - 24:right - 8].astype(int)
    blue = (disk[..., 2] > 200) & (disk[..., 0] < 90)
    side = image[bottom - 28:bottom - 4, right - 7:right - 1].astype(int)
    return blue.mean() > .3 and (side.min(axis=2) > 220).mean() > .8


def plan_id(board, count, tiles):
    key = [board, count, [(t['row'], t['column'], t['status'], t['package']) for t in tiles]]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12]


def same_library(planned, tiles):
    return [(t['row'], t['column'], t['status'], t['package']) for t in planned] == \
           [(t['row'], t['column'], t['status'], t['package']) for t in tiles]


# ---- The phone ----------------------------------------------------------------------------------

class Phone:
    """One lease on one board; every frame is kept in the run folder (output/, never committed)."""
    def __init__(self, base, board, folder):
        from identify_phone import acquire, post, request
        from farm_observations import WindowsOcr
        self.base, self.post, self.folder, self.ocr, self.frames = base, post, folder, WindowsOcr(), 0
        device = next((d for d in request(base, 'GET', '/device/get', timeout=8)['list'] if d.get('pid', '').upper() == board), None)
        require(device, f'No board {board}.')
        status = next((r for r in request(base, 'GET', '/kernel/status', timeout=8)['receivers'] if r['deviceid'] == device['deviceid']), None)
        require(status and status['live'], f'{board} is not mirroring; nothing was sent.')
        self.id = device['deviceid']
        self.token = acquire(base, self.id)
        self.steps = []
        # The lease lasts 15 s and comparing 38 tiles with every package video takes longer; an expired lease
        # marks the board stopped (phone 16, 1 Nov), so it is renewed in the background until close().
        self.lock, self.done = threading.Lock(), threading.Event()
        self.keeper = threading.Thread(target=self.keep, daemon=True); self.keeper.start()

    def keep(self):
        while not self.done.wait(4.0):
            with self.lock: self.post(self.base, '/input/renew', dict(id=self.id, token=self.token))

    def send(self, fun, purpose, **data):
        with self.lock:
            self.post(self.base, '/input/renew', dict(id=self.id, token=self.token))
            got = self.post(self.base, fun, dict(id=self.id, token=self.token, **data))
        self.steps.append(dict(t=round(time.time(), 2), fun=fun, purpose=purpose, code=got.get('code'), **data))
        require(got.get('code') == 0, f'{purpose}: {got}')

    def tap(self, point, purpose, settle=1.5):
        self.send('/mouse/reset', purpose + ' (reset)')
        self.send('/mouse/click', purpose, x=int(point[0]), y=int(point[1]))
        time.sleep(settle)

    def frame(self, label):
        raw = urllib.request.urlopen(f'{self.base}/pic/screenshot?id={self.id}', timeout=8).read()
        self.frames += 1
        picture = Image.open(io.BytesIO(raw)).convert('RGB')
        picture.save(self.folder / f'{self.frames:02d}-{label}.png')
        return np.asarray(picture), self.ocr.read(raw)

    def close(self):
        self.done.set(); self.keeper.join(timeout=10)
        with self.lock: self.post(self.base, '/input/release', dict(id=self.id, token=self.token))


def in_main(text):
    return bool(find(text, r'Photos', (20, 50, 200, 110))[0]) and selected_count(text) is None


def in_select(text):
    return bool(find(text, r'Library', (20, 50, 200, 110))[0]) and selected_count(text) is not None


def select_frame(phone, label):
    """Select mode with nothing selected, entered from Photos' main view if needed: (image, text, count, cells)."""
    image, text = phone.frame(label)
    if not in_select(text):
        require(in_main(text), "Start on Photos' main view with nothing over it; nothing was sent.")
        phone.tap(SELECT, 'Select', settle=2.0)
        image, text = phone.frame(label + '-select')
    require(in_select(text) and selected_count(text) == 0, 'Select mode did not open with nothing selected.')
    count = item_count(text)
    require(count, 'The library item count is not readable.')
    return image, text, count, grid_cells(image)


def cancel_select(phone):
    _, text = phone.frame('before-cancel')
    if in_select(text):
        phone.tap(CANCEL, 'Cancel Select', settle=1.5)
        _, text = phone.frame('after-cancel')
    return in_main(text)


def read_library(phone, refs):
    image, text, count, cells = select_frame(phone, 'library')
    tiles = classify(image, cells, refs)
    require(len(tiles) == count, f'Photos lists {count} items but {len(tiles)} are visible; the library is larger than one screen.')
    # Nothing is selected yet, so a check read here means the badge test cannot be trusted on this library.
    require(not any(badge(image, t['box']) for t in tiles), 'A tile reads as selected before anything was selected.')
    return count, tiles


def run_plan(args, refs, folder):
    phone = Phone(args.base, args.board, folder)
    record = dict(mode='plan', board=args.board, utc=datetime.now(timezone.utc).isoformat(), references=len(refs))
    try:
        count, tiles = read_library(phone, refs)
        record.update(itemCount=count, tiles=tiles, planId=plan_id(args.board, count, tiles),
                      farm=sum(t['status'] == 'farm' for t in tiles), other=sum(t['status'] == 'other' for t in tiles),
                      unsure=sum(t['status'] == 'unsure' for t in tiles))
    except Stopped as error:
        record['stopped'] = str(error)
    finally:
        try: record['selectClosed'] = cancel_select(phone)
        finally:
            phone.close(); record['steps'] = phone.steps
            (folder / 'plan.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record


def run_move(args, refs, folder):
    plans = [json.loads(p.read_text(encoding='utf-8')) for p in OUTPUT.glob('*/plan.json')]
    plan = next((p for p in plans if p.get('planId') == args.plan and p.get('board') == args.board), None)
    require(plan, f'No plan {args.plan} for {args.board}.')
    planned = plan['tiles']
    farm = [t for t in planned if t['status'] == 'farm']
    require(farm, 'The plan has no farm videos.')
    phone = Phone(args.base, args.board, folder)
    record = dict(mode='move', board=args.board, planId=args.plan, utc=datetime.now(timezone.utc).isoformat(), planned=len(farm))
    deleted = False
    try:
        count, tiles = read_library(phone, refs)
        require(count == plan['itemCount'] and same_library(planned, tiles),
                'The library differs from the plan; nothing was selected. Make a new plan.')
        for tile in farm:
            left, top, right, bottom = tile['box']
            phone.tap(((left + right) // 2, (top + bottom) // 2), f'select r{tile["row"]}c{tile["column"]}', settle=.8)
        time.sleep(1.0)
        image, text = phone.frame('selected')
        record['selectedCount'] = selected_count(text)
        require(record['selectedCount'] == len(farm), f'Photos reports {record["selectedCount"]} selected, not {len(farm)}.')
        marks = {(t['row'], t['column']): badge(image, t['box']) for t in tiles}
        wrong = [k for k, v in marks.items() if v != any((t['row'], t['column']) == k for t in farm)]
        require(not wrong, f'Selection badges differ from the plan at {wrong}.')
        phone.tap(TRASH, 'trash', settle=1.5)
        _, text = phone.frame('confirm')
        target = delete_target(text, len(farm))
        require(target, f"The confirmation does not offer 'Delete {len(farm)} Videos'.")
        phone.tap(target, f'Delete {len(farm)} Videos (to Recently Deleted)', settle=3.0)
        deleted = True
        # Photos may leave Select mode after the move or stay in it with nothing selected.
        image, text, after, cells = select_frame(phone, 'after-move')
        left = classify(image, cells, refs)
        record.update(itemCountAfter=after, farmLeft=sum(t['status'] == 'farm' for t in left))
        require(after == count - len(farm), f'Photos lists {after} items after the move, not {count - len(farm)}.')
        record['result'] = f'moved {len(farm)} farm videos to Recently Deleted'
    except Stopped as error:
        record['stopped'] = str(error)
    finally:
        try: record['selectClosed'] = cancel_select(phone)
        finally:
            phone.close(); record.update(steps=phone.steps, deleteTapped=deleted)
            (folder / 'move.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('mode', choices=('plan', 'move'))
    parser.add_argument('--board', required=True)
    parser.add_argument('--plan', help='move: the plan id the operator approved')
    parser.add_argument('--base', default=BASE)
    args = parser.parse_args(argv)
    args.board = args.board.upper()
    if args.mode == 'move' and not args.plan: parser.error('move needs --plan')
    refs = references()
    folder = OUTPUT / f'{args.board}-{args.mode}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}'; folder.mkdir(parents=True)
    record = (run_plan if args.mode == 'plan' else run_move)(args, refs, folder)
    summary = {k: record.get(k) for k in ('planId', 'itemCount', 'farm', 'other', 'unsure', 'result', 'stopped', 'selectClosed',
                                          'itemCountAfter', 'farmLeft', 'deleteTapped') if k in record}
    print(json.dumps(dict(summary, folder=str(folder))))
    return 0 if 'stopped' not in record else 1


if __name__ == '__main__':
    sys.exit(main())
