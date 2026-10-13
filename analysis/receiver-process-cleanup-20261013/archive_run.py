"""Archive receiver-lifetime evidence without launching or touching rack services."""
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

archive = repo.parent / 'iMouseXP-2.0-evidence-archive/20261013-receiver-process-cleanup'
assert not archive.exists(), 'Never overwrite an evidence archive'
manifest = json.loads((record / 'kernel-manifest.json').read_text(encoding='utf-8'))
assert not bm.verify(manifest, repo, record / 'final-kernel')
source_names = set(manifest['sources'])
for name, folder in (('process-tests', 'final-process-tests'), ('recovery-tests', 'final-recovery')):
    test = json.loads((record / (name + '-manifest.json')).read_text(encoding='utf-8'))
    assert bm.snapshot(record / folder) == test['artifacts']
    for filename, row in test['sources'].items():
        assert bm.sha256(repo / filename) == row['sha256'], filename
    source_names.update(test['sources'])
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
    if source.is_file() and 'obj' not in relative.parts and 'bin' not in relative.parts and source.name != 'archive-verification.json':
        copy(source, 'record/' + relative.as_posix())
source_names.update(('PROGRESS.md', 'WORK-REMAINING.md', 'docs/OPERATOR-GUIDE.md', 'docs/CANDIDATE-ACCEPTANCE.md', '.gitattributes'))
for name in sorted(source_names):
    copy(repo / name, 'source/' + name)
git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
patch = archive / 'repair.patch'
patch.write_bytes(subprocess.check_output(git + ['format-patch', '--stdout', '--binary', '61e7d4d..HEAD']))
files['repair.patch'] = {'sha256': bm.sha256(patch), 'bytes': patch.stat().st_size}
for name, row in files.items():
    assert bm.sha256(archive / name) == row['sha256'], name
(archive / 'SHA256SUMS.json').write_text(json.dumps(files, indent=2), encoding='utf-8')
receipt = {'archive': str(archive), 'commit': commit, 'files': len(files),
           'bytes': sum(row['bytes'] for row in files.values()), 'all_hashes_verified': True,
           'installed_static_hashes_unchanged': True,
           'kernel_sha256': manifest['artifacts']['iMouse2.Kernel.dll']['sha256'],
           'candidate_physically_tested': False, 'rebuilt_kernel_packaged_for_live': False,
           'full_release_acceptance': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
