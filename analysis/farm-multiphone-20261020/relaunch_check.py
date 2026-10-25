"""Priority 2: does a verified draft survive closing and relaunching its app?

For one window attempt whose draft is already verified, once per check number:
  1. open the app on its start screen (farm_start_screen), so it is the front switcher card;
  2. close it from the App Switcher (close_app.close: the app's own card, one swipe up);
  3. start it again from Home (a cold start) on its start screen;
  4. run the same read-only verifier as creation (Drafts lists exactly one draft with the exact
     text and the package video's thumbnail; nothing is reopened, played or saved).
appRestartVerified is true only when the close was confirmed and the verifier passed.
No draft is created, changed or deleted; no Post, Upload, publishing or messaging.

  python relaunch_check.py --window x-slot17 --attempt 1 --check 1
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from farm_draft_workflow import atomic_json  # noqa: E402
from close_app import close  # noqa: E402
from verify_window import verify  # noqa: E402

APPS = {'x': ('X', 'x-timeline'), 'youtube': ('YouTube', 'youtube-home'), 'tiktok': ('TikTok', 'tiktok-profile'),
        'reel': ('Instagram', 'instagram-profile')}


def verified(attempt, run):
    """The creation run verified its draft, or a later verification-N.json of this attempt did."""
    if run['savedDraftVerified']: return 'creation'
    for path in sorted(attempt.glob('verification-*.json')):
        if json.loads(path.read_text(encoding='utf-8')).get('savedDraftVerified'): return path.name
    return None


def start_screen(target, folder, config_path):
    out = subprocess.run([sys.executable, '-X', 'utf8', str(HERE.parents[1] / 'tools' / 'farm_start_screen.py'), target, str(folder),
                          str(config_path)], capture_output=True, text=True, encoding='utf-8')
    last = (out.stdout.strip().splitlines() or ['{}'])[-1]
    try: return json.loads(last)
    except json.JSONDecodeError: return dict(state='unknown', error=last[-300:])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--window', required=True); p.add_argument('--attempt', type=int, required=True)
    p.add_argument('--check', type=int, required=True, help='1 for the first relaunch check; never reused.')
    args = p.parse_args()
    # A window name, or a path under this folder for an archived window (the 22 Oct Reel: windows-archive/...).
    window = HERE / 'windows' / args.window if (HERE / 'windows' / args.window).is_dir() else HERE / args.window
    prep = json.loads((window / 'preparation.json').read_text(encoding='utf-8'))
    if not Path(prep['config']).exists():   # An archived window keeps its config beside its record.
        prep['config'] = str(window / 'creation-config.json')
    attempt = window / f'attempt-{args.attempt}'
    run = json.loads((attempt / 'result.json').read_text(encoding='utf-8'))['run']
    basis = verified(attempt, run)
    if not basis: raise SystemExit('This attempt has no verified draft. Nothing was sent.')
    out_path = attempt / f'relaunch-{args.check}.json'
    child = Path(prep['backendData']) / prep['route'] / run['id'] / f'relaunch-{args.check}'
    if out_path.exists() or child.exists(): raise SystemExit('This relaunch check exists. Never replay a check.')
    app, target = APPS[prep['platform']]
    config = json.loads(Path(prep['config']).read_text(encoding='utf-8'))
    record = dict(window=args.window, attempt=args.attempt, check=args.check, app=app, verifiedBy=basis, appRestartVerified=False)
    steps = window / f'relaunch-{args.check}'
    record['opened'] = start_screen(target, steps / 'open', prep['config'])
    if record['opened'].get('state') not in ('at_start', 'already_at_start'):
        record['result'] = 'stopped: the app did not open on its start screen'
    else:
        record['closed'] = close(config, steps / 'close', app, purpose='relaunch-check-close')
        if record['closed'].get('state') != 'closed':
            record['result'] = 'stopped: the app was not closed'
        else:
            record['relaunched'] = start_screen(target, steps / 'relaunch', prep['config'])
            if record['relaunched'].get('state') != 'at_start':   # A cold start goes through Home and the app icon.
                record['result'] = 'stopped: the app did not relaunch on its start screen'
            else:
                result = verify(prep, run, child)
                record['verification'] = {k: result.get(k) for k in ('state', 'savedDraftVerified', 'error', 'cleanup', 'draftRow',
                                                                     'draftsBefore', 'reopened', 'finalScreen')}
                record['appRestartVerified'] = bool(result.get('savedDraftVerified'))
                record['result'] = 'draft found after relaunch' if record['appRestartVerified'] else 'stopped: verifier did not pass'
    atomic_json(out_path, record)
    print(json.dumps({k: record.get(k) for k in ('window', 'app', 'verifiedBy', 'result', 'appRestartVerified')}))


if __name__ == '__main__':
    main()
