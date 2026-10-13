"""Preserve this offline repair, exact package, prepared run and local branch."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

record = Path(__file__).resolve().parent
repo = record.parents[1]
root = (repo.parent / 'iMouseXP-2.0-evidence-archive').resolve()
archive = root / '20261013-runtime-startup-guard'
assert archive.resolve().is_relative_to(root) and not archive.exists()
sha = lambda file: hashlib.sha256(file.read_bytes()).hexdigest()
row = lambda file: {'sha256': sha(file), 'bytes': file.stat().st_size}
inventory = lambda folder: {file.relative_to(folder).as_posix(): row(file) for file in folder.rglob('*') if file.is_file()}
git = ['git', '-c', f'safe.directory={repo.as_posix()}']
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=repo, text=True).strip()
assert not subprocess.check_output(git + ['diff', 'HEAD'], cwd=repo)
prepared = json.loads((record / 'preparation.json').read_text(encoding='utf-8'))
run = Path(prepared['run_directory'])
expected_run = json.loads((record / 'run-inventory.json').read_text(encoding='utf-8'))
assert inventory(run) == expected_run
files = {}
package = repo / 'output/staging/combined-runtime-guard-20261013'
for source, prefix in ((record, 'record'), (package, 'review-package'), (run, 'prepared-run')):
    for file in source.rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts:
            files[prefix + '/' + file.relative_to(source).as_posix()] = file
for name in ('PROGRESS.md', 'WORK-REMAINING.md', 'FINISH-CRITERIA.md', 'docs/CANDIDATE-ACCEPTANCE.md'):
    files['project-record/' + name] = repo / name
archive.mkdir(parents=True)
for name, source in files.items():
    target = archive / name
    assert target.resolve().is_relative_to(archive.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = row(source)
    shutil.copy2(source, target)
    assert row(target) == expected == row(source), name
bundle = archive / 'candidate-branch.bundle'
subprocess.run(git + ['bundle', 'create', str(bundle), 'local/combined-candidate-20261012'], cwd=repo, capture_output=True, check=True)
checked = subprocess.run(git + ['bundle', 'verify', str(bundle)], cwd=repo, capture_output=True, check=True)
(archive / 'bundle-verification.txt').write_bytes(checked.stdout + checked.stderr)
checked = subprocess.run(['python', str(archive / 'review-package/verify_package.py'), 'verify', '--bundle', str(archive / 'review-package')], capture_output=True, check=True)
(archive / 'package-verification.txt').write_bytes(checked.stdout + checked.stderr)
rows = inventory(archive)
(archive / 'SHA256SUMS.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
assert all(row(archive / name) == expected for name, expected in rows.items())
assert inventory(archive / 'prepared-run') == expected_run
receipt = {'archive': str(archive), 'source_commit': commit, 'files': len(rows), 'bytes': sum(x['bytes'] for x in rows.values()),
    'all_hashes_verified': True, 'prepared_run_inventory_verified': True,
    'git_bundle_verified': True, 'archived_review_package_verified': True,
    'candidate_launched': False, 'phone_input_sent': False,
    'source_record': 'record/REPORT.md', 'kernel_self_tests_passed': 206, 'cli_checks_passed': 3}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
