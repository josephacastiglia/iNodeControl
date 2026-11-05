"""Starts one draft run in a running window and follows it to its end. Never replays an attempt.

The run itself (all phone input) is the backend's bounded creation workflow for this window's
phone; this driver only admits it over the backend's loopback API, the same request the native
console sends. A new attempt is refused unless every earlier one in this window ended as a
confirmed stop before media import.

  python run_window.py --window tiktok-slot20 --attempt 1
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
import sys  # noqa: E402
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
import farm_paths  # noqa: E402
from farm_rack_lock import hold_rack  # noqa: E402
STATE = farm_paths.rack_state(HERE)  # windows/, identify/ ...: beside this script in a checkout, the data folder when installed
KERNEL = 'http://127.0.0.1:9916/api'


def call(url, body=None, timeout=10):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method='GET' if body is None else 'POST',
                                     headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:   # The backend's own reason (22 Oct: a refused admission printed none).
        raise SystemExit(f'{error.code} from {url}: ' + error.read().decode('utf-8', 'replace')[:600]) from error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--window', required=True)
    parser.add_argument('--attempt', type=int, required=True)
    args = parser.parse_args()
    folder = STATE / 'windows' / args.window
    prep = json.loads((folder / 'preparation.json').read_text(encoding='utf-8'))
    if not (folder / 'processes.json').exists(): raise SystemExit('This window is not started.')
    out = folder / f'attempt-{args.attempt}'
    if out.exists(): raise SystemExit('This attempt exists. Retrieve it; never replay.')
    for earlier in range(1, args.attempt):
        result = folder / f'attempt-{earlier}' / 'result.json'
        if not result.exists(): raise SystemExit(f'Attempt {earlier} has no retained result. No new attempt.')
        run = json.loads(result.read_text(encoding='utf-8')).get('run') or {}
        if not (run.get('terminal') and run.get('state') == 'review_required' and run.get('retryBeforeImportAllowed')):
            raise SystemExit(f'Attempt {earlier} is not a confirmed stop before import. No new attempt.')
    # One opted-in run on the rack at a time; the phone checks below are made once it is this run's turn.
    with hold_rack(f'run_window {args.window} attempt {args.attempt}'):
        admit_and_follow(args, prep, out)


def admit_and_follow(args, prep, out):
    status = call(KERNEL + '/kernel/status')['data']
    own = [r for r in status['receivers'] if r['deviceid'] == prep['phone']['deviceId']]
    if status['build_identity']['sha256'] != prep['kernelSha256'] or len(own) != 1 or own[0]['name'] != prep['phone']['receiver'] or not own[0]['live']:
        raise SystemExit(f"{prep['phone']['receiver']} is not live on the prepared kernel.")
    phones = call(KERNEL + '/', dict(fun='/input/status', data={}))['data']['phones']
    mine = [p for p in phones if p['id'] == prep['phone']['deviceId']]
    if len(mine) != 1 or any(mine[0][k] for k in ('owned', 'active', 'stopped', 'releasing', 'release_failed')):
        raise SystemExit(f"{prep['phone']['board']} is not free. No takeover.")

    base = f"http://127.0.0.1:{prep['backendPort']}/api/farm/{prep['route']}"
    draft_id = prep.get('draftId') or prep['videoDraftId']   # Image windows name only draftId.
    query = urllib.parse.urlencode(dict(draft_id=draft_id, revision=prep['revision']))
    eligibility = call(f'{base}/eligibility?{query}')['eligibility']
    if not eligibility.get('eligible'): raise SystemExit('Not eligible: ' + json.dumps(eligibility)[:400])
    spec = dict(id=str(uuid.uuid4()), draft_id=draft_id, revision=prep['revision'], store_id=eligibility['storeId'])
    out.mkdir()
    (out / 'request.json').write_text(json.dumps(dict(spec, utc=datetime.now(timezone.utc).isoformat()), indent=2), encoding='utf-8')
    run = call(base, spec)['run']
    last = None
    while not run.get('terminal'):
        state = (run.get('state'), (run.get('workflow') or {}).get('phase'))
        if state != last: print(datetime.now().strftime('%H:%M:%S'), *state, flush=True); last = state
        time.sleep(3)
        run = call(f"{base}/{spec['id']}")['run']
    (out / 'result.json').write_text(json.dumps(dict(run=run), indent=2), encoding='utf-8')
    workflow = run.get('workflow') or {}
    print(json.dumps(dict(window=args.window, attempt=args.attempt, state=run.get('state'), reason=run.get('reason'),
                          cleanup=run.get('cleanup'), savedDraftVerified=run.get('savedDraftVerified'),
                          retryBeforeImportAllowed=run.get('retryBeforeImportAllowed'), commands=len(workflow.get('commands', [])))))


if __name__ == '__main__':
    main()
