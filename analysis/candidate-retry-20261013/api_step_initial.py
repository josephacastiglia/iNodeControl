"""One reviewed C24C smoke step; reuse the existing runner's lease/API helper.

This is a bounded smoke record, not a Gate 4 accuracy run or console UI test.
Each invocation checks the exact candidate, saves frames and releases ownership.
"""
import json
from pathlib import Path
import sys
import time
from datetime import datetime, timezone

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
from gate4_1000_tap_suite import Kernel, command_ok, grid

ID = '86:1D:4A:04:2F:F6'
HASH = 'e0f00fa86c217e2c00913e22adc04c7c9c5477e670078b7a94f19e9d5af92e16'
STEPS = {
    'move-upper': [('/mouse/reset', {}), ('/mouse/move', {'x': 40, 'y': 100})],
    'move-lower': [('/mouse/move', {'x': 460, 'y': 980})],
    'calculator': [('/mouse/click', {'x': 193, 'y': 754})],
    'home-gesture': [('/mouse/swipe', {'x1': 250, 'y1': 1070, 'x2': 250, 'y2': 550, 'duration': 350})],
    'swipe-left': [('/mouse/swipe', {'x1': 430, 'y1': 855, 'x2': 70, 'y2': 855, 'duration': 350})],
    'swipe-right': [('/mouse/swipe', {'x1': 70, 'y1': 855, 'x2': 430, 'y2': 855, 'duration': 350})],
    'stop-held': [('/mouse/move', {'x': 250, 'y': 845}), ('/mouse/down', {'button': 1})],
}
name = sys.argv[1]
assert name in STEPS
out = record / name
out.mkdir(exist_ok=False)
k = Kernel('http://127.0.0.1:9913/api')
result = {'step': name, 'started_utc': datetime.now(timezone.utc).isoformat(), 'api_only': True,
          'C241_addressed': False, 'commands': [], 'completed': False}
def save():
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
def frame(label):
    status = k.status()
    assert status['live'] and status['frame_delivery'] == 'flowing' and status['frame_age_ms'] < 2000, 'Video is not current'
    data = k.shot(ID)
    assert grid(data)[:2] == (500, 1080)
    (out / (label + '.bmp')).write_bytes(data)
    result[label + '_video'] = status
def post(fun, data):
    begin = time.perf_counter()
    reply = k.post(fun, data)
    result['commands'].append({'fun': fun, 'utc': datetime.now(timezone.utc).isoformat(),
        'rtt_ms': round((time.perf_counter() - begin) * 1000, 2), 'response': reply})
    save()
    return reply

tokens = {}
try:
    status = k.status()
    assert status['build_identity']['sha256'] == HASH and status['allowed'] == ['C24C']
    assert len(status['receivers']) == 1 and status['receivers'][0]['deviceid'] == ID
    states = k.input_status()
    assert set(states) == {ID}
    assert not any(states[ID][key] for key in ('owned', 'active', 'stopped', 'releasing', 'release_failed'))
    result['before_input'] = states
    frame('before')
    tokens = k.acquire([ID], lease_ms=30000)
    for index, (fun, data) in enumerate(STEPS[name]):
        assert command_ok(post(fun, {'id': ID, 'token': tokens[ID], **data}))
        if name != 'stop-held':
            time.sleep(0.8)
            frame(f'after-{index}')
    if name == 'stop-held':
        # A brief hold in blank Home-screen space, then Stop, not a long press.
        stale = tokens[ID]
        reply = post('/input/stop', {'id': ID})
        assert command_ok(reply)
        tokens = {}
        stopped = k.input_status()[ID]
        assert stopped['stopped'] and not stopped['owned'] and not stopped['active'] and not stopped['release_failed']
        result['stopped_input'] = stopped
        refused = post('/mouse/move', {'id': ID, 'token': stale, 'x': 251, 'y': 845})
        assert refused['code'] == 409
        assert command_ok(post('/input/resume', {'id': ID}))
        tokens = k.acquire([ID], lease_ms=30000)
        assert command_ok(post('/mouse/move', {'id': ID, 'token': tokens[ID], 'x': 250, 'y': 840}))
        time.sleep(0.8)
        frame('after-resume')
    result['completed'] = True
except Exception as error:
    result['error'] = str(error)
    raise
finally:
    try:
        if tokens:
            reply = post('/input/release', {'id': ID, 'tokens': tokens})
            assert command_ok(reply), 'Release unconfirmed; inspect the phone and input status'
        result['final_input'] = k.input_status()
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    finally:
        save()
print(json.dumps({'step': name, 'completed': result['completed'], 'commands': result['commands'], 'final_input': result['final_input']}, indent=2))
