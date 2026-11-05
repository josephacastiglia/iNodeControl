"""A prepared content item -> the media of one farm window, so an approved real package runs a slot as a test window does.

A content item (farm_preparation_schedule.read_prepared_packages) names its files and its batch manifest. Here the
manifest's checksum and every file's are checked, the files are copied into the window's own backend stage, and one
saved draft is created through the same VideoDrafts / ImageDrafts as test media, so everything after it (package,
transfer, creation, verifier) is the existing path. Local only: no phone, no kernel, no socket; draft only.

Nothing is trimmed, re-captioned or substituted: a changed file, a format no window runs, or content the platform's
runs class would refuse stops here, before a window is queued. Called by prepare_window.py --content.
"""
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from farm_drafts import generated_manifest  # noqa: E402

# Package format -> (prepare_window platform, runs module, runs class). Images go through ImageDrafts.
FORMATS = {'ig_reel': ('reel', 'farm_reel_runs', 'ReelCreationRuns'),
           'tt_video': ('tiktok', 'farm_tiktok_runs', 'TikTokCreationRuns'),
           'x_video': ('x', 'farm_x_runs', 'XCreationRuns'),
           'yt_short': ('youtube', 'farm_youtube_runs', 'YouTubeCreationRuns'),
           'x_image': ('x-image', 'farm_x_runs', 'XImageCreationRuns'),
           'tt_photo': ('tiktok-photo', 'farm_tiktok_photo_runs', 'TikTokPhotoCreationRuns')}
IMAGE_FORMATS = ('x_image', 'tt_photo')


class ContentRefused(ValueError):
    """This content cannot become a window; nothing was queued."""


def platform_of(fmt):
    """The prepare_window platform for a package format, or a clear refusal."""
    if fmt not in FORMATS:
        raise ContentRefused(f'No window runs format {fmt!r} (runnable: {", ".join(sorted(FORMATS))}).')
    return FORMATS[fmt][0]


def source_board(item):
    """The board whose media stage holds this batch, from the item's own manifest path."""
    parts = str(item.get('manifest', '')).split('/')
    if len(parts) != 4 or parts[0] or parts[1] != 'stage' or not parts[2]:
        raise ContentRefused('The content item does not name its batch manifest.')
    return parts[2]


def checked_files(item, stage_root):
    """[(name, source path, sha256, bytes)] in the item's order, each proven against the checksum-pinned manifest."""
    board = source_board(item)
    try: document, _ = generated_manifest(stage_root, item.get('generation'), item.get('manifestSha256'), board)
    except ValueError as error: raise ContentRefused(str(error)) from None
    assets = {a.get('url'): a for a in document['assets'] if isinstance(a, dict)}
    names = item.get('stagedFiles')
    if not isinstance(names, list) or not names: raise ContentRefused('The content item names no files.')
    folder, files = (Path(stage_root) / board).resolve(), []
    for name in names:
        if not isinstance(name, str) or Path(name).name != name or any(c in name for c in '/\\:%\x00'):
            raise ContentRefused(f'Invalid staged file name {name!r}.')
        asset = assets.get(f'/stage/{board}/{name}')
        if asset is None: raise ContentRefused(f'{name} is not in its batch manifest.')
        path = folder / name
        if not path.is_file(): raise ContentRefused(f'{name} is missing from the media stage.')
        raw = path.read_bytes()
        if len(raw) != asset.get('bytes') or hashlib.sha256(raw).hexdigest() != asset.get('sha256'):
            raise ContentRefused(f'{name} changed after its batch was prepared; review it again.')
        files.append((name, path, asset['sha256'], asset['bytes']))
    return files


def stage_content(item, stage_root, board, backend, stage, title):
    """Copies the checked files to the window's stage and creates its one draft.
    Returns (draft, package bytes, transfer package, media fields for preparation.json)."""
    from farm_image import ImageDrafts
    from farm_media_transfer import TransferPackage
    from farm_video import VideoDrafts, VideoTransferPackage
    fmt = item.get('format'); platform_of(fmt)
    files = checked_files(item, stage_root)
    for name, path, _, _ in files: shutil.copyfile(path, Path(stage) / name)
    assets = [{'url': f'/stage/{board}/{name}', 'sha256': digest, 'bytes': size} for name, _, digest, size in files]
    (Path(stage) / 'manifest.json').write_text(json.dumps({'deviceId': board, 'assets': assets}), encoding='utf-8')
    caption, draft_id = item.get('caption', ''), str(uuid.uuid4())
    try:
        if fmt in IMAGE_FORMATS:
            images = ImageDrafts(Path(backend) / 'image-drafts.db', Path(backend) / 'stage', board)
            draft = images.create(dict(id=draft_id, device_id=board, format=fmt, title=title, caption=caption,
                                       images=[dict(name=name, sha256=digest) for name, _, digest, _ in files]))
            package = images.export(draft['id'], draft['revision'])
            return draft, package, TransferPackage(package, board), dict(
                imageSha256s=[a['sha256'] for a in draft['assets']], slideCount=len(draft['assets']))
        if len(files) != 1: raise ContentRefused(f'A {fmt} package holds exactly one video, not {len(files)} files.')
        videos = VideoDrafts(Path(backend) / 'video-drafts.db', Path(backend) / 'stage', board)
        draft = videos.create(dict(id=draft_id, device_id=board, format=fmt, name=files[0][0], sha256=files[0][2],
                                   title=title, caption=caption))
        package = videos.export(draft['id'], draft['revision'])
        return draft, package, VideoTransferPackage(package, board), dict(videoDraftId=draft['id'], videoSha256=draft['sha256'])
    except ContentRefused: raise
    except ValueError as error: raise ContentRefused(f'The draft was refused: {error}') from None


def refusal(fmt, package, config):
    """Why this format's runs class would refuse the package at its first eligibility check, or None. Asked here
    so unfit content stops before a slot is spent on it: a run stops only after its start screen has used the phone."""
    _, module, name = FORMATS[fmt]
    runs = getattr(importlib.import_module(module), name)
    gate = runs.__new__(runs); gate.config = config
    if gate.supports(package): return None
    return getattr(runs, 'UNSUPPORTED_REASON', None) or f'The {fmt} runs do not accept this content.'
