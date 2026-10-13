"""Preserve prior notices/provenance while extending the local-only runtime.

No downloads, installation, receivers or service calls. All outputs are new.
"""
import json
from pathlib import Path
import shutil
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
import stage_receiver_runtime as r
import runtime_package_provenance as provenance

old = repo / 'output/staging/combined-scope-release-20261012/dependencies/receiver-runtime'
base = repo / 'output/staging/native-runtime-startup-20261013'
out = repo / 'output/staging/native-runtime-startup-preserved-final-20261013'
assert r.verify(old) == r.verify(base) == []
assert not out.exists()
previous, current = (r.package.load(p / 'runtime.json') for p in (old, base))
for name, row in previous['files'].items():
    if name.startswith('runtime/'):
        assert current['files'][name] == row, f'Existing binary changed: {name}'
shutil.copytree(base, out)
preserved = []
for name in previous['files'].keys() - current['files'].keys():
    assert name.startswith(('metadata/provenance/', 'metadata/source-notices/', 'metadata/source-notice-index.json'))
    src, target = r.package.safe(old, name), r.package.safe(out, name)
    assert r.package.row(src) == previous['files'][name]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, target)
    assert r.package.row(target) == previous['files'][name]
    preserved.append(name)

receipts = r.package.load(out / 'metadata/receipts.json')['packages']
added = sorted(name for name in current['files'].keys() - previous['files'].keys() if name.startswith('runtime/'))
owners = [item for item in receipts if set(item['runtime_files']) & set(added)]
msys = repo.parent / 'iMouseXP-2.0/tools/airplay/msys64'
audit_dir = record / 'added-package-evidence-final'
audit_dir.mkdir(exist_ok=False)
keyring = old / 'metadata/provenance/selected-public-keyring.gpg'
rows = [provenance.audit_package(item, out, msys / 'var/cache/pacman/pkg', audit_dir,
        Path(r'C:\Windows\System32\tar.exe'), msys / 'usr/bin/gpgv.exe', keyring) for item in owners]
extension = {
    'preserved_prior_metadata_files': sorted(preserved),
    'prior_runtime_manifest': r.package.row(old / 'runtime.json'),
    'unchanged_prior_runtime_files': 126,
    'added_runtime_files': {name: current['files'][name] for name in added},
    'verified_added_file_packages': rows,
    'limits': ['Prior package/source records retain their original scope; they are not new acceptance.',
               'The added binaries match signed local cached packages; no trust-chain refresh.',
               'gst-plugins-good adds a local/source notice gap. Distribution remains uncleared.',
               'No installed binary, service or phone was changed by this assembly.']}
(out / 'metadata/runtime-extension.json').write_text(json.dumps(extension, indent=2), encoding='utf-8')
(record / 'runtime-extension.json').write_text(json.dumps(extension, indent=2), encoding='utf-8')
current['files'] = r.package.inventory(out, 'runtime.json')
current['limits'].append('Previous source notices/provenance are preserved unchanged; runtime-extension.json scopes the added files separately.')
(out / 'runtime.json').write_text(json.dumps(current, indent=2), encoding='utf-8')
assert r.verify(out) == []
print(json.dumps({'runtime_files': current['runtime_file_count'], 'packages': current['package_count'],
                  'added_files': len(added), 'preserved_metadata_files': len(preserved),
                  'added_packages_verified': len(rows), 'notice_gaps': len(current['notice_gaps'])}))
