"""Offline preparation for one C24C TikTok acceptance window. No socket, phone or service.

Creates an isolated run folder: a byte-identical copy of the verified C24C
kernel mapping/calibration, a fresh backend data folder holding one labelled
TikTok test video copy, and the pinned identities the live scripts check. It
refuses to overwrite an existing run, never reads operator settings and starts
nothing. The private kernel, receiver and backend are started only during an
agreed window by live/Start-TikTokWindow.ps1.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from farm_tiktok_layout import TikTokReference, caption_supported  # noqa: E402
from farm_reel_test_media import render, colour_code  # noqa: E402
from farm_video import VideoDrafts, VideoTransferPackage  # noqa: E402

P2 = ROOT/'analysis/farm-recovery-live-20261019'
RUN = ROOT/'output/candidate-runs/farm-tiktok-20261019'
PROBE = ROOT/'output/farm-tiktok-native-probe-20261019'
CAPTION = 'Fresh tiktok acceptance'   # One visible line beside the cover card; no I/l-ambiguous capitals.
SOURCES = ['tools/' + name for name in (
    'imouse_farm_server.py', 'farm_tiktok_layout.py', 'farm_tiktok_controls.json', 'farm_tiktok_creation.py', 'farm_tiktok_runs.py',
    'farm_reel_layout.py', 'farm_reel_controls.json', 'farm_reel_creation.py', 'farm_reel_runs.py', 'farm_reel_test_media.py',
    'farm_video.py', 'farm_media_transfer.py', 'farm_transitions.py', 'farm_draft_creation.py', 'farm_draft_workflow.py',
    'farm_draft_transport.py', 'farm_creation_layout.py', 'farm_observations.py', 'farm_format_coverage.py', 'farm_permission_prompts.py')]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    if RUN.exists(): raise SystemExit('This TikTok run folder already exists; never overwrite or reuse a window.')
    previous = load(P2/'preparation.json')
    native = load(HERE/'native-summary.json')
    if native.get('exitCode') != 0 or not native.get('passed'): raise SystemExit('Native headless checks have not passed.')
    assembly = Path(native['output'])/'iMouse2.dll'
    if sha(assembly) != native['dllSha256']: raise SystemExit('Prepared native assembly changed.')
    kernel = Path(previous['kernel'])
    if sha(kernel.with_suffix('.dll')) != previous['kernelSha256']: raise SystemExit('Prepared private kernel changed.')
    config = load(ROOT/'analysis/farm-recovery-20261019/creation-config.json')
    if (config['kernelSha256'] != previous['kernelSha256'] or config['expectedUid'] != previous['expectedUid']
            or config['api'] != 'http://127.0.0.1:9916/api' or config['mediaPort'] != 9917):
        raise SystemExit('Isolated creation configuration does not match the verified kernel.')
    source_data = Path(previous['runDirectory'])/'data'
    devices, receivers = load(source_data/'devices.json'), load(source_data/'receivers.json')
    calibration = load(source_data/'pointer-calibration.json')
    if (len(devices) != 1 or devices[0]['pid'] != 'C24C' or devices[0]['uid'] != previous['expectedUid']
            or len(receivers) != 1 or receivers[0]['DeviceId'] != previous['expectedDeviceId'] or receivers[0]['Name'] != 'iMouse2-C24C'
            or len(calibration) != 1 or calibration[0].get('Pid') != 'C24C'):
        raise SystemExit('C24C-only mapping changed.')
    protected = load(P2/'protected-before.json')
    for value in protected:
        if sha(value['path']) != value['sha256']: raise SystemExit('Protected installed file changed: ' + value['path'])
    if not caption_supported(CAPTION): raise SystemExit('Prepared description is outside the TikTok candidate.')
    if not (PROBE/'TikTokProbe.exe').is_file(): raise SystemExit('Build the TikTok probe first.')

    data, backend = RUN/'data', RUN/'backend'
    data.mkdir(parents=True)
    for name in ('devices.json', 'receivers.json', 'pointer-calibration.json'):
        shutil.copyfile(source_data/name, data/name)
        if sha(data/name) != sha(source_data/name): raise SystemExit('Mapping copy is not byte-identical.')
    arguments = [str(data) if a == str(source_data) else str(data/'receivers.json') if a == str(source_data/'receivers.json') else a
                 for a in previous['arguments']]
    if str(source_data) in ' '.join(arguments): raise SystemExit('Kernel arguments still reference the previous window.')
    receiver = Path(arguments[arguments.index('--receiver')+1]); runtime = Path(arguments[arguments.index('--receiver-runtime')+1])
    if not receiver.is_file() or not runtime.is_dir(): raise SystemExit('The verified private receiver or its runtime is missing.')

    token = uuid.uuid4().hex[:12]
    stage = backend/'stage/C24C'; stage.mkdir(parents=True)
    video = render(token, stage/f'tiktok-{token}.mp4', label='TIKTOK DRAFT TEST')
    raw = video.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    (stage/'manifest.json').write_text(json.dumps({'deviceId': 'C24C', 'assets': [
        {'url': f'/stage/C24C/{video.name}', 'sha256': digest, 'bytes': len(raw)}]}), encoding='utf-8')
    videos = VideoDrafts(backend/'video-drafts.db', backend/'stage')
    draft = videos.create(dict(id=str(uuid.uuid4()), device_id='C24C', format='tt_video', name=video.name, sha256=digest,
                               title='TikTok acceptance ' + token[:6], caption=CAPTION))
    package = videos.export(draft['id'], draft['revision'])
    parsed = VideoTransferPackage(package)
    reference = TikTokReference(parsed.video)

    sources = {name: sha(ROOT/name) for name in SOURCES}
    import imouse_farm_server as server  # Same fingerprint code the live backend reports; simulation, no listener.
    with tempfile.TemporaryDirectory(prefix='tiktok-source-hash-') as directory:
        source_hash = server.FarmBackendRuntime(Path(directory)/'farm.db', Path(directory)/'stage').source_hash
    preparation = dict(
        runDirectory=str(RUN), backendData=str(backend), config=str(ROOT/'analysis/farm-recovery-20261019/creation-config.json'),
        kernel=str(kernel), kernelSha256=previous['kernelSha256'], arguments=arguments, expectedDeviceId=previous['expectedDeviceId'],
        expectedUid=previous['expectedUid'], assembly=str(assembly), nativeSha256=native['dllSha256'],
        nativeProbe=str(PROBE/'TikTokProbe.exe'), nativeProbeSha256=sha(PROBE/'TikTokProbe.exe'),
        nativeProbeManagedSha256=sha(PROBE/'TikTokProbe.dll'),
        videoDraftId=draft['id'], revision=draft['revision'], caption=CAPTION, testToken=token, colourCode=colour_code(token),
        videoSha256=draft['sha256'], videoSeconds=draft['video']['seconds'], packageSha256=hashlib.sha256(package).hexdigest(),
        downloadName=parsed.download_name, sampledFrames=reference.count, durationLabel=reference.clock,
        mediaBind=config['mediaBind'], mediaClient=config['mediaClient'], productSources=sources,
        backendSourceHash=source_hash, receiver=str(receiver), receiverSha256=sha(receiver),
        protectedFiles=len(protected), serviceStarted=False, phoneInput=False, desktopControl=False, receiverRuntimeFrom=previous['runDirectory'])
    (HERE/'live').mkdir(exist_ok=True)
    (HERE/'live/preparation.json').write_text(json.dumps(preparation, indent=2), encoding='utf-8')
    (HERE/'live/protected-before.json').write_text(json.dumps(protected, indent=2), encoding='utf-8')
    options = dict(assembly=str(assembly), nativeSha256=native['dllSha256'], draftId=draft['id'], revision=draft['revision'],
                   backendSourceHash=source_hash, output=str(HERE/'live/native-tiktok-1'), dataDirectory=str(RUN/'native-tiktok-1-data'))
    (HERE/'live/native-options-1.json').write_text(json.dumps(options, indent=2), encoding='utf-8')
    dry = dict(options, output=str(HERE/'live/native-dry-run'), dataDirectory=str(RUN/'native-dry-run-data'), dryRun=True)
    (HERE/'live/native-dry-options.json').write_text(json.dumps(dry, indent=2), encoding='utf-8')
    print(json.dumps(dict(prepared=True, run=str(RUN), downloadName=parsed.download_name, caption=CAPTION,
                          videoSha256=draft['sha256'], serviceStarted=False, phoneInput=False)))


if __name__ == '__main__':
    main()
