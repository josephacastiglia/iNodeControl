"""Preserve this exact candidate, prepared run and raw static evidence locally."""
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
import build_manifest as bm

archive = repo.parent / 'iMouseXP-2.0-evidence-archive/20261014-re-improvements'
package = repo / 'output/staging/combined-re-improvements-20261014'
prepared = repo / 'output/candidate-runs/re-improvements-20261014'
assert not archive.exists(), 'Never overwrite existing evidence'
assert stage.verify(package) == []
inventory = stage.load(record / 'run-inventory.json')
assert stage.inventory(prepared, 'no-manifest') == inventory
for component in ('console', 'kernel'):
    assert bm.verify(stage.load(record / (component + '-manifest.json')), repo, record / (component + '-final')) == []
files = {}

def copy(source, name):
    target = archive / name
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = stage.row(source)
    shutil.copy2(source, target)
    assert stage.row(target) == expected, name
    files[name] = expected

for root, prefix in ((record, 'record'), (package, 'package'), (prepared, 'prepared')):
    for source in sorted(root.rglob('*')):
        if source.is_file() and '__pycache__' not in source.parts and source.name != 'archive-verification.json':
            copy(source, prefix + '/' + source.relative_to(root).as_posix())
for name in ('PROGRESS.md', 'RESUME-NEXT.md', 'WORK-REMAINING.md', 'RE-IMPROVEMENTS-PLAN.md',
             'tools/managed_symbols.py', 'tools/test_managed_symbols.py', 'tools/stage_release.py',
             'tools/test_stage_release.py', 'docs/RELEASE-STAGING.md'):
    copy(repo / name, 'source/' + name)
git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
subprocess.run(git + ['bundle', 'create', str(archive / 'active-branch.bundle'), 'HEAD'], check=True, capture_output=True, timeout=120)
verified = subprocess.run(git + ['bundle', 'verify', str(archive / 'active-branch.bundle')], capture_output=True, timeout=60)
assert verified.returncode == 0
files['active-branch.bundle'] = stage.row(archive / 'active-branch.bundle')
for name, expected in files.items():
    assert stage.row(archive / name) == expected, name
assert stage.verify(archive / 'package') == []
assert stage.inventory(archive / 'prepared', 'no-manifest') == inventory
(archive / 'SHA256SUMS.json').write_text(json.dumps(files, indent=2), encoding='utf-8')
receipt = {'archive': str(archive), 'commit': commit, 'files': len(files),
    'bytes': sum(row['bytes'] for row in files.values()), 'all_hashes_verified': True,
    'relocated_package_verified': True, 'prepared_inventory_verified': True, 'git_bundle_verified': True,
    'off_machine_backup': False, 'physical_acceptance': False, 'deployed': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
(archive / 'RECEIPT.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
