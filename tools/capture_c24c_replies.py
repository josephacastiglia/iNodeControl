"""Bounded C24C-only input-report capture. Writes use the release's lease API only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

REPO = Path(__file__).resolve().parents[1]
RECORD = REPO / 'analysis/hid-input-replies-20261014'
RELEASE = REPO.parent / 'iMouseXP-2.0'
READER = RECORD / 'capture-build/hid-input-capture.exe'
BASE = 'http://127.0.0.1:9913/api/'
PHONE = '86:1D:4A:04:2F:F6'
OTHER = 'FE:A9:BC:D7:A0:44'
KERNEL_HASH = 'bd1a68168e9270f029336cf8e13ff85e9b15fd67951ef545d1e973c2bfe634fc'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def request(endpoint='', data=None):
    body = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(BASE + endpoint, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as response:
        result = json.load(response)
    if result.get('status') != 200 or result.get('data', {}).get('code') != 0:
        raise RuntimeError('Kernel refused request: ' + str(result))
    return result['data']


def status():
    return {row['id']: row for row in request('input/status')['phones']}


def require_idle(row):
    if any(row.get(k, True) for k in ('owned', 'active', 'stopped', 'releasing', 'release_failed')):
        raise RuntimeError('C24C is not idle, unowned and ready; no takeover or Resume attempted')


def verify_device(row):
    expected = {'deviceid': PHONE, 'pid': 'C24C', 'uid': 'C24CBFBD', 'receiver_name': 'iMouse2-C24C'}
    if any(row.get(k) != v for k, v in expected.items()):
        raise RuntimeError('C24C phone/board/receiver binding mismatch')
    if row.get('state') != 1:
        raise RuntimeError('C24C must be mirroring before the move-only check')


def process_snapshot():
    script = """$ErrorActionPreference='Stop'
@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(iMouse2(\\.Kernel)?|IMService|uxplay|hid-input-capture)\\.exe$' } |
 Select-Object ProcessId,Name,ExecutablePath,CreationDate) | ConvertTo-Json -Compress
"""
    rows = json.loads(subprocess.check_output(['powershell.exe', '-NoProfile', '-Command', script], text=True))
    if isinstance(rows, dict):
        rows = [rows]
    kernels = [row for row in rows if row['Name'].lower() == 'imouse2.kernel.exe']
    expected = RELEASE / 'release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe'
    if len(kernels) != 1 or Path(kernels[0]['ExecutablePath']).resolve() != expected.resolve():
        raise RuntimeError('Expected only the installed release kernel')
    if any(row['Name'].lower() in ('imservice.exe', 'hid-input-capture.exe') for row in rows):
        raise RuntimeError('Another vendor/capture process is present')
    return sorted(rows, key=lambda row: row['ProcessId'])


def run(destination, pattern='basic'):
    if pattern not in ('basic', 'diagonal'):
        raise ValueError('Unknown move-only pattern')
    destination = Path(destination).resolve()
    if not destination.is_relative_to(RECORD.resolve()):
        raise ValueError('Output must be a new folder under the dated analysis record')
    destination.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (destination / name).write_text(json.dumps(value, indent=2), encoding='utf-8')
    before_processes = process_snapshot()
    save('processes-before.json', before_processes)
    dll = RELEASE / 'release/iMouse2-kernel-two-phone/iMouse2.Kernel.dll'
    if sha(dll) != KERNEL_HASH:
        raise RuntimeError('Installed kernel differs from the statically audited release')
    audit = subprocess.run([str(READER), '--audit-release', str(dll), str(dll.with_suffix('.pdb')),
        str(REPO / 'src/iMouse.Kernel/HidConnection.cs')], text=True, capture_output=True, check=True)
    save('release-audit.json', json.loads(audit.stdout))
    protected = json.loads((REPO / 'analysis/candidate-retry-20261013/protected-after.json').read_text(encoding='utf-8-sig'))
    hashes = {row['path']: sha(row['path']) for row in protected}
    save('protected-before.json', hashes)
    before = status()
    require_idle(before[PHONE])
    verify_device(next(row for row in request('device/get')['list'] if row['deviceid'] == PHONE))
    save('input-before.json', before)
    kernel_before = request('kernel/status')
    save('kernel-before.json', kernel_before)
    token = None
    reader = None
    thread = None
    errors = []
    events = []
    ready = threading.Event()
    closed = threading.Event()
    clock = time.perf_counter()
    log = (destination / 'events.jsonl').open('x', encoding='utf-8', buffering=1)
    lock = threading.Lock()
    def record(kind, detail):
        row = {'kind': kind, 'elapsed_ms': (time.perf_counter()-clock)*1000,
               'utc': datetime.now(timezone.utc).isoformat(), 'detail': detail}
        with lock:
            log.write(json.dumps(row)+'\n')
            events.append(row)
    def drain():
        try:
            for line in reader.stdout:
                row = json.loads(line)
                record('reader', row)
                if row['kind'] == 'ready': ready.set()
                if row['kind'] == 'closed': closed.set()
                if row['kind'] == 'error': errors.append(row)
        except Exception as exc:
            errors.append(str(exc))
    def command(label, fun, **fields):
        if reader.poll() is not None or errors:
            raise RuntimeError('Capture stopped; no next command sent')
        state = status()
        if state[OTHER] != before[OTHER]:
            raise RuntimeError('C241 state changed; stop the experiment')
        current = state[PHONE]
        if not current['owned'] or any(current[k] for k in ('active','stopped','releasing','release_failed')):
            raise RuntimeError('C24C ownership/state changed')
        record('command-start', {'label':label, 'fun':fun, **fields})
        result = request(data={'fun':fun, 'data':{'id':PHONE, 'token':token, **fields}})
        record('command-end', {'label':label, 'result':result})
        time.sleep(0.65)
    failure = None
    cleanup = {}
    try:
        acquired = request(data={'fun':'/input/acquire', 'data':{'id':PHONE,'lease_ms':30000}})
        token = acquired['leases'][0]['token']
        record('lease-acquired', {'phone':PHONE, 'lease_ms':30000})
        reader = subprocess.Popen([str(READER),'--pid','C24C','--seconds','25'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        thread = threading.Thread(target=drain, daemon=True)
        thread.start()
        if not ready.wait(5) or reader.poll() is not None or errors:
            raise RuntimeError('Reader did not become ready')
        record('idle-start', {})
        time.sleep(1.2)
        record('idle-end', {})
        command('reset', '/mouse/reset')
        if pattern == 'basic':
            command('right-two-units', '/mouse/move', x=24, y=14)
            command('down-two-units', '/mouse/move', x=24, y=24)
            command('left-two-units', '/mouse/move', x=14, y=24)
            command('up-two-units', '/mouse/move', x=14, y=14)
        else:
            command('diagonal-positive-two', '/mouse/move', x=24, y=24)
            command('diagonal-negative-two', '/mouse/move', x=14, y=14)
            command('right-two-units', '/mouse/move', x=24, y=14)
            command('left-two-units', '/mouse/move', x=14, y=14)
    except Exception as exc:
        failure = {'type':type(exc).__name__, 'message':str(exc)}
        record('failure', failure)
    finally:
        if token:
            try:
                record('release-start', {})
                cleanup['release'] = request(data={'fun':'/input/release','data':{'id':PHONE,'token':token}})
                record('release-end', cleanup['release'])
            except Exception as exc:
                cleanup['release_error'] = str(exc)
                record('release-error', {'message':str(exc)})
        if reader is not None:
            time.sleep(0.8)
            if reader.poll() is None:
                try:
                    reader.stdin.write('stop\n'); reader.stdin.flush(); reader.stdin.close()
                    reader.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    reader.kill()  # This exact read-only child only, never the kernel/receiver.
                    reader.wait(timeout=5)
                    cleanup['reader_forced_closed'] = True
            thread.join(timeout=3)
            cleanup['reader_exit'] = reader.returncode
            cleanup['reader_closed_record'] = closed.is_set()
            (destination/'reader-stderr.txt').write_text(reader.stderr.read(),encoding='utf-8')
        try:
            after = status()
            save('input-after.json', after)
            cleanup['c24c_free'] = not any(after[PHONE][k] for k in ('owned','active','releasing','release_failed','stopped'))
            cleanup['c241_unchanged'] = after[OTHER] == before[OTHER]
            after_processes = process_snapshot()
            save('processes-after.json', after_processes)
            cleanup['processes_unchanged'] = after_processes == before_processes
            save('kernel-after.json', request('kernel/status'))
            after_hashes = {p:sha(p) for p in hashes}
            save('protected-after.json', after_hashes)
            cleanup['protected_unchanged'] = after_hashes == hashes
        except Exception as exc:
            cleanup['verification_error'] = str(exc)
        record('complete', {'failure':failure, 'cleanup':cleanup, 'reader_errors':errors})
        log.close()
    summary = {'pattern':pattern, 'failure':failure, 'cleanup':cleanup, 'reader_errors':errors,
        'input_reports':sum(row['kind']=='reader' and row['detail']['kind']=='input' for row in events),
        'scope':'C24C reset and small pointer moves only; release API owns every write; no iOS success inferred'}
    save('summary.json', summary)
    print(json.dumps(summary,indent=2))
    if failure or errors or not all(cleanup.get(k) for k in ('c24c_free','c241_unchanged','processes_unchanged','protected_unchanged','reader_closed_record')):
        raise SystemExit(1)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', help='Explicitly enable the bounded live check')
    parser.add_argument('--output',required=True)
    parser.add_argument('--pattern',choices=['basic','diagonal'],default='basic')
    args=parser.parse_args()
    if not args.run:
        parser.error('--run is required; no activity was started')
    run(args.output,args.pattern)
