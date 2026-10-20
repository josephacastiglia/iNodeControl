"""Guarded steps for a C24C permission-prompt validation window. Nothing here runs by default.

Every step talks only to the private kernel on 127.0.0.1:9916 with the prepared SHA-256,
process and C24C-only mapping. It needs C24C free, takes its own lease and always releases it.

- observe: read-only. Reports a recognized prompt and its declining button. No input.
- trial: one input method, once, aimed only at the declining button of a recognized prompt.
  pointer_tap and keyboard_escape are the class checks (both ignored on 17 Oct); they and
  long_press send exactly what the run answer path sends. keyboard_focus presses Tab until a
  focus highlight is verified on the declining button, then sends one Space (never Return).
- probe: on the move-only absolute probe kernel (--absolute-probe-pid C24C), A0 moves to
  blank points, each checked for the pointer at that point. That kernel cannot press.
- confirm / promote: the operator's statement of what the phone shows, then the entry for
  farm_permission_prompts.WINDOW_EVIDENCE. A method is validated only this way.

A lost reply stays uncertain. Nothing is retried, replayed or sent to an Allow button.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import threading
import time
import urllib.request
import uuid

import numpy as np
from PIL import Image

import farm_permission_prompts as prompts
from farm_carousel_inspection import OwnedCaptureRun, InspectionStopped
from farm_draft_workflow import DecisionExpired, atomic_json
from farm_frame_evidence import capture_settled, delivery_evidence
from farm_live_verification import NoRedirect, ReadOnlyKernel, idle, validate_runtime
from farm_observations import ObservationStore, expectations
from imouse_social_automation import IMouseKernel, KernelSafetyError, LIVE_TEST_DEVICE_ID

KERNEL_URL = 'http://127.0.0.1:9916/api'
# Observation requests need an app and handle; trials use only the frame, its OCR and freshness.
OBSERVATION = dict(device_id='C24C', platform='instagram', account='prompt.validation', caption='')
TRIAL_METHODS = ('pointer_tap', 'keyboard_escape', 'long_press', 'keyboard_focus')
CHALLENGES = ((480, 300), (450, 300))   # The runs' fresh-frame moves, beside any alert.
PARK = (480, 300)                        # Where the run answer path parks after an answer.
SETTLED_TAP = .6                         # The runs' settled tap rests on the target first.
HOLD = (.6, 1.1)                         # The runs' long press: rest, then hold the button.
AFTER_ANSWER = .7                        # The runs' pause after parking.
OUTCOME_WAIT = .8                        # More time for an alert to animate away.
POINTER_REST = 1.2                       # After the reset; FKA hides its focus after 1 s on C24C.
MAX_TABS = 4                             # A three-answer alert plus one step onto it.
FOCUS_MAX_AGE_MS = 900                   # Space follows the verified frame while its focus still shows.
NEW_FRAME_SECONDS = 1.0
PROBE_POINTS = ((250, 540), (80, 160), (420, 160), (420, 860), (80, 860))
PROBE_FRAME_SECONDS = 2.0
LABEL = re.compile(r'[a-z0-9][a-z0-9-]{1,47}')


def sha(data): return hashlib.sha256(data).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def utc(clock=time.time): return datetime.fromtimestamp(clock(), timezone.utc).isoformat()


def rgb(raw):
    with Image.open(io.BytesIO(raw)) as image: return np.asarray(image.convert('RGB'))


def png(image):
    out = io.BytesIO(); Image.fromarray(image).save(out, 'PNG'); return out.getvalue()


def changed(first, second, threshold=20):
    return np.abs(first.astype(np.int16) - second.astype(np.int16)).max(axis=2) > threshold


# -- prompt geometry -------------------------------------------------------------------------
def button_cells(boxes):
    """One region per answer, wide enough to hold its focus ring.

    Regions meet halfway between neighbouring answers, less 5 pixels on each side, so a ring
    drawn on or just past a shared edge counts for neither; outer edges reach 10 pixels further.
    """
    centres = {label: ((l+r)/2, (t+b)/2) for label, (l, t, r, b) in boxes.items()}
    row = max(c[1] for c in centres.values()) - min(c[1] for c in centres.values()) <= 20
    axis = 0 if row else 1
    order = sorted(centres, key=lambda k: centres[k][axis])
    cells = {}
    for i, label in enumerate(order):
        x, y = centres[label]
        half = min(abs(centres[order[j]][axis] - centres[label][axis]) for j in (i-1, i+1) if 0 <= j < len(order))/2
        low = centres[label][axis] - half + (5 if i > 0 else -10)
        high = centres[label][axis] + half - (5 if i+1 < len(order) else -10)
        cells[label] = (low, y-30, high, y+30) if row else (x-165, low, x+165, high)
    return {k: (max(0, round(l)), max(0, round(t)), min(500, round(r)), min(1080, round(b))) for k, (l, t, r, b) in cells.items()}


def target_plan(text):
    """The recognized prompt, its declining button and the regions a focus check reads."""
    found = prompts.detect(text)
    if not found: raise InspectionStopped('No recognized permission prompt is visible. No validation input is sent.')
    kind = found['kind']
    if found.get('ambiguous') or kind not in prompts.DECLINING:
        raise InspectionStopped('The prompt is not a recognized family with a declining button. No validation input is sent.')
    declining = prompts.DECLINING[kind]
    boxes = prompts.button_boxes(text)
    if not boxes or declining not in boxes:
        raise InspectionStopped(f'"{declining}" is not read on this frame. No validation input is sent.')
    if len(boxes) < 2:
        raise InspectionStopped('The other answers are not read, so the declining button cannot be told apart.')
    l, t, r, b = boxes[declining]
    target = (round((l+r)/2), round((t+b)/2))
    for label, (ol, ot, orr, ob) in boxes.items():
        if label != declining and math.hypot((ol+orr)/2 - target[0], (ot+ob)/2 - target[1]) < 40:
            raise InspectionStopped('The answers are too close together to aim at the declining button alone.')
    if not (10 <= target[0] <= 490 and 65 <= target[1] <= 1035):
        raise InspectionStopped('The declining button is outside the reviewed phone area.')
    cells = button_cells(boxes)
    cl, ct, cr, cb = cells[declining]
    if not (cl + 8 <= target[0] <= cr - 8 and ct + 4 <= target[1] <= cb - 4):
        raise InspectionStopped('The declining button has no clear region of its own.')
    # The alert's own title band: its title row (app name or family wording) and the next 90
    # pixels. A map or video lower in the alert may still be moving; the title never does.
    left = min(c[0] for c in cells.values()) - 10; right = max(c[2] for c in cells.values()) + 10
    top = min(c[1] for c in cells.values())
    rows = [r for r in prompts._rows(text) if r['text'] not in boxes and r['bottom'] <= top and r['left'] >= left and r['right'] <= right]
    titles = [r['top'] for r in rows if prompts.APP.search(r['text']) or any(p.search(r['text']) for _, p in prompts.FAMILIES)]
    words = [r for r in rows if titles and min(titles) <= r['top'] <= min(titles) + 90]
    if not words: raise InspectionStopped('The prompt title above the answers is not read.')
    return dict(kind=kind, app=found.get('app'), declining=declining, target=target,
                buttons={k: [round((v[0]+v[2])/2), round((v[1]+v[3])/2)] for k, v in boxes.items()},
                cells={k: list(v) for k, v in cells.items()},
                textBoxes=[[r['left'], r['top'], r['right'], r['bottom']] for r in words],
                layout='row' if len({round(v[1]/20) for v in boxes.values()}) == 1 else 'stacked')


def focused_button(base, after, geometry):
    """Where a keyboard focus highlight appeared, from pixels only, against the unfocused frame.

    A pale fill or a ring changes one answer's region by more than 10 levels and no other. The
    prompt's own text rows are compared at 40 levels, above video-compression noise: a highlight
    on another control of the alert (iOS 18's location alert has Precise: On) changes them while
    no answer is focused, and a dismissed or replaced alert changes the text and the answers.
    """
    mask = changed(base, after, 10)
    scores = {label: round(float(mask[t:b, l:r].mean()), 4) for label, (l, t, r, b) in geometry['cells'].items()}
    large = changed(base, after, 40)
    text = [large[t:b, l:r] for l, t, r, b in geometry['textBoxes']]
    text_change = round(float(sum(m.sum() for m in text) / max(1, sum(m.size for m in text))), 4)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, value = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    result = dict(scores=scores, textChange=text_change)
    if text_change > .02 and sum(v > .3 for v in scores.values()) >= 2: return dict(result, state='alert_changed', button=None)
    if value < .05: return dict(result, state='focus_elsewhere' if text_change > .02 else 'no_focus', button=None)
    if second > .02 or value < 3*second: return dict(result, state='ambiguous', button=None)
    if text_change > .02: return dict(result, state='focused_text_changed', button=None)
    return dict(result, state='focused', button=best)


def recognized(text):
    """A recognized family with a declining button, for the read-only check before any input.

    Its buttons need not be read here: a label under the resting pointer is lost (17 Oct), and
    the trial reads the full target only after parking the pointer off the alert.
    """
    found = prompts.detect(text)
    if not found or found.get('ambiguous') or found['kind'] not in prompts.DECLINING:
        raise InspectionStopped('No recognized permission prompt with a declining answer is visible. Nothing was sent.')
    return dict(kind=found['kind'], app=found.get('app'), declining=prompts.DECLINING[found['kind']])


def outcome(geometry, text):
    found = prompts.detect(text)
    if found is None: return 'dismissed'
    if found['kind'] == geometry['kind'] and found.get('app') == geometry['app']: return 'ignored'
    return 'changed'


# -- probe pixels --------------------------------------------------------------------------
def blank_at(image, point, radius=30):
    x, y = point
    window = image[y-radius:y+radius, x-radius:x+radius].astype(float) @ np.array([.299, .587, .114])
    return bool(window.size and window.std() <= 6 and window.max() - window.min() <= 30)


def pointer_near(base, frame, point, radius=24):
    x, y = point
    mask = changed(base[y-radius:y+radius, x-radius:x+radius], frame[y-radius:y+radius, x-radius:x+radius])
    if mask.mean() < .08: return None
    ys, xs = np.nonzero(mask)
    centre = (x - radius + float(xs.mean()), y - radius + float(ys.mean()))
    return dict(fraction=round(float(mask.mean()), 3), centre=[round(centre[0]), round(centre[1])],
                distance=round(math.hypot(centre[0]-x, centre[1]-y), 1))


def change_clusters(base, frame, top=60, tile=10):
    """Changed areas below the status bar, grouped from 10-pixel tiles."""
    mask = changed(base, frame); mask[:top] = False
    rows, cols = mask.shape[0]//tile, mask.shape[1]//tile
    tiles = mask[:rows*tile, :cols*tile].reshape(rows, tile, cols, tile).mean(axis=(1, 3)) >= .1
    seen, clusters = np.zeros_like(tiles), []
    for r0, c0 in zip(*np.nonzero(tiles)):
        if seen[r0, c0]: continue
        stack, cells = [(r0, c0)], []
        seen[r0, c0] = True
        while stack:
            r, c = stack.pop(); cells.append((r, c))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r+dr, c+dc
                    if 0 <= rr < rows and 0 <= cc < cols and tiles[rr, cc] and not seen[rr, cc]:
                        seen[rr, cc] = True; stack.append((rr, cc))
        rs, cs = [int(c[0]) for c in cells], [int(c[1]) for c in cells]
        box = (min(cs)*tile, min(rs)*tile, (max(cs)+1)*tile, (max(rs)+1)*tile)
        ys, xs = np.nonzero(mask[box[1]:box[3], box[0]:box[2]])
        clusters.append(dict(tiles=len(cells), box=list(box), centre=[round(box[0]+float(xs.mean())), round(box[1]+float(ys.mean()))]))
    return clusters


def probe_result(base, frame, point):
    clusters = change_clusters(base, frame)
    near = pointer_near(base, frame, point)
    row = dict(pointer=near, clusters=clusters)
    if any(c['tiles'] > 16 for c in clusters) or len(clusters) > 2 or sum(c['tiles'] for c in clusters) > 30:
        return dict(row, state='unexpected_change')
    if near and near['distance'] <= 12: return dict(row, state='positioned')
    return dict(row, state='mispositioned' if clusters else 'no_visible_change')


# -- restricted transports ----------------------------------------------------------------
class TrialKernel(IMouseKernel):
    """C24C-only transport for a trial: its lease, pointer, Tab, Escape and one Space. Nothing else."""
    COMMANDS = ('/input/acquire', '/input/renew', '/input/release', '/mouse/reset', '/mouse/move',
                '/mouse/click', '/mouse/down', '/mouse/up', '/key/sendkey')

    def __init__(self, url=KERNEL_URL, transport=None):
        reader = ReadOnlyKernel(url, transport=transport)
        super().__init__(reader.url)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

        def limited(method, target, body, timeout):
            if method == 'GET' or body == {'fun': '/input/status', 'data': {}}:
                return reader._transport(method, target, body, timeout)
            if (method != 'POST' or target != self.url + '/' or not isinstance(body, dict)
                    or not isinstance(body.get('data'), dict)):
                raise KernelSafetyError('Unsupported validation transport.')
            self.guard(body.get('fun'), body['data'])
            if transport is not None: return transport(method, target, body, timeout)
            request = urllib.request.Request(target, data=json.dumps(body).encode('utf-8'), method=method,
                                             headers={'Content-Type': 'application/json'})
            with opener.open(request, timeout=min(timeout, 8)) as response:
                raw = response.read(1024*1024+1)
                if len(raw) > 1024*1024: raise KernelSafetyError('Candidate response exceeds the evidence limit.')
                return raw, dict(response.headers)
        self._transport = limited
        self.devices = reader.devices

    def guard(self, fun, data):
        if fun not in self.COMMANDS: raise KernelSafetyError(f'Prompt validation cannot send {fun}.')
        if data.get('id') != LIVE_TEST_DEVICE_ID: raise KernelSafetyError('Only C24C is accepted.')
        fields = set(data) - {'id', 'token'}
        if fun in ('/mouse/click', '/mouse/down', '/mouse/up') and data.get('button') != 1:
            raise KernelSafetyError('Only the verified left button is used.')
        if fun == '/key/sendkey' and not ((fields == {'fn_key'} and data['fn_key'] in ('Tab', 'Escape'))
                                          or (fields == {'key'} and data['key'] == ' ')):
            raise KernelSafetyError('Validation keys are Tab, Escape and one Space; never Return, Home or text.')


class ProbeKernel(TrialKernel):
    """The move-only absolute probe: its lease and A0 moves. The probe kernel refuses the rest too."""
    COMMANDS = ('/input/acquire', '/input/renew', '/input/release', '/mouse/move')


# -- one window step ------------------------------------------------------------------------
class ValidationStep:
    def __init__(self, folder, kernel, store, expected_hash, expected_uid, *, probe=False, kernel_process=None,
                 cancelled=None, monotonic=time.monotonic, pause=time.sleep, clock=time.time):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        if (self.folder/'record.json').exists(): raise InspectionStopped('This step already has a record; a step is never replayed.')
        self.kernel, self.store = kernel, store
        self.expected_hash, self.expected_uid, self.probe = expected_hash, expected_uid, probe
        self.kernel_process = tuple(kernel_process) if kernel_process else None
        self.cancelled = cancelled or threading.Event()
        self.monotonic, self.pause, self.clock = monotonic, pause, clock
        self.owned = OwnedCaptureRun(kernel, str(uuid.uuid4()), self.cancelled, monotonic, budget_seconds=120)
        self.identity = None
        self.raw = {}
        self.record = dict(id=self.owned.run_id, phone='C24C', kernelMode='probe' if probe else 'normal',
                           source='phone' if kernel._is_live_http else 'offline_fixture', started=utc(clock), state='not_started',
                           cleanup='not_needed', commands=[], observations=[], frames=[], publishing=False, messaging=False,
                           desktopControl=False, allowTargeted=False)

    def save(self): atomic_json(self.folder/'record.json', self.record)

    def receiver(self):
        return next(r for r in self.kernel.kernel_status().get('receivers', []) if r.get('deviceid') == LIVE_TEST_DEVICE_ID)

    def runtime(self):
        status = self.kernel.kernel_status()
        identity = validate_runtime(status, self.kernel.devices(), self.expected_hash, self.expected_uid)
        if self.kernel_process is not None and tuple(identity) != self.kernel_process:
            raise KernelSafetyError('The kernel is not the process this window started.')
        config = status.get('input_configuration') or {}
        if self.probe and (config.get('absolute_probe_board') != 'C24C' or config.get('hid_reply_boards') != ['C24C']):
            raise KernelSafetyError('The move-only absolute probe kernel is not the one running.')
        if not self.probe and config.get('absolute_probe_board') is not None:
            raise KernelSafetyError('This step needs the normal kernel; the probe kernel refuses presses and keys.')
        return identity

    def check(self):
        if (self.folder/'STOP').exists(): self.cancelled.set()
        self.owned.check(self.kernel)
        if self.runtime() != self.identity: raise InspectionStopped('The kernel changed during the step.')

    def validate(self, value, frame):
        if (value.get('state') != 'observed' or value.get('expired') or value.get('stable') is not True
                or value.get('inputSettled') is not True or not capture_settled(value)
                or value.get('frameEvidence', {}).get('pairedMetadata') is not True
                or value.get('ownershipEvidence', {}).get('runId') != self.owned.run_id
                or value.get('inputGeneration') != self.owned.generation
                or value.get('resolvedDeviceId') != LIVE_TEST_DEVICE_ID
                or value.get('observerSession') != self.store.session
                or value.get('receiverPid') != self.owned.stream[1]
                or value.get('frameEvidence', {}).get('session') != self.owned.stream[3]
                or value.get('expected') != expectations(OBSERVATION)
                or not value.get('frameSha256') or value.get('text', {}).get('frameSha256') != value.get('frameSha256')
                or value.get('reviewFrameSha256') != sha(frame)):
            raise InspectionStopped('The decision has no fresh, intact C24C frame under this ownership.')
        if value.get('freshness') != 'recent':
            raise DecisionExpired('The decision frame is no longer recent; nothing was sent.')

    def command(self, fun, *, purpose, basis=None, fast=None, **data):
        self.check()
        item = dict(fun=fun, data=data, purpose=purpose, state='not_sent')
        self.record['commands'].append(item); self.save()

        def check_basis(stage):
            if basis is not None:
                value, frame = self.store.current_evidence(basis['id'])
                item.setdefault('decisionChecks', []).append(dict(stage=stage, observationId=value['id'],
                    freshness=value.get('freshness'), frameAgeMs=value.get('frameEvidence', {}).get('currentAgeUpperBoundMs')))
                if value.get('evidenceRecordSha256') != basis.get('evidenceRecordSha256'):
                    raise InspectionStopped('The exact decision evidence changed.')
                self.validate(value, frame)
            if fast is not None:
                age = fast['evidence']['ageUpperBoundMs'] + (self.monotonic() - fast['grabbedAt'])*1000
                item.setdefault('decisionChecks', []).append(dict(stage=stage, frame=fast['name'], ageMs=round(age, 1)))
                if age > FOCUS_MAX_AGE_MS:
                    raise DecisionExpired('The focus frame aged to %.0f ms (limit %d ms); no Space was sent.' % (age, FOCUS_MAX_AGE_MS))
        try:
            check_basis('before_dispatch_journal')
            item['state'] = 'outcome_unknown'; self.save()
            check_basis('before_transport')
            self.owned.check_budget()
        except Exception as error:
            item.update(state='not_sent', refusal=type(error).__name__ + ': ' + str(error)); self.save(); raise
        item['response'] = self.kernel.send('C24C', self.owned.tokens['C24C'], fun, **data)
        item['state'] = 'answered'; self.save()

    def read_only(self, role):
        """A capture without a lease or any input, for a check before the step takes C24C."""
        key = str(uuid.uuid4())
        entry = dict(role=role, observationId=key, state='requested', owned=False)
        self.record['observations'].append(entry); self.save()
        observed = self.store.capture(dict(id=key, **OBSERVATION), self.kernel)
        if observed.get('state') != 'observed':
            entry.update(state='failed', reason=observed.get('reason')); self.save()
            raise InspectionStopped('Read-only capture failed: ' + str(observed.get('reason')))
        value, frame = self.store.current_evidence(key)
        entry.update(state='observed', observation=value); self.save()
        return value, frame

    def capture(self, role):
        """An owned decision frame after the runs' fresh-frame pointer move."""
        self.check()
        before = self.receiver()['frames']
        x, y = CHALLENGES[sum(1 for o in self.record['observations'] if o.get('owned') is not False) % 2]
        self.command('/mouse/move', purpose='fresh_frame_challenge', x=x, y=y)
        self.pause(.12)
        key = str(uuid.uuid4())
        entry = dict(role=role, observationId=key, state='requested')
        self.record['observations'].append(entry); self.save()
        observed = self.store.capture(dict(id=key, **OBSERVATION), self.kernel, owned_run=self.owned)
        if observed.get('state') != 'observed':
            entry.update(state='failed', reason=observed.get('reason')); self.save()
            raise InspectionStopped('Capture failed: ' + str(observed.get('reason')))
        value, frame = self.store.current_evidence(key)
        entry.update(state='observed', observation=value); self.save()
        self.validate(value, frame)
        sequence = value['frameEvidence']['sequence']
        if sequence <= max(before, self.record.get('lastSequence', -1)):
            raise InspectionStopped('The pointer challenge did not produce a new frame.')
        self.record['lastSequence'] = sequence
        return value, frame

    def wait_frame(self, after_sequence, seconds):
        deadline = self.monotonic() + seconds
        while self.receiver()['frames'] <= after_sequence:
            if self.monotonic() >= deadline: return False
            self.pause(.05)
        return True

    def grab(self, purpose, *, after_sequence=None, owned=True):
        """A frame without OCR: paired metadata from this receiver session, kept for export."""
        if owned: self.owned.check(self.kernel)
        started = self.monotonic()
        before = self.receiver()
        raw, headers = self.kernel.shot('C24C')
        after = self.receiver()
        measured = self.monotonic()
        evidence = delivery_evidence(before, headers, after, (measured - started)*1000)
        if owned: self.owned.check(self.kernel)
        if evidence.get('pairedMetadata') is not True or (owned and evidence.get('session') != self.owned.stream[3]):
            raise InspectionStopped('The frame has no paired metadata from this receiver session.')
        if after_sequence is not None and evidence['sequence'] <= after_sequence:
            raise InspectionStopped('No new frame was delivered.')
        image = rgb(raw)
        if image.shape[:2] != (1080, 500): raise InspectionStopped('The C24C frame size is not the reviewed 500x1080.')
        name = '%02d-%s.png' % (len(self.record['frames']) + 1, purpose)
        self.raw[name] = image
        self.record['frames'].append(dict(name=name, purpose=purpose, rawSha256=sha(raw), sequence=evidence['sequence'],
                                          freshness=evidence['freshness'], ageUpperBoundMs=evidence['ageUpperBoundMs']))
        self.save()
        return dict(image=image, name=name, evidence=evidence, grabbedAt=measured)

    def replies(self):
        boards = (self.kernel.kernel_status().get('hid_replies') or {}).get('boards') or []
        return next((b.get('observation') for b in boards if b.get('pid') == 'C24C'), None)

    # -- steps ------------------------------------------------------------------------------
    def observe(self):
        self.record.update(step='observe')
        try:
            self.identity = self.runtime()
            value, _ = self.read_only('observe')
            try: self.record['detected'] = recognized(value['text'])
            except InspectionStopped: self.record['detected'] = None
            try: self.record['prompt'] = target_plan(value['text'])
            except InspectionStopped as error: self.record.update(prompt=None, promptReason=str(error))
            self.record['state'] = 'completed'
        except BaseException as error:
            self.record.update(state='review_required', error=type(error).__name__ + ': ' + str(error))
        finally:
            self.finish()
        return self.record

    def trial(self, method, *, activate=True):
        self.record.update(step='trial', method=method, activate=activate if method == 'keyboard_focus' else None)
        try:
            if method not in TRIAL_METHODS: raise InspectionStopped('Unknown validation method.')
            self.identity = self.runtime()
            if not idle(self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)):
                raise InspectionStopped('C24C is not free; no takeover is allowed.')
            value, _ = self.read_only('precheck')
            first = recognized(value['text'])       # Nothing is sent unless this succeeds.
            self.record['precheck'] = first
            self.record['cleanup'] = 'unconfirmed'; self.save()
            self.owned.acquire()
            # Off the alert, so no answer is hovered or highlighted; let any focus highlight hide.
            self.command('/mouse/reset', purpose='park_pointer_off_alert')
            self.pause(POINTER_REST)
            value, frame = self.capture('prompt_before')
            geometry = target_plan(value['text'])
            if (geometry['kind'], geometry['app'], geometry['declining']) != (first['kind'], first['app'], first['declining']):
                raise InspectionStopped('The prompt changed after the read-only check.')
            self.record['prompt'] = geometry; self.save()
            x, y = geometry['target']
            sent = True
            if method == 'pointer_tap':          # As the run's settled tap: rest, then one click.
                self.command('/mouse/move', basis=value, purpose='pointer-tap-position', x=x, y=y)
                self.pause(SETTLED_TAP)
                self.command('/mouse/click', purpose='pointer-tap', x=x, y=y, button=1)
            elif method == 'long_press':         # As the run's hold step.
                self.command('/mouse/move', basis=value, purpose='long-press-position', x=x, y=y)
                self.pause(HOLD[0])
                self.command('/mouse/down', purpose='long-press-press', button=1)
                self.pause(HOLD[1])
                self.command('/mouse/up', purpose='long-press-release', button=1)
            elif method == 'keyboard_escape':
                self.command('/key/sendkey', basis=value, purpose='escape', fn_key='Escape')
            else:
                sent = self.keyboard_focus(value, frame, geometry, activate)
            self.command('/mouse/move', purpose='park_after_answered_action', x=PARK[0], y=PARK[1])
            self.pause(AFTER_ANSWER + OUTCOME_WAIT)
            after, _ = self.capture('prompt_after')
            self.record['outcome'] = outcome(geometry, after['text'])
            if method != 'keyboard_focus' or sent: result = self.record['outcome']
            elif self.record['focusResult'] == 'no_visible_focus': result = 'ignored'
            else: result = self.record['focusResult']
            self.record.update(result=result, state='completed')
        except BaseException as error:
            unknown = any(c['state'] == 'outcome_unknown' for c in self.record['commands'])
            self.record.update(state='review_required', result='uncertain' if unknown else 'stopped',
                               error=type(error).__name__ + ': ' + str(error))
        finally:
            self.finish()
        return self.record

    def keyboard_focus(self, value, frame, geometry, activate):
        """Tab until the focus highlight is verified on the declining answer, then one Space."""
        base, path = rgb(frame), self.record.setdefault('focusPath', [])
        for tab in range(1, MAX_TABS + 1):
            sequence = self.receiver()['frames']
            self.command('/key/sendkey', basis=value if tab == 1 else None, purpose=f'focus-tab-{tab}', fn_key='Tab')
            if not self.wait_frame(sequence, NEW_FRAME_SECONDS):
                path.append(dict(tab=tab, state='no_new_frame')); self.save(); continue
            self.pause(.15)
            grabbed = self.grab(f'focus-tab-{tab}', after_sequence=sequence)
            found = focused_button(base, grabbed['image'], geometry)
            path.append(dict(tab=tab, frame=grabbed['name'], ageUpperBoundMs=grabbed['evidence']['ageUpperBoundMs'], **found))
            self.save()
            if found['state'] in ('alert_changed', 'ambiguous', 'focused_text_changed'):
                raise InspectionStopped(f'After Tab {tab} the focus is not on one clear answer ({found["state"]}); no Space was sent.')
            if found['state'] == 'focused' and found['button'] == geometry['declining']:
                if not activate:
                    self.record['focusResult'] = 'declining_focused_not_activated'; return False
                self.command('/key/sendkey', fast=grabbed, purpose='activate-declining-focus', key=' ')
                self.record['focusResult'] = 'space_sent_on_declining_focus'; return True
        seen = any(step.get('state') == 'focused' for step in path)
        self.record['focusResult'] = 'declining_never_focused' if seen else 'no_visible_focus'
        return False

    def probe_moves(self):
        self.record.update(step='probe', points=[list(p) for p in PROBE_POINTS])
        try:
            self.identity = self.runtime()
            if not idle(self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)):
                raise InspectionStopped('C24C is not free; no takeover is allowed.')
            for attempt in range(3):              # Read-only: wait out a visible pointer before refusing.
                pre = self.grab('probe-precheck', owned=False)
                blank = [blank_at(pre['image'], p) for p in PROBE_POINTS]
                if all(blank): break
                self.pause(4)
            else:
                raise InspectionStopped('The probe points are not on a blank screen (open Safari about:blank). No input was sent.')
            self.record['cleanup'] = 'unconfirmed'; self.save()
            self.owned.acquire()
            base = self.grab('probe-baseline')
            if not all(blank_at(base['image'], p) for p in PROBE_POINTS):
                raise InspectionStopped('The screen changed before the first move. No move was sent.')
            self.record['repliesBefore'] = self.replies()
            rows = self.record['probe'] = []
            for index, point in enumerate(PROBE_POINTS, 1):
                sequence = self.receiver()['frames']
                self.command('/mouse/move', purpose=f'absolute-move-{index}', x=point[0], y=point[1])
                if not self.wait_frame(sequence, PROBE_FRAME_SECONDS):
                    rows.append(dict(point=list(point), state='no_visible_change', newFrame=False, replies=self.replies()))
                    break
                self.pause(.25)
                grabbed = self.grab(f'absolute-move-{index}', after_sequence=sequence)
                row = probe_result(base['image'], grabbed['image'], point)
                rows.append(dict(row, point=list(point), frame=grabbed['name'], newFrame=True, replies=self.replies()))
                self.save()
                if row['state'] != 'positioned': break
            complete = len(rows) == len(PROBE_POINTS) and all(r['state'] == 'positioned' for r in rows)
            self.record.update(result='positioned' if complete else rows[-1]['state'], state='completed')
        except BaseException as error:
            unknown = any(c['state'] == 'outcome_unknown' for c in self.record['commands'])
            self.record.update(state='review_required', result='uncertain' if unknown else 'stopped',
                               error=type(error).__name__ + ': ' + str(error))
        finally:
            self.finish()
        return self.record

    def finish(self):
        try:
            if self.owned.tokens: self.owned.release(); self.record['cleanup'] = 'confirmed'
            self.record['finalInput'] = self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)
            if not idle(self.record['finalInput']):
                self.record.update(state='review_required', cleanup='unconfirmed')
        except Exception as error:
            self.record.update(state='review_required', cleanup='unconfirmed', cleanupError=str(error))
        try:
            for index, entry in enumerate(self.record['observations'], 1):
                if entry.get('state') != 'observed': continue
                value, frame = self.store.evidence(entry['observationId'])
                if value['reviewFrameSha256'] != entry['observation']['reviewFrameSha256']:
                    raise InspectionStopped('A retained image changed before export.')
                entry['frame'] = 'obs-%02d-%s.png' % (index, entry['role'])
                entry['pngSha256'] = sha(frame)
                (self.folder/entry['frame']).write_bytes(frame)
            for entry in self.record['frames']:
                data = png(self.raw[entry['name']])
                entry['pngSha256'] = sha(data)
                (self.folder/entry['name']).write_bytes(data)
            self.record['evidenceExport'] = 'confirmed'
        except Exception as error:
            self.record.update(state='review_required', evidenceExport='failed', exportError=str(error))
        self.record['finished'] = utc(self.clock)
        self.save()


# -- records -------------------------------------------------------------------------------
def frame_sha(record, role):
    entry = next((o for o in record['observations'] if o.get('role') == role and o.get('state') == 'observed'), None)
    return entry.get('pngSha256') if entry else None


def summarize(record, label, kernel_sha):
    """The Git summary of one step: no OCR text, account names or frames, only their hashes."""
    prompt = record.get('prompt') or {}
    commands = [dict(fun=c['fun'], data=c['data'], purpose=c['purpose'], state=c['state']) for c in record['commands']]
    return dict(
        label=label, trial=record['id'], date=record['started'][:10], phone='C24C', source=prompts.WINDOW_SOURCE,
        recordSource=record['source'], kernelMode=record['kernelMode'], kernelSha256=kernel_sha, step=record.get('step'),
        method=record.get('method'), activate=record.get('activate'), state=record['state'], error=record.get('error'),
        cleanup=record['cleanup'], family=prompt.get('kind'), app=prompt.get('app'), answerTargeted=prompt.get('declining'),
        target=prompt.get('target'), buttons=prompt.get('buttons'), layout=prompt.get('layout'), promptReason=record.get('promptReason'),
        detected=record.get('detected'), precheck=record.get('precheck'),
        commands=commands, commandsAnswered=bool(commands) and all(c['state'] == 'answered' for c in commands),
        focusPath=[{k: v for k, v in step.items()} for step in record.get('focusPath', [])], focusResult=record.get('focusResult'),
        probePoints=record.get('points'), probe=record.get('probe'), repliesBefore=record.get('repliesBefore'),
        outcome=record.get('outcome'), result=record.get('result'),
        beforeFrameSha256=frame_sha(record, 'prompt_before'), afterFrameSha256=frame_sha(record, 'prompt_after'),
        frames=[dict(name=f['name'], pngSha256=f.get('pngSha256'), sequence=f['sequence'], ageUpperBoundMs=f['ageUpperBoundMs'])
                for f in record['frames']]
               + [dict(name=o.get('frame'), pngSha256=o.get('pngSha256')) for o in record['observations'] if o.get('frame')],
        allowTargeted=False, publishing=False, messaging=False, desktopControl=False, confirmation=None)


def window_entry(summary, path, digest):
    """The farm_permission_prompts.WINDOW_EVIDENCE record a confirmed trial supports."""
    result = summary.get('result')
    confirmation = summary.get('confirmation') or {}
    state = {'dismissed': 'validated', 'ignored': 'ignored'}.get(result)
    note = (f"{summary.get('method')} on {summary.get('answerTargeted')!s} of {summary.get('app')!s}'s "
            f"{str(summary.get('family')).replace('_', ' ')} prompt: {result}")
    if confirmation.get('observed'): note += '; operator: ' + confirmation['observed']
    return dict(family=summary.get('family'), method=summary.get('method'), state=state, answer=summary.get('answerTargeted'),
                app=summary.get('app'), phone=summary.get('phone'), source=summary.get('source'), date=summary.get('date'),
                trial=summary.get('trial'), summary=path, summarySha256=digest,
                beforeFrameSha256=summary.get('beforeFrameSha256'), afterFrameSha256=summary.get('afterFrameSha256'),
                outcome=result, commandsAnswered=summary.get('commandsAnswered'),
                declinedConfirmed=confirmation.get('declined') is True, confirmation=confirmation.get('observed', ''), note=note)


def promotion(summary_path, root):
    """The WINDOW_EVIDENCE entry for one completed trial, or the reasons it cannot be one."""
    raw = Path(summary_path).read_bytes()
    summary = json.loads(raw.decode('utf-8'))
    path = Path(summary_path).resolve().relative_to(Path(root).resolve()).as_posix()
    entry = window_entry(summary, path, sha(raw))
    problems = list(prompts.window_problems(entry))
    if summary.get('step') != 'trial' or summary.get('recordSource') != 'phone':
        problems.append('Only a phone trial can become evidence.')
    if summary.get('state') != 'completed' or summary.get('cleanup') != 'confirmed':
        problems.append('The trial did not finish with its lease released.')
    if summary.get('method') == 'keyboard_focus' and summary.get('activate') is not True:
        problems.append('A focus-only observation is not an answer.')
    return entry, problems


# -- command line --------------------------------------------------------------------------
def kernel_process(live, part):
    processes, ready = live/f'processes-{part}.json', live/f'receiver-ready-{part}.json'
    if not processes.is_file() or not ready.is_file():
        raise SystemExit(f'Part {part} has no started kernel; run Start-PromptWindow.ps1 -Part {part} first.')
    if (live/f'restoration-{part}.json').exists(): raise SystemExit(f'Part {part} has been stopped.')
    process = load(processes)['kernel']
    status = load(ready)
    status = status.get('data', status)
    if status.get('process', {}).get('pid') != process['pid']: raise SystemExit('The recorded kernel process does not match its readiness record.')
    return process['pid'], status['process']['started_utc']


def main(argv=None, *, kernel_factory=None, ocr=None, clock=time.time, monotonic=time.monotonic, pause=time.sleep):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest='step', required=True)
    for name in ('observe', 'trial', 'probe', 'confirm', 'promote'):
        command = sub.add_parser(name)
        command.add_argument('--preparation', type=Path, required=True)
        command.add_argument('--label', required=True)
        if name in ('observe', 'trial', 'probe'): command.add_argument('--part', choices=('A', 'B'), required=True)
        if name == 'trial':
            command.add_argument('--method', choices=TRIAL_METHODS, required=True)
            command.add_argument('--no-activate', action='store_true', help='keyboard_focus: find the focus, never send Space')
        if name == 'confirm':
            answer = command.add_mutually_exclusive_group(required=True)
            answer.add_argument('--declined', action='store_true')
            answer.add_argument('--not-declined', action='store_true')
            answer.add_argument('--unclear', action='store_true')
            command.add_argument('--observed', required=True, help='what the phone shows, in the operator\'s words')
    args = parser.parse_args(argv)
    if not LABEL.fullmatch(args.label): parser.error('Use a short lowercase label such as a3-long-press.')
    preparation = load(args.preparation)
    live = Path(args.preparation).resolve().parent
    root = Path(preparation['root'])
    summary_path = Path(preparation['windowRecord'])/f'{args.label}.json'
    folder = Path(preparation['runDirectory'])/'trials'/args.label
    if args.step in ('confirm', 'promote') and not summary_path.is_file(): raise SystemExit('No step has this label.')
    if args.step == 'confirm':
        summary = load(summary_path)
        if summary.get('confirmation') is not None: raise SystemExit('This step already has a confirmation; it is not rewritten.')
        summary['confirmation'] = dict(declined=True if args.declined else False if args.not_declined else None,
                                       observed=args.observed.strip(), utc=utc(clock))
        atomic_json(summary_path, summary)
        print(json.dumps(dict(label=args.label, confirmation=summary['confirmation'])))
        return 0
    if args.step == 'promote':
        entry, problems = promotion(summary_path, root)
        print(json.dumps(dict(label=args.label, promotable=not problems, problems=problems, entry=entry), indent=2))
        return 0 if not problems else 2
    if summary_path.exists() or folder.exists(): raise SystemExit('This label was already used; a step is never replayed.')
    probe = args.step == 'probe'
    if probe != (args.part == 'B'): raise SystemExit('The probe runs on part B; observe and trials run on part A.')
    process = None if kernel_factory else kernel_process(live, args.part)
    kernel = kernel_factory(probe) if kernel_factory else (ProbeKernel() if probe else TrialKernel())
    folder.mkdir(parents=True)
    store = ObservationStore(folder/'observations.sqlite3', ocr=ocr, clock=clock, monotonic=monotonic)
    step = ValidationStep(folder, kernel, store, preparation['kernelSha256'], preparation['expectedUid'], probe=probe,
                          kernel_process=process, monotonic=monotonic, pause=pause, clock=clock)
    if args.step == 'observe': record = step.observe()
    elif probe: record = step.probe_moves()
    else: record = step.trial(args.method, activate=not args.no_activate)
    summary = summarize(record, args.label, preparation['kernelSha256'])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(summary_path, summary)
    print(json.dumps(dict(label=args.label, step=summary['step'], method=summary['method'], state=summary['state'],
                          family=summary['family'], app=summary['app'], target=summary['answerTargeted'],
                          outcome=summary['outcome'], result=summary['result'], focus=summary['focusResult'],
                          cleanup=summary['cleanup'], error=summary['error'])))
    return 0 if record['state'] == 'completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
