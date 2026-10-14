"""Archive this completed experiment locally, refusing to replace an existing archive."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

RECORD = Path(__file__).resolve().parent
REPO = RECORD.parents[1]
ARCHIVE = REPO.parent / 'iMouseXP-2.0-evidence-archive/20261014-hid-input-replies'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_text(path):
    data = path.read_bytes()
    return data.decode('utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')


def main():
    if ARCHIVE.exists():
        raise SystemExit('Archive exists; verify it instead of replacing it.')
    assert '245 tests passed' in read_text(RECORD / 'kernel-self-tests-final.txt')
    assert '30 parser/monitor checks and 6 argument cases passed' in read_text(RECORD / 'reader-self-tests.txt')
    for name, count in [('export-tests.txt', 23), ('capture-guard-tests.txt', 3)]:
        log = read_text(RECORD / name)
        assert f'Ran {count} tests' in log and 'OK' in log
    restoration = json.loads(read_text(RECORD / 'final-restoration.json'))
    assert all(restoration[key] for key in ('same_release_processes', 'c24c_free',
        'c241_unchanged_since_capture', 'protected_hashes_unchanged'))

    source = set()
    for folder in ('src/iMouse.Kernel', 'tools/hid-input-capture'):
        source.update(p for p in (REPO / folder).rglob('*') if p.is_file()
            and p.suffix in ('.cs', '.csproj') and not {'bin', 'obj'}.intersection(p.relative_to(REPO).parts))
    for name in ('tools/capture_c24c_replies.py', 'tools/test_capture_c24c_replies.py',
        'tools/analyze_hid_reply_capture.py', 'tools/vendor_hid_decode.py',
        'tools/export_diagnostics.py', 'tools/test_export_diagnostics.py',
        'PROGRESS.md', 'RESUME-NEXT.md', 'analysis/HID-PROTOCOL.md', '.gitattributes'):
        path = REPO / name
        if path.is_file():
            source.add(path)
    for name in ('Directory.Build.props', 'Directory.Build.targets', 'global.json', 'NuGet.Config'):
        path = REPO / name
        if path.is_file():
            source.add(path)
    binaries = [p for folder in ('capture-build', 'kernel-build') for p in (RECORD / folder).glob('*')
        if p.is_file() and p.suffix in ('.exe', '.dll', '.pdb')]
    base = subprocess.check_output(['git', '-c', f'safe.directory={REPO.as_posix()}',
        'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    validation = {
        'utc': datetime.now(timezone.utc).isoformat(), 'base_commit': base,
        'source_state': 'Uncommitted source hash snapshot; these hashes identify the tested files.',
        'kernel_self_tests': 245, 'capture_parser_monitor_tests': 30,
        'capture_argument_cases': 6, 'overlap': 'The 30 parser/monitor checks are also in the kernel suite.',
        'export_tests': 23, 'capture_guard_tests': 3,
        'live_runs': [json.loads(read_text(RECORD / run / 'summary.json')) for run in ('live-01', 'live-03')],
        'preflight_only': 'live-02 aborted before lease acquisition, reader startup or input.',
        'final_restoration': restoration,
        'binaries': {p.relative_to(REPO).as_posix(): digest(p) for p in sorted(binaries)},
        'sources': {p.relative_to(REPO).as_posix(): digest(p) for p in sorted(source)},
        'full_candidate_kernel_live': False, 'installed_or_promoted': False,
    }
    (RECORD / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n', encoding='utf-8')

    ARCHIVE.mkdir(parents=True, exist_ok=False)
    files = [(p, Path('source') / p.relative_to(REPO)) for p in source]
    files += [(p, Path('record') / p.relative_to(RECORD)) for p in RECORD.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.name != 'archive-verification.json']
    hashes = []
    total = 0
    for original, relative in sorted(files):
        target = ARCHIVE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = digest(original)
        shutil.copy2(original, target)
        if digest(target) != before or digest(original) != before:
            raise RuntimeError(f'Copy or source changed: {relative}')
        hashes.append(f'{before}  {relative.as_posix()}\n')
        total += original.stat().st_size
    manifest = ARCHIVE / 'SHA256SUMS.txt'
    manifest.write_text(''.join(hashes), encoding='utf-8', newline='\n')
    # Read the saved manifest back, then independently verify every copied file.
    for line in manifest.read_text(encoding='utf-8').splitlines():
        expected, relative = line.split('  ', 1)
        if digest(ARCHIVE / relative) != expected:
            raise RuntimeError(f'Archive readback failed: {relative}')
    receipt = {'archive': str(ARCHIVE), 'files': len(files), 'bytes': total,
        'manifest_sha256': digest(manifest), 'verified_against_sources': True,
        'manifest_readback_verified': True, 'off_machine_backup': False,
        'receipt_excluded_from_manifest': True}
    encoded = json.dumps(receipt, indent=2) + '\n'
    (RECORD / 'archive-verification.json').write_text(encoded, encoding='utf-8')
    (ARCHIVE / 'archive-verification.json').write_text(encoded, encoding='utf-8')
    print(encoded)


if __name__ == '__main__':
    main()
