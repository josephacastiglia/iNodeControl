"""Guarded auto-connect: refusals, the bounded blind sequence and the verified close. No phone, socket or desktop."""
import io
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

import farm_test_network  # noqa: F401  Refuse every real socket in this process.
import farm_mirroring as fm
from imouse_social_automation import LIVE_TEST_DEVICE_ID, KernelSafetyError

BROWSE_13_OCT = """Browsing for _airplay._tcp.local
Timestamp     A/R Flags if Domain                    Service Type              Instance Name
 0:27:47.457  Add     3 21 local.                    _airplay._tcp.            Bedroom TV
 0:27:47.457  Add     3  6 local.                    _airplay._tcp.            iMouse2-C241
 0:27:47.457  Add     2  6 local.                    _airplay._tcp.            iMouse2-C24C
 0:27:47.503  Add     2 21 local.                    _airplay._tcp.            iMouse2-C24C
 0:27:48.100  Rmv     0 21 local.                    _airplay._tcp.            iMouse2-C241
"""


def png(colour):
    image = Image.new('RGB', (500, 1080), colour); ImageDraw.Draw(image).rectangle((60, 340, 440, 740), fill='gray')
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


SCREENS = {'sheet': png('navy'), 'grid': png('teal'), 'app': png('white')}
LABELS = {'sheet': [('Screen Mirroring', 171, 417), ('iMouse2-C24C', 97, 480), ('Stop Mirroring', 180, 715)], 'grid': [('Focus', 130, 520)],
          'app': [('Edit profile', 70, 135)]}


class Kernel:
    def __init__(self, live=False, connects=True):
        self.live, self.connects, self.frames, self.calls, self.owned = live, connects, 10, [], False
        self.screen, self.pointer, self.ticks = 'app', None, 0
    def kernel_status(self):
        if self.screen == 'mirroring-sheet-pending':
            self.ticks += 1
            if self.connects and self.ticks >= 3: self.live, self.screen = True, 'sheet'
        return dict(allowed=['C24C'], receivers=[dict(name='iMouse2-C24C', live=self.live, frames=self.frames)])
    def input_status(self):
        return {LIVE_TEST_DEVICE_ID: dict(generation=4, owned=self.owned, active=False, stopped=False, releasing=False, release_failed=False)}
    def acquire(self, ids, lease_ms): assert not self.owned; self.owned = True; return {'C24C': 'token'}
    def release(self, tokens): self.owned = False; self.calls.append('release')
    def send(self, pid, token, fun, **data):
        assert self.owned and pid == 'C24C'; self.calls.append((fun, dict(data)))
        if fun == '/mouse/move' and self.pointer != (data['x'], data['y']) and self.live: self.pointer = (data['x'], data['y']); self.frames += 1
        if fun == '/key/sendkey': self.screen = 'control-center'
        if fun == '/mouse/click':
            point = (data['x'], data['y'])
            if point == fm.TILE: self.screen = 'mirroring-sheet'
            elif point in fm.ROWS: self.screen = 'mirroring-sheet-pending'
            elif point == fm.CLOSE: self.screen = {'sheet': 'grid', 'grid': 'app'}[self.screen]; self.frames += 1
        return dict(code=0)
    def shot(self, pid):
        return SCREENS[self.screen], {'X-iMouse-Frame-Sequence': str(self.frames), 'X-iMouse-Frame-Age-Ms': '200'}


class Ocr:
    def read(self, raw):
        screen = next(k for k, v in SCREENS.items() if v == raw)
        return dict(lines=[dict(text=t, words=[dict(text=t, x=x, y=y, width=9*len(t), height=18)]) for t, x, y in LABELS[screen]])


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): self.now += .01; return self.now
    def pause(self, seconds): self.now += seconds


def run(kernel, names):
    clock = Clock()
    with tempfile.TemporaryDirectory() as folder:
        tool = fm.AutoConnect(folder, kernel=kernel, browse=lambda: (set(names), 'fixture browse'), ocr=Ocr(), clock=clock, pause=clock.pause)
        return tool.run()


class FirstRowTests(unittest.TestCase):
    def test_browse_output_is_parsed_with_removals(self):
        self.assertEqual({'Bedroom TV', 'iMouse2-C24C'}, fm.parse_browse(BROWSE_13_OCT))

    def test_our_receiver_must_sort_first_under_every_collation(self):
        self.assertEqual(0, fm.first_row('iMouse2-C24C', {'iMouse2-C24C'}))
        self.assertEqual(0, fm.first_row('iMouse2-C24C', {'iMouse2-C24C', 'iMouse3-A', 'kitchen'}))
        # Unproven phone collation: uppercase names and C241 (1 < C in ASCII) may come first, so refuse.
        for names in ({'iMouse2-C24C', 'Living Room'}, {'iMouse2-C24C', 'iMouse2-C241'}):
            with self.subTest(names=names), self.assertRaises(fm.MirroringRefused): fm.first_row('iMouse2-C24C', names)
        for names in ({'iMouse2-C24C', 'Bedroom TV'}, {'iMouse2-C24C', 'iMouse2-724E'}, {'iMouse2-C24C', ' `iMouseXP-5429'},
                      {'iMouse2-C24C', 'IMOUSE1'}, {'iMouse2-C241'}, {'iMouse2-C24C', 'w', 'x', 'y', 'z'}):
            with self.subTest(names=names), self.assertRaises(fm.MirroringRefused):
                fm.first_row('iMouse2-C24C', names)


class AutoConnectTests(unittest.TestCase):
    def test_connects_with_three_blind_inputs_then_closes_on_verified_frames(self):
        kernel = Kernel(); record = run(kernel, {'iMouse2-C24C'})
        self.assertEqual('connected', record['state'], record.get('error'))
        sent = [c for c in kernel.calls if c != 'release' and c[0] != '/mouse/move']
        self.assertEqual([('/key/sendkey', {'fn_key': 'ControlBar'}), ('/mouse/click', {'x': 199, 'y': 432, 'button': 1}),
                          ('/mouse/click', {'x': 250, 'y': 489, 'button': 1}), ('/mouse/click', {'x': 250, 'y': 960, 'button': 1}),
                          ('/mouse/click', {'x': 250, 'y': 960, 'button': 1})], sent)
        self.assertEqual(3, record['blindInputs']); self.assertEqual('app', kernel.screen)
        self.assertEqual('release', kernel.calls[-1]); self.assertTrue(record['leaseReleased'])

    def test_refusals_send_nothing(self):
        for kernel, names, reason in ((Kernel(live=True), {'iMouse2-C24C'}, None),
                                      (Kernel(), {'iMouse2-C24C', 'Bedroom TV'}, 'sort before'),
                                      (Kernel(), set(), 'not advertised')):
            with self.subTest(names=names):
                record = run(kernel, names)
                self.assertEqual([], [c for c in kernel.calls if c != 'release'])
                self.assertEqual(0, record['blindInputs'])
                if reason is None: self.assertEqual('already_live', record['state'])
                else: self.assertEqual('refused', record['state']); self.assertIn(reason, record['error'])

    def test_no_connection_means_no_retry_and_no_further_input(self):
        kernel = Kernel(connects=False); record = run(kernel, {'iMouse2-C24C'})
        self.assertEqual('stopped', record['state']); self.assertIn('did not go live', record['error'])
        sent = [c for c in kernel.calls if c != 'release']
        self.assertEqual(3, len(sent)); self.assertEqual(('/mouse/click', {'x': 250, 'y': 489, 'button': 1}), sent[-1])
        self.assertEqual('release', kernel.calls[-1])

    def test_transport_allows_only_controlbar_and_calibrated_points(self):
        seen = []
        def transport(method, target, body, timeout):
            seen.append(body); return b'{"status":200,"data":{"code":0}}', {}
        kernel = fm.MirroringKernel('http://127.0.0.1:9916/api', transport=transport)
        for fun, data in (('/key/sendkey', {'fn_key': 'Home'}), ('/key/sendkey', {'key': 'x'}), ('/mouse/click', {'x': 300, 'y': 300}),
                          ('/mouse/swipe', {'direction': 'down'})):
            with self.subTest(fun=fun, data=data), self.assertRaises(KernelSafetyError):
                kernel._transport('POST', kernel.url + '/', dict(fun=fun, data=dict(id=LIVE_TEST_DEVICE_ID, token='t', **data)), 5)
        kernel._transport('POST', kernel.url + '/', dict(fun='/key/sendkey', data=dict(id=LIVE_TEST_DEVICE_ID, token='t', fn_key='ControlBar')), 5)
        kernel._transport('POST', kernel.url + '/', dict(fun='/mouse/click', data=dict(id=LIVE_TEST_DEVICE_ID, token='t', x=199, y=432)), 5)
        self.assertEqual(2, len(seen))


if __name__ == '__main__':
    unittest.main()
