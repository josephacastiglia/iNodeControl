"""Read-only C24C candidate verification. This tool cannot acquire or send input.

Requires the prepared kernel's exact hash and one-phone configuration. It uses
the production observer/OCR and retains real frame evidence without claiming
that a draft was saved. No receiver, console or service is started here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import uuid

from farm_observations import ObservationStore
from imouse_social_automation import IMouseKernel, LIVE_TEST_DEVICE_ID, KernelSafetyError


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise KernelSafetyError('Candidate verification refuses HTTP redirects.')


class ReadOnlyKernel(IMouseKernel):
    def __init__(self, url, transport=None):
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
                    base + '/pic/screenshot?id=' + urllib.parse.quote(LIVE_TEST_DEVICE_ID) + '&binary=true')
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

        super().__init__(base, transport=restricted)
        self._is_live_http = True  # Keep the production C24C target checks.

    def devices(self):
        raw, _ = self._transport('GET', self.url + '/device/get', None, 5)
        value = json.loads(raw)
        if value.get('status') != 200 or value.get('data', {}).get('code') != 0:
            raise KernelSafetyError('Device identity read failed.')
        return value['data'].get('list', [])


def validate_runtime(status, devices, expected_hash, expected_uid):
    if not re.fullmatch(r'[0-9a-f]{64}', expected_hash):
        raise ValueError('An exact prepared kernel SHA-256 is required.')
    if (status.get('code') != 0 or status.get('build_identity', {}).get('sha256') != expected_hash
            or status.get('input_leases_required') is not True or status.get('allowed') != ['C24C']):
        raise KernelSafetyError('Running kernel does not match the prepared C24C-only candidate.')
    process = status.get('process', {})
    if type(process.get('pid')) is not int or process['pid'] <= 0 or not process.get('started_utc'):
        raise KernelSafetyError('Kernel process identity is incomplete.')
    receivers = status.get('receivers', [])
    if (len(receivers) != 1 or receivers[0].get('deviceid') != LIVE_TEST_DEVICE_ID
            or receivers[0].get('name') != 'iMouse2-C24C'):
        raise KernelSafetyError('Receiver mapping is not exclusively C24C.')
    if (len(devices) != 1 or devices[0].get('deviceid') != LIVE_TEST_DEVICE_ID
            or devices[0].get('pid') != 'C24C' or devices[0].get('uid') != expected_uid):
        raise KernelSafetyError('Phone/board identity does not match the prepared configuration.')
    return process['pid'], process['started_utc']


def idle(state):
    return (isinstance(state, dict) and type(state.get('generation')) is int
            and all(state.get(key) is False for key in ('owned', 'active', 'stopped', 'releasing', 'release_failed')))


def capture_once(kernel, store, expectation, expected_hash, expected_uid):
    before = kernel.kernel_status()
    identity = validate_runtime(before, kernel.devices(), expected_hash, expected_uid)
    original_input = kernel.input_status().get(LIVE_TEST_DEVICE_ID)
    if not idle(original_input):
        raise KernelSafetyError('C24C is not idle/free; verification will not take control.')
    request_id = str(uuid.uuid4())
    value = store.capture(dict(id=request_id, device_id='C24C', **expectation), kernel)
    after = kernel.kernel_status()
    if validate_runtime(after, kernel.devices(), expected_hash, expected_uid) != identity:
        raise KernelSafetyError('Kernel changed during verification.')
    final_input = kernel.input_status().get(LIVE_TEST_DEVICE_ID)
    if not idle(final_input) or original_input != final_input:
        raise KernelSafetyError('Phone input state changed during verification; no conclusion is accepted.')
    # Extra identity reads consume the age budget too.
    value = store.get(request_id)
    accepted = (value.get('state') == 'observed' and value.get('freshness') == 'recent'
                and value.get('stable') is True and value.get('inputIdle') is True
                and value.get('frameEvidence', {}).get('pairedMetadata') is True)
    return dict(observation=value, metadataUsableAtCheck=accepted, kernelProcess=identity,
                inputBefore=original_input, inputAfter=final_input, automaticInputAllowed=False,
                savedDraftVerified=False)


def check_retained_expiry(store, observation_id, wait=time.sleep):
    """No new screenshot: real elapsed time must expire the original observation."""
    wait(1.7)
    result = store.get(observation_id)
    return dict(observationId=observation_id, expired=result.get('freshness') != 'recent',
                freshness=result.get('freshness'), frameEvidence=result.get('frameEvidence'),
                recaptured=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preparation', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--account', required=True)
    parser.add_argument('--caption', default='')
    parser.add_argument('--samples', type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    preparation = json.loads(args.preparation.read_text(encoding='utf-8-sig'))
    expected_hash = preparation['validation']['build']['sha256']
    kernel_path = Path(preparation['kernel']).with_suffix('.dll')
    if hashlib.sha256(kernel_path.read_bytes()).hexdigest() != expected_hash:
        raise KernelSafetyError('Prepared kernel bytes changed.')
    args.out.mkdir(parents=True, exist_ok=False)
    kernel = ReadOnlyKernel(preparation['arguments'][0])
    store = ObservationStore(args.out / 'observations.sqlite3')
    report = dict(source='phone', samples=[], automaticInputAllowed=False, savedDraftVerified=False,
                  phoneInput=False, publishing=False, messaging=False, kernelSha256=expected_hash)
    try:
        for index in range(args.samples):
            sample = capture_once(kernel, store, dict(platform='instagram', account=args.account, caption=args.caption),
                                  expected_hash, preparation['expectedUid'])
            report['samples'].append(sample)
            value = sample['observation']
            if value.get('state') == 'observed':
                _, frame = store.evidence(value['id'])
                (args.out / f'frame-{index + 1}.png').write_bytes(frame)
            if not sample['metadataUsableAtCheck']:
                report['reason'] = value.get('frameEvidence', {}).get('reason', value.get('reason'))
                break
        if report['samples']:
            report['retainedExpiry'] = check_retained_expiry(store, report['samples'][-1]['observation']['id'])
        sequences = [s['observation'].get('frameEvidence', {}).get('sequence') for s in report['samples']]
        report['metadataCheckPassed'] = (len(report['samples']) == args.samples
            and all(s['metadataUsableAtCheck'] for s in report['samples'])
            and all(type(s) is int for s in sequences) and len(set(sequences)) == len(sequences)
            and report.get('retainedExpiry', {}).get('expired') is True)
        report['meaning'] = 'Receiver-delivery evidence only, not iOS source time, app identity or a saved draft.'
    except Exception as exc:
        report.update(metadataCheckPassed=False, error=str(exc))
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['metadataCheckPassed'], 'samples': len(report['samples']),
                      'reason': report.get('error', report.get('reason')), 'folder': str(args.out)}))
    return 0 if report['metadataCheckPassed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
