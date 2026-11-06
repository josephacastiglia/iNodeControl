"""Runs the platform's read-only verifier once for a Reel attempt that saved its draft and stopped right after.

verify_window.py re-checks a stopped verifier, or a saved YouTube draft whose creation stopped after 'Draft saved'. A Reel
run can stop the same way (A19, 5 Nov: the saved picker's toolbar was not recognized yet): creating again would make a
second draft, so this runs the same verifier, once, against the admitted package. Refused unless the attempt's last action
is its one answered 'save-reel-draft-once' and a later frame shows 'Draft saved'. Nothing is reopened or saved.

  python tools/farm_fleet_verify.py --window reel-slot19 --attempt 3 --check 2
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
WINDOWS = HERE.parent / 'analysis/farm-multiphone-20261020'
sys.path[:0] = [str(HERE), str(WINDOWS)]


def saved_then_stopped(run):
    """Creation answered its one Save draft, a later frame showed 'Draft saved', and nothing ran after."""
    workflow = run['workflow']
    actions = workflow.get('actions') or []
    if not (run['terminal'] and run['state'] == 'review_required' and not run['savedDraftVerified']
            and workflow.get('cleanup') == 'confirmed' and 'verification' not in workflow
            and actions and actions[-1]['label'] == 'save-reel-draft-once' and actions[-1]['state'] == 'answered'):
        return False
    observations = workflow['observations']
    saved = next((i for i, o in enumerate(observations) if o.get('observationId') == actions[-1]['observationId']), None)
    return saved is not None and any(line['text'].strip().casefold() == 'draft saved' for o in observations[saved+1:]
                                     for line in (o.get('observation') or {}).get('text', {}).get('lines', []))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--window', required=True); p.add_argument('--attempt', type=int, required=True)
    p.add_argument('--check', type=int, required=True)
    a = p.parse_args()
    import verify_window as vw
    from farm_draft_workflow import atomic_json
    window = vw.STATE / 'windows' / a.window
    prep = json.loads((window / 'preparation.json').read_text(encoding='utf-8'))
    if prep['platform'] != 'reel': raise SystemExit('Reel windows only; verify_window.py covers the others.')
    out = window / f'attempt-{a.attempt}'
    run = json.loads((out / 'result.json').read_text(encoding='utf-8'))['run']
    if not saved_then_stopped(run):
        raise SystemExit('This attempt is not a saved Reel draft whose creation stopped after Draft saved. Nothing was sent.')
    child = Path(prep['backendData']) / prep['route'] / run['id'] / f'verification-{a.check}'
    if a.check < 2 or child.exists(): raise SystemExit('This check exists or is reserved. Never replay a check.')
    result = vw.verify(prep, run, child)
    atomic_json(out / f'verification-{a.check}.json', result)
    print(vw.summary(a, result))


if __name__ == '__main__':
    main()
