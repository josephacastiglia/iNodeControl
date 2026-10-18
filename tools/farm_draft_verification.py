"""Immutable, read-only carousel evidence reviews. No phone or network dependency.

Visual comparisons are not byte identity or proof that Instagram saved a new draft.
Account bracketing is not uninterrupted account continuity. Never authorizes input.
"""
from contextlib import contextmanager
import hashlib
import io
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
import zipfile

import numpy as np
from PIL import Image
from farm_drafts import identifier, DraftConflict
from farm_observations import classify, expectations, image_size

ROLES = ('account_before', 'prepared', 'library', 'reopened', 'account_after')
MAX_EVIDENCE_BYTES = 32 * 1024 * 1024


def request_spec(request):
    if set(request) - {'id', 'draft_id', 'revision', 'device_id', 'platform', 'account', 'observations'}:
        raise ValueError('Verification accepts saved observation IDs only, not supplied verdicts, images or paths.')
    desired = expectations(request)
    if desired['platform'] != 'instagram': raise ValueError('This evidence review supports Instagram carousels; other formats remain unverified.')
    if type(request.get('revision')) is not int or request['revision'] < 1: raise ValueError('Choose a saved draft revision.')
    roles = request.get('observations', {})
    if not isinstance(roles, dict) or set(roles) - set(ROLES): raise ValueError('Unknown observation stage.')
    normalized = {}
    for role in ROLES:
        ids = roles.get(role, [])
        maximum = 10 if role in ('prepared', 'reopened') else 1
        if not isinstance(ids, list) or len(ids) > maximum: raise ValueError('Too many observations for ' + role)
        normalized[role] = [identifier(value) for value in ids]
    flat = sum(normalized.values(), [])
    if len(set(flat)) != len(flat): raise ValueError('Each stage needs distinct observations; one capture cannot prove a return to the draft.')
    return dict(id=identifier(request.get('id')), draft_id=identifier(request.get('draft_id')),
                revision=request['revision'], **desired, observations=normalized)


def caption_comparison(text, expected):
    """Exact visible lines in the supported carousel caption area; no fuzzy repair."""
    rows = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if words:
            y = min(w['y'] for w in words) / text['height']
            if .40 < y < .52: rows.append((y, min(w['x'] for w in words), line['text']))
    lines = [row[2] for row in sorted(rows)]
    visible = '\n'.join(lines)
    exact = visible == expected.replace('\r\n', '\n') if expected else lines == ['Add a caption...']
    return dict(status='exact_visible_lines' if exact else 'needs_review', visibleText=visible,
                reason='Only the supported visible caption area was compared; hidden or truncated text cannot pass.')


def media_comparison(frame, assets, layout):
    if layout not in ('carousel_details', 'draft_library_candidate'): return dict(status='unsupported_layout', matchedIndex=None)
    width, height = image_size(frame)
    if abs(width / height - 500 / 1080) > .01:
        return dict(status='unsupported_geometry', matchedIndex=None)
    with Image.open(io.BytesIO(frame)) as image:
        # Only the first fully visible 4:5 preview in the validated English layout.
        bounds = (20, 126, 260, 426) if layout == 'carousel_details' else (0, 112, 124, 236)
        crop = image.convert('RGB').crop(tuple(round(v * (width / 500 if i % 2 == 0 else height / 1080)) for i, v in enumerate(bounds)))
    def pixels(image):
        image = image.convert('RGB').resize((100, 125), Image.Resampling.LANCZOS)
        return np.asarray(image, dtype=np.float32)[5:-5, 4:-4] / 255
    observed = pixels(crop)
    # A flat patch cannot establish image identity even when its colour matches.
    if float(np.mean(np.std(observed, axis=(0, 1)))) < .04:
        return dict(status='insufficient_detail', matchedIndex=None)
    scores = []
    for number, raw in enumerate(assets):
        with Image.open(io.BytesIO(raw)) as source:
            if layout == 'draft_library_candidate':
                # Candidate square centre-crop layout; real thumbnails that differ remain unresolved.
                side = min(source.size); x = (source.width - side) // 2; y = (source.height - side) // 2
                source = source.crop((x, y, x + side, y + side))
            difference = np.abs(observed - pixels(source))
        blocks = [float(block.mean()) for band in np.array_split(difference, 5) for block in np.array_split(band, 4, axis=1)]
        scores.append(dict(index=number + 1, meanError=float(difference.mean()), worstBlock=max(blocks)))
    ordered = sorted(scores, key=lambda s: s['meanError'])
    best = ordered[0]
    margin = ordered[1]['meanError'] - best['meanError']
    accepted = best['meanError'] <= .045 and best['worstBlock'] <= .12 and margin >= .025
    return dict(status='visual_match' if accepted else 'ambiguous_or_different', matchedIndex=best['index'] if accepted else None,
                scores=scores, margin=margin, byteIdentityVerified=False)


def assess(spec, draft, assets, captures):
    expected = dict(device_id='C24C', platform='instagram', account=spec['account'], caption=draft['caption'])
    blockers, details, ordered = [], {}, []
    for role in ROLES:
        details[role] = []
        if not spec['observations'][role]: blockers.append('Missing ' + role.replace('_', ' ') + ' evidence.')
        for observation_id in spec['observations'][role]:
            if observation_id not in captures:
                blockers.append('Missing or damaged saved observation for ' + role + '.'); continue
            value, frame = captures[observation_id]
            ordered.append(value)
            if value.get('state') != 'observed' or value.get('expected', {}).get('device_id') != 'C24C':
                blockers.append('Observation is incomplete or belongs to another device.'); continue
            if value.get('expected', {}).get('platform') != 'instagram' or value.get('expected', {}).get('account', '').casefold() != spec['account'].casefold():
                blockers.append('Observation expectations do not match this account and platform.')
            if value.get('freshness') != 'recent' or value.get('frameEvidence', {}).get('pairedMetadata') is not True:
                blockers.append('An observation had no recent paired frame evidence at capture.')
            if value.get('stable') is not True or value.get('inputIdle') is not True:
                blockers.append('An observation overlapped changed or active input/receiver state.')
            result = classify(value['text'], expected)
            row = dict(id=observation_id, screen=result['screen'], account=result['accountStatus'],
                       frameSha256=value['reviewFrameSha256'])
            if role in ('account_before', 'account_after'):
                if result['screen'] not in ('profile', 'account_menu') or result['accountStatus'] != 'exact_text_match':
                    blockers.append('Expected account was not read exactly at ' + role.replace('_', ' ') + '.')
            elif role == 'library':
                # Match a thumbnail in a sparse library without changing the global unknown-app classification.
                titles = [line['text'].casefold() for line in value['text'].get('lines', []) if line.get('words')
                          and .04 < min(w['y'] for w in line['words']) / value['text']['height'] < .12]
                candidate = result['screen'] == 'unknown' and 'drafts' in titles and 'select' in titles
                row['media'] = media_comparison(frame, assets, 'draft_library_candidate' if candidate else None)
                row['appIndependentlyIdentified'] = False
                if row['media']['matchedIndex'] != 1:
                    blockers.append('Library does not show a matching first-slide thumbnail in the supported layout.')
            else:
                row['media'] = media_comparison(frame, assets, result.get('layout'))
                row['caption'] = (caption_comparison(value['text'], draft['caption']) if result.get('layout') == 'carousel_details'
                                  else dict(status='unsupported_layout'))
            details[role].append(row)
    times = [(v.get('requestedAt'), v.get('completedAt')) for v in ordered]
    valid_times = all(all(type(t) in (int, float) and math.isfinite(t) for t in pair) and pair[0] <= pair[1] for pair in times)
    chronological = bool(times) and valid_times and all(a[1] < b[0] for a, b in zip(times, times[1:]))
    if not chronological or times[-1][1] - times[0][0] > 900:
        blockers.append('Evidence must be chronological, nonoverlapping and within one 15-minute review run.')
    contexts = [(v.get('observerSession'), v.get('resolvedDeviceId'), v.get('receiverPid'), v.get('inputGeneration'),
                 v.get('frameEvidence', {}).get('session')) for v in ordered]
    if not contexts or any(any(item is None for item in c) or c != contexts[0] for c in contexts):
        blockers.append('Observer, device, receiver, input generation or stream identity changed or is missing.')
    sequences = [v.get('frameEvidence', {}).get('sequence') for v in ordered]
    if not sequences or any(type(s) is not int for s in sequences) or any(a >= b for a, b in zip(sequences, sequences[1:])):
        blockers.append('Distinct, advancing frame sequences are required for the review stages.')
    for role in ('prepared', 'reopened'):
        rows = details[role]
        indices = [r.get('media', {}).get('matchedIndex') for r in rows]
        if indices != list(range(1, len(assets) + 1)):
            blockers.append(role.title() + ' media does not show every expected slide once in the requested sequence.')
        if not rows or any(r.get('caption', {}).get('status') != 'exact_visible_lines' for r in rows):
            blockers.append(role.title() + ' full visible caption does not match exactly.')
    source = 'phone' if ordered and all(v.get('source') == 'phone' for v in ordered) else 'simulation_or_mixed'
    return dict(status='incomplete' if blockers else 'consistent_visual_evidence', source=source,
                blockers=list(dict.fromkeys(blockers)), stages=details, automaticInputAllowed=False,
                savedDraftVerified=False, accountContinuityProven=False,
                limits=['Account observations bracket the run; actions between frames are not witnessed.',
                        'Similar pixels are not byte identity, and observation sequence does not prove carousel navigation order.',
                        'A library and reopened content can be consistent with a draft; saving a new draft is not independently proven.',
                        'This is historical evidence, never current readiness or permission to publish, message or send input.'])


class DraftVerifications:
    def __init__(self, path, observations, drafts):
        self.path, self.observations, self.drafts = Path(path), observations, drafts
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, document TEXT NOT NULL, evidence BLOB NOT NULL, package BLOB NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db: yield db
        finally: db.close()

    def get(self, review_id):
        with self.connect() as db:
            row = db.execute('SELECT document,evidence,package FROM reviews WHERE id=?', (identifier(review_id),)).fetchone()
        if not row: raise KeyError('Review not found. No phone capture or action was replayed.')
        value = json.loads(row[0])
        if hashlib.sha256(row[1]).hexdigest() != value['evidenceSha256'] or hashlib.sha256(row[2]).hexdigest() != value['packageSha256']:
            raise ValueError('Saved review evidence is damaged; no verdict can be trusted.')
        try: value['draftChangedSinceReview'] = self.drafts.get(value['draft']['id'])['revision'] != value['draft']['revision']
        except KeyError: value['draftChangedSinceReview'] = True
        return value

    def list(self, draft_id):
        draft_id = identifier(draft_id)
        with self.connect() as db: records = [json.loads(r[0]) for r in db.execute('SELECT document FROM reviews ORDER BY rowid DESC')]
        return [dict(id=r['id'], createdAt=r['createdAt'], status=r['assessment']['status'], revision=r['draft']['revision'])
                for r in records if r['draft']['id'] == draft_id][:50]

    def frame(self, review_id, observation_id):
        review_id, observation_id = identifier(review_id), identifier(observation_id)
        record = self.get(review_id)  # Verifies archive integrity before serving a retained image.
        if observation_id not in sum(record['request']['observations'].values(), []):
            raise KeyError('This observation does not belong to the saved review.')
        with self.connect() as db: evidence = db.execute('SELECT evidence FROM reviews WHERE id=?', (review_id,)).fetchone()[0]
        with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
            try: return archive.read(observation_id + '.png')
            except KeyError as error: raise KeyError('Image was unavailable when this review was recorded.') from error

    def create(self, request):
        spec = request_spec(request)
        fingerprint = json.dumps(spec, sort_keys=True)
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT fingerprint FROM reviews WHERE id=?', (spec['id'],)).fetchone()
            if old:
                if old[0] != fingerprint: raise DraftConflict('Review ID already belongs to different evidence.')
                return self.get(spec['id'])
            package = self.drafts.export(spec['draft_id'], spec['revision'])
            if len(package) > MAX_EVIDENCE_BYTES: raise ValueError('Source package exceeds the 32 MiB evidence-review limit.')
            with zipfile.ZipFile(io.BytesIO(package)) as files:
                draft = json.loads(files.read('manifest.json'))
                assets = [files.read(asset['file']) for asset in draft['assets']]
                if any(hashlib.sha256(raw).hexdigest() != info['sha256'] for raw, info in zip(assets, draft['assets'])):
                    raise ValueError('Exported media integrity check failed.')
            captures, missing, size = {}, [], len(package)
            for role in ROLES:
                for observation_id in spec['observations'][role]:
                    try: captures[observation_id] = self.observations.evidence(observation_id)
                    except (KeyError, ValueError) as error: missing.append(str(error)); continue
                    value, frame = captures[observation_id]
                    size += len(frame) + len(json.dumps(value, ensure_ascii=False).encode('utf-8'))
                    if size > MAX_EVIDENCE_BYTES: raise ValueError('Selected review evidence exceeds 32 MiB; no partial review stored.')
            assessment = assess(spec, draft, assets, captures)
            assessment['blockers'].extend(dict.fromkeys(missing))
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for observation_id, (value, frame) in captures.items():
                    archive.writestr(observation_id + '.json', json.dumps(value, ensure_ascii=False))
                    archive.writestr(observation_id + '.png', frame)
            document = dict(id=spec['id'], createdAt=time.time(), request=spec,
                            draft={k: draft[k] for k in ('id', 'title', 'revision', 'caption', 'slideIds')},
                            packageSha256=hashlib.sha256(package).hexdigest(), evidenceSha256=hashlib.sha256(buffer.getvalue()).hexdigest(),
                            assessment=assessment)
            db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)', (spec['id'], fingerprint, json.dumps(document), buffer.getvalue(), package))
        return self.get(spec['id'])
