"""Archive the verified offline sources, records, package and unused run."""
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

archive = repo.parent / 'iMouseXP-2.0-evidence-archive/20261013-timing-preflight-combined'
assert not archive.exists(), 'Never overwrite an archive'
package = repo / 'output/staging/combined-timing-20261013'
prepared = repo / 'output/candidate-runs/timing-20261013'
repair = repo / 'analysis/gate6-preflight-20261013'
assert stage.verify(package) == []
inventory = stage.load(record / 'run-inventory.json')
assert stage.inventory(prepared, 'no-manifest') == inventory
manifest = stage.load(repair / 'console-manifest.json')
assert bm.verify(manifest, repo, repair / 'console-artifacts') == []
sources = stage.load(repair / 'source-manifest.json')
for name, row in sources.items():
    assert stage.row(repo / name) == row, name
    assert stage.row(repair / 'final-source' / name) == row, name
files = {}

def copy(source, name):
    target = archive / name
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = stage.row(source)
    shutil.copy2(source, target)
    assert stage.row(target) == expected, name
    files[name] = expected

for root, prefix in ((record, 'record'), (repair, 'repair'), (package, 'package'), (prepared, 'prepared')):
    for source in sorted(root.rglob('*')):
        if source.is_file() and '__pycache__' not in source.parts and source.name != 'archive-verification.json':
            copy(source, prefix + '/' + source.relative_to(root).as_posix())
extra = ('PROGRESS.md', 'WORK-REMAINING.md', 'RESUME-NEXT.md', '.gitattributes',
         'analysis/gate6-release-validation-20260916/README.md', 'tools/OFFLINE-VERIFICATION.md',
         'tools/build_manifest.py', 'tools/stage_release.py', 'tools/candidate-launcher/Start-iMouse2Candidate.ps1')
for name in sorted(set(sources) | set(extra)):
    copy(repo / name, 'source/' + name)
git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
patch = archive / 'changes.patch'
patch.write_bytes(subprocess.check_output(git + ['format-patch', '--stdout', '--binary', '01e2f60..HEAD']))
files[patch.name] = stage.row(patch)
for name, row in files.items():
    assert stage.row(archive / name) == row, name
assert stage.verify(archive / 'package') == []
assert stage.inventory(archive / 'prepared', 'no-manifest') == inventory
(archive / 'SHA256SUMS.json').write_text(json.dumps(files, indent=2), encoding='utf-8')
receipt = {'archive': str(archive), 'commit': commit, 'files': len(files),
           'bytes': sum(row['bytes'] for row in files.values()), 'all_hashes_verified': True,
           'relocated_package_verified': True, 'prepared_inventory_verified': True,
           'off_machine_backup': False, 'physical_acceptance': False, 'deployed': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, indent=2))
