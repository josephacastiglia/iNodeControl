"""Offline tests for scale_gate.py: safety guards and frame analysis. No kernel, no phone.

  python -m pytest analysis/scale-gate-20261104/test_scale_gate.py -q
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scale_gate as g  # noqa: E402

BOARDS = {'B1': {'board': 'EE14', 'receiver': 'iMouse2-B1'}, 'B2': {'board': 'CA05', 'receiver': 'iMouse2-B2'},
          'B5': {'board': 'CD51', 'receiver': 'iMouse2-B5'}}
DEVICES = [{'receiver_name': 'iMouse2-B1', 'pid': 'EE14', 'deviceid': 'dev-b1'},
           {'receiver_name': 'iMouse2-B2', 'pid': 'CA05', 'deviceid': 'dev-b2'},
           {'receiver_name': 'iMouse2-B5', 'pid': 'CD51', 'deviceid': 'dev-b5'}]


class Fake:
    def __init__(self):
        self.sent = []

    def __call__(self, method, path, body, timeout):
        self.sent.append(body)
        fun = body['fun']
        if fun == '/input/acquire':
            ids = body['data']['id'].split(',')
            data = {'code': 0, 'leases': [{'id': i, 'token': 't-' + i} for i in ids]}
        else:
            data = {'code': 0, 'results': [{'id': i, 'code': 0} for i in body['data'].get('id', '').split(',') if i]}
        return json.dumps({'data': data}).encode(), {}, 200


def kernel(slots=('B1', 'B2')):
    fake = Fake()
    return g.Kernel(list(slots), transport=fake, devices=DEVICES, board_map=BOARDS), fake


def test_never_slots_refused():
    for slot in ('B5', 'B3', 'B7', 'B10', 'B17', 'A17'):
        with pytest.raises(g.Refused):
            g.Kernel([slot], transport=Fake(), devices=DEVICES, board_map=BOARDS)


def test_binding_mismatch_refused():
    devices = [dict(DEVICES[0], pid='F605'), DEVICES[1]]
    with pytest.raises(g.Refused):
        g.Kernel(['B1'], transport=Fake(), devices=devices, board_map=BOARDS)


@pytest.mark.parametrize('fun,data', [
    ('/mouse/click', {'x': 250, 'y': 540}),
    ('/mouse/swipe', {'direction': 'left'}),
    ('/mouse/down', {}),
    ('/mouse/up', {}),
])
def test_launching_input_refused(fun, data):
    k, fake = kernel()
    k.acquire(['B1'])
    with pytest.raises(g.Refused):
        k.send(fun, ['B1'], **data)
    assert all(b['fun'] == '/input/acquire' for b in fake.sent)


def test_only_home_key_and_spacing():
    k, fake = kernel()
    k.acquire(['B1', 'B2'])
    with pytest.raises(g.Refused):
        k.send('/key/sendkey', ['B1'], fn_key='ControlBar')
    with pytest.raises(g.Refused):
        k.send('/key/sendkey', ['B1'], key='a')
    k.send('/key/sendkey', ['B1', 'B2'], fn_key='Home')
    with pytest.raises(g.Refused):
        k.send('/key/sendkey', ['B2'], fn_key='Home')   # within 3 s: never a double press
    assert sum(1 for b in fake.sent if b['fun'] == '/key/sendkey') == 1


def test_foreign_target_refused():
    k, fake = kernel()
    with pytest.raises(g.Refused):
        k.post('/mouse/move', {'id': 'dev-b5', 'token': 'x', 'x': 1, 'y': 1})
    with pytest.raises(g.Refused):
        k.post('/mouse/move', {'id': 'dev-b1,dev-b5', 'tokens': {}, 'x': 1, 'y': 1})
    assert fake.sent == []


def test_move_carries_only_its_point():
    k, _ = kernel()
    k.acquire(['B1'])
    with pytest.raises(g.Refused):
        k.send('/mouse/move', ['B1'], x=1, y=1, button=1)


def test_group_move_uses_per_phone_tokens():
    k, fake = kernel()
    k.acquire(['B1', 'B2'])
    k.send('/mouse/move', ['B1', 'B2'], x=250, y=540)
    body = fake.sent[-1]['data']
    assert body['id'] == 'dev-b1,dev-b2' and body['tokens'] == {'dev-b1': 't-dev-b1', 'dev-b2': 't-dev-b2'}


def frame(dots=(), lines=()):
    f = np.full((1080, 500), 120, np.int16)
    yy, xx = np.ogrid[:1080, :500]
    for x, y in dots:
        f[(xx - x) ** 2 + (yy - y) ** 2 <= 12 ** 2] = 70
    for x, y in lines:
        f[y:y + 25, x:x + 2] = 20
    return f


def quiet():
    noise = np.zeros((1080, 500), bool)
    noise[g.STATUS_BAR[0]:g.STATUS_BAR[1]] = True
    return noise


def test_dot_found_at_target():
    d = g.dot_near(frame(), frame([(250, 540)]), (250, 540), quiet())
    assert d and abs(d[0] - 250) <= 1 and abs(d[1] - 540) <= 1


def test_dot_elsewhere_not_counted_as_landing():
    assert g.dot_near(frame(), frame([(100, 300)]), (390, 700), quiet()) is None


def test_thin_clock_hand_is_not_a_dot():
    assert g.blobs(frame(), frame(lines=[(300, 300)]), quiet()) == []


def test_control_dot_flagged_but_own_fading_pointer_allowed():
    before, after = frame([(110, 260)]), frame([(390, 700)])
    assert g.stray_dots(before, after, quiet(), [(110, 260)]) == [(390, 700)]
    assert g.stray_dots(frame([(110, 260)]), frame(), quiet(), [(110, 260)]) == []


def test_screen_change_fraction():
    base = frame()
    other = base.copy()
    other[200:800, :] = 250
    assert g.screen_changed(base, base, quiet()) == 0
    assert g.screen_changed(base, other, quiet()) > g.SCREEN_CHANGE


def test_summary_p95():
    s = g.summary(list(range(1, 101)))
    assert s['median'] == 50.5 and s['p95'] == 95 and s['max'] == 100
    assert g.summary([None]) == {'n': 0}
