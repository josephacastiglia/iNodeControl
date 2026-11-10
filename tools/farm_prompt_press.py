"""Answering a verified iOS alert with one settled, held press, after a correctly placed click was ignored.

Instagram's photos reminder ignored a click placed on 'Allow Full Access' (A11, A15, A12, 5 Nov 2026). On A12 a press
held 800 ms answered it; the same press held 80 ms or 300 ms did nothing (orchestrator's trial, one result). An 800 ms
hold is a long press on any other screen, so this tool:

  1. reads the alert and requires a family in farm_permission_prompts.SLOW_PRESS with its answer's own OCR box;
  2. clicks once at that box's centre, pointer settled (skipped only when the caller already saw a click ignored);
  3. if the alert stays, presses at the same point, shortest hold first (SLOW_PRESS_HOLDS_MS), recording each result;
  4. before every click and press, needs the pointer's dot inside the box and the same alert on the frame: its text
     and the other button where they were. The dot hides the answer's own label, so that label is never the proof;
  5. calls the alert gone only when no row of it reads, on two frames; a frame that is neither stops the tool.

Never the other button, Escape, or a press on anything else. Frames and decisions go to output/fleet/<run>/ (not committed).

  python tools/farm_prompt_press.py <board> [--run name]

Runs stop on this reminder (Reel, TikTok and X have no validated method for it), so a lane answers it with this tool
and then retries the attempt. Not wired into the run answer path.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from farm_owned_capture import InspectionStopped  # noqa: E402
import farm_permission_prompts as P  # noqa: E402

ROOT = HERE.parent / 'output' / 'fleet'
API = 'http://127.0.0.1:9916/api'
RESET_REST, SETTLE_REST, OUTCOME_REST = .4, 1.2, 2.0   # The A12 trial's timings.
DOT_DELTA, DOT_MIN_PIXELS, DOT_REACH = 40, 20, 120
LANDING_TOLERANCE = 4
SAME_PLACE = 4


def read_alert(text):
    """(prompt, boxes) from the alert's own column, without the dimmed Home labels behind it."""
    from farm_fleet_survey import alert_only
    alert = alert_only(text)
    return P.detect(alert), P.button_boxes(alert) or {}


def alert_state(text, family, others):
    """'up': this alert, its other buttons where they were (the answer's label may be under the dot). 'gone': no row
    of it reads. 'unclear': neither, which never justifies another press."""
    prompt, boxes = read_alert(text)
    if prompt and prompt['kind'] == family and others and all(
            label in boxes and all(abs(a - b) <= SAME_PLACE for a, b in zip(boxes[label], box)) for label, box in others.items()):
        return 'up'
    return 'unclear' if P.alert_reads(text, family) else 'gone'


def landing(parked, settled, point):
    """Where the pointer's dot sits: the centroid of what changed near `point` between the parked and settled frames."""
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(io.BytesIO(parked)).convert('L'), dtype=float)
    b = np.asarray(Image.open(io.BytesIO(settled)).convert('L'), dtype=float)
    if a.shape != b.shape: return None
    x, y = point
    near = np.zeros_like(a, dtype=bool); near[max(0, y - DOT_REACH):y + DOT_REACH, max(0, x - DOT_REACH):x + DOT_REACH] = True
    ys, xs = np.nonzero((np.abs(a - b) > DOT_DELTA) & near)
    return (int(xs.mean()), int(ys.mean())) if len(xs) >= DOT_MIN_PIXELS else None


class Phone:
    """One board through the kernel: its own lease, renewed before each command; frames with their sequence numbers."""
    def __init__(self, board):
        from identify_phone import acquire, post, request
        self.post, self.request = post, request
        rows = [d for d in request(API, 'GET', '/device/get', timeout=8)['list'] if str(d.get('pid', '')).upper() == board]
        if len(rows) != 1: raise SystemExit(f'Expected one {board} device.')
        self.id = rows[0]['deviceid']
        own = [r for r in request(API, 'GET', '/kernel/status', timeout=8)['receivers'] if r['deviceid'] == self.id]
        if len(own) != 1 or not own[0]['live']: raise SystemExit(f'{board} is not mirroring; nothing was sent.')
        self.token = acquire(API, self.id)

    def send(self, fun, **data):
        self.post(API, '/input/renew', dict(id=self.id, token=self.token))
        got = self.post(API, fun, dict(id=self.id, token=self.token, **data))
        if got.get('code') != 0: raise InspectionStopped(f'{fun} refused: {got}')

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


def answer(phone, folder, ocr, *, click_ignored=False, pause=time.sleep, clock=time.perf_counter):
    record = dict(tool='farm_prompt_press', steps=[], attempts=[], state='started', method=None, holdMs=None)
    def save(): (folder / 'record.json').write_text(json.dumps(record, indent=1), encoding='utf-8')
    def keep(role, newer_than=None):
        raw, sequence = phone.shot(newer_than)
        name = f"{len(record['steps']) + 1:02d}-{role}.bmp"
        (folder / name).write_bytes(raw)
        text = ocr(raw); (folder / name.replace('.bmp', '.json')).write_text(json.dumps(text), encoding='utf-8')
        record['steps'].append(dict(role=role, frame=name, sequence=sequence)); save()
        return raw, text
    def stop(reason):
        record.update(state='stopped', reason=reason); save(); return record

    _, text = keep('before')
    prompt, boxes = read_alert(text)
    if prompt is None: return stop('No alert is on screen; nothing was sent.')
    # Checked before the click too: this tool clicks nothing it could not then press.
    decision = P.slow_press_plan(prompt, click_ignored=True)
    if decision['action'] != 'press': return stop(decision['reason'] + ' Nothing was sent.')
    family, target = prompt['kind'], decision['answer']
    if target not in boxes: return stop('The answer has no box of its own; nothing was sent.')
    box = boxes[target]
    point = (round((box[0] + box[2]) / 2), round((box[1] + box[3]) / 2))
    others = {label: b for label, b in boxes.items() if label != target}
    record.update(family=family, answer=target, point=list(point), box=list(box)); save()

    def settle(role):
        """Pointer at rest on the answer, on the same alert. None when it may go on, else why not."""
        count = phone.frames()
        phone.send('/mouse/reset'); pause(RESET_REST)
        parked, parked_text = keep(f'{role}-parked', count)
        if alert_state(parked_text, family, others) != 'up': return 'The alert changed; nothing was pressed.'
        count = phone.frames()
        phone.send('/mouse/move', x=point[0], y=point[1]); pause(SETTLE_REST)
        settled, settled_text = keep(f'{role}-settled', count)
        if alert_state(settled_text, family, others) != 'up': return 'The alert changed; nothing was pressed.'
        dot = landing(parked, settled, point)
        record['steps'][-1]['landing'] = list(dot) if dot else None; save()
        if dot is None: return "The pointer's dot was not found; nothing was pressed."
        inside = (box[0] - LANDING_TOLERANCE <= dot[0] <= box[2] + LANDING_TOLERANCE
                  and box[1] - LANDING_TOLERANCE <= dot[1] <= box[3] + LANDING_TOLERANCE)
        return None if inside else f'The pointer landed at {dot}, outside {box}; nothing was pressed.'

    def outcome(method, hold=None, held=None):
        """The screen after one input: True gone, False still up, None unclear."""
        count = phone.frames(); pause(OUTCOME_REST)
        _, after = keep(f'after-{method}', count)
        state = alert_state(after, family, others)
        if state == 'gone':
            count = phone.frames(); pause(1.0)
            _, again = keep(f'after-{method}-again', count)
            state = alert_state(again, family, others)
        record['attempts'].append(dict(method=method, holdMs=hold, heldMs=held, result=state)); save()
        return {'gone': True, 'up': False}.get(state)

    if not click_ignored:
        why = settle('click')
        if why: return stop(why)
        phone.send('/mouse/click', x=point[0], y=point[1], button=1)
        gone = outcome('click')
        if gone is None: return stop('After the click the screen is neither the alert nor clear of it.')
        if gone:
            record.update(state='answered', method='pointer_tap'); save(); return record
    for hold in decision['holdsMs']:
        why = settle(f'press-{hold}')
        if why: return stop(why)
        phone.send('/mouse/down', button=1)
        started = clock()
        try: pause(hold / 1000)
        finally: phone.send('/mouse/up', button=1)   # A press is never left down.
        gone = outcome(f'press-{hold}', hold, round((clock() - started) * 1000))
        if gone is None: return stop(f'After the {hold} ms press the screen is neither the alert nor clear of it.')
        if gone:
            record.update(state='answered', method='slow_press', holdMs=hold); save(); return record
    record.update(state='ignored', reason='The alert stayed after every hold; no further input.'); save()
    return record


def main():
    p = argparse.ArgumentParser()
    p.add_argument('board'); p.add_argument('--run')
    a = p.parse_args()
    board = a.board.upper()
    from farm_fleet_survey import FLEET
    if board not in FLEET: raise SystemExit(f'{board} is not a Fleet lane phone; refused.')
    from farm_observations import WindowsOcr
    from farm_rack_lock import rack_run_lock
    folder = ROOT / (a.run or f'press-{FLEET[board][0]}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}')
    folder.mkdir(parents=True, exist_ok=True)
    with rack_run_lock(f'prompt press {board}'):
        phone = Phone(board)
        try:
            record = answer(phone, folder, WindowsOcr().read)
            phone.send('/mouse/reset')
        finally: released = phone.release()
    print(json.dumps(dict(board=board, state=record['state'], method=record['method'], holdMs=record['holdMs'], reason=record.get('reason'),
                          attempts=record['attempts'], leaseReleased=released, folder=str(folder.relative_to(HERE.parent)))))


if __name__ == '__main__':
    main()
