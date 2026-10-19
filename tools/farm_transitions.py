"""Bounded read-only settling of supported Instagram draft screens.

No transport or action callback is accepted. A wait collects new evidence; it
never repeats a tap, changes its target, reuses expired OCR, or dismisses a dialog.
"""
import hashlib
import time

import numpy as np

from farm_carousel_inspection import InspectionStopped
from farm_frame_evidence import capture_settled
from farm_draft_media import media_comparison
from imouse_social_automation import LIVE_TEST_DEVICE_ID
from farm_screen_layout import (create_menu_controls, editor_controls, next_label,
                                picker_controls, picker_stability, pixels)

MAX_CAPTURES = 4
# Four live OCR/capture passes plus integrity checks can exceed six seconds.
# Only read-only settling gets this allowance; each frame must remain <1.5 s old.
WAIT_SECONDS = 8
POLL_SECONDS = .15
HOME_INDICATOR = (155, 1060, 345, 1075)
AUDIO_SUGGESTION = (123, 65, 377, 133)


def _difference(before, after, ignored):
    difference = np.abs(pixels(before, exact=True).astype(float)-pixels(after, exact=True).astype(float))/255
    mask = np.ones((1080, 500), dtype=bool)
    mask[:65] = False
    for left, top, right, bottom in ignored: mask[top:bottom, left:right] = False
    changed = difference.max(axis=2) > 35/255
    return dict(mean=float(difference[mask].mean()), changed=float(changed[mask].mean()))


def _small(change):
    return change['mean'] <= .002 and change['changed'] <= .005


def screen_ready(stage, frame, text, assets=(), index=None, require_next=False):
    if stage == 'create':
        ready = create_menu_controls(frame, text)
    elif stage == 'picker':
        ready = picker_controls(frame, text)
    elif stage == 'editor':
        ready = editor_controls(frame, text)
        if ready:
            comparison = media_comparison(frame, assets, 'carousel_editor') if assets else {}
            position = comparison.get('position', {})
            if (comparison.get('status') != 'visual_match' or comparison.get('matchedIndex') != index
                    or position.get('index') != index or position.get('count') != len(assets)):
                raise InspectionStopped('Full-size slide, order or carousel count changed during settling.')
            if require_next and not next_label(frame, text):
                raise InspectionStopped('The exact Next label is unresolved; no action sent.')
            ready = {**ready, 'media': comparison}
    else:
        raise ValueError('Unsupported transition stage.')
    if not ready:
        raise InspectionStopped('Expected '+stage+' controls are missing or a dialog interrupted settling.')
    return ready


def compare_frames(stage, first, first_text, second, second_text):
    """A known transient may request another capture, never a ready decision.

    Final picker readiness uses the unchanged full protected-grid comparison.
    Final editor readiness compares the whole page except its status bar; the
    suggestion region is NOT excluded from a successful comparison.
    """
    if stage == 'picker':
        result = picker_stability(first, first_text, second, second_text)
        if result['controlsStable']: return {**result, 'state': 'ready'}
        # Retain all the picker's existing thresholds, including its block and
        # per-control checks. Replace only the indicator for this wait diagnosis.
        from PIL import Image
        import io
        a = Image.fromarray(pixels(first, exact=True))
        b = Image.fromarray(pixels(second, exact=True))
        b.paste(a.crop(HOME_INDICATOR), HOME_INDICATOR)
        buffer = io.BytesIO(); b.save(buffer, 'PNG')
        outside = picker_stability(first, first_text, buffer.getvalue(), second_text)
        if outside['controlsStable']:
            return {**result, 'state': 'wait', 'reason': 'Home indicator is fading; recapture without input.'}
        raise InspectionStopped('Picker controls or library changed outside the indicator; no action sent.')
    if stage == 'editor':
        a, b = pixels(first, exact=True).astype(float), pixels(second, exact=True).astype(float)
        changed = np.abs(a-b).max(axis=2) > 35
        # Tiny local changes must not disappear in a whole-screen average.
        for left, top, right, bottom in ((15,70,70,130),(20,880,480,945),(396,980,478,1032)):
            if int(changed[top:bottom, left:right].sum()) >= 4:
                raise InspectionStopped('Editor action controls changed; no action sent.')
    change = _difference(first, second, ())
    if _small(change): return dict(state='ready', **change, automaticInputAllowed=False)
    if stage == 'editor' and _small(_difference(first, second, (AUDIO_SUGGESTION,))):
        return dict(state='wait', **change, reason='Editor suggestion header is changing; recapture without input.',
                    automaticInputAllowed=False)
    raise InspectionStopped('Protected screen content changed during settling; no action sent.')


def _validate(value, frame, platform='instagram'):
    if (value.get('freshness') != 'recent' or value.get('expired') or value.get('state') != 'observed'
            or value.get('stable') is not True or value.get('inputSettled') is not True
            or not capture_settled(value) or value.get('frameEvidence', {}).get('pairedMetadata') is not True):
        raise InspectionStopped('Settling requires a fresh authenticated frame at every capture.')
    if (value.get('expected', {}).get('device_id') != 'C24C'
            or value.get('expected', {}).get('platform') != platform
            or value.get('resolvedDeviceId') not in ('C24C', LIVE_TEST_DEVICE_ID)
            or value.get('reviewFrameSha256') != hashlib.sha256(frame).hexdigest()
            or not value.get('frameSha256') or value.get('text', {}).get('frameSha256') != value['frameSha256']):
        raise InspectionStopped('Settling frame, OCR or target identity changed.')
    context = (value.get('observerSession'), value.get('resolvedDeviceId'), value.get('receiverPid'),
               value.get('inputGeneration'), value['frameEvidence'].get('session'),
               value.get('ownershipEvidence', {}).get('runId'), value.get('source'),
               value['expected'].get('account'), value['expected'].get('caption'))
    if any(x is None for x in context) or not context[5] or not context[7]:
        raise InspectionStopped('Settling has incomplete ownership or account context.')
    sequence = value['frameEvidence'].get('sequence')
    if type(sequence) is not int or sequence < 0:
        raise InspectionStopped('Settling frame sequence is invalid.')
    return context, sequence


def wait_for_transition(stage, capture, check, current, *, assets=(), index=None,
                        require_next=False, journal=lambda event: None,
                        monotonic=time.monotonic, pause=time.sleep, ready=None, compare=None, platform='instagram'):
    """Return the latest of two fresh stable observations, or stop within bounds.

    capture retains evidence through the owning workflow. check authenticates its
    lease and cancellation. current re-ages/revalidates the final immutable record.
    All intervening captures must be recognized and share one context; a later
    matching frame cannot erase a dialog, wrong slide or ownership discontinuity.
    Another screen family supplies both its own ready and compare checks; the
    capture, context and final-revalidation rules here stay the same.
    """
    if (ready is None) != (compare is None): raise ValueError('Supply both screen checks or neither.')
    if ready is None and stage not in ('create', 'picker', 'editor'): raise ValueError('Unsupported transition stage.')
    if ready is None:
        ready = lambda frame, text: screen_ready(stage, frame, text, assets, index, require_next)
        compare = lambda first, first_text, second, second_text: compare_frames(stage, first, first_text, second, second_text)
    started = monotonic()
    deadline = started+WAIT_SECONDS
    previous = None
    try:
        for attempt in range(1, MAX_CAPTURES+1):
            check()
            if monotonic() >= deadline: raise InspectionStopped('Transition settling timed out without input.')
            value, frame = capture()
            check()
            if monotonic() >= deadline: raise InspectionStopped('Transition capture exceeded its settling budget.')
            context, sequence = _validate(value, frame, platform)
            ready(frame, value['text'])
            if previous is None:
                decision = dict(state='wait', reason='A second independently fresh observation is required.')
            else:
                old, old_frame, old_context, old_sequence = previous
                if old_context != context or sequence <= old_sequence or old['id'] == value['id']:
                    raise InspectionStopped('Settling changed context or reused a frame; no action sent.')
                decision = compare(old_frame, old['text'], frame, value['text'])
                decision.update(beforeObservationId=old['id'], afterObservationId=value['id'])
            journal(dict(stage=stage, attempt=attempt, observationId=value['id'],
                         elapsedSeconds=round(monotonic()-started,3), **decision))
            if decision['state'] == 'ready':
                check()
                final, retained = current(value['id'])
                final_context = _validate(final, retained, platform)
                if monotonic() >= deadline:
                    raise InspectionStopped('Transition verification exceeded its settling budget.')
                if (final_context != (context, sequence)
                        or final.get('evidenceRecordSha256') != value.get('evidenceRecordSha256')
                        or not final.get('evidenceRecordSha256') or retained != frame):
                    raise InspectionStopped('Settled evidence expired or changed before the decision.')
                return final, frame, decision
            previous = value, frame, context, sequence
            if attempt < MAX_CAPTURES:
                check(); pause(POLL_SECONDS)
        raise InspectionStopped('Transition did not settle within four captures; no action sent.')
    except Exception as error:
        journal(dict(stage=stage, state='held', automaticInputAllowed=False,
                     elapsedSeconds=round(monotonic()-started,3), reason=str(error)))
        raise
