"""Fleet survey: recognition, guards and the prompt rule, with a fake screen. No phone, no socket."""
import io
import unittest

import numpy as np
from PIL import Image

from farm_owned_capture import InspectionStopped
import farm_fleet_survey as F


def line(text, x, y, w=60, h=20):
    return dict(text=text, words=[dict(text=text, x=x, y=y, width=w, height=h)])


def frame(fill=200, letterbox=False):
    a = np.full((1080, 500), fill, dtype=np.uint8)
    if letterbox: a[:95] = 0; a[985:] = 0
    out = io.BytesIO(); Image.fromarray(a).save(out, 'BMP'); return out.getvalue()


XR_HOME = dict(lines=[line(n, 40 + 110 * (i % 4), 171 + 127 * (i // 4)) for i, n in enumerate(
    ['FaceTime', 'Calendar', 'Photos', 'Camera', 'Mail', 'Clock', 'Instagram', 'X'])])
SMALL_HOME = dict(lines=[line(n, 46 + 116 * (i % 4), 225 + 117 * (i // 4)) for i, n in enumerate(
    ['Clock', 'Maps', 'TikTok', 'YouTube', 'Notes', 'Safari'])])
CONTROL = dict(lines=[line('Focus', 40, 520), line('84%', 400, 100)])
PROMPT = dict(lines=[line('"TikTok" Would Like to Send You Notifications', 100, 450, 300), line("Don't Allow", 90, 600, 100),
                     line('Allow', 330, 600, 50)])
UNKNOWN_PROMPT = dict(lines=[line('"TikTok" Would Like to Access Your Photos', 100, 450, 300), line('Limit Access...', 90, 600, 120),
                             line('Allow Full Access', 90, 650, 150), line("Don't Allow", 90, 700, 100)])   # Policy answer grants.


class FakeScreen:
    def __init__(self, frames):
        self.frames = list(frames); self.commands = []; self.taps = []
        self.record = dict(commands=[], observations=[], state='started')
    def fresh(self, role):
        raw, text = self.frames.pop(0)
        self.record['observations'].append(dict(role=role, frame=f'{len(self.record["observations"])+1:02d}-{role}.bmp', state='fresh'))
        return raw, text, 0, 0
    def command(self, fun, purpose, **data): self.commands.append((fun, purpose, data))
    def tap(self, raw, text, point, role, purpose, only=None): self.taps.append((point, purpose))
    def pause(self, s): pass
    def save(self): pass
    def control_center(self, text):
        return any(r['fold'] == 'focus' for r in F.rows(text)) and any('%' in r['fold'] for r in F.rows(text))


class Recognition(unittest.TestCase):
    def test_home_and_labels(self):
        self.assertTrue(F.home_like(XR_HOME, 'xr'))
        self.assertTrue(F.home_like(SMALL_HOME, 'small'))
        self.assertFalse(F.home_like(SMALL_HOME, 'xr'))
        self.assertFalse(F.home_like(CONTROL, 'xr'))
        self.assertTrue(F.label_matches('x', 'X')); self.assertFalse(F.label_matches('xbox', 'X'))
        self.assertTrue(F.label_matches('tube', 'YouTube') is False)
        self.assertTrue(F.label_matches('outube', 'YouTube'))

    def test_model_from_frame(self):
        self.assertEqual(F.model_of(frame(letterbox=True)), 'small')
        self.assertEqual(F.model_of(frame()), 'xr')
        self.assertIsNone(F.model_of(frame(fill=0)))
        self.assertTrue(F.dark(frame(fill=0)))

    def test_app_states(self):
        self.assertEqual(F.app_state(dict(lines=[line('Welcome to YouTube', 0, 300), line('Sign in with Google', 0, 700)]), 'YouTube'), 'signed_out')
        self.assertEqual(F.app_state(dict(lines=[line('For you', 0, 120), line('Following', 200, 120)]), 'X'), 'signed_in')
        self.assertEqual(F.app_state(dict(lines=[line('Following', 200, 120)]), 'X'), 'unknown')
        self.assertEqual(F.app_state(dict(lines=[line('Inbox', 300, 1000), line('Profile', 420, 1000)]), 'TikTok'), 'signed_in')
        self.assertEqual(F.app_state(dict(lines=[line('Log in to TikTok', 0, 300), line('Inbox', 300, 1000), line('Profile', 420, 1000)]), 'TikTok'), 'signed_out')


class Guards(unittest.TestCase):
    def survey(self, frames, model='xr'):
        return F.FleetSurvey(FakeScreen(frames), 'A10', model)

    def test_no_home_over_control_center(self):
        s = self.survey([])
        with self.assertRaises(InspectionStopped): s.home('x', frame(), CONTROL)
        self.assertEqual(s.s.commands, [])

    def test_no_home_on_home(self):
        s = self.survey([])
        s.home('x', frame(), XR_HOME)
        self.assertEqual(s.s.commands, [])

    def test_home_that_opens_control_center_stops(self):
        s = self.survey([(frame(), CONTROL)])
        with self.assertRaises(InspectionStopped): s.home('x', frame(), dict(lines=[line('Inbox', 0, 1000)]))
        self.assertEqual([c[0] for c in s.s.commands], ['/key/sendkey'])

    def test_safe_prompt_answered_once(self):
        s = self.survey([(frame(), dict(lines=[line('Inbox', 300, 1000)]))])
        raw, text = s.answer_prompt('TikTok', frame(), PROMPT)
        self.assertEqual(len(s.s.taps), 1)
        self.assertEqual(s.record['prompts'][0]['outcome'], 'answered')
        self.assertEqual(s.record['prompts'][0]['answer'], "Don't Allow")

    def test_every_look_answers_a_photos_reminder_first(self):
        reminder = dict(lines=[line('"Instagram" has been able to access your entire photo library for 6 months.', 100, 300, 300),
                               line('Limit Access', 190, 752, 110), line('Allow Full Access', 170, 807, 150)] + XR_HOME['lines'])
        s = self.survey([(frame(), reminder), (frame(), XR_HOME)])
        raw, text = s.look('first')
        self.assertIs(text, XR_HOME)
        self.assertEqual([((245, 817), 'prompt-photos_reminder')], s.s.taps)
        self.assertEqual(('photos_reminder', 'Allow Full Access', 'answered', 'Instagram'),
                         tuple(s.record['prompts'][0][k] for k in ('kind', 'answer', 'outcome', 'promptApp')))

    def test_alert_read_without_the_home_labels_behind_it(self):
        # A11, 5 Nov 17:30: OCR lines (left, top) of Instagram's photos reminder over Home page 2.
        rows = [('Fitness', 168, 170), ('"Instagram" has been able to', 112, 290), ('o Mail', 415, 297),
                ('access your entire photo', 133, 316), ('library for 6 months. Do you', 118, 343),
                ('want to continue to allow full', 114, 369), ('yah', 54, 392), ('access?', 212, 397), ('gram', 419, 426),
                ('5 Photos, 6 Videos', 179, 620), ('Limit Access', 194, 747), ('Allow Full Access', 172, 800), ('Q Search', 218, 893)]
        text = dict(lines=[line(t, x, y, w=min(len(t) * 9, 495 - x)) for t, x, y in rows])
        import farm_permission_prompts as P
        self.assertIsNone(P.detect(text))
        prompt = P.detect(F.alert_only(text))
        self.assertEqual(('photos_reminder', 'Instagram'), (prompt['kind'], prompt['app']))
        self.assertIn('Allow Full Access', prompt['buttons'])
        self.assertIs(XR_HOME, F.alert_only(XR_HOME))

    def test_ignored_prompt_stops(self):
        s = self.survey([(frame(), PROMPT)])
        with self.assertRaises(InspectionStopped): s.answer_prompt('TikTok', frame(), PROMPT)
        self.assertEqual(s.record['prompts'][0]['outcome'], 'ignored')

    def test_prompt_outside_safe_families_is_not_tapped(self):
        s = self.survey([])
        with self.assertRaises(InspectionStopped): s.answer_prompt('TikTok', frame(), UNKNOWN_PROMPT)   # Its policy answer grants access.
        self.assertEqual(s.s.taps, [])

    def test_an_apps_own_declining_answer_is_tapped_but_not_from_home(self):
        contacts = dict(lines=[line('"TikTok" Would Like to Access Your Contacts', 100, 450, 300), line("Don't Allow", 90, 600, 100),
                               line('Open settings', 290, 600, 110)])
        s = self.survey([(frame(), dict(lines=[line('Inbox', 300, 1000)]))])
        s.answer_prompt('TikTok', frame(), contacts)
        self.assertEqual(("Don't Allow", 'answered'), (s.record['prompts'][0]['answer'], s.record['prompts'][0]['outcome']))
        home = self.survey([])
        with self.assertRaises(InspectionStopped): home.answer_prompt('system', frame(), contacts)
        self.assertEqual(home.s.taps, [])

    def test_small_phone_app_off_pages_is_not_searched(self):
        s = self.survey([], model='small'); s.pages = {1: {'clock': (76, 225)}, 2: {}}; s.current = 1
        result, _, _ = s.open_app('Instagram', frame(), SMALL_HOME)
        self.assertEqual(result, dict(state='not_on_pages_1_2', opened=False))
        self.assertEqual(s.s.taps, [])

    def test_icon_tap_below_label(self):
        s = self.survey([], model='small'); s.pages = {1: F.grid_labels(SMALL_HOME, 'small'), 2: {}}; s.current = 1
        result, _, _ = s.open_app('TikTok', frame(), SMALL_HOME)
        self.assertEqual(result['route'], 'page-1')
        (x, y), purpose = s.s.taps[0]
        self.assertEqual(purpose, 'open-tiktok')
        self.assertEqual((x, y), (308, 225 - 50))

    def test_not_fleet_board_refused(self):
        for board in ('724E', 'C24C', 'C214', 'CD51', 'F215'):
            self.assertNotIn(board, F.FLEET)


class RackLockTests(unittest.TestCase):
    """main() for one fleet phone, with the kernel, the start screen and the survey itself replaced."""
    DEVICE = '02:00:00:00:00:10'   # A fixture device ID.

    def run_main(self, hold):
        import sys
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        events = self.events = []
        def request(base, method, path, **options):
            events.append(('read', path))
            if path == '/kernel/status': return dict(receivers=[dict(deviceid=self.DEVICE, live=True, name='iMouse2-10')])
            return dict(list=[dict(pid='374C', deviceid=self.DEVICE)])
        class Kernel:
            def acquire(self, boards, lease_ms): events.append(('acquire', tuple(boards))); return {boards[0]: 'token'}
            def release(self, tokens): events.append(('release',))
        class Screen:
            def __init__(self, folder, phone=None):
                events.append(('screen', phone.board)); self.kernel, self.tokens = Kernel(), None
                self.record = dict(observations=[], commands=[], state='started')
            def save(self): pass
        class Survey:
            def __init__(self, screen, label, model):
                self.model = model; self.record = screen.record
                self.record.update(apps={}, prompts=[], homes=0, pages={}, model=model)
            def look(self, role, app=None): events.append(('input', 'look')); return b'frame', {}
            def run(self, apps): events.append(('input', 'survey')); self.record['state'] = 'done'
        with tempfile.TemporaryDirectory() as directory, patch.object(F, 'ROOT', Path(directory) / 'output' / 'fleet'), \
                patch.object(F, 'HERE', Path(directory) / 'tools'), patch('identify_phone.request', request), \
                patch('farm_start_screen.StartScreen', Screen), patch.object(F, 'FleetSurvey', Survey), \
                patch.object(F, 'contact_sheet', return_value=None), patch('farm_rack_lock.hold_rack', hold), \
                patch.object(sys, 'argv', ['farm_fleet_survey.py', '374C', '--run', 'run-1']), patch('builtins.print'):
            F.main()

    def test_the_lease_and_every_input_sit_inside_the_rack_lock(self):
        from contextlib import contextmanager
        @contextmanager
        def hold(holder):
            self.events.append(('lock', holder))
            try: yield
            finally: self.events.append(('unlock', holder))
        self.run_main(hold)
        acting = [event for event in self.events if event[0] != 'read']
        self.assertEqual([('lock', 'farm_fleet_survey A10 run-1'), ('screen', '374C'), ('acquire', ('374C',)), ('input', 'look'),
                          ('input', 'survey'), ('release',), ('unlock', 'farm_fleet_survey A10 run-1')], acting)

    def test_a_busy_rack_takes_no_lease_and_sends_nothing(self):
        def busy(holder): raise SystemExit('The rack is busy. Nothing was sent to a phone; run it again later.')
        with self.assertRaisesRegex(SystemExit, 'Nothing was sent to a phone'): self.run_main(busy)
        self.assertEqual([], [event for event in self.events if event[0] != 'read'])   # Only the two read-only status reads.


if __name__ == '__main__':
    unittest.main()
