"""Keyboard answering of an alert: space only on the policy answer's focus ring; every other path stops. Offline."""
import io
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

import farm_prompt_keyboard as K


def line(text, x, y, w, h=20):
    return dict(text=text, words=[dict(text=text, x=x, y=y, width=w, height=h)])


ALERT = dict(width=500, height=1080, lines=[
    line('"Instagram" has been able to', 112, 290, 270), line('access your entire photo', 133, 316, 230),
    line('library for 6 months. Do you', 118, 343, 260), line('want to continue to allow full', 114, 369, 270),
    line('access?', 212, 397, 70), line('Limit Access', 194, 747, 110), line('Allow Full Access', 172, 800, 150)])
HOME = dict(width=500, height=1080, lines=[line('Drive', 40, 171, 50), line('Gmail', 150, 171, 50)])


def frame(ring=None):
    a = np.full((1080, 500, 3), 60, dtype=np.uint8)
    if ring == 'Limit Access': a[735:780, 95:405][[0, -1]] = 255; a[735:780, [95, 404]] = 255
    if ring == 'Allow Full Access': a[790:835, 95:405][[0, -1]] = 255; a[790:835, [95, 404]] = 255
    out = io.BytesIO(); Image.fromarray(a).save(out, 'BMP'); return out.getvalue()


class FakePhone:
    def __init__(self, shots):
        self.shots = list(shots); self.keys = []; self.n = 0
    def key(self, **data): self.keys.append(data)
    def frames(self): return self.n
    def shot(self, newer_than=None):
        self.n += 1; return self.shots.pop(0)[0], self.n


def run(sequence):
    """sequence: [(ring, text), ...]; the first is the frame before any key."""
    texts = {}
    shots = []
    for i, (ring, text) in enumerate(sequence):
        raw = frame(ring) + bytes([i])   # Distinct bytes per frame for the OCR fake.
        texts[raw] = text; shots.append((raw, None))
    phone = FakePhone(shots)
    with tempfile.TemporaryDirectory() as d:
        record = K.answer(phone, Path(d), 'photos_reminder', lambda raw: texts[raw], pause=lambda s: None)
    return record, phone.keys


class KeyboardAnswer(unittest.TestCase):
    def test_space_only_when_the_answer_is_focused(self):
        record, keys = run([(None, ALERT), ('Limit Access', ALERT), ('Allow Full Access', ALERT), (None, HOME)])
        self.assertEqual([dict(fn_key='Tab'), dict(fn_key='Tab'), dict(key=' ')], keys)
        self.assertEqual('answered', record['state'])
        self.assertEqual(['Limit Access', 'Allow Full Access'], [s.get('focused') for s in record['steps'] if s['role'].startswith('tab')])

    def test_still_up_after_space_is_ignored_not_repeated(self):
        record, keys = run([(None, ALERT), ('Allow Full Access', ALERT), ('Allow Full Access', ALERT)])
        self.assertEqual([dict(fn_key='Tab'), dict(key=' ')], keys)
        self.assertEqual('ignored', record['state'])

    def test_no_ring_stops_with_nothing_pressed(self):
        record, keys = run([(None, ALERT), (None, ALERT)])
        self.assertEqual([dict(fn_key='Tab')], keys)
        self.assertEqual(('stopped', False), (record['state'], record['spacePressed']))

    def test_never_more_than_four_tabs_and_no_space_elsewhere(self):
        record, keys = run([(None, ALERT)] + [('Limit Access', ALERT)] * 4)
        self.assertEqual([dict(fn_key='Tab')] * 4, keys)
        self.assertFalse(record['spacePressed'])
        self.assertNotIn(dict(fn_key='Escape'), keys)

    def test_no_alert_sends_nothing(self):
        record, keys = run([(None, HOME)])
        self.assertEqual([], keys)
        self.assertEqual('stopped', record['state'])


if __name__ == '__main__':
    unittest.main()
