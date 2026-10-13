"""Preserve the paused draft and candidate history without operating the rack."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

record = Path(__file__).resolve().parent
repo = record.parents[1]
archive = repo.parent / 'iMouseXP-2.0-evidence-archive/20261013-fleet-shutdown-pause'
assert not archive.exists(), 'Never overwrite an evidence archive'
git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
manifest = json.loads((record / 'draft-manifest.json').read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for name, row in manifest['files'].items():
    assert sha(record / name) == row['sha256'], name
files = {}

def copy(source, name):
    target = archive / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    assert source.read_bytes() == target.read_bytes(), name
    files[name] = {'bytes': source.stat().st_size, 'sha256': sha(source)}

for p in sorted(record.rglob('*')):
    if p.is_file() and '__pycache__' not in p.parts and p.name != 'archive-verification.json':
        copy(p, 'record/' + p.relative_to(record).as_posix())
for name in ('RESUME-NEXT.md', 'PROGRESS.md', 'WORK-REMAINING.md', '.gitattributes', 'docs/CANDIDATE-ACCEPTANCE.md'):
    copy(repo / name, 'source/' + name)
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
bundle = archive / 'candidate-history.bundle'
subprocess.run(git + ['bundle', 'create', str(bundle), 'local/combined-candidate-20261012'], check=True, capture_output=True)
verified = subprocess.run(git + ['bundle', 'verify', str(bundle)], check=True, capture_output=True, text=True)
(archive / 'bundle-verification.txt').write_text(verified.stdout + verified.stderr, encoding='utf-8')
for p in (bundle, archive / 'bundle-verification.txt'):
    files[p.name] = {'bytes': p.stat().st_size, 'sha256': sha(p)}
for name, row in files.items():
    assert sha(archive / name) == row['sha256'], name
(archive / 'SHA256SUMS.json').write_text(json.dumps(files, indent=2) + '\n', encoding='utf-8')
receipt = {'archive': str(archive), 'candidate_branch': 'local/combined-candidate-20261012',
           'bundle_through_commit': commit, 'bundle_verified': True,
           'files': len(files), 'bytes': sum(r['bytes'] for r in files.values()),
           'all_hashes_verified': True, 'draft_executed': False, 'product_fix_implemented': False,
           'off_machine_backup': False, 'pushed': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps(receipt, indent=2))
