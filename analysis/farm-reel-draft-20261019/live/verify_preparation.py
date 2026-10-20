"""Read-only recheck of the prepared Reel window. No socket, phone or service.

Run immediately before Start-ReelWindow.ps1. Any changed source, binary,
mapping, test media or protected installed file stops the window.
"""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'tools'))


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    prep = load(HERE/'preparation.json')
    problems = []
    for name, digest in prep['productSources'].items():
        if sha(ROOT/name) != digest: problems.append('Product source changed: ' + name)
    # The live Start script refuses a different backend fingerprint; catch that here, offline.
    import imouse_farm_server as server  # Same fingerprint code the live backend reports; simulation, no listener.
    with tempfile.TemporaryDirectory(prefix='verify-source-hash-') as directory:
        if server.FarmBackendRuntime(Path(directory)/'farm.db', Path(directory)/'stage').source_hash != prep['backendSourceHash']:
            problems.append('Backend source fingerprint changed; Start would refuse. Re-prepare this window.')
    for path, digest in ((prep['assembly'], prep['nativeSha256']), (Path(prep['kernel']).with_suffix('.dll'), prep['kernelSha256']),
                         (prep['nativeProbe'], prep['nativeProbeSha256']), (prep['receiver'], prep['receiverSha256'])):
        if sha(path) != digest: problems.append('Prepared binary changed: ' + str(path))
    data = Path(prep['runDirectory'])/'data'
    devices, receivers = load(data/'devices.json'), load(data/'receivers.json')
    if (len(devices) != 1 or devices[0]['pid'] != 'C24C' or devices[0]['uid'] != prep['expectedUid']
            or len(receivers) != 1 or receivers[0]['DeviceId'] != prep['expectedDeviceId'] or receivers[0]['Name'] != 'iMouse2-C24C'):
        problems.append('C24C-only mapping changed.')
    from farm_video import VideoDrafts
    package = VideoDrafts(Path(prep['backendData'])/'video-drafts.db', Path(prep['backendData'])/'stage').export(prep['videoDraftId'], prep['revision'])
    if hashlib.sha256(package).hexdigest() != prep['packageSha256']: problems.append('Prepared Reel package changed.')
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        if archive.read('caption.txt').decode('utf-8') != prep['caption']: problems.append('Prepared caption changed.')
    for value in load(HERE/'protected-before.json'):
        if sha(value['path']) != value['sha256']: problems.append('Protected installed file changed: ' + value['path'])
    for folder in (HERE/'native-reel-1', Path(prep['runDirectory'])/'native-reel-1-data', Path(prep['backendData'])/'reel-creations'):
        if folder.exists(): problems.append('A previous attempt exists; never replay it: ' + str(folder))
    result = dict(ready=not problems, problems=problems, phoneInput=False, serviceStarted=False)
    (HERE/'preparation-recheck.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    return 0 if not problems else 2


if __name__ == '__main__':
    raise SystemExit(main())
