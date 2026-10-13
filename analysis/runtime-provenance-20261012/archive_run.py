"""Preserve the exact package evidence and current branch; never replace an archive."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
import stage_release as p

archive_root = (repo.parent / 'iMouseXP-2.0-evidence-archive').resolve()
archive = archive_root / '20261012-runtime-provenance'
assert archive.resolve().is_relative_to(archive_root) and not archive.exists()
result = p.load(record / 'package-result.json')
assert result['all_package_hashes_verified'] and result['installed_hashes_unchanged']
git = ['git', '-c', f'safe.directory={repo.as_posix()}']
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=repo, text=True).strip()
assert not subprocess.check_output(git + ['diff', 'HEAD', '--', 'tools', 'docs', 'PROGRESS.md', 'WORK-REMAINING.md'], cwd=repo)
files = {}
for path in record.iterdir():
    if path.is_file(): files['record/' + path.name] = path
for name in ('stage_receiver_runtime.py', 'test_stage_receiver_runtime.py', 'runtime_package_provenance.py',
             'test_runtime_package_provenance.py', 'stage_release.py', 'build_manifest.py'):
    files['tools/' + name] = repo / 'tools' / name
for name in ('PROGRESS.md', 'WORK-REMAINING.md', 'FINISH-CRITERIA.md', 'docs/RELEASE-STAGING.md', 'docs/OPERATOR-GUIDE.md'):
    files['project-record/' + name] = repo / name
copies = {
    'review-package': repo / 'output/staging/combined-runtime-provenance-final-20261012',
    'signed-binary-packages': repo / 'output/provenance/native-packages-20261012',
    'signed-source-packages': repo / 'output/provenance/native-sources-20261012',
    'source-notices': repo / 'output/provenance/source-notices-final-20261012',
    'first-extraction': repo / 'output/provenance/source-notices-20261012',
}
for prefix, root in copies.items():
    for path in root.rglob('*'):
        if path.is_file():
            relative = path.relative_to(root)
            # Git objects can be reconstructed from the preserved signed source
            # archives; do not duplicate their expanded object databases.
            if any(part.startswith('objects-') for part in relative.parts): continue
            files[prefix + '/' + relative.as_posix()] = path
armored = repo.parent / 'iMouseXP-2.0/tools/airplay/msys64/usr/share/pacman/keyrings/msys2.gpg'
files['public-keyring/msys2-armored.gpg'] = armored
archive.mkdir(parents=True)
rows = {}
for name, source in files.items():
    expected = p.row(source)
    target = p.safe(archive, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    assert p.row(target) == expected == p.row(source), name
    rows[name] = expected
bundle = archive / 'candidate-branch.bundle'
subprocess.run(git + ['bundle', 'create', str(bundle), 'local/combined-candidate-20261012'], cwd=repo, check=True, capture_output=True)
checked = subprocess.run(git + ['bundle', 'verify', str(bundle)], cwd=repo, check=True, capture_output=True)
(archive / 'bundle-verification.txt').write_bytes(checked.stdout + checked.stderr)
run = subprocess.run([sys.executable, str(archive / 'review-package/verify_package.py'), 'verify', '--bundle', str(archive / 'review-package')], capture_output=True, check=True)
(archive / 'package-verification.txt').write_bytes(run.stdout + run.stderr)
for name in ('candidate-branch.bundle', 'bundle-verification.txt', 'package-verification.txt'):
    rows[name] = p.row(archive / name)
(archive / 'SHA256SUMS.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
assert p.bm.compare_rows(rows, p.inventory(archive, 'SHA256SUMS.json'), 'archive') == []
assert p.bm.compare_rows(p.load(archive / 'signed-binary-packages/SHA256SUMS.json'),
    p.inventory(archive / 'signed-binary-packages', 'SHA256SUMS.json'), 'signed packages') == []
receipt = {'archive': str(archive), 'source_commit': commit, 'files': len(rows),
    'bytes': sum(row['bytes'] for row in rows.values()), 'all_hashes_verified': True,
    'originals_match_archive': True, 'review_package_verified': True,
    'binary_package_inventory_verified': True, 'git_bundle_verified': True,
    'source_notices': p.load(record / 'result.json')['source_notice_files'], 'launched': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt))
