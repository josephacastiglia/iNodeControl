"""Archive the live retry; reference the already verified immutable candidate archive."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

record = Path(__file__).resolve().parent
repo = record.parents[1]
root = (repo.parent / 'iMouseXP-2.0-evidence-archive').resolve()
archive = root / '20261013-candidate-retry'
assert archive.resolve().is_relative_to(root) and not archive.exists()
sha = lambda file: hashlib.sha256(file.read_bytes()).hexdigest()
row = lambda file: {'sha256': sha(file), 'bytes': file.stat().st_size}
inventory = lambda folder: {file.relative_to(folder).as_posix(): row(file) for file in folder.rglob('*') if file.is_file()}
git = ['git', '-c', f'safe.directory={repo.as_posix()}']
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=repo, text=True).strip()
assert not subprocess.check_output(git + ['diff', 'HEAD'], cwd=repo)
final = json.loads((record / 'restoration-final.json').read_text(encoding='utf-8-sig'))
assert final['both_mirroring'] and final['both_free']
guard_record = repo / 'analysis/runtime-startup-guard-20261013'
preserved = json.loads((guard_record / 'archive-verification.json').read_text(encoding='utf-8'))
candidate_archive = Path(preserved['archive'])
package = candidate_archive / 'review-package'
manifest = json.loads((package / 'package.json').read_text(encoding='utf-8'))
expected_package = json.loads((guard_record / 'package-result.json').read_text(encoding='utf-8'))
assert row(package / 'package.json') == expected_package['package_manifest']
assert all(row(package / name) == value for name, value in manifest['files'].items())
run = repo / 'output/candidate-runs/runtime-guard-20261013'
for component in ('kernel', 'console'):
    for name, value in manifest['files'].items():
        prefix = 'payload/' + component + '/'
        if name.startswith(prefix):
            assert row(run / component / 'bin' / name[len(prefix):]) == value
files = {}
for source, prefix in ((record, 'record'), (run, 'tested-run')):
    for file in source.rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts:
            files[prefix + '/' + file.relative_to(source).as_posix()] = file
for name in ('PROGRESS.md', 'WORK-REMAINING.md', 'FINISH-CRITERIA.md', 'docs/CANDIDATE-ACCEPTANCE.md', 'tools/gate4_1000_tap_suite.py'):
    files['project-record/' + name] = repo / name
archive.mkdir(parents=True)
for name, source in files.items():
    target = archive / name
    assert target.resolve().is_relative_to(archive.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = row(source)
    shutil.copy2(source, target)
    assert row(target) == expected == row(source), name
reference = {'archive': str(candidate_archive), 'receipt': preserved,
    'package_manifest': row(package / 'package.json'), 'all_package_files_reverified': True,
    'tested_managed_binaries_match_package': True}
(archive / 'CANDIDATE-ARCHIVE.json').write_text(json.dumps(reference, indent=2), encoding='utf-8')
bundle = archive / 'candidate-branch.bundle'
subprocess.run(git + ['bundle', 'create', str(bundle), 'local/combined-candidate-20261012'], cwd=repo, capture_output=True, check=True)
checked = subprocess.run(git + ['bundle', 'verify', str(bundle)], cwd=repo, capture_output=True, check=True)
(archive / 'bundle-verification.txt').write_bytes(checked.stdout + checked.stderr)
rows = inventory(archive)
(archive / 'SHA256SUMS.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
assert all(row(archive / name) == expected for name, expected in rows.items())
receipt = {'archive': str(archive), 'source_commit': commit, 'files': len(rows), 'bytes': sum(x['bytes'] for x in rows.values()),
    'all_hashes_verified': True, 'git_bundle_verified': True,
    'candidate_archive': str(candidate_archive), 'candidate_package_reverified': True,
    'tested_managed_binaries_match_package': True, 'release_restored_both_live_and_free': True,
    'restoration_record': 'record/restoration-final.json', 'C241_input_sent': False,
    'upward_home_gesture_failed': True, 'release_acceptance_complete': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
