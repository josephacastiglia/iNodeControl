"""Receiver-delivery evidence, never a claim about iOS's source capture time."""
import math
import re

MAX_AGE_MS = 1500


def counter(value):
    return type(value) is int and value >= 0


def delivery_evidence(before, headers, after, elapsed_ms):
    result = {'freshness': 'unavailable', 'pairedMetadata': False, 'ageUpperBoundMs': None,
              'deliveryAdvanced': False, 'phoneCaptureTimeKnown': False,
              'meaning': 'Age since kernel received this BMP, including this observation; not iOS capture time.'}
    def finish(state, reason):
        result.update(freshness=state, reason=reason)
        return result
    same_receiver = (before.get('deviceid') == after.get('deviceid') and bool(before.get('deviceid'))
                     and type(before.get('receiver_pid')) is int and before['receiver_pid'] > 0
                     and before['receiver_pid'] == after.get('receiver_pid')
                     and counter(before.get('receiver_restarts'))
                     and before['receiver_restarts'] == after.get('receiver_restarts')
                     and before.get('live') is True and after.get('live') is True)
    counts_valid = counter(before.get('frames')) and counter(after.get('frames'))
    result['deliveryAdvanced'] = bool(same_receiver and counts_valid and after['frames'] > before['frames'])
    if not same_receiver:
        return finish('invalid', 'Receiver identity, process, restart count or availability changed or is missing.')
    if not isinstance(elapsed_ms, (int, float)) or not math.isfinite(elapsed_ms) or elapsed_ms < 0:
        return finish('invalid', 'Observation elapsed time is invalid.')
    h = {k.lower(): v for k, v in headers.items()}
    required = ['x-imouse-frame-' + name for name in ('session', 'sequence', 'age-ms', 'delivery')]
    if not any(name in h for name in required):
        return finish('unavailable', 'Video delivery advanced, but screenshot age is not paired with its bytes.'
                      if result['deliveryAdvanced'] else 'Screenshot has no paired frame metadata; age is unknown.')
    if not all(name in h for name in required):
        return finish('invalid', 'Screenshot frame metadata is incomplete.')
    session, seq_text, age_text, state = [h[name] for name in required]
    if not isinstance(session, str) or not re.fullmatch(r'[0-9a-f]{32}', session):
        return finish('invalid', 'Frame session is malformed.')
    if not isinstance(seq_text, str) or not re.fullmatch(r'[1-9][0-9]{0,18}', seq_text):
        return finish('invalid', 'Frame sequence is malformed.')
    try: age = float(age_text)
    except (TypeError, ValueError): return finish('invalid', 'Frame age is malformed.')
    if not math.isfinite(age) or age < 0:
        return finish('invalid', 'Frame age is not finite and nonnegative.')
    sequence = int(seq_text)
    if (before.get('frame_session') != session or after.get('frame_session') != session
            or not counts_valid or not before['frames'] <= sequence <= after['frames']):
        return finish('invalid', 'Screenshot session or sequence does not fit the surrounding receiver observations.')
    result.update(pairedMetadata=True, session=session, sequence=sequence, reportedAgeMs=age,
                  observationElapsedMs=elapsed_ms, ageUpperBoundMs=age + elapsed_ms)
    if state != 'flowing' or age + elapsed_ms > MAX_AGE_MS:
        return finish('stale', 'Receiver-delivered frame is too old after download and recognition, or delivery is not flowing.')
    return finish('recent', 'Paired receiver-delivery metadata is recent. This does not prove a current iOS source capture.')


def capture_settled(value):
    """Unowned idle frame, or capture authenticated by the internal owned-run guard."""
    if value.get('inputIdle') is True:
        return not value.get('ownershipEvidence')
    proof = value.get('ownershipEvidence', {})
    return (value.get('inputSettled') is True and proof.get('source') == 'owned_capture_guard'
            and proof.get('authenticatedBeforeAndAfter') is True and bool(proof.get('runId'))
            and type(proof.get('generation')) is int and proof['generation'] == value.get('inputGeneration'))


def workflow_review(value):
    """Explain missing evidence. No result is an input/publish/message authorization."""
    blocked = []
    result = value.get('result', {})
    if value.get('state') != 'observed': blocked.append('No completed screen observation.')
    if value.get('expired'): blocked.append('Observation expired or belongs to an earlier observer session.')
    if value.get('freshness') != 'recent': blocked.append('Recent paired frame evidence is missing.')
    if value.get('stable') is not True: blocked.append('Receiver or input ownership changed during observation.')
    if not capture_settled(value): blocked.append('Phone input is active, paused, owned by another controller or its state is incomplete.')
    if result.get('screen') not in ('profile', 'account_menu', 'draft_details', 'draft_preview', 'draft_library'):
        blocked.append('Screen is interrupted, unknown or still being edited.')
    if result.get('expectedAppMatches') is not True: blocked.append('Expected app pattern is missing.')
    if result.get('accountStatus') != 'exact_text_match': blocked.append('Expected account is not visible as exact text.')
    if value.get('expected', {}).get('caption') and result.get('captionStatus') != 'exact_line_match':
        blocked.append('Expected caption has not been read exactly in its content area.')
    return {'status': 'blocked' if blocked else 'ready_for_review', 'blockers': blocked,
            'automaticInputAllowed': False, 'savedDraftVerified': False,
            'reason': 'Review evidence only; media identity and persisted draft state still need verification.'}
