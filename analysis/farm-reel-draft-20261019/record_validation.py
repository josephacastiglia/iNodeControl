"""Record what was validated offline and pin the exact product bytes. No socket or phone."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRODUCT = ['tools/' + n for n in (
    'farm_format_coverage.py', 'farm_capabilities.py', 'farm_reel_layout.py', 'farm_reel_controls.json', 'farm_reel_creation.py',
    'farm_reel_runs.py', 'farm_reel_test_media.py', 'farm_video.py', 'farm_media_transfer.py', 'farm_transitions.py',
    'imouse_farm_server.py')] + ['src/iMouse.Console/' + n for n in (
    'FarmDraftRunWindow.cs', 'VideoDraftWindow.cs', 'FarmReadinessWindow.cs', 'FarmPreparationWindow.cs', 'MainWindow.FarmJobs.cs')]
TESTS = ['tools/' + n for n in ('test_farm_format_coverage.py', 'test_farm_reel_layout.py', 'test_farm_reel_creation.py',
                                'test_farm_reel_runs.py')]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    log = (HERE/'python-full.txt').read_text(encoding='utf-8', errors='replace')
    ran = re.findall(r'^Ran (\d+) tests? in ([\d.]+)s', log, re.M)
    skipped = re.findall(r'skipped=(\d+)', log)
    native = json.loads((HERE/'native-summary.json').read_text(encoding='utf-8-sig'))
    value = dict(
        python=dict(tests=int(ran[-1][0]) if ran else None, seconds=float(ran[-1][1]) if ran else None,
                    passed=bool(ran) and '\nOK' in log[log.rfind('Ran '):] and 'FAILED' not in log[log.rfind('Ran '):],
                    skipped=int(skipped[-1]) if skipped else 0, exitLine=log.strip().splitlines()[-1] if log.strip() else None),
        native=dict(passed=native.get('passed'), exitCode=native.get('exitCode'), dllSha256=native.get('dllSha256')),
        productSources={name: sha(ROOT/name) for name in PRODUCT}, testSources={name: sha(ROOT/name) for name in TESTS},
        phoneInput=False, desktopControl=False, serviceStarted=False, publishing=False, messaging=False,
        liveAccepted=False, meaning='Offline candidate checks only; retained frames and simulated HID, not fresh-phone acceptance.')
    (HERE/'validation.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: value[k] for k in ('python', 'native')}))


if __name__ == '__main__':
    main()
