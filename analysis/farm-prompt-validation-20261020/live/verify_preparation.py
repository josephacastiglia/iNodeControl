"""Read-only recheck of the prepared prompt-validation window. No socket, phone or service.

Start-PromptWindow.ps1 runs it before each part. Any changed source, binary, C24C-only mapping
or protected installed file stops the window. It never reads trial results.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MAPPING = ('devices.json', 'receivers.json', 'pointer-calibration.json')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--part', choices=('A', 'B'), required=True)
    args = parser.parse_args()
    prep = load(HERE/'preparation.json')
    problems = []
    if Path(prep['root']).resolve() != ROOT.resolve(): problems.append('The window was prepared in a different checkout; prepare it here.')
    for name, digest in prep['productSources'].items():
        if not (ROOT/name).is_file() or sha(ROOT/name) != digest: problems.append('Product source changed: ' + name)
    kernel = Path(prep['kernel'])
    if not kernel.is_file() or sha(kernel.with_suffix('.dll')) != prep['kernelSha256']: problems.append('Prepared kernel changed.')
    elif not all(text.encode('utf-16-le') in kernel.with_suffix('.dll').read_bytes() for text in prep['kernelProbeStrings']):
        problems.append('The kernel build lacks the move-only absolute probe.')
    if sha(prep['receiver']) != prep['receiverSha256'] or not Path(prep['receiverRuntime']).is_dir():
        problems.append('Prepared receiver or runtime changed.')
    part = prep['parts'][args.part]
    data = Path(part['data'])
    for name, digest in part['mapping'].items():
        if sha(data/name) != digest: problems.append(f'Part {args.part} mapping changed: {name}')
    devices, receivers = load(data/'devices.json'), load(data/'receivers.json')
    if (len(devices) != 1 or devices[0]['pid'] != 'C24C' or devices[0]['uid'] != prep['expectedUid']
            or len(receivers) != 1 or receivers[0]['DeviceId'] != prep['expectedDeviceId'] or receivers[0]['Name'] != 'iMouse2-C24C'):
        problems.append('C24C-only mapping changed.')
    probe = ['--hid-replies-pid', 'C24C', '--absolute-probe-pid', 'C24C']
    arguments = part['arguments']
    if (arguments[0] != 'http://127.0.0.1:9916/api/' or arguments[arguments.index('--input-pid')+1] != 'C24C'
            or arguments[arguments.index('--data-dir')+1] != str(data)
            or (arguments[-4:] == probe) != (args.part == 'B') or ('--absolute-probe-pid' in arguments) != (args.part == 'B')):
        problems.append(f'Part {args.part} kernel arguments changed.')
    for value in load(HERE/'protected-before.json'):
        if sha(value['path']) != value['sha256']: problems.append('Protected installed file changed: ' + value['path'])
    result = dict(part=args.part, ready=not problems, problems=problems, phoneInput=False, serviceStarted=False,
                  utc=datetime.now(timezone.utc).isoformat())
    (HERE/f'preparation-recheck-{args.part}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    return 0 if not problems else 2


if __name__ == '__main__':
    raise SystemExit(main())
