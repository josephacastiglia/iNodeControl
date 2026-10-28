"""Offline preparation of one farm window on the multi-phone kernel. No socket, phone or service.

A window is one platform on one rack phone: its own backend port, media port, run folder and
version 2 creation config (that phone, the kernel's exact allow-list, the signed-in account).
The phone comes from the running multi-phone preparation (slots/preparation.json and its run
data), never a default. The window shares the kernel; it never starts or stops it.

  python prepare_window.py --platform tiktok --slot 20 --phone-ip 192.168.4.27 --account <handle>
  python prepare_window.py --platform youtube --slot 16 --phone-ip 192.168.4.69

Writes windows/<platform>-slot<N>/{preparation.json, creation-config.json} and
output/candidate-runs/farm-<platform>-slot<N>-<date>-<n>/backend. Refuses to overwrite either.
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_creation_runs import MEDIA_PORTS, creation_config  # noqa: E402
from farm_paths import RACK  # noqa: E402  (the main folder's rack, also from a lane worktree)
from farm_phone_identity import PhoneIdentity  # noqa: E402
from farm_reel_test_media import render, colour_code  # noqa: E402
from farm_video import VideoDrafts, VideoTransferPackage  # noqa: E402

PC_LAN = '192.168.4.26'
BACKEND_PORTS = {18: 9915, 20: 9925, 17: 9935, 16: 9945}
PLATFORMS = {   # format, caption, label, route, capability key, whether a fixed signed-in account is required
    'reel': ('ig_reel', 'Fresh reel acceptance', 'REEL DRAFT TEST', 'reel-creations', 'reelCreation', True),
    'tiktok': ('tt_video', 'Fresh tiktok acceptance', 'TIKTOK DRAFT TEST', 'tiktok-creations', 'tiktokCreation', True),
    'x': ('x_video', 'Fresh x acceptance', 'X DRAFT TEST', 'x-creations', 'xCreation', False),
    'youtube': ('yt_short', 'Fresh short test', 'SHORT DRAFT TEST', 'youtube-creations', 'youtubeCreation', False),
}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', required=True, choices=sorted(PLATFORMS))
    parser.add_argument('--slot', required=True, type=int, choices=sorted(BACKEND_PORTS))
    parser.add_argument('--phone-ip', required=True)
    parser.add_argument('--account')
    args = parser.parse_args()
    fmt, caption, label, route, capability, pinned = PLATFORMS[args.platform]
    if pinned != (args.account is not None):
        raise SystemExit(f'{args.platform} needs ' + ('the handle signed in on that phone.' if pinned else 'no account: creation binds the signed-in one.'))

    rack = load(RACK / 'preparation.json')
    kernel = Path(rack['kernel'])
    if sha(kernel.with_suffix('.dll')) != rack['kernelSha256']: raise SystemExit('Multi-phone kernel changed.')
    data = Path(rack['runDirectory']) / 'data'
    for name, digest in rack['dataSha256'].items():
        if sha(data / name) != digest: raise SystemExit(f'Multi-phone {name} changed.')
    board = next((b for b, s in rack['slots'].items() if s == args.slot), None)
    if board is None or board not in rack['inputEnabled']: raise SystemExit(f'Slot {args.slot} has no input-enabled board.')
    device = [d for d in load(data / 'devices.json') if d['pid'] == board]
    receiver = [r for r in load(data / 'receivers.json') if r['BoardPid'] == board]
    if len(device) != 1 or len(receiver) != 1 or device[0]['deviceid'] != receiver[0]['DeviceId']:
        raise SystemExit(f'Board {board} has no single phone and receiver.')
    phone = PhoneIdentity(board=board, device_id=device[0]['deviceid'], receiver=receiver[0]['Name'], slot=args.slot)

    window = HERE / 'windows' / f'{args.platform}-slot{args.slot}'
    run = next(ROOT / f'output/candidate-runs/farm-{args.platform}-slot{args.slot}-{date.today():%Y%m%d}-{n}' for n in range(1, 100)
               if not (ROOT / f'output/candidate-runs/farm-{args.platform}-slot{args.slot}-{date.today():%Y%m%d}-{n}').exists())
    if (window / 'preparation.json').exists(): raise SystemExit('This window is prepared; archive it before preparing again.')
    window.mkdir(parents=True, exist_ok=True)
    config = dict(version=2, api='http://127.0.0.1:9916/api', kernelSha256=rack['kernelSha256'], expectedUid=device[0]['uid'],
                  phone=phone.as_config(), allowed=list(rack['inputEnabled']), account=args.account,
                  mediaBind=PC_LAN, mediaClient=args.phone_ip, mediaPort=MEDIA_PORTS[args.slot])
    config_path = window / 'creation-config.json'
    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    creation_config(config_path, 'live')   # The backend's own strict check, before anything else is written.

    backend = run / 'backend'
    token = uuid.uuid4().hex[:12]
    stage = backend / 'stage' / board; stage.mkdir(parents=True)
    video = render(token, stage / f'{args.platform}-{token}.mp4', label=label)
    raw = video.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    (stage / 'manifest.json').write_text(json.dumps({'deviceId': board, 'assets': [
        {'url': f'/stage/{board}/{video.name}', 'sha256': digest, 'bytes': len(raw)}]}), encoding='utf-8')
    videos = VideoDrafts(backend / 'video-drafts.db', backend / 'stage', board)
    draft = videos.create(dict(id=str(uuid.uuid4()), device_id=board, format=fmt, name=video.name, sha256=digest,
                               title=f'{args.platform} slot {args.slot} ' + token[:6], caption=caption))
    package = videos.export(draft['id'], draft['revision'])
    parsed = VideoTransferPackage(package, board)

    import imouse_farm_server as server   # The fingerprint the live backend reports; simulation, no listener.
    with tempfile.TemporaryDirectory(prefix='window-source-hash-') as directory:
        source_hash = server.FarmBackendRuntime(Path(directory) / 'farm.db', Path(directory) / 'stage').source_hash
    preparation = dict(platform=args.platform, route=route, capability=capability, slot=args.slot, phone=phone.as_config(),
                       runDirectory=str(run), backendData=str(backend), backendPort=BACKEND_PORTS[args.slot],
                       mediaPort=MEDIA_PORTS[args.slot], config=str(config_path), configSha256=sha(config_path),
                       kernel=str(kernel), kernelSha256=rack['kernelSha256'], rackPreparation=str(RACK / 'preparation.json'),
                       account=args.account, videoDraftId=draft['id'], revision=draft['revision'], caption=caption, testToken=token,
                       colourCode=colour_code(token), videoSha256=draft['sha256'], packageSha256=hashlib.sha256(package).hexdigest(),
                       downloadName=parsed.download_name, backendSourceHash=source_hash,
                       serviceStarted=False, phoneInput=False)
    (window / 'preparation.json').write_text(json.dumps(preparation, indent=2), encoding='utf-8')
    print(json.dumps(dict(prepared=True, window=str(window.relative_to(HERE)), phone=phone.receiver, board=board,
                          backendPort=preparation['backendPort'], mediaPort=preparation['mediaPort'], caption=caption)))


if __name__ == '__main__':
    main()
