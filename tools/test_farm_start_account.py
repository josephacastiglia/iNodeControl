"""The Instagram start screen checks the account of the window it is run for. Offline: no phone, no kernel."""
import io
import json
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import farm_start_screen as fs
from farm_phone_identity import PhoneIdentity
from test_farm_observations import NEW_PROFILE, _profile

PHONE = PhoneIdentity(board='C214', device_id='02:00:00:00:00:20', receiver='iMouse2-20', slot=20)   # A fixture phone.
PROFILE = _profile(*NEW_PROFILE)   # Instagram's own profile of 'demo.account', as OCR reads it.


class InstagramAccountTests(unittest.TestCase):
    def screen(self):
        start = fs.StartScreen.__new__(fs.StartScreen)
        self.sent = []
        start.phone, start.tokens = PHONE, None
        start.record = dict(tool='farm_start_screen', target=None, commands=[], observations=[], state='started')
        start.kernel = mock.Mock()
        start.kernel.preflight_phone.return_value = dict(receiver=dict(live=True), input_status=dict(generation=3))
        start.kernel.acquire.return_value = {PHONE.board: 'token'}
        start.save = lambda: None
        start.command = lambda fun, purpose, **data: self.sent.append(purpose)
        start.fresh = lambda role: (b'frame', PROFILE, 0, 0)
        start.control_center = lambda text: False
        start.close_new_reel = lambda raw, text: (raw, text)
        return start

    def test_the_profile_must_show_the_account_the_route_was_given(self):
        start = self.screen()
        with mock.patch.object(fs, 'account_label', return_value='first.window'):
            start.instagram_account = 'demo.account'
            ready, result = start.instagram_profile(None, PROFILE)
            self.assertEqual((True, 'profile', 'exact_text_match'), (ready, result['screen'], result['accountStatus']))
            start.instagram_account = 'other.account'
            ready, result = start.instagram_profile(None, PROFILE)
            self.assertEqual((False, 'different_text'), (ready, result['accountStatus']))

    def test_without_an_account_the_private_default_is_used_as_before(self):
        start = self.screen()
        self.assertIsNone(fs.StartScreen.instagram_account)
        with mock.patch.object(fs, 'account_label', return_value='demo.account') as label:
            self.assertTrue(start.instagram_profile(None, PROFILE)[0]); label.assert_called_once_with()
        with mock.patch.object(fs, 'account_label', return_value='first.window'):
            self.assertFalse(start.instagram_profile(None, PROFILE)[0])
        with mock.patch.object(fs, 'account_label', return_value=''):   # A machine with no private default matches nothing.
            self.assertFalse(start.instagram_profile(None, PROFILE)[0])

    def test_another_windows_phone_already_on_its_own_profile_is_at_start_without_a_tap(self):
        start = self.screen()
        with mock.patch.object(fs, 'account_label', return_value='first.window'):
            record = start.to_instagram_profile_top('demo.account')
        self.assertEqual(('already_at_start', 'exact_text_match'), (record['state'], record['before']['accountStatus']))
        self.assertEqual(['initial_pointer_reset'], self.sent)
        start.kernel.acquire.assert_called_once_with(['C214'], 30000); start.kernel.release.assert_called_once()

    def test_a_phone_on_another_account_is_never_at_start(self):
        start = self.screen()
        start.instagram_feed = lambda text, raw: False
        start.own_profile_scrolled = lambda text: False
        start.open_from_home = lambda app: (b'frame', PROFILE, 0, 0)
        with mock.patch.object(fs, 'account_label', return_value='demo.account'):   # Even though the old default would match.
            with self.assertRaisesRegex(fs.InspectionStopped, 'did not open on the authorized profile'):
                start.to_instagram_profile_top('other.account')
        self.assertEqual('stopped', start.record['state'])
        self.assertEqual('different_text', start.record['before']['accountStatus'])
        self.assertEqual(['initial_pointer_reset'], self.sent)
        start.kernel.release.assert_called_once()

    def test_main_gives_the_route_the_windows_configured_account(self):
        class Tool:
            seen = []
            def __init__(self, folder, phone=None): self.record = dict(state='started', commands=[])
            def to_instagram_profile_top(self, account=None):
                Tool.seen.append(account); self.record['state'] = 'at_start'; return self.record
        with tempfile.TemporaryDirectory() as folder:
            for settings, expected in ((dict(version=2, account='window.account'), 'window.account'),
                                       (dict(version=2, account=None), None), (dict(version=1), None)):
                config = Path(folder) / 'config.json'; config.write_text(json.dumps(settings), encoding='utf-8')
                with self.subTest(settings=settings), mock.patch.object(fs, 'StartScreen', Tool), mock.patch.object(fs, 'phone_of', lambda c: PHONE), \
                        mock.patch('farm_rack_lock.hold_rack', lambda holder: nullcontext()), \
                        mock.patch.object(fs.sys, 'argv', ['farm_start_screen.py', 'instagram-profile', folder, str(config)]), \
                        redirect_stdout(io.StringIO()):
                    fs.main()
                    self.assertEqual(expected, Tool.seen[-1])


if __name__ == '__main__':
    unittest.main()
