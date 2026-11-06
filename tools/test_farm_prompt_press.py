"""The held press on a verified alert: only after an ignored click, only on the answer, recorded per hold. Offline."""
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

import farm_paths
import farm_permission_prompts as P
import farm_prompt_press as K

_A12 = farm_paths.ARCHIVE / '20261105-fleet-a12'


def row(label, x, y, w, h=20):
    return dict(text=label, words=[dict(text=label, x=x, y=y, width=w, height=h)])


def text(*lines): return dict(width=500, height=1080, lines=list(lines))


BODY = [row('"Instagram" has been able to', 112, 290, 270), row('access your entire photo', 133, 316, 230),
        row('library for 6 months. Do you', 118, 343, 260), row('want to continue to allow full', 114, 369, 270),
        row('access?', 212, 397, 70)]
LIMIT, ALLOW = row('Limit Access', 194, 747, 110), row('Allow Full Access', 172, 800, 150)
POINT = (247, 810)
ALERT = text(*BODY, LIMIT, ALLOW)
DOTTED = text(*BODY, LIMIT)   # The dot hides the answer's label.
MOVED = text(*BODY, row('Limit Access', 194, 700, 110), ALLOW)
HOME = text(row('Drive', 40, 171, 50), row('Gmail', 150, 171, 50))
PART = text(row('5 Photos, 17 Videos', 176, 620, 150), LIMIT)
CONTACTS = text(row('"TikTok" would like to', 112, 290, 270), row('access your contacts', 133, 316, 230),
                row("Don't Allow", 100, 800, 110), row('Allow', 300, 800, 60))


def bmp(dot=None):
    a = np.full((1080, 500, 3), 60, dtype=np.uint8)
    if dot: a[dot[1] - 8:dot[1] + 8, dot[0] - 8:dot[0] + 8] = 255
    out = io.BytesIO(); Image.fromarray(a).save(out, 'BMP'); return out.getvalue()


class FakePhone:
    """shots: [(text, dot)] in the order frames are read. Every command sent is logged."""
    def __init__(self, shots):
        self.shots, self.sent, self.n, self.texts = list(shots), [], 0, {}

    def send(self, fun, **data): self.sent.append((fun, data))

    def frames(self): return self.n

    def shot(self, newer_than=None):
        self.n += 1
        value, dot = self.shots.pop(0)
        raw = bmp(dot) + bytes([self.n])   # Distinct bytes per frame for the OCR fake.
        self.texts[raw] = value
        return raw, self.n

    def funs(self): return [f for f, _ in self.sent]


def round_of(after, *more):
    """The frames of one settled input: parked, settled, then what follows it."""
    return [(ALERT, None), (DOTTED, POINT), (after, None), *more]


def run(shots, **kwargs):
    phone = FakePhone(shots)
    with tempfile.TemporaryDirectory() as d:
        record = K.answer(phone, Path(d), lambda raw: phone.texts[raw], pause=lambda s: None, **kwargs)
    return record, phone


class Press(unittest.TestCase):
    def test_a_click_that_answers_needs_no_press(self):
        record, phone = run([(ALERT, None)] + round_of(HOME, (HOME, None)))
        self.assertEqual(('answered', 'pointer_tap'), (record['state'], record['method']))
        self.assertNotIn('/mouse/down', phone.funs())

    def test_the_first_hold_that_answers_is_the_last(self):
        record, phone = run([(ALERT, None)] + round_of(DOTTED) + round_of(DOTTED) + round_of(HOME, (HOME, None)))
        self.assertEqual(('answered', 'slow_press', 600), (record['state'], record['method'], record['holdMs']))
        self.assertEqual(1, phone.funs().count('/mouse/click'))
        self.assertEqual(2, phone.funs().count('/mouse/down'))
        self.assertEqual([('click', None, 'up'), ('press-400', 400, 'up'), ('press-600', 600, 'gone')],
                         [(a['method'], a['holdMs'], a['result']) for a in record['attempts']])

    def test_every_hold_ignored_ends_without_more_input(self):
        record, phone = run([(ALERT, None)] + round_of(DOTTED) * 4)
        self.assertEqual('ignored', record['state'])
        self.assertEqual(3, phone.funs().count('/mouse/down'))
        self.assertEqual(3, phone.funs().count('/mouse/up'))
        self.assertEqual([400, 600, 800], [a['holdMs'] for a in record['attempts'] if a['holdMs']])

    def test_only_the_answer_is_ever_aimed_at(self):
        _, phone = run([(ALERT, None)] + round_of(DOTTED) * 4)
        self.assertEqual({POINT}, {(d['x'], d['y']) for f, d in phone.sent if f in ('/mouse/move', '/mouse/click')})
        self.assertFalse(set(phone.funs()) - {'/mouse/reset', '/mouse/move', '/mouse/click', '/mouse/down', '/mouse/up'})

    def test_a_caller_that_saw_the_click_ignored_goes_straight_to_the_press(self):
        record, phone = run([(ALERT, None)] + round_of(HOME, (HOME, None)), click_ignored=True)
        self.assertEqual((0, 400), (phone.funs().count('/mouse/click'), record['holdMs']))

    def test_no_alert_or_another_family_sends_nothing(self):
        for screen in (HOME, CONTACTS):
            record, phone = run([(screen, None)])
            self.assertEqual(('stopped', []), (record['state'], phone.sent))

    def test_a_changed_alert_is_never_pressed(self):
        record, phone = run([(ALERT, None), (MOVED, None)])
        self.assertEqual(('stopped', ['/mouse/reset']), (record['state'], phone.funs()))
        record, phone = run([(ALERT, None), (ALERT, None), (HOME, POINT)])
        self.assertEqual(('stopped', ['/mouse/reset', '/mouse/move']), (record['state'], phone.funs()))

    def test_a_pointer_off_the_box_or_unseen_stops(self):
        for dot in ((247, 750), None):
            record, phone = run([(ALERT, None), (ALERT, None), (DOTTED, dot)])
            self.assertEqual('stopped', record['state'])
            self.assertFalse({'/mouse/click', '/mouse/down'} & set(phone.funs()))

    def test_an_unclear_screen_stops_any_further_input(self):
        record, phone = run([(ALERT, None)] + round_of(PART))
        self.assertEqual('stopped', record['state'])
        self.assertEqual(1, phone.funs().count('/mouse/click'))
        self.assertNotIn('/mouse/down', phone.funs())

    def test_gone_needs_a_second_frame(self):
        record, _ = run([(ALERT, None)] + round_of(HOME, (ALERT, None)) + round_of(HOME, (HOME, None)))
        self.assertEqual(('answered', 'slow_press'), (record['state'], record['method']))
        self.assertEqual('up', record['attempts'][0]['result'])

    def test_a_press_is_never_left_down(self):
        class Boom(Exception): pass
        phone = FakePhone([(ALERT, None)] + round_of(DOTTED))
        def pause(seconds):
            if phone.funs() and phone.funs()[-1] == '/mouse/down': raise Boom()
        with tempfile.TemporaryDirectory() as d, self.assertRaises(Boom):
            K.answer(phone, Path(d), lambda raw: phone.texts[raw], pause=pause, click_ignored=True)
        self.assertEqual(['/mouse/down', '/mouse/up'], phone.funs()[-2:])


class Policy(unittest.TestCase):
    def test_the_click_comes_first(self):
        self.assertEqual('stop', P.slow_press_plan(P.detect(ALERT))['action'])
        plan = P.slow_press_plan(P.detect(ALERT), click_ignored=True)
        self.assertEqual(('press', 'Allow Full Access', (400, 600, 800)), (plan['action'], plan['answer'], plan['holdsMs']))

    def test_only_the_listed_family(self):
        self.assertEqual('stop', P.slow_press_plan(P.detect(CONTACTS), click_ignored=True)['action'])

    def test_the_answer_must_be_read(self):
        self.assertEqual('stop', P.slow_press_plan(P.detect(DOTTED), click_ignored=True)['action'])

    def test_a_reminder_with_dont_allow_needs_review(self):
        odd = text(*BODY, LIMIT, ALLOW, row("Don't Allow", 100, 850, 110))
        self.assertEqual('stop', P.slow_press_plan(P.detect(odd), click_ignored=True)['action'])


@unittest.skipUnless((_A12 / 'press-start.png').exists(), 'A12 press frames of 5 Nov are not available in this checkout.')
class A12Frames(unittest.TestCase):
    def load(self, name):
        return (_A12 / f'{name}.png').read_bytes(), json.loads((_A12 / f'{name}.json').read_text(encoding='utf-8'))

    def test_the_real_outcomes(self):
        _, start = self.load('press-start')
        _, boxes = K.read_alert(start)
        others = {'Limit Access': boxes['Limit Access']}
        self.assertEqual('up', K.alert_state(start, 'photos_reminder', others))
        _, ignored = self.load('press-300ms')    # 'Allow F' Access': the dot hides the label, the alert is still up.
        self.assertEqual('up', K.alert_state(ignored, 'photos_reminder', others))
        _, answered = self.load('press-800ms')
        self.assertEqual('gone', K.alert_state(answered, 'photos_reminder', others))

    def test_the_real_dot_lands_on_the_answer(self):
        parked, start = self.load('press-start')
        settled, _ = self.load('press-300ms')
        _, boxes = K.read_alert(start)
        box = boxes['Allow Full Access']
        dot = K.landing(parked, settled, ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2))
        self.assertTrue(box[0] <= dot[0] <= box[2] and box[1] - 4 <= dot[1] <= box[3] + 4, dot)


if __name__ == '__main__':
    unittest.main()
