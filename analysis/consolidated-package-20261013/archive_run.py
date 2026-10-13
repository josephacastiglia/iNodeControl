"""Archive the fresh review package and pristine prepared run; never launch them."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / 'tools'))
import stage_release as stage

archive = repo.parent / 'iMouseXP-2.0-evidence-archive/20261013-consolidated-package'
assert not archive.exists()
result = stage.load(record / 'package-result.json')
prepared = stage.load(record / 'preparation.json')
package = Path(result['package'])
run = Path(prepared['run_directory'])
assert stage.row(package / 'package.json') == result['manifest']
expected_run = stage.load(record / 'run-inventory.json')
assert stage.inventory(run, 'no-manifest') == expected_run
protected = stage.load(repo / 'analysis/candidate-retry-20261013/restoration-files.json')
checks = [{'path': item['path'], 'sha256': stage.bm.sha256(Path(item['path'])), 'expected': item['sha256'],
           'runtime_log_excluded': Path(item['path']).name in ('receiver-C24C.log', 'receiver-C241.log')} for item in protected]
assert all(item['sha256'] == item['expected'] for item in checks if not item['runtime_log_excluded'])
(record / 'protected-files-verified.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
files = {}

def copy(source, name):
    target = archive / name
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = stage.row(source)
    shutil.copy2(source, target)
    assert stage.row(target) == expected, name
    files[name] = expected

for folder, prefix in ((record, 'record'), (package, 'review-package'), (run, 'prepared-run')):
    for source in folder.rglob('*'):
        if source.is_file() and '__pycache__' not in source.parts and source.name != 'archive-verification.json':
            copy(source, prefix + '/' + source.relative_to(folder).as_posix())
for name in ('PROGRESS.md', 'WORK-REMAINING.md', 'FINISH-CRITERIA.md', '.gitattributes',
             'docs/RELEASE-STAGING.md', 'docs/CANDIDATE-ACCEPTANCE.md', 'tools/stage_release.py',
             'tools/test_stage_release.py', 'tools/validate_rack_config.py'):
    copy(repo / name, 'project-record/' + name)
for folder in ('tools/candidate-launcher', 'tools/kernel-window'):
    for source in (repo / folder).glob('*'):
        if source.is_file(): copy(source, 'project-record/' + source.relative_to(repo).as_posix())
git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
patch = archive / 'preparation.patch'
patch.write_bytes(subprocess.check_output(git + ['format-patch', '--stdout', '--binary', 'fdcb7f5..HEAD']))
files['preparation.patch'] = stage.row(patch)
verified = subprocess.run([sys.executable, '-B', str(archive / 'review-package/verify_package.py'),
                           'verify', '--bundle', str(archive / 'review-package')], capture_output=True, timeout=90)
(archive / 'relocated-package-check.txt').write_bytes(verified.stdout + verified.stderr)
assert verified.returncode == 0
files['relocated-package-check.txt'] = stage.row(archive / 'relocated-package-check.txt')
assert stage.inventory(archive / 'prepared-run', 'no-manifest') == expected_run
for name, row in files.items():
    assert stage.row(archive / name) == row, name
(archive / 'SHA256SUMS.json').write_text(json.dumps(files, indent=2), encoding='utf-8')
receipt = {'archive': str(archive), 'commit': commit, 'files': len(files),
           'bytes': sum(item['bytes'] for item in files.values()), 'all_hashes_verified': True,
           'relocated_package_verifier_passed': True, 'prepared_inventory_preserved': True,
           'installed_static_hashes_unchanged': True,
           'package_manifest': result['manifest'], 'kernel_dll': result['kernel_dll'],
           'candidate_launched': False, 'phone_input_sent': False, 'physical_acceptance': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
