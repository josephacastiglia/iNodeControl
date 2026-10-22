"""Runs the Reel draft verifier again for one window attempt whose draft was saved but not verified.

The creation run saves one draft and then runs a separate verifier. When only the verifier stops
(for example on an unrecognized Preview), creating again would make a second draft. This runs the
same verifier, once, against the same package video and caption: Create -> Reel -> Drafts chip ->
the one draft matching the package video -> Preview -> Save draft (keeps the unchanged draft).
No Share, publishing or messaging. Refused unless the attempt's creation stopped exactly there.

  python verify_window.py --window reel-slot18 --attempt 1 --check 2
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from farm_draft_runs import account_of, allowed_of, phone_of  # noqa: E402
from farm_draft_transport import CreationKernel  # noqa: E402
from farm_draft_workflow import atomic_json, references  # noqa: E402
from farm_observations import ObservationStore  # noqa: E402
from farm_reel_creation import ReelVerification  # noqa: E402
from farm_reel_layout import VideoReference  # noqa: E402
from farm_reel_runs import reel_content  # noqa: E402
from farm_video import VideoTransferPackage  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--window', required=True)
    parser.add_argument('--attempt', type=int, required=True)
    parser.add_argument('--check', type=int, required=True, help='2 for the first re-check; never reused.')
    args = parser.parse_args()
    window = HERE / 'windows' / args.window
    prep = json.loads((window / 'preparation.json').read_text(encoding='utf-8'))
    if prep['platform'] != 'reel': raise SystemExit('Only Reel windows have this verifier.')
    run = json.loads((window / f'attempt-{args.attempt}' / 'result.json').read_text(encoding='utf-8'))['run']
    workflow = run['workflow']
    if not (run['terminal'] and workflow.get('creationState') == 'created_unverified' and not run['savedDraftVerified']
            and workflow.get('cleanup') == 'confirmed' and isinstance(workflow.get('verification'), dict)):
        raise SystemExit('This attempt is not a saved, unverified draft with a stopped verifier. Nothing was sent.')
    folder = Path(prep['backendData']) / prep['route'] / run['id']
    child = folder / f'verification-{args.check}'
    if args.check < 2 or child.exists(): raise SystemExit('This check exists or is reserved. Never replay a check.')
    config = json.loads(Path(prep['config']).read_text(encoding='utf-8'))
    # The exact package the creation run admitted, from the backend's own run journal.
    with sqlite3.connect(Path(prep['backendData']) / prep['route'] / 'runs.db') as db:
        rows = db.execute('SELECT * FROM runs WHERE id = ?', (run['id'],)).fetchall()
    package = rows[0][2] if len(rows) == 1 else b''
    if not package or hashlib.sha256(package).hexdigest() != workflow['packageSha256']:
        raise SystemExit('The admitted package is missing or changed. Nothing was sent.')
    _, caption, _ = reel_content(package)
    video = VideoReference(VideoTransferPackage(package, phone_of(config).board).video)
    child.mkdir()
    kernel = CreationKernel(config['api'], phone=phone_of(config))
    store = ObservationStore(child / 'observations.sqlite3', retained_limit=160)
    result = ReelVerification(child, kernel, store, video, caption, references(), config['kernelSha256'],
                              config['expectedUid'], account=account_of(config), package_hash=workflow['packageSha256'],
                              cancelled=threading.Event(), allowed=allowed_of(config)).run()
    atomic_json(window / f'attempt-{args.attempt}' / f'verification-{args.check}.json', result)
    print(json.dumps(dict(window=args.window, attempt=args.attempt, check=args.check, state=result['state'],
                          savedDraftVerified=result['savedDraftVerified'], error=result.get('error'),
                          cleanup=result.get('cleanup'), commands=len(result.get('commands', [])))))


if __name__ == '__main__':
    main()
