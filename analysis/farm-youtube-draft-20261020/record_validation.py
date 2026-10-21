"""Record what was validated offline and pin the exact product bytes. No socket or phone."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRODUCT = ['tools/' + n for n in (
    'farm_youtube_layout.py', 'farm_youtube_controls.json', 'farm_youtube_creation.py', 'farm_youtube_runs.py',
    'farm_format_coverage.py', 'farm_capabilities.py', 'farm_video.py', 'farm_tiktok_layout.py', 'farm_permission_prompts.py',
    'farm_reel_creation.py', 'farm_reel_runs.py', 'farm_creation_runs.py', 'farm_transitions.py', 'farm_draft_creation.py',
    'farm_draft_workflow.py', 'imouse_farm_server.py')] + ['src/iMouse.Console/' + n for n in (
    'FarmDraftRunWindow.cs', 'VideoDraftWindow.cs')] + ['Open Marketing Farm Candidate.ps1']
TESTS = ['tools/' + n for n in ('test_farm_youtube_layout.py', 'test_farm_youtube_creation.py', 'test_farm_youtube_runs.py',
                                'test_farm_reel_runs.py', 'test_farm_video.py', 'test_farm_format_coverage.py')] + [
    'src/iMouse.Console/' + n for n in ('FarmDraftRunTests.cs', 'VideoDraftTests.cs')]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_fingerprint():
    """The backend fingerprint the server reports and the launcher recomputes, over the pinned list."""
    server = (ROOT/'tools/imouse_farm_server.py').read_text(encoding='utf-8')
    names = re.findall(r'"([^"]+)"', re.search(r'b"".join\(\(source / name\)\.read_bytes\(\) for name in \(([^)]*)\)', server).group(1))
    return len(names), hashlib.sha256(b''.join((ROOT/'tools'/name).read_bytes() for name in names)).hexdigest()


def main():
    log = (HERE/'python-full.txt').read_text(encoding='utf-8', errors='replace')
    ran = re.findall(r'^Ran (\d+) tests? in ([\d.]+)s', log, re.M)
    skipped = re.findall(r'skipped=(\d+)', log)
    native = json.loads((HERE/'native-summary.json').read_text(encoding='utf-8-sig'))
    controls = json.loads((HERE/'youtube-controls-check.json').read_text(encoding='utf-8'))
    files, fingerprint = source_fingerprint()
    value = dict(
        python=dict(tests=int(ran[-1][0]) if ran else None, seconds=float(ran[-1][1]) if ran else None,
                    passed=bool(ran) and '\nOK' in log[log.rfind('Ran '):] and 'FAILED' not in log[log.rfind('Ran '):],
                    skipped=int(skipped[-1]) if skipped else 0, exitLine=log.strip().splitlines()[-1] if log.strip() else None),
        native=dict(passed=native.get('passed'), exitCode=native.get('exitCode'), dllSha256=native.get('dllSha256')),
        controls=dict(templates=len(controls), allChecksAsExpected=all(r['accepted'] == r['expected'] for v in controls.values()
                                                                        for r in v['checks'])),
        backendSourceFingerprint=dict(files=files, sha256=fingerprint,
                                      note='Working-tree bytes of this branch; preparing a live window recomputes it.'),
        productSources={name: sha(ROOT/name) for name in PRODUCT}, testSources={name: sha(ROOT/name) for name in TESTS},
        phoneInput=False, desktopControl=False, serviceStarted=False, publishing=False, messaging=False,
        liveAccepted=False, livePrepared=False,
        meaning='Offline candidate checks only; retained frames and simulated HID, not fresh-phone acceptance.')
    (HERE/'validation.json').write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: value[k] for k in ('python', 'native', 'controls', 'backendSourceFingerprint')}))


if __name__ == '__main__':
    main()
