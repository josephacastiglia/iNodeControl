"""Scale gate on rack B home screens: many phones at once on one kernel, mirroring and pointer input only.

What it measures (FINISH-CRITERIA gates 8 and 11 at the 8-phone and largest-available stages):
- mirroring: every phone live, frame age on every capture, new frames after each input;
- per-phone input: one /mouse/move to one phone at a time, acknowledged, the pointer found where it
  was sent in a fresh frame, and no other phone in the set changing;
- group dispatch: one /mouse/move (comma ids, per-phone tokens) to a group, per-phone landing,
  visible-arrival spread, misses, and no change on set members outside the group;
- leases under load: one atomic acquire, a refused second acquire, a refused wrong token,
  renewals every few seconds (the kernel's lease is 30 s here; lanes renew within 15 s),
  release, and a refused command on the released token.

Safety (the phones carry apps the farm must never open):
- only rack B slots named on the command line, never B5, B3, B7, B10, B17 or rack A; each slot's
  receiver name and board are checked against rack-b-slots.json and the kernel's device list;
- only /input/acquire|renew|release|status, /mouse/reset, /mouse/move and Home. No click, no
  button press, no swipe, no other key: nothing this tool sends can launch an app;
- Home at most once per phone per 3 s (never read as a double press);
- before each burst every phone's frame is compared with its preflight home-screen frame; a
  phone whose screen changed is pressed Home once (only if allowed) and dropped from the run;
- captures go to output/ (never committed); records name phones by slot, never by device ID.

  python scale_gate.py preflight --slots B1,B2,...           # read-only: frames, ages, noise masks
  python scale_gate.py run --slots B1,... --group B1,...,B8   # group test on a subset, rest as controls
"""
from __future__ import annotations

import argparse
import io
import json
import math
import random
import statistics
import struct
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
API = 'http://127.0.0.1:9916/api'
SLOTS_FILE = REPO / 'analysis/farm-multiphone-20261020/rack-b-slots.json'
OUT_ROOT = REPO / 'output/scale-gate-20261104'

NEVER = frozenset({'B3', 'B5', 'B7', 'B10', 'B17'})
ALLOWED_FUNS = frozenset({'/input/acquire', '/input/renew', '/input/release', '/input/status',
                          '/input/stop', '/input/resume', '/mouse/reset', '/mouse/move', '/key/sendkey'})
HOME_SPACING_S = 3.0
LEASE_MS = 30_000
RENEW_EVERY_S = 6.0
MAX_AGE_MS = 1500.0
SETTLE_S = 0.25          # landing is measured on a frame this long after the move completed
# 4.7-inch phones letterboxed in the 500 x 1080 frame from y 95 (500 x 889 visible).
SCREEN_TOP, SCREEN_BOTTOM = 95, 984
STATUS_BAR = (SCREEN_TOP, SCREEN_TOP + 30)
# Pointer targets inside the phone area, far enough apart that two dots never overlap.
TARGETS = [(110, 260), (390, 260), (250, 470), (110, 700), (390, 700), (250, 880), (250, 190), (250, 620)]
DOT_RADIUS = 45          # px around a target in which the dot is looked for
LAND_PX = 15.0           # landing error that still counts as "landed" (about 2.7 pointer units)
DOT_MIN, DOT_MAX, DOT_FILL = 12, 45, 0.45   # pointer-dot blob: bbox side range and fill ratio
DIFF = 18                # grey-level change counted as a change
MIN_DOT = 20             # changed pixels needed to count a dot
SCREEN_CHANGE = 0.04     # fraction of non-noise phone-area pixels changed => the screen is no longer home


class Refused(RuntimeError):
    """A safety rule refused the request; nothing was sent."""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def bmp_headers(raw):
    if raw[:2] != b'BM':
        raise ValueError('not a BMP frame')
    return struct.unpack_from('<i', raw, 18)[0], abs(struct.unpack_from('<i', raw, 22)[0])


def gray(raw):
    return np.asarray(Image.open(io.BytesIO(raw)).convert('L'), dtype=np.int16)


# ---------------------------------------------------------------- frame analysis (pure, tested)

def dilate(mask, size=41):
    return np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(size))) > 0


def noise_mask(frames):
    """Pixels that change with no input (clock hands, status bar), widened to whole icons."""
    noise = np.zeros(frames[0].shape, bool)
    for a in range(len(frames)):
        for b in range(a + 1, len(frames)):
            noise |= np.abs(frames[a] - frames[b]) > DIFF
    noise[STATUS_BAR[0]:STATUS_BAR[1], :] = True
    return dilate(noise)


def phone_area(shape):
    area = np.zeros(shape, bool)
    area[SCREEN_TOP:SCREEN_BOTTOM, :] = True
    return area


def changed(a, b, noise):
    return (np.abs(a - b) > DIFF) & ~noise & phone_area(a.shape)


def disc(shape, point, radius=DOT_RADIUS):
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return (xx - point[0]) ** 2 + (yy - point[1]) ** 2 <= radius ** 2


def blobs(before, after, noise):
    """Pointer-shaped changes: compact, filled, about the size of the AssistiveTouch dot (~25 px).

    Clock hands and the status bar are thin or masked; a dot that appears or fades is round."""
    from scipy import ndimage
    mask = changed(before, after, noise)
    labels, count = ndimage.label(mask)
    out = []
    for index, box in enumerate(ndimage.find_objects(labels), start=1):
        if box is None:
            continue
        ys, xs = np.nonzero(labels[box] == index)
        n = len(xs)
        h, w = box[0].stop - box[0].start, box[1].stop - box[1].start
        if n < MIN_DOT or not (DOT_MIN <= w <= DOT_MAX and DOT_MIN <= h <= DOT_MAX) or n / (w * h) < DOT_FILL:
            continue
        out.append((float(np.median(xs) + box[1].start), float(np.median(ys) + box[0].start), n))
    return out


def dot_near(before, after, target, noise, radius=DOT_RADIUS):
    """The pointer-shaped change nearest target, if one lies within radius."""
    near = [(math.hypot(x - target[0], y - target[1]), (x, y, n)) for x, y, n in blobs(before, after, noise)]
    near = [item for item in near if item[0] <= radius]
    return min(near)[1] if near else None


def stray_dots(before, after, noise, allowed_points=(), radius=45):
    """Pointer-shaped changes away from every allowed point (where this phone's own pointer may fade)."""
    return [(round(x), round(y)) for x, y, _ in blobs(before, after, noise)
            if all(math.hypot(x - p[0], y - p[1]) > radius for p in allowed_points)]


def stray_change(before, after, noise, allowed_points=(), radius=45):
    """Changed pixels outside the discs where the pointer is expected (left or arrived)."""
    mask = changed(before, after, noise)
    for point in allowed_points:
        mask &= ~disc(before.shape, point, radius)
    return int(mask.sum())


def screen_changed(baseline, frame, noise, pointer_points=()):
    """Fraction of the phone area that differs from the home-screen baseline, pointer discs excluded."""
    mask = changed(baseline, frame, noise)
    for point in pointer_points:
        mask &= ~disc(baseline.shape, point, 40)
    area = phone_area(baseline.shape) & ~noise
    return float(mask.sum()) / max(1, int(area.sum()))


def summary(values):
    values = sorted(v for v in values if v is not None and math.isfinite(v))
    if not values:
        return dict(n=0)
    p95 = values[min(len(values) - 1, math.ceil(0.95 * len(values)) - 1)]
    return dict(n=len(values), min=round(values[0], 1), median=round(statistics.median(values), 1),
                p95=round(p95, 1), max=round(values[-1], 1))


# ---------------------------------------------------------------- guarded kernel client

class Kernel:
    """Rack B home-screen client: only the named slots, only pointer moves, reset and spaced Home."""

    def __init__(self, slots, url=API, transport=None, devices=None, board_map=None):
        bad = [s for s in slots if s in NEVER or not s.startswith('B')]
        if bad:
            raise Refused(f'Slots not allowed for the scale gate: {bad}')
        self.url = url.rstrip('/')
        self._transport = transport or self._http
        board_map = board_map or {f'B{k}': v for k, v in json.loads(SLOTS_FILE.read_text(encoding='utf-8'))['slots'].items()}
        devices = devices if devices is not None else self.get('/device/get')['list']
        self.ids, self.slot_of = {}, {}
        for slot in slots:
            expected = board_map[slot]
            rows = [d for d in devices if d.get('receiver_name') == expected['receiver']]
            if len(rows) != 1 or rows[0].get('pid') != expected['board']:
                raise Refused(f'{slot}: receiver/board binding does not match rack-b-slots.json; nothing was sent.')
            self.ids[slot] = rows[0]['deviceid']
            self.slot_of[rows[0]['deviceid']] = slot
        self.tokens = {}
        self.last_home = {}
        self.lock = threading.Lock()
        self.calls = []

    # transport
    def _http(self, method, path, body, timeout):
        data = None if body is None else json.dumps(body).encode('utf-8')
        request = urllib.request.Request(self.url + path, data=data, method=method,
                                         headers={'Content-Type': 'application/json'} if body is not None else {})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=timeout) as response:
                return response.read(), dict(response.headers), response.status
        except urllib.error.HTTPError as error:
            return error.read(), dict(error.headers or {}), error.code

    def get(self, path, timeout=5.0):
        raw, _, _ = self._transport('GET', path, None, timeout)
        return json.loads(raw.decode('utf-8'))['data']

    def timed_status(self):
        t0 = time.perf_counter()
        data = self.get('/kernel/status')
        return (time.perf_counter() - t0) * 1000, data

    def post(self, fun, data, timeout=15.0):
        if fun not in ALLOWED_FUNS:
            raise Refused(f'{fun} is not allowed in the scale gate.')
        if fun != '/input/status':
            ids = data.get('id', '').split(',')
            foreign = [i for i in ids if i not in self.slot_of]
            if foreign or not ids:
                raise Refused('A target outside the named slots; nothing was sent.')
            for field in ('tokens',):
                if field in data and set(data[field]) - set(self.slot_of):
                    raise Refused('A token for a phone outside the named slots; nothing was sent.')
        if fun == '/key/sendkey':
            if set(data) - {'id', 'token', 'tokens', 'fn_key'} or data.get('fn_key') != 'Home':
                raise Refused('Only Home is allowed.')
            now = time.monotonic()
            with self.lock:
                for i in data['id'].split(','):
                    if now - self.last_home.get(i, -1e9) < HOME_SPACING_S:
                        raise Refused(f'Home on {self.slot_of[i]} again within {HOME_SPACING_S} s; nothing was sent.')
                for i in data['id'].split(','):
                    self.last_home[i] = now
        if fun == '/mouse/move' and set(data) - {'id', 'token', 'tokens', 'x', 'y'}:
            raise Refused('A move carries only its point.')
        if fun == '/mouse/reset' and set(data) - {'id', 'token', 'tokens'}:
            raise Refused('A reset carries no other fields.')
        t0 = time.perf_counter()
        raw, _, http = self._transport('POST', '/', {'fun': fun, 'data': data}, timeout)
        rtt = (time.perf_counter() - t0) * 1000
        reply = json.loads(raw.decode('utf-8')).get('data') or {}
        item = dict(at=now_iso(), fun=fun, slots=[self.slot_of[i] for i in data.get('id', '').split(',') if i in self.slot_of],
                    http=http, code=reply.get('code'), message=reply.get('message'), rtt_ms=round(rtt, 1),
                    results={self.slot_of.get(r.get('id'), '?'): r.get('code') for r in reply.get('results') or []})
        with self.lock:
            self.calls.append(item)
        return reply, rtt

    # leases
    def input_status(self):
        reply, _ = self.post('/input/status', {})
        return {self.slot_of[p['id']]: p for p in reply.get('phones') or [] if p['id'] in self.slot_of}

    def acquire(self, slots, lease_ms=LEASE_MS):
        reply, rtt = self.post('/input/acquire', {'id': ','.join(self.ids[s] for s in slots), 'lease_ms': lease_ms})
        if reply.get('code') == 0:
            for row in reply['leases']:
                self.tokens[self.slot_of[row['id']]] = row['token']
        return reply, rtt

    def tokens_for(self, slots):
        return {self.ids[s]: self.tokens[s] for s in slots}

    def renew(self, slots):
        return self.post('/input/renew', {'id': ','.join(self.ids[s] for s in slots), 'tokens': self.tokens_for(slots)})

    def release(self, slots):
        slots = [s for s in slots if s in self.tokens]
        if not slots:
            return {'code': 0}, 0.0
        reply, rtt = self.post('/input/release', {'id': ','.join(self.ids[s] for s in slots), 'tokens': self.tokens_for(slots)})
        if reply.get('code') == 0:
            for s in slots:
                self.tokens.pop(s, None)
        return reply, rtt

    # input
    def send(self, fun, slots, **data):
        body = {'id': ','.join(self.ids[s] for s in slots), 'tokens': self.tokens_for(slots), **data}
        return self.post(fun, body)

    # frames
    def shot(self, slot):
        """(gray frame, raw, sequence, age_ms, arrival perf time) for one phone; retries one 503."""
        for attempt in range(4):
            t0 = time.perf_counter()
            raw, headers, http = self._transport('GET', f'/pic/screenshot?id={urllib.request.quote(self.ids[slot])}&binary=true', None, 8.0)
            t1 = time.perf_counter()
            if http == 503:
                time.sleep(0.25 * (attempt + 1))
                continue
            if raw[:2] != b'BM':
                raise RuntimeError(f'{slot}: no live frame ({raw[:120]!r})')
            age = float(headers.get('X-iMouse-Frame-Age-Ms', 'nan'))
            seq = int(headers.get('X-iMouse-Frame-Sequence', -1))
            return dict(gray=gray(raw), raw=raw, seq=seq, age_ms=age, t=t1, shot_ms=(t1 - t0) * 1000,
                        arrival=t1 - (age / 1000 if math.isfinite(age) else 0), busy_retries=attempt)
        raise RuntimeError(f'{slot}: screenshots busy after retries')


# ---------------------------------------------------------------- background samplers

class Sampler(threading.Thread):
    """CPU of this PC and the kernel's /kernel/status response time every 2 s, plus my phones' frame ages."""

    def __init__(self, kernel, slots):
        super().__init__(daemon=True)
        self.kernel, self.slots, self.rows, self.stop = kernel, slots, [], threading.Event()

    def run(self):
        import psutil
        psutil.cpu_percent(None)
        while not self.stop.wait(2.0):
            row = dict(at=now_iso(), cpu=psutil.cpu_percent(None), mem=psutil.virtual_memory().percent)
            try:
                ms, status = self.kernel.timed_status()
                row['kernel_ms'] = round(ms, 1)
                rec = {r['deviceid']: r for r in status.get('receivers') or []}
                row['ages'] = {s: (round(rec[i]['frame_age_ms'], 1) if rec.get(i, {}).get('frame_age_ms') is not None else None)
                               for s, i in self.kernel.ids.items() if s in self.slots}
                row['delivery'] = {s: rec.get(i, {}).get('frame_delivery') for s, i in self.kernel.ids.items() if s in self.slots}
                row['other_receivers_live'] = sum(1 for r in rec.values() if r.get('live') and r['deviceid'] not in self.kernel.slot_of)
            except Exception as error:   # recorded, the run decides whether to stop
                row['kernel_error'] = str(error)
            self.rows.append(row)


class Renewer(threading.Thread):
    def __init__(self, kernel, slots_fn, log):
        super().__init__(daemon=True)
        self.kernel, self.slots_fn, self.log, self.stop = kernel, slots_fn, log, threading.Event()

    def run(self):
        while not self.stop.wait(RENEW_EVERY_S):
            slots = [s for s in self.slots_fn() if s in self.kernel.tokens]
            if not slots:
                continue
            try:
                before = self.kernel.input_status()
                reply, rtt = self.kernel.renew(slots)
                self.log.append(dict(at=now_iso(), slots=len(slots), code=reply.get('code'), message=reply.get('message'),
                                     rtt_ms=round(rtt, 1),
                                     min_remaining_before_ms=min(before[s]['lease_remaining_ms'] for s in slots)))
            except Exception as error:
                self.log.append(dict(at=now_iso(), error=str(error)))


# ---------------------------------------------------------------- the run

class Run:
    def __init__(self, slots, group, folder, kernel=None, rounds=None, seed=None):
        self.slots, self.group = list(slots), list(group)
        if set(self.group) - set(self.slots):
            raise Refused('The group must be inside the named slots.')
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.k = kernel or Kernel(self.slots)
        self.rng = random.Random(seed)
        self.rounds = rounds or len(TARGETS)
        self.live = list(self.slots)           # phones still in the run
        self.dropped = {}
        self.base, self.noise, self.last = {}, {}, {}
        self.pointer = {}                      # where each phone's pointer was last sent
        self.record = dict(tool='scale_gate', started=now_iso(), slots=self.slots, group=self.group,
                           controls=[s for s in self.slots if s not in self.group], apps_opened=0,
                           clicks_sent=0, swipes_sent=0, other_keys_sent=0, events=[])
        self.frames_saved = 0

    def save(self):
        (self.folder / 'record.json').write_text(json.dumps(self.record, indent=1), encoding='utf-8')

    def keep(self, slot, role, shot):
        name = f'{slot}-{role}.png'
        Image.open(io.BytesIO(shot['raw'])).save(self.folder / 'frames' / name)
        self.frames_saved += 1

    def event(self, **row):
        row['at'] = now_iso()
        self.record['events'].append(row)
        print(json.dumps(row), flush=True)

    def drop(self, slot, why):
        if slot in self.live:
            self.live.remove(slot)
        self.dropped[slot] = why
        self.event(kind='dropped', slot=slot, why=why)

    # preflight: read-only
    def preflight(self, samples=4):
        (self.folder / 'frames').mkdir(exist_ok=True)
        ms, status = self.k.timed_status()
        rec = {r['deviceid']: r for r in status['receivers']}
        inputs = self.k.input_status()
        rows = {}
        for slot in self.slots:
            r = rec.get(self.k.ids[slot], {})
            st = inputs.get(slot, {})
            row = dict(live=r.get('live'), delivery=r.get('frame_delivery'), status_age_ms=r.get('frame_age_ms'),
                       restarts=r.get('receiver_restarts'),
                       input_free=not any(st.get(f) for f in ('owned', 'active', 'stopped', 'releasing', 'release_failed')),
                       input_message=st.get('message'))
            if not r.get('live'):
                rows[slot] = row
                self.drop(slot, 'not live in preflight')
                continue
            if not row['input_free']:
                rows[slot] = row
                self.drop(slot, f'input not free in preflight: {st}')
                continue
            frames = []
            for i in range(samples):
                s = self.k.shot(slot)
                frames.append(s)
                time.sleep(0.6)
            self.keep(slot, 'preflight', frames[-1])
            grays = [f['gray'] for f in frames]
            self.noise[slot] = noise_mask(grays)
            self.base[slot] = grays[-1]
            row.update(shot_ages_ms=[round(f['age_ms'], 1) for f in frames], seqs=[f['seq'] for f in frames],
                       seq_advanced=frames[-1]['seq'] > frames[0]['seq'],
                       noise_fraction=round(float(self.noise[slot][SCREEN_TOP:SCREEN_BOTTOM].mean()), 3),
                       shape=list(grays[-1].shape))
            rows[slot] = row
        self.record['preflight'] = dict(kernel_status_ms=round(ms, 1), phones=rows,
                                        other_receivers_live=sum(1 for r in rec.values() if r.get('live') and r['deviceid'] not in self.k.slot_of))
        self.save()
        return rows

    def screens_ok(self, label):
        """Fresh frame per live phone, compared with its home-screen baseline (pointer discs excluded)."""
        out = {}
        for slot in list(self.live):
            s = self.k.shot(slot)
            pts = [p for p in (self.pointer.get(slot),) if p] + [(0, SCREEN_TOP)]
            frac = screen_changed(self.base[slot], s['gray'], self.noise[slot], pts)
            out[slot] = dict(age_ms=round(s['age_ms'], 1), seq=s['seq'], changed=round(frac, 4))
            self.last[slot] = s
            if frac > SCREEN_CHANGE:
                self.keep(slot, f'screen-changed-{label}', s)
                self.record['apps_opened'] += 0   # unknown what opened; recorded below, never touched inside
                self.event(kind='screen_changed', slot=slot, label=label, fraction=round(frac, 4))
                self.recover(slot)
        return out

    def recover(self, slot):
        """Home once (spacing permitting), touch nothing else, drop the phone."""
        try:
            if slot in self.k.tokens:
                reply, _ = self.k.send('/key/sendkey', [slot], fn_key='Home')
                self.event(kind='recovery_home', slot=slot, code=reply.get('code'))
        except Refused as refused:
            self.event(kind='recovery_home_refused', slot=slot, why=str(refused))
        self.drop(slot, 'screen changed from its home-screen baseline')

    def fresh_after(self, slot, sent_at, done_at, target, prev, budget_s=3.0):
        """Poll one phone after a move.

        first: the first frame newer than the command whose dot is within LAND_PX of target
        (visible arrival); settled: a frame at least SETTLE_S after the command completed, on
        which the landing error is measured (earlier frames can catch the pointer mid-walk)."""
        polls, first, settled, last = 0, None, None, None
        deadline = time.perf_counter() + budget_s
        while time.perf_counter() < deadline:
            s = self.k.shot(slot)
            polls += 1
            last = s
            if s['arrival'] >= sent_at:
                d = dot_near(prev['gray'], s['gray'], target, self.noise[slot])
                if d and first is None and math.hypot(d[0] - target[0], d[1] - target[1]) <= LAND_PX:
                    first = (s, d)
                if s['arrival'] >= done_at + SETTLE_S:
                    settled = (s, d)
                    if d or first is None and time.perf_counter() > deadline - 0.5:
                        break
                    if first is not None:
                        break
            time.sleep(0.03)
        return first, settled, last, polls

    def sweep(self, slots, sent_at, done_at, target, prev, budget_s=4.0):
        """Round-robin polling of every target phone, one frame each per sweep, so no phone's
        arrival time waits on another phone being settled first (resolution: one sweep)."""
        state = {slot: dict(first=None, settled=None, last=None, polls=0) for slot in slots}
        order = list(slots)
        self.rng.shuffle(order)            # no phone is always polled first
        deadline = time.perf_counter() + budget_s
        while time.perf_counter() < deadline:
            pending = [slot for slot in order if not state[slot].get('done')]
            if not pending:
                break
            for slot in pending:
                st = state[slot]
                s = self.k.shot(slot)
                st['polls'] += 1
                st['last'] = s
                if s['arrival'] < sent_at:
                    continue
                d = dot_near(prev[slot]['gray'], s['gray'], target, self.noise[slot])
                if d and st['first'] is None and math.hypot(d[0] - target[0], d[1] - target[1]) <= LAND_PX:
                    st['first'] = (s, d)
                if s['arrival'] >= done_at + SETTLE_S:
                    st['settled'] = (s, d)
                    if d or st['first'] is not None:
                        st['done'] = True
            order = order[1:] + order[:1]  # rotate the start of the next sweep
            time.sleep(0.02)
        return {slot: (st['first'], st['settled'], st['last'], st['polls']) for slot, st in state.items()}

    def move_and_check(self, targets_slots, target, label, observe):
        """One /mouse/move to targets_slots; check landing on them and no change on the other observed phones."""
        prev = {s: self.last[s] for s in observe}
        sent = time.perf_counter()
        reply, rtt = self.k.send('/mouse/move', targets_slots, x=target[0], y=target[1])
        done = time.perf_counter()
        acks = {self.k.slot_of[r['id']]: r.get('code') for r in reply.get('results') or []}
        row = dict(label=label, target=target, group=len(targets_slots), code=reply.get('code'), rtt_ms=round(rtt, 1),
                   acks=acks, phones={})
        found = self.sweep(targets_slots, sent, done, target, prev)
        for slot in targets_slots:
            first, settled, s, polls = found[slot]
            d = settled[1] if settled else None
            err = math.hypot(d[0] - target[0], d[1] - target[1]) if d else None
            row['phones'][slot] = dict(ack=acks.get(slot), landed=bool(d and err <= LAND_PX),
                                       found=bool(d), error_px=round(err, 1) if err is not None else None,
                                       dot=[round(d[0]), round(d[1])] if d else None,
                                       arrived=first is not None,
                                       visible_ms=round((first[0]['arrival'] - sent) * 1000, 1) if first else None,
                                       after_done_ms=round((first[0]['arrival'] - done) * 1000, 1) if first else None,
                                       age_ms=round(s['age_ms'], 1), polls=polls, fresh=s['arrival'] >= sent,
                                       settled_frame=settled is not None)
            if not (d and err <= LAND_PX):   # keep every frame the landing check could not confirm
                self.keep(slot, f'miss-{label}', settled[0] if settled else s)
            self.last[slot] = s
        # isolation: phones observed but not sent to must not change
        for slot in observe:
            if slot in targets_slots:
                continue
            s = self.k.shot(slot)
            pts = [p for p in (self.pointer.get(slot),) if p]
            stray = stray_change(prev[slot]['gray'], s['gray'], self.noise[slot], pts)
            dots = stray_dots(prev[slot]['gray'], s['gray'], self.noise[slot], pts)
            row['phones'][slot] = dict(control=True, stray_px=stray, new_dots=dots,
                                       age_ms=round(s['age_ms'], 1), fresh=s['arrival'] >= sent)
            if dots:
                self.keep(slot, f'control-change-{label}', s)
            self.last[slot] = s
        for slot in targets_slots:
            self.pointer[slot] = target
        row['dispatch_done_ms'] = round((done - sent) * 1000, 1)
        vis = [p['visible_ms'] for p in row['phones'].values() if p.get('visible_ms') is not None]
        row['spread_ms'] = round(max(vis) - min(vis), 1) if len(vis) > 1 else None
        return row

    def lease_tests(self, slots):
        """Under load: second acquire refused, wrong token refused, both without changing the lease."""
        out = {}
        one = slots[0]
        before = self.k.input_status()[one]
        reply, rtt = self.k.post('/input/acquire', {'id': self.k.ids[one], 'lease_ms': LEASE_MS})
        out['second_acquire'] = dict(code=reply.get('code'), message=reply.get('message'), rtt_ms=round(rtt, 1),
                                     refused=reply.get('code') != 0)
        if reply.get('code') == 0:   # should never happen; give it straight back
            for row in reply.get('leases') or []:
                self.k.post('/input/release', {'id': row['id'], 'tokens': {row['id']: row['token']}})
        bogus = {self.k.ids[one]: '0' * 32}
        try:
            reply, rtt = self.k.post('/mouse/move', {'id': self.k.ids[one], 'tokens': bogus, 'x': 250, 'y': 540})
            out['wrong_token'] = dict(code=reply.get('code'), message=reply.get('message'), refused=reply.get('code') != 0)
        except Exception as error:
            out['wrong_token'] = dict(error=str(error), refused=True)
        after = self.k.input_status()[one]
        out['lease_kept'] = after['owned'] and not after['stopped'] and after['generation'] == before['generation']
        out['status_after'] = {k: after[k] for k in ('owned', 'active', 'stopped', 'generation', 'lease_remaining_ms')}
        return out

    def run(self):
        sampler = Sampler(self.k, self.slots)
        sampler.start()
        renew_log = []
        renewer = Renewer(self.k, lambda: list(self.live), renew_log)
        result = {}
        try:
            self.preflight()
            if not self.live:
                raise RuntimeError('No phone passed preflight.')
            group = [s for s in self.group if s in self.live]
            reply, rtt = self.k.acquire(self.live)
            result['acquire'] = dict(code=reply.get('code'), message=reply.get('message'), rtt_ms=round(rtt, 1),
                                     phones=len(self.live), tokens=len(self.k.tokens))
            if reply.get('code') != 0:
                raise RuntimeError(f'Acquire refused: {reply}')
            renewer.start()
            result['lease_tests'] = self.lease_tests(self.live)

            # normalise: one group Home (page 1 / leaves nothing open), then a reset
            reply, rtt = self.k.send('/key/sendkey', self.live, fn_key='Home')
            result['home_1'] = dict(code=reply.get('code'), rtt_ms=round(rtt, 1),
                                    acks={self.k.slot_of[r['id']]: r.get('code') for r in reply.get('results') or []})
            time.sleep(2.0)
            reply, rtt = self.k.send('/mouse/reset', self.live)
            result['reset'] = dict(code=reply.get('code'), rtt_ms=round(rtt, 1))
            for s in self.live:
                self.pointer[s] = (0, SCREEN_TOP)
            time.sleep(0.8)
            result['screens_start'] = self.screens_ok('start')

            # 1) per-phone input: each phone alone, every other live phone watched
            per_phone = []
            for i, slot in enumerate(list(self.live)):
                if slot not in self.live:
                    continue
                target = TARGETS[i % len(TARGETS)]
                per_phone.append(self.move_and_check([slot], target, f'single-{slot}', list(self.live)))
                self.save_progress(result, per_phone=per_phone)
            result['per_phone'] = per_phone
            result['screens_mid'] = self.screens_ok('mid')

            # 2) group dispatch: one command to the group per round; controls watched
            group = [s for s in self.group if s in self.live]
            rounds = []
            for r in range(self.rounds):
                rounds.append(self.move_and_check(group, TARGETS[(r + 3) % len(TARGETS)], f'group-r{r + 1}', list(self.live)))
                self.save_progress(result, per_phone=per_phone, rounds=rounds)
                group = [s for s in group if s in self.live]
            result['group_rounds'] = rounds
            time.sleep(max(0.0, HOME_SPACING_S - 0.5))
            result['screens_end'] = self.screens_ok('end')
            reply, rtt = self.k.send('/key/sendkey', self.live, fn_key='Home')
            result['home_2'] = dict(code=reply.get('code'), rtt_ms=round(rtt, 1),
                                    acks={self.k.slot_of[r['id']]: r.get('code') for r in reply.get('results') or []})
            time.sleep(2.0)
            result['screens_after_home'] = self.screens_ok('after-home')
        except Refused as refused:
            self.event(kind='refused', why=str(refused))
            result['refused'] = str(refused)
        except Exception as error:
            self.event(kind='error', why=repr(error))
            result['error'] = repr(error)
        finally:
            renewer.stop.set()
            held = list(self.k.tokens)
            old = dict(self.k.tokens)
            try:
                reply, rtt = self.k.release(held)
                result['release'] = dict(code=reply.get('code'), message=reply.get('message'), rtt_ms=round(rtt, 1), phones=len(held))
            except Exception as error:
                result['release'] = dict(error=repr(error))
            try:
                st = self.k.input_status()
                result['release']['owned_after'] = [s for s in held if st.get(s, {}).get('owned')]
                if held:
                    one = held[0]
                    reply, _ = self.k.post('/mouse/move', {'id': self.k.ids[one], 'tokens': {self.k.ids[one]: old[one]}, 'x': 250, 'y': 540})
                    result['release']['old_token_after_release'] = dict(code=reply.get('code'), message=reply.get('message'),
                                                                        refused=reply.get('code') != 0)
            except Exception as error:
                result['release']['after_error'] = repr(error)
            sampler.stop.set()
            sampler.join(timeout=5)
            result['renewals'] = renew_log
            result['samples'] = sampler.rows
            result['dropped'] = self.dropped
            result['calls'] = len(self.k.calls)
            result['call_log'] = self.k.calls
            result['frames_saved'] = self.frames_saved
            self.record['result'] = result
            self.record['finished'] = now_iso()
            self.record['metrics'] = metrics(self.record)
            self.save()
        return self.record

    def save_progress(self, result, **parts):
        self.record['result'] = {**result, **parts}
        self.save()


class CancelRun(Run):
    """Gate 8 stop control: a long group pointer walk is stopped mid-way; the pointers must halt
    short of the target and stay there (no replay), and input must resume cleanly with a new lease."""

    def run(self, stop_after_s=0.25, target=(390, 880)):
        result = {}
        try:
            self.preflight()
            group = [s for s in self.group if s in self.live]
            reply, rtt = self.k.acquire(group)
            result['acquire'] = dict(code=reply.get('code'), rtt_ms=round(rtt, 1), phones=len(group))
            if reply.get('code') != 0:
                raise RuntimeError(f'Acquire refused: {reply}')
            reply, _ = self.k.send('/mouse/reset', group)
            result['reset'] = reply.get('code')
            for s in group:
                self.pointer[s] = (0, SCREEN_TOP)
            time.sleep(0.8)
            result['screens_before'] = self.screens_ok('cancel-before')
            box = {}

            def walk():
                box['t0'] = time.perf_counter()
                box['reply'], box['rtt'] = self.k.send('/mouse/move', group, x=target[0], y=target[1])
                box['t1'] = time.perf_counter()
            thread = threading.Thread(target=walk)
            thread.start()
            time.sleep(stop_after_s)
            t_stop = time.perf_counter()
            stop, stop_rtt = self.k.post('/input/stop', {'id': ','.join(self.k.ids[s] for s in group)})
            t_stopped = time.perf_counter()
            thread.join(timeout=15)
            result['walk'] = dict(codes={self.k.slot_of[r['id']]: (r.get('code'), r.get('message')) for r in box['reply'].get('results') or []},
                                  rtt_ms=round(box['rtt'], 1), stop_sent_after_ms=round((t_stop - box['t0']) * 1000, 1),
                                  walk_returned_after_stop_ms=round((box['t1'] - t_stop) * 1000, 1))
            result['stop'] = dict(code=stop.get('code'), message=stop.get('message'), rtt_ms=round(stop_rtt, 1),
                                  stop_to_released_ms=round((t_stopped - t_stop) * 1000, 1))
            self.k.tokens.clear()            # stop revokes every token
            status = self.k.input_status()
            result['status_after_stop'] = {s: dict(owned=status[s]['owned'], stopped=status[s]['stopped'],
                                                   release_failed=status[s]['release_failed']) for s in group}
            # Where did each pointer halt, and does it stay there (no replay)?
            time.sleep(0.6)
            halted = {}
            first = {s: self.k.shot(s) for s in group}
            time.sleep(2.0)
            later = {s: self.k.shot(s) for s in group}
            for s in group:
                dots = blobs(self.last[s]['gray'], first[s]['gray'], self.noise[s])
                moved = blobs(first[s]['gray'], later[s]['gray'], self.noise[s])
                at_target = dot_near(self.last[s]['gray'], first[s]['gray'], target, self.noise[s])
                halted[s] = dict(dots=[(round(x), round(y)) for x, y, _ in dots], reached_target=bool(at_target),
                                 moved_after_stop=[(round(x), round(y)) for x, y, _ in moved])
                self.keep(s, 'cancel-halted', first[s])
            result['halted'] = halted
            reply, _ = self.k.post('/input/resume', {'id': ','.join(self.k.ids[s] for s in group)})
            result['resume'] = dict(code=reply.get('code'), message=reply.get('message'))
            reply, rtt = self.k.acquire(group)
            result['reacquire'] = dict(code=reply.get('code'), rtt_ms=round(rtt, 1))
            reply, _ = self.k.send('/mouse/move', group, x=250, y=470)
            result['move_after_resume'] = dict(code=reply.get('code'),
                                               acks={self.k.slot_of[r['id']]: r.get('code') for r in reply.get('results') or []})
            time.sleep(0.8)
            result['screens_after'] = self.screens_ok('cancel-after')
        except Exception as error:
            self.event(kind='error', why=repr(error))
            result['error'] = repr(error)
        finally:
            try:
                reply, _ = self.k.release(list(self.k.tokens))
                result['release'] = dict(code=reply.get('code'), message=reply.get('message'))
            except Exception as error:
                result['release'] = dict(error=repr(error))
            result['call_log'] = self.k.calls
            self.record['result'] = result
            self.record['finished'] = now_iso()
            self.save()
        return self.record


def metrics(record):
    """Numbers the gate is judged on, from a run record."""
    res = record.get('result') or {}
    group, controls = record['group'], record['controls']
    pp = res.get('per_phone') or []
    gr = res.get('group_rounds') or []

    def targets(rows):
        return [(row, s, p) for row in rows for s, p in row['phones'].items() if not p.get('control')]

    def ctrl(rows):
        return [(row, s, p) for row in rows for s, p in row['phones'].items() if p.get('control')]

    out = {}
    for name, rows in (('per_phone', pp), ('group', gr)):
        t, c = targets(rows), ctrl(rows)
        out[name] = dict(commands=len(rows), deliveries=len(t),
                         acked=sum(1 for _, _, p in t if p.get('ack') == 0),
                         landed=sum(1 for _, _, p in t if p.get('landed')),
                         found=sum(1 for _, _, p in t if p.get('found')),
                         arrived=sum(1 for _, _, p in t if p.get('arrived')),
                         misses=sorted({f'{row["label"]}:{s}' for row, s, p in t if not p.get('landed')}),
                         error_px=summary([p.get('error_px') for _, _, p in t]),
                         visible_ms=summary([p.get('visible_ms') for _, _, p in t]),
                         visible_within_500=sum(1 for _, _, p in t if p.get('visible_ms') is not None and p['visible_ms'] <= 500),
                         rtt_ms=summary([row['rtt_ms'] for row in rows]),
                         spread_ms=summary([row.get('spread_ms') for row in rows]),
                         control_checks=len(c),
                         isolation_failures=sorted({f'{row["label"]}:{s}' for row, s, p in c if p.get('new_dots')}),
                         after_done_ms=summary([p.get('after_done_ms') for _, _, p in t]),
                         stray_px=summary([p.get('stray_px') for _, _, p in c]))
    ages = [p.get('age_ms') for rows in (pp, gr) for row in rows for p in row['phones'].values()]
    out['frame_age_ms'] = summary(ages)
    out['frame_age_over_1500'] = sum(1 for a in ages if a is not None and a > MAX_AGE_MS)
    samples = res.get('samples') or []
    out['cpu'] = summary([s.get('cpu') for s in samples])
    out['kernel_status_ms'] = summary([s.get('kernel_ms') for s in samples])
    out['kernel_errors'] = sum(1 for s in samples if 'kernel_error' in s)
    out['sampled_age_ms'] = summary([a for s in samples for a in (s.get('ages') or {}).values()])
    out['other_receivers_live'] = summary([s.get('other_receivers_live') for s in samples])
    ren = res.get('renewals') or []
    out['renewals'] = dict(n=len(ren), ok=sum(1 for r in ren if r.get('code') == 0),
                           rtt_ms=summary([r.get('rtt_ms') for r in ren]),
                           min_remaining_ms=min((r['min_remaining_before_ms'] for r in ren if 'min_remaining_before_ms' in r), default=None))
    out['dropped'] = res.get('dropped')
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=('preflight', 'run', 'cancel'))
    p.add_argument('--slots', required=True)
    p.add_argument('--group', default='')
    p.add_argument('--name', default=None)
    p.add_argument('--rounds', type=int, default=None)
    a = p.parse_args()
    slots = [s.strip() for s in a.slots.split(',') if s.strip()]
    group = [s.strip() for s in a.group.split(',') if s.strip()] or slots
    name = a.name or f'{a.mode}-{datetime.now().strftime("%H%M%S")}'
    run = (CancelRun if a.mode == 'cancel' else Run)(slots, group, OUT_ROOT / name, rounds=a.rounds)
    if a.mode == 'cancel':
        record = run.run()
        print(json.dumps({k: v for k, v in record['result'].items() if k != 'call_log'}, indent=1))
        print('folder:', run.folder)
    elif a.mode == 'preflight':
        rows = run.preflight()
        print(json.dumps(rows, indent=1))
        print('folder:', run.folder)
    else:
        record = run.run()
        print(json.dumps(record['metrics'], indent=1))
        print('folder:', run.folder)


if __name__ == '__main__':
    main()
