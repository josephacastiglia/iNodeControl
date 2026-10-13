"""Preserve candidate preparation and records, without launching or changing the rack."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
import stage_release as p

root = (repo.parent / 'iMouseXP-2.0-evidence-archive').resolve()
archive = root / '20261012-candidate-acceptance'
assert archive.resolve().is_relative_to(root) and not archive.exists()
result = p.load(record / 'preparation.json')
assert result['prepared'] and not result['service_started'] and not result['window_shown'] and not result['rack_contacted']
run = Path(result['run_directory'])
assert p.inventory(run, 'no-manifest') == p.load(record / 'run-inventory.json')
git = ['git', '-c', f'safe.directory={repo.as_posix()}']
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=repo, text=True).strip()
assert not subprocess.check_output(git + ['diff', 'HEAD', '--', 'docs', 'FINISH-CRITERIA.md', 'PROGRESS.md', 'WORK-REMAINING.md'], cwd=repo)
files = {}
for file in record.iterdir():
    if file.is_file(): files['record/' + file.name] = file
for folder, prefix in ((run, 'prepared-run'),
    (repo / 'output/candidate-runs/combined-acceptance-20261012', 'attempt-1'),
    (repo / 'output/candidate-runs/combined-acceptance-final-20261012', 'attempt-2')):
    for file in folder.rglob('*'):
        if file.is_file(): files[prefix + '/' + file.relative_to(folder).as_posix()] = file
for name in ('docs/CANDIDATE-ACCEPTANCE.md', 'docs/RELEASE-STAGING.md', 'docs/OPERATOR-GUIDE.md',
    'FINISH-CRITERIA.md', 'PROGRESS.md', 'WORK-REMAINING.md',
    'analysis/input-cleanup-20261012/console-manifest.json', 'analysis/persistence-20261012/kernel-manifest.json',
    'analysis/runtime-provenance-20261012/archive-verification.json'):
    files['project-record/' + name] = repo / name
archive.mkdir(parents=True)
for name, source in files.items():
    target = p.safe(archive, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = p.row(source)
    shutil.copy2(source, target)
    assert p.row(target) == expected == p.row(source), name
bundle = archive / 'candidate-branch.bundle'
subprocess.run(git + ['bundle', 'create', str(bundle), 'local/combined-candidate-20261012'], cwd=repo, check=True, capture_output=True)
checked = subprocess.run(git + ['bundle', 'verify', str(bundle)], cwd=repo, check=True, capture_output=True)
(archive / 'bundle-verification.txt').write_bytes(checked.stdout + checked.stderr)
inventory = p.inventory(archive, 'SHA256SUMS.json')
(archive / 'SHA256SUMS.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
assert inventory == p.inventory(archive, 'SHA256SUMS.json')
assert p.inventory(archive / 'prepared-run', 'no-manifest') == p.load(record / 'run-inventory.json')
receipt = {'archive': str(archive), 'source_commit': commit, 'files': len(inventory),
    'bytes': sum(row['bytes'] for row in inventory.values()), 'all_hashes_verified': True,
    'prepared_run_inventory_verified': True, 'git_bundle_verified': True,
    'service_started': False, 'window_shown': False, 'rack_contacted': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt))
