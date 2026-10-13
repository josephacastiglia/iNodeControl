"""Preserve this focused repair and exact tested bytes outside the checkout."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

record = Path(__file__).resolve().parent
repo = record.parents[1]
archive = repo.parent / 'iMouseXP-2.0-evidence-archive/20261013-launcher-startup-errors'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert not archive.exists(), 'Preserve an existing archive'
protected = json.loads((repo / 'analysis/candidate-retry-20261013/restoration-files.json').read_text(encoding='utf-8-sig'))
checks = [{'path': row['path'], 'sha256': sha(Path(row['path'])), 'expected': row['sha256'],
           'runtime_log_excluded': Path(row['path']).name in ('receiver-C24C.log', 'receiver-C241.log')} for row in protected]
# The restored receiver processes keep appending their own logs. Protect installed
# binaries, scripts, configuration and settings; do not mistake live logs for them.
assert all(row['sha256'] == row['expected'] for row in checks if not row['runtime_log_excluded'])
(record / 'protected-files-verified.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
tested = json.loads((record / 'results.json').read_text(encoding='utf-8'))
assert sha(repo / 'Open iMouse 2.0.ps1') == tested['launcher_sha256']
files = {}
for source in record.rglob('*'):
    if source.is_file() and source.name != 'archive-verification.json':
        relative = 'record/' + source.relative_to(record).as_posix()
        target = archive / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        files[relative] = {'sha256': sha(source), 'bytes': source.stat().st_size}
for name in ('Open iMouse 2.0.ps1', 'tools/test_launcher.ps1', '.gitattributes', 'PROGRESS.md', 'WORK-REMAINING.md', 'docs/OPERATOR-GUIDE.md'):
    target = archive / 'source' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo / name, target)
    files['source/' + name] = {'sha256': sha(repo / name), 'bytes': target.stat().st_size}
git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
patch = archive / 'repair.patch'
patch.write_bytes(subprocess.check_output(git + ['format-patch', '--stdout', '--binary', 'f835998..HEAD']))
files['repair.patch'] = {'sha256': sha(patch), 'bytes': patch.stat().st_size}
for relative, row in files.items():
    assert sha(archive / relative) == row['sha256'], relative
(archive / 'SHA256SUMS.json').write_text(json.dumps(files, indent=2), encoding='utf-8')
receipt = {'archive': str(archive), 'commit': commit, 'files': len(files), 'bytes': sum(row['bytes'] for row in files.values()),
           'all_hashes_verified': True, 'installed_files_unchanged': True, 'tested_launcher_sha256': tested['launcher_sha256'],
           'contains': 'Exact source, tests, raw probe records, report, protected-file check and focused patches since the prior archive base.',
           'previous_base': 'f835998; earlier full branch/rack evidence retained in the preceding candidate retry and runtime archives.',
           'live_or_release_acceptance': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
