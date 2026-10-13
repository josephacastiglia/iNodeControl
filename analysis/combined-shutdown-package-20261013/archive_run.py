"""Archive the verified repair, package and unused preparation. Never launch them."""
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

archive = repo.parent / 'iMouseXP-2.0-evidence-archive/20261013-shutdown-combined'
assert not archive.exists(), 'Never overwrite an archive'
package = repo / 'output/staging/combined-shutdown-20261013'
prepared = repo / 'output/candidate-runs/shutdown-20261013'
repair = repo / 'analysis/fleet-shutdown-20261013'
assert stage.verify(package) == []
inventory = json.loads((record / 'run-inventory.json').read_text(encoding='utf-8'))
assert stage.inventory(prepared, 'no-manifest') == inventory
source_names = set()
for name, output in (('kernel', 'final-kernel'), ('recovery', 'expanded-recovery'), ('frame', 'frame-tests'), ('process', 'process-tests')):
    manifest = json.loads((repair / 'resumed' / (name + '-manifest.json')).read_text(encoding='utf-8'))
    assert bm.snapshot(repair / 'resumed' / output) == manifest['artifacts'], name
    for source, row in manifest['sources'].items():
        assert bm.sha256(repo / source) == row['sha256'], source
    source_names.update(manifest['sources'])
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
source_names.update(('PROGRESS.md', 'WORK-REMAINING.md', 'RESUME-NEXT.md', 'docs/CANDIDATE-ACCEPTANCE.md',
                     'tools/build_manifest.py', 'tools/stage_release.py', '.gitattributes'))
for name in sorted(source_names):
    copy(repo / name, 'source/' + name)
git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
patch = archive / 'changes.patch'
patch.write_bytes(subprocess.check_output(git + ['format-patch', '--stdout', '--binary', 'e82117e..HEAD']))
files[patch.name] = stage.row(patch)
for name, row in files.items():
    assert stage.row(archive / name) == row, name
assert stage.verify(archive / 'package') == []
assert stage.inventory(archive / 'prepared', 'no-manifest') == inventory
(archive / 'SHA256SUMS.json').write_text(json.dumps(files, indent=2) + '\n', encoding='utf-8')
receipt = {'archive': str(archive), 'commit': commit, 'files': len(files),
           'bytes': sum(row['bytes'] for row in files.values()), 'all_hashes_verified': True,
           'relocated_package_verified': True, 'prepared_inventory_verified': True,
           'off_machine_backup': False, 'physical_acceptance': False, 'deployed': False}
(record / 'archive-verification.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
print(json.dumps(receipt, indent=2))
