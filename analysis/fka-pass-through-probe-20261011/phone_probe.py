"""Explicit, single-operation C24C probe. No retries, automatic Resume, or other targets."""
import argparse
import json
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

BASE = 'http://127.0.0.1:9913/api/'
PHONE = '86:1D:4A:04:2F:F6'
LIVE = Path(__file__).resolve().parent / 'live-20261011'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('inspect', 'toggle', 'text'))
    parser.add_argument('label')
    args = parser.parse_args()
    if not args.label.replace('-', '').replace('_', '').isalnum():
        raise SystemExit('Invalid label')
    output = LIVE / args.label
    output.mkdir(exist_ok=False)
    log = output / 'requests.jsonl'

    def record(value):
        with log.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), **value}) + '\n')

    def request(path, fun=None, data=None):
        started = time.monotonic()
        body = None if fun is None else json.dumps({'fun': fun, 'data': data}).encode('utf-8')
        req = urllib.request.Request(BASE + path, data=body, headers={'Content-Type': 'application/json'})
        raw = urllib.request.urlopen(req, timeout=12).read()
        result = json.loads(raw)['data']
        safe = json.loads(json.dumps(result))
        if 'leases' in safe:
            for lease in safe['leases']:
                lease['token'] = '[redacted]'
        safe_data = {k: ('[redacted]' if k == 'token' else v) for k,v in (data or {}).items()}
        record({'path': path, 'fun': fun, 'data': safe_data, 'response': safe, 'elapsed_ms': round((time.monotonic()-started)*1000, 3)})
        return result

    def frame(name):
        raw = urllib.request.urlopen(BASE + 'pic/screenshot?id=' + PHONE + '&binary=true', timeout=5).read()
        if raw[:2] != b'BM':
            raise RuntimeError('Mirrored BMP unavailable')
        target = output / (name + '.bmp')
        target.write_bytes(raw)
        Image.open(target).save(target.with_suffix('.png'))

    kernel = request('kernel/status')
    assert kernel['allowed'] == ['C24C'] and kernel['fka_pass_through_probe_enabled'] is True
    assert len(kernel['receivers']) == 1 and kernel['receivers'][0]['deviceid'] == PHONE
    assert kernel['receiver_pid'] == 36360 and kernel['live'], 'Wrong receiver or no live video'
    devices = request('device/get')['list']
    assert len(devices) == 1 and devices[0]['deviceid'] == PHONE and devices[0]['pid'] == 'C24C' and devices[0]['uid'] == 'C24CBFBD'
    status = request('input/status')
    phone = next(p for p in status['phones'] if p['id'] == PHONE)
    assert not any(phone[k] for k in ('owned', 'active', 'stopped', 'releasing', 'release_failed')), 'Input unavailable; no automatic recovery'
    frame('before')
    if args.action == 'inspect':
        print('Read-only frame:', output / 'before.png')
        return

    lease = request('', '/input/acquire', {'id': PHONE, 'lease_ms': 30000})
    assert lease['code'] == 0 and len(lease['leases']) == 1
    token = lease['leases'][0]['token']
    capture_errors = []
    stop_capture = threading.Event()
    def capture():
        for index in range(16):
            if stop_capture.is_set():
                break
            try: frame(f'during-{index:02d}')
            except Exception as e: capture_errors.append(str(e)); break
            stop_capture.wait(0.2)
    worker = threading.Thread(target=capture)
    worker.start()
    try:
        # No accompanying text for a toggle. Exactly one command is attempted.
        data = {'id': PHONE, 'token': token}
        if args.action == 'toggle': data['fn_key'] = 'FkaPassThrough'
        else: data['key'] = 'Hi there'
        result = request('', '/key/sendkey', data)
        print(args.action, 'response:', json.dumps(result))
        if result['code'] != 0:
            raise RuntimeError('Input failed or uncertain; do not retry')
        time.sleep(2)
        frame('after')
    finally:
        stop_capture.set()
        worker.join(timeout=6)
        released = request('', '/input/release', {'id': PHONE, 'token': token})
        if released['code'] != 0:
            raise RuntimeError('Release not confirmed')
        status = request('input/status')
        assert not any(p['owned'] or p['active'] or p['releasing'] for p in status['phones'])
        record({'capture_errors': capture_errors, 'capture_worker_finished': not worker.is_alive()})
    print('C24C released. Frames:', output)

if __name__ == '__main__':
    main()
