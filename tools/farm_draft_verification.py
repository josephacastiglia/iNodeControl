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

from farm_drafts import identifier, DraftConflict
from farm_observations import classify, expectations
from farm_draft_media import media_comparison

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
        maximum = 11 if role in ('prepared', 'reopened') else 1
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


def library_candidate(text, result):
    titles = [line['text'].casefold() for line in text.get('lines', []) if line.get('words')
              and .04 < min(w['y'] for w in line['words']) / text['height'] < .12]
    return result['screen'] == 'unknown' and 'drafts' in titles and 'select' in titles


def account_history(spec, timeline, expected):
    """Audit every stored observation, including ones the caller did not select."""
    blockers, rows = [], []
    if not timeline:
        return dict(status='unavailable', blockers=['Account observation interval is unavailable.'], observations=[], maxGapSeconds=None)
    ids = [v['id'] for v, _ in timeline]
    if any(i not in ids for i in sum(spec['observations'].values(), [])):
        blockers.append('Selected evidence lies outside the account observation interval.')
    previous = None; max_gap = 0; context = None
    for value, frame in timeline:
        row = dict(id=value['id'], screen='unavailable', account='unavailable')
        rows.append(row)
        if frame is None or value.get('state') != 'observed':
            blockers.append('Account history contains a failed, pruned or damaged observation.'); continue
        if (value.get('expected', {}).get('platform') != expected['platform']
                or value.get('expected', {}).get('account', '').casefold() != expected['account'].casefold()):
            blockers.append('Account history includes a different expected app or account.')
        result = classify(value['text'], expected)
        row.update(screen=result['screen'], account=result['accountStatus'])
        if result['screen'] in ('profile', 'account_menu') and result['accountStatus'] != 'exact_text_match':
            blockers.append('Account history contains a different or unreadable account.')
        allowed = result['appPattern'] == 'instagram' and result['screen'] in ('profile', 'draft_details', 'draft_editor')
        if not allowed and not library_candidate(value['text'], result):
            blockers.append('Account history crosses an interruption, another app or an unrecognized screen.')
        if value.get('freshness') != 'recent' or value.get('stable') is not True or value.get('inputIdle') is not True:
            blockers.append('Account history has stale, unavailable or unsettled input evidence.')
        evidence=value.get('frameEvidence', {})
        current=(value.get('observerSession'), value.get('resolvedDeviceId'), value.get('receiverPid'),
                 value.get('inputGeneration'), evidence.get('session'), value.get('source'))
        if context is None: context=current
        if current != context or any(item is None for item in current) or evidence.get('pairedMetadata') is not True:
            blockers.append('Account history changed observer, device, ownership generation or stream context.')
        start,end,seq=value.get('requestedAt'),value.get('completedAt'),evidence.get('sequence')
        valid=all(type(t) in (int,float) and math.isfinite(t) for t in (start,end)) and start<=end and type(seq) is int
        if not valid: blockers.append('Account history has invalid timing or frame sequence.'); continue
        if previous:
            gap=start-previous[0]; max_gap=max(max_gap,gap)
            if gap<=0 or seq<=previous[1]: blockers.append('Account history is out of order or repeats a frame sequence.')
            if gap>15: blockers.append('Account history has an unobserved interval longer than 15 seconds.')
        previous=(end,seq)
    return dict(status='incomplete' if blockers else 'consistent_sampled_history', blockers=list(dict.fromkeys(blockers)),
                observations=rows, maxGapSeconds=max_gap, continuousRecording=False,
                meaning='Checks every stored C24C observation, not phone activity between captures.')


def assess(spec, draft, assets, captures, timeline=None):
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
                candidate = library_candidate(value['text'], result)
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
    coverage = {}
    for role in ('prepared', 'reopened'):
        rows = details[role]
        editors = [r for r in rows if 'position' in r.get('media', {})]
        indices = [r['media'].get('matchedIndex') for r in editors]
        full = (indices == list(range(1, len(assets)+1)) and all(
            r['media']['position'] == dict(status='visible_position', index=n, count=len(assets))
            for n,r in enumerate(editors,1)))
        captions = [r['caption']['status'] for r in rows if r.get('caption', {}).get('status') != 'unsupported_layout']
        caption_ok = bool(captions) and all(c == 'exact_visible_lines' for c in captions)
        # Details previews must also match, even though only editor dots establish count/order.
        other_ok = all(r.get('media', {}).get('matchedIndex') is not None for r in rows)
        coverage[role] = dict(expectedCount=len(assets), observedIndices=indices,
                              fullSizeAndPositionMatch=full, captionMatches=caption_ok)
        if not full or not other_ok:
            blockers.append(role.title() + ' needs every full-size slide in order with its matching position and total count.')
        if not caption_ok: blockers.append(role.title() + ' full visible caption does not match exactly.')
    continuity = account_history(spec, timeline, expected)
    blockers.extend(continuity['blockers'])
    source = 'phone' if ordered and all(v.get('source') == 'phone' for v in ordered) else 'simulation_or_mixed'
    return dict(status='incomplete' if blockers else 'consistent_visual_evidence', source=source,
                blockers=list(dict.fromkeys(blockers)), stages=details, slideCoverage=coverage, accountHistory=continuity, automaticInputAllowed=False,
                savedDraftVerified=False, accountContinuityProven=False,
                limits=['All stored observations in the interval are checked; actions between captures are not witnessed.',
                        'Full-size pixels and page dots check visible slide order/count, not media byte identity.',
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
        if observation_id not in sum(record['request']['observations'].values(), []) + record.get('intervalObservationIds', []):
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
            timeline, timeline_error = None, None
            if spec['observations']['account_before'] and spec['observations']['account_after']:
                try:
                    timeline = self.observations.interval(spec['observations']['account_before'][0], spec['observations']['account_after'][0])
                except ValueError as error: timeline_error = str(error)
            for value, frame in timeline or []:
                if value['id'] not in captures:
                    size += len(frame or b'') + len(json.dumps(value, ensure_ascii=False).encode('utf-8'))
                    if size > MAX_EVIDENCE_BYTES: raise ValueError('Selected review evidence exceeds 32 MiB; no partial review stored.')
            assessment = assess(spec, draft, assets, captures, timeline)
            if timeline_error: assessment['blockers'].append(timeline_error)
            assessment['blockers'].extend(dict.fromkeys(missing))
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for observation_id, (value, frame) in captures.items():
                    archive.writestr(observation_id + '.json', json.dumps(value, ensure_ascii=False))
                    archive.writestr(observation_id + '.png', frame)
                for value, frame in timeline or []:
                    if value['id'] in captures: continue
                    archive.writestr(value['id'] + '.json', json.dumps(value, ensure_ascii=False))
                    if frame is not None: archive.writestr(value['id'] + '.png', frame)
            document = dict(id=spec['id'], createdAt=time.time(), request=spec, verificationVersion=2,
                            intervalObservationIds=[v['id'] for v, _ in timeline or []],
                            draft={k: draft[k] for k in ('id', 'title', 'revision', 'caption', 'slideIds')},
                            packageSha256=hashlib.sha256(package).hexdigest(), evidenceSha256=hashlib.sha256(buffer.getvalue()).hexdigest(),
                            assessment=assessment)
            db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)', (spec['id'], fingerprint, json.dumps(document), buffer.getvalue(), package))
        return self.get(spec['id'])
