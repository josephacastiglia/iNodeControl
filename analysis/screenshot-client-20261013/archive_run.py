"""Archive screenshot-client repair evidence without starting the rack or UI."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / 'tools'))
import build_manifest as bm

archive = repo.parent / 'iMouseXP-2.0-evidence-archive/20261013-screenshot-client'
assert not archive.exists(), 'Never overwrite an archive'
console = json.loads((record / 'console-manifest.json').read_text(encoding='utf-8'))
assert not bm.verify(console, repo, record / 'console-artifacts')
source_names = set(console['sources'])
for name, output in (('preview', 'verified-preview'), ('wall', 'final-wall')):
    test = json.loads((record / (name + '-manifest.json')).read_text(encoding='utf-8'))
    assert bm.snapshot(record / output) == test['artifacts']
    for filename, row in test['sources'].items():
        assert bm.sha256(repo / filename) == row['sha256'], filename
    source_names.update(test['sources'])
before = json.loads((record / 'before-manifest.json').read_text(encoding='utf-8'))
assert bm.snapshot(record / 'before-source') == before['sources']
assert bm.snapshot(record / 'before-preview') == before['artifacts']
protected = json.loads((repo / 'analysis/candidate-retry-20261013/restoration-files.json').read_text(encoding='utf-8-sig'))
checks = [{'path': row['path'], 'sha256': bm.sha256(Path(row['path'])), 'expected': row['sha256'],
           'runtime_log_excluded': Path(row['path']).name in ('receiver-C24C.log', 'receiver-C241.log')} for row in protected]
assert all(row['sha256'] == row['expected'] for row in checks if not row['runtime_log_excluded'])
(record / 'protected-files-verified.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
files = {}

def copy(source, name):
    target = archive / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    files[name] = {'sha256': bm.sha256(source), 'bytes': source.stat().st_size}

for source in record.rglob('*'):
    relative = source.relative_to(record)
    if source.is_file() and not {'test-temp', '__pycache__'}.intersection(relative.parts) and source.name != 'archive-verification.json':
        copy(source, 'record/' + relative.as_posix())
source_names.update(('PROGRESS.md', 'WORK-REMAINING.md', 'docs/CANDIDATE-ACCEPTANCE.md', '.gitattributes', 'tools/build_manifest.py'))
for name in sorted(source_names):
    copy(repo / name, 'source/' + name)
git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
patch = archive / 'repair.patch'
patch.write_bytes(subprocess.check_output(git + ['format-patch', '--stdout', '--binary', 'a170ff1..HEAD']))
files['repair.patch'] = {'sha256': bm.sha256(patch), 'bytes': patch.stat().st_size}
for name, row in files.items():
    assert bm.sha256(archive / name) == row['sha256'], name
(archive / 'SHA256SUMS.json').write_text(json.dumps(files, indent=2), encoding='utf-8')
receipt = {'archive': str(archive), 'commit': commit, 'files': len(files),
           'bytes': sum(row['bytes'] for row in files.values()), 'all_hashes_verified': True,
           'installed_static_hashes_unchanged': True,
           'console_sha256': console['artifacts']['iMouse2.dll']['sha256'],
           'console_physically_tested': False, 'rebuilt_console_packaged_for_live': False,
           'full_release_acceptance': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
