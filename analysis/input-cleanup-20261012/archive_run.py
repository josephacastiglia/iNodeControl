"""Preserve validated source, evidence and the consolidated review package locally."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

record = Path(__file__).resolve().parent
repo = record.parents[1]
archive = repo.parent / 'iMouseXP-2.0-evidence-archive/20261012-input-cleanup'
assert not archive.exists(), 'Never replace a prior archive'
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
git = ['git', '-c', f'safe.directory={repo.as_posix()}']
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=repo, text=True).strip()
assert not subprocess.check_output(git + ['diff', 'HEAD', '--', 'src/iMouse.Console'], cwd=repo)
files = {}
for path in record.iterdir():
    if path.is_file(): files[Path('record') / path.name] = path
for folder in ('candidate-console', 'negative-operator-wait', 'negative-reconnect-wait',
               'negative-operator-wait-build', 'negative-reconnect-wait-build'):
    for path in (record / folder).rglob('*'):
        if path.is_file() and not any(p in ('obj', 'bin') for p in path.relative_to(record / folder).parts):
            files[Path('record') / path.relative_to(record)] = path
manifest = json.loads((record / 'console-manifest.json').read_text(encoding='utf-8'))
for name, info in manifest['sources'].items():
    path = repo / name
    assert sha(path) == info['sha256'], name
    files[Path('tested-source') / name] = path
for name in ('PROGRESS.md', 'WORK-REMAINING.md', 'FINISH-CRITERIA.md', 'docs/OPERATOR-GUIDE.md', 'docs/RELEASE-STAGING.md'):
    files[Path('project-record') / name] = repo / name
package = repo / 'output/staging/combined-input-cleanup-20261012'
prepared = repo / 'output/candidate-runs/input-cleanup-20261012'
for source, target in ((package, 'review-package'), (prepared, 'prepared-not-launched')):
    for path in source.rglob('*'):
        if path.is_file(): files[Path(target) / path.relative_to(source)] = path
archive.mkdir(parents=True)
for relative, source in files.items():
    target = archive / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    assert sha(target) == sha(source), relative
bundle = archive / 'candidate-branch.bundle'
subprocess.run(git + ['bundle', 'create', str(bundle), 'local/combined-candidate-20261012'], cwd=repo, check=True, capture_output=True)
verified = subprocess.run(git + ['bundle', 'verify', str(bundle)], cwd=repo, check=True, capture_output=True)
(archive / 'bundle-verification.txt').write_bytes(verified.stdout + verified.stderr)
run = subprocess.run(['python', str(archive / 'review-package/verify_package.py'), 'verify', '--bundle', str(archive / 'review-package')], capture_output=True, check=True)
(archive / 'package-verification.txt').write_bytes(run.stdout + run.stderr)
rows = {p.relative_to(archive).as_posix(): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in archive.rglob('*') if p.is_file()}
(archive / 'SHA256SUMS.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
assert set(rows) == {p.relative_to(archive).as_posix() for p in archive.rglob('*') if p.is_file() and p.name != 'SHA256SUMS.json'}
assert all(sha(archive / name) == item['sha256'] for name, item in rows.items())
receipt = {'archive': str(archive), 'source_commit': commit, 'files': len(rows), 'bytes': sum(r['bytes'] for r in rows.values()),
    'all_hashes_verified': True, 'source_snapshot_verified': True, 'git_bundle_verified': True,
    'full_review_package_verified': True, 'launched': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt))
