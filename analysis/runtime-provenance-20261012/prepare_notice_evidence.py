"""Attach reviewed source notices to a new local-test capsule; never install anything."""
import json
from pathlib import Path
import shutil
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
import stage_receiver_runtime as runtime

p = runtime.package
capsule = repo / 'output/staging/native-runtime-notices-20261012'
binary_root = repo / 'output/provenance/native-packages-20261012'
source_root = repo / 'output/provenance/native-sources-20261012'
notice_root = repo / 'output/provenance/source-notices-final-20261012'
out = repo / 'output/staging/native-runtime-provenance-final-20261012'
assert not out.exists(), 'Never replace an existing capsule'
assert runtime.verify(capsule) == []
manifest = p.load(capsule / 'runtime.json')
receipts = p.load(capsule / 'metadata/receipts.json')['packages']
binary = p.load(binary_root / 'package-provenance.json')
source = p.load(source_root / 'source-provenance.json')
notices = p.load(notice_root / 'source-notices.json')
binary_files = p.load(binary_root / 'SHA256SUMS.json')
assert p.bm.compare_rows(binary_files, p.inventory(binary_root, 'SHA256SUMS.json'), 'binary evidence') == []
by_name = {r['name']: r for r in binary['packages']}
assert len(by_name) == len(receipts) == binary['verified_count'] == binary['package_count']
assert set(by_name) == {r['name'][0] for r in receipts}
for receipt in receipts:
    row = by_name[receipt['name'][0]]
    assert row['state'] == 'verified' and row['version'] == receipt['version'][0]
    files = {f['file']: {k: f[k] for k in ('sha256', 'bytes')} for f in row['files']}
    assert len(files) == len(row['files'])
    assert set(files) == set(receipt['runtime_files'] + receipt['notices'])
    assert all(manifest['files'][name] == info for name, info in files.items())

copies = {}
def add(origin, destination, expected=None):
    target = p.safe(out, destination)
    row = p.row(origin)
    assert expected is None or row == expected, str(origin)
    assert destination not in copies, destination
    copies[destination] = (origin, row)

for name, row in manifest['files'].items():
    if name != 'verify_runtime.py':
        add(p.safe(capsule, name), name, row)
add(repo / 'tools/stage_receiver_runtime.py', 'verify_runtime.py')
add(binary_root / 'package-provenance.json', 'metadata/provenance/package-provenance.json')
add(binary_root / 'selected-public-keyring.gpg', 'metadata/provenance/selected-public-keyring.gpg', binary['keyring'])
add(source_root / 'source-provenance.json', 'metadata/provenance/source-provenance.json')
add(notice_root / 'source-notices.json', 'metadata/source-notices/source-notices.json')
indexed_sources = {(r['base'], r['version']): r for r in source['sources']}
assert len(indexed_sources) == len(source['sources']) == len(notices['sources'])
coverage = {}
for row in notices['sources']:
    original = indexed_sources[(row['base'], row['version'])]
    assert row['state'] == original['state'] == 'signature_and_recipe_verified'
    assert row['notice_state'] == 'source_notices_collected' and row['notices']
    assert row['archive_sha256'] == original['archive_sha256']
    assert row['recipe_sha256'] == row['expected_recipe_sha256'] == original['expected_recipe_sha256']
    folder = row['base'] + '-' + row['version']
    archive = p.safe(source_root, folder + '/' + folder + '.src.tar.zst')
    assert p.row(archive) == {'sha256': row['archive_sha256'], 'bytes': row['archive_bytes']}
    recipe = p.safe(source_root, folder + '/PKGBUILD')
    assert p.bm.sha256(recipe) == row['recipe_sha256']
    add(recipe, 'metadata/source-notices/' + folder + '/PKGBUILD.txt')
    add(p.safe(notice_root, folder + '/SRCINFO'), 'metadata/source-notices/' + folder + '/SRCINFO')
    for notice in row['notices']:
        assert notice['source_kind'] in ('checksummed_nested_archive', 'signed_git_objects')
        add(p.safe(notice_root, notice['file']), 'metadata/source-notices/' + notice['file'],
            {key: notice[key] for key in ('sha256', 'bytes')})
    for name in row['packages']:
        assert name not in coverage and name in manifest['notice_gaps']
        dependency = by_name[name]
        assert dependency['pkgbase'] == [row['base']] and dependency['version'] == row['version']
        assert dependency['pkgbuild_sha256'] == row['recipe_sha256']
        coverage[name] = {'version': row['version'], 'recipe_sha256': row['recipe_sha256'],
            'source_archive_sha256': row['archive_sha256'],
            'notices': ['metadata/source-notices/' + n['file'] for n in row['notices']]}
assert set(coverage) == set(manifest['notice_gaps'])

out.mkdir(parents=True, exist_ok=False)
for name, (source_file, expected) in copies.items():
    target = p.safe(out, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, target)
    assert p.row(target) == expected, name
index = {'packages': coverage, 'local_notice_gaps_unchanged': manifest['notice_gaps'],
    'scope': 'Version-matched source notices supplement absent installed notices. Full signed archives are in the external evidence archive. This does not establish complete notice coverage, corresponding-source sufficiency, reproducible dependencies, or redistribution clearance.'}
(out / 'metadata/source-notice-index.json').write_text(json.dumps(index, indent=2), encoding='utf-8')
manifest['files'] = p.inventory(out, 'runtime.json')
manifest['limits'].append('Supplemental source notices and recorded signature checks are included as evidence, not a license clearance; local notice gaps remain explicitly recorded.')
(out / 'runtime.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
assert runtime.verify(out) == []
assert {k: v for k, v in manifest['files'].items() if k.startswith('runtime/')} == {
    k: v for k, v in p.load(capsule / 'runtime.json')['files'].items() if k.startswith('runtime/')}
result = {'runtime_files': manifest['runtime_file_count'], 'packages': manifest['package_count'],
    'signed_binary_packages': binary['verified_count'], 'matched_binary_members': sum(len(r['files']) for r in binary['packages']),
    'source_archives': len(indexed_sources), 'supplemented_packages': len(coverage),
    'source_notice_files': sum(len(r['notices']) for r in notices['sources']),
    'local_notice_gaps': len(manifest['notice_gaps']), 'runtime_bytes_unchanged': True,
    'capsule': str(out), 'files': len(manifest['files']), 'capsule_verifies': True,
    'installation_allowed': False, 'redistribution_cleared': False}
(record / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
