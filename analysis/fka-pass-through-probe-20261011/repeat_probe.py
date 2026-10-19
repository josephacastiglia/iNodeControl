"""C24C-only repeated typing, with a measured wait and no automatic retry."""
import argparse
import json
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image
import io

BASE = 'http://127.0.0.1:9913/api/'
PHONE = '86:1D:4A:04:2F:F6'
LIVE = Path(__file__).resolve().parent / 'live-repeat-20261011'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('inspect', 'trial', 'shortcut'))
    parser.add_argument('label')
    parser.add_argument('--shortcut', action='store_true')
    args = parser.parse_args()
    assert args.label.replace('-', '').replace('_', '').isalnum()
    assert not args.shortcut or args.action == 'trial'
    output = LIVE / args.label
    output.mkdir(exist_ok=False)
    log = output / 'requests.jsonl'
    lock = threading.Lock()

    def record(value):
        with lock, log.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'utc': datetime.now(timezone.utc).isoformat(), **value}) + '\n')

    def request(path, fun=None, data=None):
        start = time.monotonic()
        body = None if fun is None else json.dumps({'fun': fun, 'data': data}).encode()
        req = urllib.request.Request(BASE + path, data=body, headers={'Content-Type':'application/json'})
        result = json.loads(urllib.request.urlopen(req, timeout=12).read())['data']
        safe = json.loads(json.dumps(result))
        for lease in safe.get('leases', []): lease['token'] = '[redacted]'
        record({'path':path, 'fun':fun, 'data':{k:('[redacted]' if k=='token' else v) for k,v in (data or {}).items()}, 'response':safe, 'elapsed_ms':round((time.monotonic()-start)*1000,3)})
        return result

    def frame(name, keep_bmp=False):
        raw = urllib.request.urlopen(BASE + 'pic/screenshot?id=' + PHONE + '&binary=true', timeout=5).read()
        assert raw[:2] == b'BM', 'Mirrored frame unavailable'
        if keep_bmp: (output / (name+'.bmp')).write_bytes(raw)
        Image.open(io.BytesIO(raw)).save(output / (name+'.png'))

    def ready(require_free=True):
        kernel = request('kernel/status')
        expected = json.loads((LIVE/'test-start.json').read_text(encoding='utf-8-sig'))
        assert kernel['allowed'] == ['C24C'] and kernel['fka_pass_through_probe_enabled'] is True
        assert len(kernel['receivers']) == 1 and kernel['receivers'][0]['deviceid'] == PHONE
        assert kernel['receiver_pid'] == expected['receiver_pid'] and kernel['live']
        devices = request('device/get')['list']
        assert len(devices)==1 and devices[0]['deviceid']==PHONE and devices[0]['pid']=='C24C' and devices[0]['uid']=='C24CBFBD'
        status = request('input/status')
        assert len(status['phones'])==1 and status['phones'][0]['id']==PHONE
        phone = status['phones'][0]
        flags = ('owned','active','stopped','releasing','release_failed') if require_free else ('active','stopped','releasing','release_failed')
        assert not any(phone[k] for k in flags), 'Phone unavailable; no automatic recovery'

    def command(data):
        ready()
        acquired = request('', '/input/acquire', {'id':PHONE, 'lease_ms':30000})
        assert acquired['code']==0 and len(acquired['leases'])==1
        lease = acquired['leases'][0]
        assert lease['id']==PHONE and lease.get('token')
        token = lease['token']
        try:
            record({'command_started_monotonic':time.monotonic(), 'wait_from_measurement_ms':round((time.monotonic()-measured)*1000,3)})
            result = request('', '/key/sendkey', {'id':PHONE, 'token':token, **data})
            assert result['code']==0, 'Uncertain command; do not retry'
            print(json.dumps({'submitted':data, 'code':result['code']}), flush=True)
        finally:
            released = request('', '/input/release', {'id':PHONE, 'token':token})
            assert released['code']==0, 'Release unconfirmed'
        ready()

    ready()
    frame('before', True)
    measured = time.monotonic()
    record({'measurement_start_monotonic':measured, 'action':args.action, 'shortcut_before_text':args.shortcut, 'matched_wait_seconds':30 if args.action=='trial' else None})
    if args.action=='inspect':
        print(output/'before.png'); return
    done = threading.Event()
    errors = []
    def capture():
        index=0
        while not done.is_set():
            try: frame(f'during-{index:03d}')
            except Exception as exc: errors.append(str(exc)); return
            index+=1
            done.wait(0.2 if time.monotonic()-measured < 5 else 1.0)
    worker = threading.Thread(target=capture)
    worker.start()
    try:
        if args.action=='shortcut' or args.shortcut:
            command({'fn_key':'FkaPassThrough'})
        if args.action=='trial':
            print('Measurement frame recorded; typing once at 30 seconds. Do not touch C24C.', flush=True)
            remaining=measured+30-time.monotonic()
            assert remaining>0, 'Setup exceeded matched wait; no text sent'
            time.sleep(remaining)
            command({'key':'Hi there'})
        time.sleep(2 if args.action=='trial' else 5)
        frame('after', True)
    finally:
        done.set(); worker.join(timeout=6)
        record({'capture_errors':errors, 'capture_finished':not worker.is_alive()})
    print('C24C released. '+str(output/'after.png'), flush=True)

if __name__=='__main__': main()
