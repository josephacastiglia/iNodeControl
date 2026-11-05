"""Answering an iOS alert from the keyboard (Full Keyboard Access), for when a correctly placed click is ignored.

Fleet lane, 5 Nov 2026: Instagram's photos reminder ignored a click placed 1 px from the centre of 'Allow Full Access'
on A11 and A15 (the row highlighted under the pointer). With Full Keyboard Access on, Tab moves a focus ring between the
alert's buttons and space presses the focused one. This tool:

  1. reads the alert (OCR, the alert's own column) and requires a prompt whose policy answer is known;
  2. sends Tab, reads a fresh frame and finds the focus ring by comparing it with the frame from before any key;
  3. presses space only when the ring surrounds the policy answer's button; on any other button, Tab again
     (at most MAX_TABS in all); no ring, or the answer never focused: stop with nothing pressed;
  4. never sends Escape (its effect on this alert is unknown), never a second space.

Every frame and decision is kept under output/fleet/<run>/ (never committed).

  python tools/farm_prompt_keyboard.py <board> [--run name] [--family photos_reminder]

Hook (proposed, not wired): farm_permission_prompts gains method 'keyboard_focus' for a family only after window
evidence shows 'pointer_tap' ignored with a correctly placed tap (landing within a few px of the button's OCR centre);
the run answer path (ReelCreationWorkflow.answer_prompt) then calls answer() below with the same lease instead of
stopping. Families whose answer is a grant are never answered here unless the policy names that answer.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from farm_carousel_inspection import InspectionStopped  # noqa: E402

ROOT = HERE.parent / 'output' / 'fleet'
API = 'http://127.0.0.1:9916/api'
MAX_TABS = 4
RING_DELTA = 40          # A focus ring changes pixels strongly; frame noise stays far below.
RING_MIN_PIXELS = 60
FAMILIES = ('photos_reminder',)   # Families this tool may answer (their policy answer keeps the current setting).


def boxes_of(text):
    """The alert's buttons {label: (left, top, right, bottom)} from the alert's own column."""
    import farm_permission_prompts as P
    from farm_fleet_survey import alert_only
    alert = alert_only(text)
    prompt = P.detect(alert)
    boxes = P.button_boxes(alert)
    return prompt, boxes or {}


def focused(before, after, boxes):
    """The button whose row holds the focus ring: pixels that changed strongly since `before`, inside one button's
    row band (the full alert width at that button's height). None when no ring is found or it is ambiguous."""
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(io.BytesIO(before)).convert('RGB'), dtype=int)
    b = np.asarray(Image.open(io.BytesIO(after)).convert('RGB'), dtype=int)
    if a.shape != b.shape: return None, {}
    changed = np.abs(a - b).max(axis=2) > RING_DELTA
    counts = {}
    for label, (left, top, right, bottom) in boxes.items():
        band = changed[max(0, top - 18):bottom + 18, 85:415]
        counts[label] = int(band.sum())
    hits = [label for label, n in counts.items() if n >= RING_MIN_PIXELS]
    return (hits[0] if len(hits) == 1 else None), counts


class Phone:
    """One board through the kernel: its own lease, renewed before each key; frames with their sequence numbers."""
    def __init__(self, board):
        from identify_phone import acquire, post, request
        self.post, self.request = post, request
        rows = [d for d in request(API, 'GET', '/device/get', timeout=8)['list'] if str(d.get('pid', '')).upper() == board]
        if len(rows) != 1: raise SystemExit(f'Expected one {board} device.')
        self.id = rows[0]['deviceid']
        status = request(API, 'GET', '/kernel/status', timeout=8)
        own = [r for r in status['receivers'] if r['deviceid'] == self.id]
        if len(own) != 1 or not own[0]['live']: raise SystemExit(f'{board} is not mirroring; nothing was sent.')
        self.token = acquire(API, self.id)

    def key(self, **data):
        self.post(API, '/input/renew', dict(id=self.id, token=self.token))
        got = self.post(API, '/key/sendkey', dict(id=self.id, token=self.token, **data))
        if got.get('code') != 0: raise InspectionStopped(f'Key refused: {got}')

    def frames(self):
        return [r for r in self.request(API, 'GET', '/kernel/status', timeout=8)['receivers'] if r['deviceid'] == self.id][0]['frames']

    def shot(self, newer_than=None, waits=30):
        import urllib.request
        for _ in range(waits):
            if newer_than is None or self.frames() > newer_than: break
            time.sleep(.1)
        with urllib.request.urlopen(f'{API}/pic/screenshot?id={self.id}', timeout=8) as response:
            return response.read(), int(response.headers.get('X-iMouse-Frame-Sequence', -1))

    def release(self):
        return self.post(API, '/input/release', dict(id=self.id, token=self.token)).get('code') == 0


def answer(phone, folder, family, ocr, pause=time.sleep):
    import farm_permission_prompts as P
    record = dict(tool='farm_prompt_keyboard', family=family, method='keyboard_focus', steps=[], state='started',
                  spacePressed=False, escapeSent=False)
    def keep(role, raw):
        name = f"{len(record['steps']) + 1:02d}-{role}.bmp"
        (folder / name).write_bytes(raw)
        text = ocr(raw); (folder / name.replace('.bmp', '.json')).write_text(json.dumps(text), encoding='utf-8')
        return name, text
    def save(): (folder / 'record.json').write_text(json.dumps(record, indent=1), encoding='utf-8')
    raw, seq = phone.shot()
    name, text = keep('before', raw)
    prompt, boxes = boxes_of(text)
    record['steps'].append(dict(role='before', frame=name, sequence=seq, prompt=prompt and prompt['kind'], buttons=sorted(boxes)))
    if not prompt or prompt['kind'] != family or family not in FAMILIES:
        record.update(state='stopped', reason='The expected prompt is not on screen; nothing was sent.'); save(); return record
    target = P.POLICY.get(family)
    if target not in boxes:
        record.update(state='stopped', reason='The policy answer is not read on the alert; nothing was sent.'); save(); return record
    before = raw
    for tab in range(1, MAX_TABS + 1):
        count = phone.frames()
        phone.key(fn_key='Tab'); pause(1.0)
        raw, seq = phone.shot(newer_than=count)
        name, text = keep(f'tab-{tab}', raw)
        ring, counts = focused(before, raw, boxes)
        record['steps'].append(dict(role=f'tab-{tab}', frame=name, sequence=seq, focused=ring, ringPixels=counts)); save()
        if ring is None:
            record.update(state='stopped', reason=f'No single focus ring after Tab {tab}; nothing was pressed.'); save(); return record
        if ring == target:
            count = phone.frames()
            phone.key(key=' '); record['spacePressed'] = True; save()
            pause(1.5)
            raw, seq = phone.shot(newer_than=count)
            name, text = keep('after-space', raw)
            again, _ = boxes_of(text)
            gone = not (again and again['kind'] == family)
            record['steps'].append(dict(role='after-space', frame=name, sequence=seq, promptGone=gone))
            record.update(state='answered' if gone else 'ignored'); save(); return record
    record.update(state='stopped', reason=f'{target} was not focused within {MAX_TABS} Tabs; nothing was pressed.'); save()
    return record


def main():
    p = argparse.ArgumentParser()
    p.add_argument('board'); p.add_argument('--run'); p.add_argument('--family', default='photos_reminder', choices=FAMILIES)
    a = p.parse_args()
    board = a.board.upper()
    from farm_fleet_survey import FLEET
    if board not in FLEET: raise SystemExit(f'{board} is not a Fleet lane phone; refused.')
    from farm_observations import WindowsOcr
    folder = ROOT / (a.run or f'keyboard-{FLEET[board][0]}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}')
    folder.mkdir(parents=True, exist_ok=True)
    phone = Phone(board)
    try: record = answer(phone, folder, a.family, WindowsOcr().read)
    finally: released = phone.release()
    print(json.dumps(dict(board=board, state=record['state'], reason=record.get('reason'), spacePressed=record['spacePressed'],
                          steps=[{k: v for k, v in s.items() if k != 'buttons'} for s in record['steps']],
                          leaseReleased=released, folder=str(folder.relative_to(HERE.parent)))))


if __name__ == '__main__':
    main()
