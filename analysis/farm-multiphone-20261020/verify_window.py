"""Runs a draft verifier again for one window attempt whose draft was saved but not verified.

The creation run saves one draft and then runs a separate verifier. When only the verifier stops
(for example on an unrecognized Preview), creating again would make a second draft. This runs the
same verifier, once, against the same package video and caption: Create -> Reel -> Drafts chip ->
the one draft matching the package video -> Preview -> Save draft (keeps the unchanged draft).
No Share, publishing or messaging. Refused unless the attempt's creation stopped exactly there.

YouTube (23 Oct, slot 16): creation pressed Save draft once, a following frame showed YouTube's own
'Draft saved' toast, and only the home check after it stopped (the toast covered the + button), so
the verifier never ran. That exact case runs the YouTube verifier once on the channel creation
bound: Create -> Drafts -> the one exact-title draft -> play -> Save draft (keeps it) -> Drafts.

  python verify_window.py --window reel-slot18 --attempt 1 --check 2
  python verify_window.py --window x-slot17 --attempt 1 --check 2
  python verify_window.py --window youtube-slot16 --attempt 1 --check 1
  python verify_window.py --window x-image-slot17 --attempt 1 --check 2

Image windows (x-image, tiktok-photo) run the verifier of their lane's runs class
(farm_reel_runs.LANE_RUNS: farm_x_runs.XImageCreationRuns, farm_tiktok_photo_runs.TikTokPhotoCreationRuns)
against a farm_image.ImageReference of the admitted package. They are loaded only when needed and
refused, before any phone command, while the lane's class does not exist.
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
from farm_reel_runs import LANE_RUNS, image_content, reel_content  # noqa: E402
from farm_video import VideoTransferPackage  # noqa: E402


# Image platforms -> (package format, account policy). 'workflow': the account creation bound; 'config': pinned.
IMAGE_PLATFORMS = {'x-image': ('x_image', 'workflow'), 'tiktok-photo': ('tt_photo', 'config')}


def admitted(prep, run):
    """The window's config and the exact package the creation run admitted, from the backend's own journal.

    Video windows get the package video; image windows get the ordered package images."""
    config = json.loads(Path(prep['config']).read_text(encoding='utf-8'))
    with sqlite3.connect(Path(prep['backendData']) / prep['route'] / 'runs.db') as db:
        rows = db.execute('SELECT * FROM runs WHERE id = ?', (run['id'],)).fetchall()
    package = rows[0][2] if len(rows) == 1 else b''
    if not package or hashlib.sha256(package).hexdigest() != run['workflow']['packageSha256']:
        raise SystemExit('The admitted package is missing or changed. Nothing was sent.')
    if prep['platform'] in IMAGE_PLATFORMS:
        from farm_media_transfer import TransferPackage
        _, caption, _ = image_content(package)
        return config, caption, list(TransferPackage(package, phone_of(config).board).images.values())
    _, caption, _ = reel_content(package)
    return config, caption, VideoTransferPackage(package, phone_of(config).board).video


def lane_runs(platform):
    """The lane's runs class for an image window, imported only now; refuses clearly while it is absent."""
    import importlib
    fmt, _ = IMAGE_PLATFORMS[platform]
    module_name, class_name, label, _ = LANE_RUNS[fmt]
    try: found = getattr(importlib.import_module(module_name), class_name, None)
    except ModuleNotFoundError as error:
        if error.name != module_name: raise
        found = None
    if found is None or getattr(found, 'verifier', None) is None:
        raise SystemExit(f'No {label} verifier yet: {module_name}.{class_name} does not exist or has no verifier. Nothing was sent.')
    return found


def verify(prep, run, child):
    """Runs the platform's verifier once in `child` (a new folder) against the admitted package."""
    if prep['platform'] in IMAGE_PLATFORMS: runs = lane_runs(prep['platform'])   # Before reading or decoding anything.
    config, caption, raw = admitted(prep, run)
    workflow, extra = run['workflow'], {}
    if prep['platform'] in IMAGE_PLATFORMS:
        verifier, video = runs.verifier, runs.reference(raw)
        account = workflow['account'] if IMAGE_PLATFORMS[prep['platform']][1] == 'workflow' else account_of(config)
    elif prep['platform'] == 'x':   # X binds the account creation read from its menu (23 Oct, slot 17).
        from farm_tiktok_layout import TikTokReference
        from farm_x_creation import XVerification
        verifier, video, account = XVerification, TikTokReference(raw), workflow['account']
    elif prep['platform'] == 'youtube':
        from farm_tiktok_layout import TikTokReference
        from farm_youtube_creation import YouTubeVerification, phone_from_config
        verifier, video, account = YouTubeVerification, TikTokReference(raw), workflow['account']
        extra = dict(phone=phone_from_config(config))
    elif prep['platform'] == 'tiktok':   # TikTok's account is pinned in the window config.
        from farm_tiktok_layout import TikTokReference
        from farm_tiktok_creation import TikTokVerification
        verifier, video, account = TikTokVerification, TikTokReference(raw), account_of(config)
    else:
        verifier, video, account = ReelVerification, VideoReference(raw), account_of(config)
    child.mkdir()
    kernel = CreationKernel(config['api'], phone=phone_of(config))
    store = ObservationStore(child / 'observations.sqlite3', retained_limit=160)
    return verifier(child, kernel, store, video, caption, references(), config['kernelSha256'],
                    config['expectedUid'], account=account, package_hash=workflow['packageSha256'],
                    cancelled=threading.Event(), allowed=allowed_of(config), **extra).run()


def summary(args, result):
    return json.dumps(dict(window=args.window, attempt=args.attempt, check=args.check, state=result['state'],
                           savedDraftVerified=result['savedDraftVerified'], error=result.get('error'),
                           cleanup=result.get('cleanup'), commands=len(result.get('commands', []))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--window', required=True)
    parser.add_argument('--attempt', type=int, required=True)
    parser.add_argument('--check', type=int, required=True, help='2 for the first re-check; never reused.')
    args = parser.parse_args()
    window = HERE / 'windows' / args.window
    prep = json.loads((window / 'preparation.json').read_text(encoding='utf-8'))
    if prep['platform'] not in ('reel', 'x', 'youtube', 'tiktok', *IMAGE_PLATFORMS): raise SystemExit('No verifier for this window.')
    run = json.loads((window / f'attempt-{args.attempt}' / 'result.json').read_text(encoding='utf-8'))['run']
    workflow = run['workflow']
    folder = Path(prep['backendData']) / prep['route'] / run['id']
    child = folder / f'verification-{args.check}'
    if prep['platform'] == 'youtube' and 'verification' not in workflow:
        if not saved_then_stopped(run):
            raise SystemExit('This attempt is not a saved YouTube draft whose creation stopped after Draft saved. Nothing was sent.')
        if child.exists() or (folder / 'verification').exists(): raise SystemExit('This check exists. Never replay a check.')
    else:   # Every platform, YouTube included once its own verifier ran and stopped (run 70, 26 Oct).
        if not (run['terminal'] and workflow.get('creationState') == 'created_unverified' and not run['savedDraftVerified']
                and workflow.get('cleanup') == 'confirmed' and isinstance(workflow.get('verification'), dict)):
            raise SystemExit('This attempt is not a saved, unverified draft with a stopped verifier. Nothing was sent.')
        if args.check < 2 or child.exists(): raise SystemExit('This check exists or is reserved. Never replay a check.')
    result = verify(prep, run, child)
    atomic_json(window / f'attempt-{args.attempt}' / f'verification-{args.check}.json', result)
    print(summary(args, result))


def saved_then_stopped(run):
    """Creation answered its one Save draft, a later frame showed 'Draft saved', and nothing ran after."""
    workflow = run['workflow']
    actions = workflow.get('actions') or []
    if not (run['terminal'] and run['state'] == 'review_required' and not run['savedDraftVerified']
            and workflow.get('cleanup') == 'confirmed' and 'verification' not in workflow and workflow.get('account')
            and actions and actions[-1]['label'] == 'save-youtube-draft-once' and actions[-1]['state'] == 'answered'):
        return False
    saved = next(i for i, o in enumerate(workflow['observations']) if o.get('observationId') == actions[-1]['observationId'])
    return any(line['text'].strip().casefold() == 'draft saved' for o in workflow['observations'][saved+1:]
               if o['role'] in ('yt_home', 'yt_home_saved') for line in o['observation']['text'].get('lines', []))


if __name__ == '__main__':
    main()
