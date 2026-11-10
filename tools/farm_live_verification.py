"""The read-only kernel client and the checks that the running kernel is the prepared one.

ReadOnlyKernel cannot acquire or send input: it reads the kernel's status, the device list, this
window's own screenshot and the input status, and refuses everything else before any transport.
validate_runtime and idle are the identity and ownership checks every draft workflow starts with.
"""
import json
import re
import urllib.parse
import urllib.request

from imouse_social_automation import IMouseKernel, KernelSafetyError
from farm_phone_identity import LEGACY_C24C, PhoneIdentityError, own_receiver


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise KernelSafetyError('Candidate verification refuses HTTP redirects.')


class ReadOnlyKernel(IMouseKernel):
    def __init__(self, url, transport=None, *, phone):
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1'
                or parsed.port not in (9916,) or parsed.path.rstrip('/') != '/api'
                or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise KernelSafetyError('Verification requires the isolated loopback kernel on port 9916.')
        base = url.rstrip('/')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

        def restricted(method, target, body, timeout):
            permitted = (
                method == 'GET' and body is None and target in (
                    base + '/kernel/status', base + '/device/get',
                    base + '/pic/screenshot?id=' + urllib.parse.quote(phone.device_id) + '&binary=true')
                or method == 'POST' and target == base + '/' and body == {'fun': '/input/status', 'data': {}})
            if not permitted:
                raise KernelSafetyError('Read-only verification refused an input or unrelated request.')
            if transport is not None:
                return transport(method, target, body, timeout)
            data = None if body is None else json.dumps(body).encode('utf-8')
            request = urllib.request.Request(target, data=data, method=method,
                                             headers={'Content-Type': 'application/json'})
            limit = 16 * 1024 * 1024 if '/pic/screenshot?' in target else 1024 * 1024
            with opener.open(request, timeout=min(timeout, 8)) as response:
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise KernelSafetyError('Candidate response exceeds its evidence limit.')
                return raw, dict(response.headers)

        super().__init__(base, transport=restricted, phone=phone)
        self._is_live_http = True  # Keep the production target checks for this window's phone.

    def devices(self):
        raw, _ = self._transport('GET', self.url + '/device/get', None, 5)
        value = json.loads(raw)
        if value.get('status') != 200 or value.get('data', {}).get('code') != 0:
            raise KernelSafetyError('Device identity read failed.')
        return value['data'].get('list', [])


def validate_runtime(status, devices, expected_hash, expected_uid, phone=LEGACY_C24C, allowed=None):
    """The running kernel is the prepared one and maps this window's phone exactly.

    allowed=None is the single-phone kernel: input enabled for this board only, one receiver and
    one device. A multi-phone kernel passes its prepared allow-list, which must match exactly;
    this phone's receiver and board must then be unique and agree on its device ID."""
    if not re.fullmatch(r'[0-9a-f]{64}', expected_hash):
        raise ValueError('An exact prepared kernel SHA-256 is required.')
    expected_allowed = [phone.board] if allowed is None else list(allowed)
    if (status.get('code') != 0 or status.get('build_identity', {}).get('sha256') != expected_hash
            or status.get('input_leases_required') is not True or status.get('allowed') != expected_allowed
            or phone.board not in expected_allowed):
        raise KernelSafetyError(f'Running kernel does not match the prepared candidate for {phone.board}.')
    process = status.get('process', {})
    if type(process.get('pid')) is not int or process['pid'] <= 0 or not process.get('started_utc'):
        raise KernelSafetyError('Kernel process identity is incomplete.')
    receivers = status.get('receivers', [])
    try:
        own_receiver(status, phone)
    except PhoneIdentityError as error:
        raise KernelSafetyError(f'Receiver mapping does not give {phone.board} exactly its own receiver.') from error
    if allowed is None and len(receivers) != 1:
        raise KernelSafetyError(f'Receiver mapping is not exclusively {phone.board}.')
    if len({r.get('name') for r in receivers}) != len(receivers) or len({r.get('deviceid') for r in receivers}) != len(receivers):
        raise KernelSafetyError('Receiver names or phones are not unique.')
    mine = [d for d in devices if d.get('pid') == phone.board or d.get('deviceid') == phone.device_id]
    if ((allowed is None and len(devices) != 1) or len(mine) != 1 or mine[0].get('deviceid') != phone.device_id
            or mine[0].get('pid') != phone.board or mine[0].get('uid') != expected_uid):
        raise KernelSafetyError('Phone/board identity does not match the prepared configuration.')
    return process['pid'], process['started_utc']


def idle(state):
    return (isinstance(state, dict) and type(state.get('generation')) is int
            and all(state.get(key) is False for key in ('owned', 'active', 'stopped', 'releasing', 'release_failed')))
