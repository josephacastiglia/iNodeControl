"""The read-only kernel client cannot issue input, even through the base client API."""
from farm_phone_identity import LEGACY_C24C
import copy
import io
import json
import unittest

from PIL import Image
from farm_live_verification import ReadOnlyKernel, validate_runtime, idle
from imouse_social_automation import LIVE_TEST_DEVICE_ID, KernelSafetyError

HASH = 'a' * 64
UID = 'test-board'
URL = 'http://127.0.0.1:9916/api'


class Fixture:
    def __init__(self):
        self.calls = []
        self.state = dict(id=LIVE_TEST_DEVICE_ID, generation=1, owned=False, active=False,
                          stopped=False, releasing=False, release_failed=False, lease_remaining_ms=0)
        self.status = dict(code=0, build_identity=dict(sha256=HASH), allowed=['C24C'], input_leases_required=True,
            process=dict(pid=10, started_utc='2026-10-18T20:00:00Z'),
            receivers=[dict(deviceid=LIVE_TEST_DEVICE_ID, name='iMouse2-C24C', receiver_pid=11,
                            receiver_restarts=0, live=True, frames=1, frame_session='b' * 32)])
        self.devices = [dict(deviceid=LIVE_TEST_DEVICE_ID, pid='C24C', uid=UID)]
        self.missing_headers = False
        self.after_shot = lambda: None

    def wire(self, method, url, body, timeout):
        self.calls.append((method, url, body))
        if url.endswith('/kernel/status'): value = self.status
        elif url.endswith('/device/get'): value = dict(list=self.devices, code=0)
        elif body == {'fun': '/input/status', 'data': {}}: value = dict(phones=[self.state], code=0)
        elif '/pic/screenshot?' in url:
            self.status['receivers'][0]['frames'] += 1
            raw = io.BytesIO(); Image.new('RGB', (500, 1080), 'white').save(raw, 'BMP')
            headers = {} if self.missing_headers else {
                'X-iMouse-Frame-Session': 'b' * 32,
                'X-iMouse-Frame-Sequence': str(self.status['receivers'][0]['frames']),
                'X-iMouse-Frame-Age-Ms': '5', 'X-iMouse-Frame-Delivery': 'flowing'}
            self.after_shot()
            return raw.getvalue(), headers
        else: raise AssertionError('Unrecognized test request')
        return json.dumps(dict(status=200, data=value)).encode(), {}


class ReadOnlyKernelTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.kernel = ReadOnlyKernel(URL, transport=self.fixture.wire, phone=LEGACY_C24C)

    def test_input_and_other_targets_blocked_before_transport(self):
        for method, target, body in (
            ('POST', URL+'/', dict(fun='/input/acquire', data=dict(id=LIVE_TEST_DEVICE_ID))),
            ('POST', URL+'/', dict(fun='/mouse/click', data=dict(id=LIVE_TEST_DEVICE_ID))),
            ('POST', URL+'/', dict(fun='/input/status', data=dict(id='C241'))),
            ('GET', URL+'/pic/screenshot?id=C241&binary=true', None),
            ('GET', 'http://127.0.0.1:9913/api/kernel/status', None),
            ('GET', URL+'/config/usb/get', None)):
            with self.subTest(target=target, body=body), self.assertRaises(KernelSafetyError):
                self.kernel._transport(method, target, body, 5)
        self.assertEqual([], self.fixture.calls)
        with self.assertRaises(KernelSafetyError): self.kernel.acquire(['C24C'])
        self.assertFalse(any(body and body.get('fun') != '/input/status' for _, _, body in self.fixture.calls))

    def test_untrusted_endpoints_refused(self):
        for endpoint in ('http://127.0.0.1:9913/api', 'http://127.0.0.1:9911/api',
                         'http://example.com:9916/api', URL+'?other=1', URL+'#fragment',
                         'http://user:pass@127.0.0.1:9916/api', 'https://127.0.0.1:9916/api'):
            with self.subTest(endpoint=endpoint), self.assertRaises(KernelSafetyError): ReadOnlyKernel(endpoint, phone=LEGACY_C24C)

    def test_wrong_build_and_extra_phone_are_refused(self):
        def check(): return validate_runtime(self.kernel.kernel_status(), self.kernel.devices(), HASH, UID, self.kernel.phone)
        self.assertEqual((10, '2026-10-18T20:00:00Z'), check())
        for key, value in (('build_identity', dict(sha256='c'*64)), ('allowed', ['C24C','C241']),
                           ('input_leases_required', False), ('process', dict(pid=0))):
            original = copy.deepcopy(self.fixture.status)
            self.fixture.status[key] = value
            with self.subTest(key=key), self.assertRaises(KernelSafetyError): check()
            self.fixture.status = original
        self.fixture.devices[0]['uid'] = 'wrong-board'
        with self.assertRaises(KernelSafetyError): check()
        self.assertFalse(any('/pic/screenshot?' in url for _, url, _ in self.fixture.calls))

    def test_idle_means_free_and_settled(self):
        self.assertTrue(idle(self.kernel.input_status()[LIVE_TEST_DEVICE_ID]))
        for flag in ('owned', 'active', 'stopped', 'releasing', 'release_failed'):
            with self.subTest(flag=flag): self.assertFalse(idle({**self.fixture.state, flag: True}))
        self.assertFalse(idle({**self.fixture.state, 'generation': None})); self.assertFalse(idle(None))


if __name__ == '__main__': unittest.main()
